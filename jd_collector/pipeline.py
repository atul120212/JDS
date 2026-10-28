"""Scrape -> normalize -> validate -> store, with run tracking and alerts."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime

from jd_collector import repository as repo
from jd_collector.config import SourceConfig, get_settings
from jd_collector.db import ScrapeRun, get_session_factory
from jd_collector.http_client import PoliteHttpClient
from jd_collector.monitoring import send_alert
from jd_collector.normalize import make_job_id, normalize
from jd_collector.scrapers import build_scraper
from jd_collector.scrapers.base import HttpClient

log = logging.getLogger(__name__)

ANOMALY_DROP_RATIO = 0.5  # alert when a source returns < 50% of its previous job count
ANOMALY_MIN_PREVIOUS = 10

# SQLite allows only one writer at a time; when several sources scrape in parallel (each on
# its own thread and session, via run_sources' ThreadPoolExecutor), their commits otherwise
# compete for that single writer slot. Relying on SQLite's own busy-timeout to queue them
# proved unreliable in practice (observed spurious "database is locked" failures on Windows
# even with a generous timeout), so writes are serialized explicitly instead: only one thread
# ever holds this lock while touching the database. The slow part of scraping - fetching pages
# over the network - happens *outside* the lock (between `yield`s in each scraper's generator),
# so sources still run fully in parallel for the part that actually benefits from it.
#
# Every write under this lock commits (or rolls back) before the lock is released - never
# leaving a flushed-but-uncommitted transaction open across a release. Letting that happen
# (as an earlier version of this code did, batching commits every N rows) created a real,
# reproducible deadlock: thread A flushes but doesn't commit, releases the lock; thread B
# acquires it and tries to write, blocking on SQLite's *own* writer lock (which A's connection
# still holds); A can now never get the Python lock back to reach its own commit. Confirmed via
# thread-stack dumps and fixed by always committing (or rolling back) before releasing.
_write_lock = threading.Lock()


@dataclass
class RunResult:
    source: str
    status: str = "running"
    fetched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    invalid: int = 0
    deactivated: int = 0
    duration_seconds: float = 0.0
    error: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


_running: set[str] = set()
_running_lock = threading.Lock()


def running_sources() -> list[str]:
    """Sources currently being scraped by this process."""
    with _running_lock:
        return sorted(_running)


def run_source(source: SourceConfig, client: HttpClient | None = None) -> RunResult:
    """Scrape one source. A source already running in this process is skipped, not doubled."""
    with _running_lock:
        if source.name in _running:
            log.info("[%s] already running; skipped", source.name)
            return RunResult(source=source.name, status="skipped", error="already running")
        _running.add(source.name)
    try:
        return _run_source(source, client)
    finally:
        with _running_lock:
            _running.discard(source.name)


def _run_source(source: SourceConfig, client: HttpClient | None = None) -> RunResult:
    client = client or PoliteHttpClient()
    factory = get_session_factory()
    result = RunResult(source=source.name)
    started = datetime.utcnow()
    t0 = time.monotonic()

    with factory() as session:
        run = ScrapeRun(source=source.name, status="running", started_at=started)
        with _write_lock:
            session.add(run)
            session.commit()
        log.info("[%s] scrape started (%s)", source.name, source.type)

        try:
            markers = repo.known_markers(session, source.name)
            session.commit()  # close the read-only transaction that query opened; see _write_lock
            scraper = build_scraper(source, client, markers)
            seen: set[str] = set()
            for raw in scraper.fetch_jobs():
                result.fetched += 1
                if raw.unchanged:
                    job_id = make_job_id(source.name, raw.external_id, raw.url)
                    with _write_lock:
                        touched = job_id not in seen and repo.touch_job(session, job_id, started)
                        session.commit()
                    if touched:
                        seen.add(job_id)
                        result.unchanged += 1
                    continue

                posting, issues = normalize(raw)
                if posting is None:
                    result.invalid += 1
                    log.debug("[%s] discarded %r: %s", source.name, raw.title or raw.url, "; ".join(issues))
                    continue
                if posting.job_id in seen:
                    continue  # same job listed twice in one run
                seen.add(posting.job_id)
                with _write_lock:
                    outcome = repo.upsert_job(session, posting, started)
                    session.commit()
                setattr(result, outcome, getattr(result, outcome) + 1)

            if scraper.complete:
                with _write_lock:
                    result.deactivated = repo.deactivate_missing(session, source.name, started)
                    session.commit()
            else:
                log.info("[%s] listing was truncated; not closing unseen jobs", source.name)
            result.status = "success"
        except Exception as exc:
            with _write_lock:
                session.rollback()
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            log.exception("[%s] scrape failed", source.name)
            send_alert(f"Scrape of '{source.name}' failed: {result.error}")

        result.duration_seconds = round(time.monotonic() - t0, 2)
        previous = repo.last_successful_run(session, source.name, exclude_id=run.id)
        for name in ("status", "fetched", "new", "updated", "unchanged", "invalid", "deactivated",
                     "duration_seconds", "error"):
            setattr(run, name, getattr(result, name))
        run.finished_at = datetime.utcnow()
        with _write_lock:
            session.commit()

    _check_anomalies(source, result, previous)
    log.info(
        "[%s] %s in %.1fs: fetched=%d new=%d updated=%d unchanged=%d invalid=%d closed=%d",
        source.name, result.status, result.duration_seconds, result.fetched, result.new,
        result.updated, result.unchanged, result.invalid, result.deactivated,
    )
    return result


def _check_anomalies(source: SourceConfig, result: RunResult, previous: ScrapeRun | None) -> None:
    if result.status != "success":
        return
    if result.fetched == 0:
        send_alert(f"Source '{source.name}' returned 0 jobs - the site or its layout may have changed")
    elif previous and previous.fetched >= ANOMALY_MIN_PREVIOUS and result.fetched < previous.fetched * ANOMALY_DROP_RATIO:
        send_alert(
            f"Source '{source.name}' returned {result.fetched} jobs, down from {previous.fetched} in the previous run"
        )
    if result.fetched and result.invalid / result.fetched > 0.5:
        send_alert(f"Source '{source.name}': {result.invalid}/{result.fetched} jobs failed validation")


def preview_source(source: SourceConfig, client: HttpClient | None = None, sample_size: int = 5,
                   max_scan: int = 15) -> dict:
    """Scrape and normalize without storing anything - used to test a source before saving it.

    Sources whose listing arrives in one request are scanned completely (cheap); others
    stop after ``max_scan`` jobs so a test never hammers a site.
    """
    from collections import Counter

    client = client or PoliteHttpClient()
    scraper = build_scraper(source, client)
    scan_all = getattr(scraper, "single_request", False)
    valid, invalid, scanned = 0, 0, 0
    issues: Counter[str] = Counter()
    samples: list[dict] = []
    error = None
    stopped_early = False
    t0 = time.monotonic()
    try:
        for raw in scraper.fetch_jobs():
            scanned += 1
            posting, problems = normalize(raw, store_raw=False)
            if posting is None:
                invalid += 1
                issues.update(problems)
            else:
                valid += 1
                if len(samples) < sample_size:
                    samples.append(posting.model_dump(
                        include={"title", "company", "location", "is_remote", "job_type", "salary",
                                 "skills", "apply_link", "posted_date", "department"}))
            if not scan_all and scanned >= max_scan:
                stopped_early = True
                break
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    return {
        "ok": error is None and valid > 0,
        "scanned": scanned,
        "valid": valid,
        "invalid": invalid,
        "complete": not stopped_early and scraper.complete,
        "issues": [{"issue": k, "count": n} for k, n in issues.most_common(5)],
        "samples": samples,
        "error": error,
        "duration_seconds": round(time.monotonic() - t0, 2),
    }


def run_sources(sources: list[SourceConfig], max_workers: int | None = None,
                client: HttpClient | None = None) -> list[RunResult]:
    """Scrape several sources in parallel; per-host rate limits still apply."""
    if not sources:
        return []
    client = client or PoliteHttpClient()
    workers = max(1, min(max_workers or get_settings().max_workers, len(sources)))
    results: list[RunResult] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scrape") as pool:
        futures = {pool.submit(run_source, s, client): s for s in sources}
        for future in as_completed(futures):
            results.append(future.result())
    return sorted(results, key=lambda r: r.source)
