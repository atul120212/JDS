"""Periodic scraping with APScheduler (per-source interval or cron expression).

Two ways to run it:
- ``python -m jd_collector schedule``: a dedicated blocking scheduler process
- ``python -m jd_collector serve --with-scheduler``: a background scheduler inside the API
  server, which the web UI can inspect and which picks up source edits immediately
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from jd_collector.config import SourceConfig, get_settings, load_sources
from jd_collector.http_client import PoliteHttpClient
from jd_collector.pipeline import run_source

log = logging.getLogger(__name__)

JOB_PREFIX = "scrape:"


def make_trigger(source: SourceConfig):
    if source.cron:
        return CronTrigger.from_crontab(source.cron, timezone="UTC")
    return IntervalTrigger(minutes=source.interval_minutes, timezone="UTC")


def _new_scheduler(cls: type[BaseScheduler]) -> BaseScheduler:
    return cls(
        executors={"default": ThreadPoolExecutor(get_settings().max_workers)},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
        timezone="UTC",
    )


def _sync_jobs(scheduler: BaseScheduler, sources: list[SourceConfig], client: PoliteHttpClient,
               run_now: bool = False) -> None:
    """Make scheduler jobs match ``sources``; unchanged schedules keep their next run time."""
    wanted = {f"{JOB_PREFIX}{s.name}": s for s in sources}
    for job in scheduler.get_jobs():
        if job.id.startswith(JOB_PREFIX) and job.id not in wanted:
            job.remove()
    for job_id, source in wanted.items():
        trigger = make_trigger(source)
        existing = scheduler.get_job(job_id)
        if existing is None:
            # Note: passing next_run_time=None would add the job *paused*; omit it to use the trigger.
            extra = {"next_run_time": datetime.now().astimezone()} if run_now else {}
            scheduler.add_job(
                run_source, trigger=trigger, args=[source, client], id=job_id, name=f"scrape {source.name}",
                replace_existing=True, **extra,
            )
            log.info("Scheduled %s (%s)", source.name, source.cron or f"every {source.interval_minutes} min")
            continue
        existing.modify(args=[source, client])
        if str(existing.trigger) != str(trigger):
            existing.reschedule(trigger=trigger)
            log.info("Rescheduled %s (%s)", source.name, source.cron or f"every {source.interval_minutes} min")


def build_scheduler(sources: list[SourceConfig] | None = None, run_now: bool = False) -> BlockingScheduler:
    scheduler = _new_scheduler(BlockingScheduler)
    _sync_jobs(scheduler, sources if sources is not None else load_sources(), PoliteHttpClient(), run_now)
    return scheduler


def run_scheduler(run_now: bool = False) -> None:
    scheduler = build_scheduler(run_now=run_now)
    log.info("Scheduler started with %d sources. Press Ctrl+C to stop.", len(scheduler.get_jobs()))
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


# --------------------------------------------------------------------------- in-process (API server)

_background: BackgroundScheduler | None = None
_client: PoliteHttpClient | None = None
_lock = threading.Lock()


def start_background(run_now: bool = False) -> None:
    global _background, _client
    with _lock:
        if _background is not None:
            return
        _client = PoliteHttpClient()
        _background = _new_scheduler(BackgroundScheduler)
        _sync_jobs(_background, load_sources(), _client, run_now)
        _background.start()
        log.info("Background scheduler started with %d sources", len(_background.get_jobs()))


def stop_background() -> None:
    global _background
    with _lock:
        if _background is not None:
            _background.shutdown(wait=False)
            _background = None


def reload_background() -> None:
    """Apply sources.yaml changes to the running background scheduler (no-op when off)."""
    with _lock:
        if _background is not None and _client is not None:
            _sync_jobs(_background, load_sources(), _client)


def scheduler_info() -> dict:
    with _lock:
        if _background is None:
            return {"running": False, "jobs": {}}
        return {
            "running": True,
            "jobs": {
                job.id[len(JOB_PREFIX):]: job.next_run_time
                for job in _background.get_jobs()
                if job.id.startswith(JOB_PREFIX)
            },
        }
