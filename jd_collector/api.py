"""REST API (FastAPI) for querying collected jobs and managing sources and scrapes."""

from __future__ import annotations

import csv
import io
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from apscheduler.triggers.cron import CronTrigger
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jd_collector import __version__
from jd_collector import repository as repo
from jd_collector import scheduler
from jd_collector.catalog import REGIONS, catalog_by_name, filter_catalog, load_catalog
from jd_collector.config import (
    SOURCE_NAME_RX, SourceConfig, delete_source, get_settings, load_sources, save_source,
)
from jd_collector.db import JobRecord, get_db, init_engine, session_scope
from jd_collector.pipeline import preview_source, run_sources, running_sources
from jd_collector.scrapers import SCRAPERS

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
EXPORT_LIMIT = 10_000
MIN_INTERVAL_MINUTES = 15
MIN_RATE_LIMIT_SECONDS = 0.2


# --------------------------------------------------------------------------- schemas


class JobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    title: str
    company: str
    location: str | None
    is_remote: bool
    region: str | None
    role_category: str | None
    experience_level: str | None
    skills: list[str]
    salary: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    salary_interval: str | None
    job_type: str | None
    department: str | None
    posted_date: datetime | None
    apply_link: str
    source: str
    is_active: bool
    first_seen_at: datetime
    last_seen_at: datetime
    snippet: str = ""


class JobDetail(JobSummary):
    description: str
    external_id: str | None
    updated_at: datetime


class JobPage(BaseModel):
    total: int
    page: int
    page_size: int
    pages: int
    items: list[JobSummary]


class CountItem(BaseModel):
    name: str
    count: int


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: float | None
    fetched: int
    new: int
    updated: int
    unchanged: int
    invalid: int
    deactivated: int
    error: str | None


class CatalogAddIn(BaseModel):
    names: list[str] = Field(min_length=1, max_length=200)


class SourceIn(BaseModel):
    # Lengths are checked in _to_source so the UI gets readable messages.
    name: str = ""
    type: str
    company: str = ""
    enabled: bool = True
    interval_minutes: int = 360
    cron: str | None = None
    rate_limit_seconds: float = 1.0
    options: dict[str, Any] = Field(default_factory=dict)


def _summary(record: JobRecord) -> JobSummary:
    item = JobSummary.model_validate(record)
    text = " ".join((record.description or "").split())
    item.snippet = text[:280] + ("…" if len(text) > 280 else "")
    return item


def _to_source(body: SourceIn, check_name: bool = True) -> SourceConfig:
    """Validate an incoming source definition; raises 422 with every problem found."""
    errors: list[str] = []
    name = body.name.strip().lower()
    if not body.company.strip():
        errors.append("Company is required")
    elif len(body.company.strip()) > 200:
        errors.append("Company name is too long (max 200 characters)")
    if check_name and not name:
        errors.append("Source ID is required")
    elif check_name and not SOURCE_NAME_RX.match(name):
        errors.append("Source ID may only use lowercase letters, digits, '-' and '_' (max 64)")
    scraper_cls = SCRAPERS.get(body.type)
    options: dict[str, Any] = {}
    if scraper_cls is None:
        errors.append(f"Unknown type '{body.type}'")
    else:
        options, option_errors = scraper_cls.clean_options(body.options)
        errors.extend(option_errors)
    cron = (body.cron or "").strip() or None
    if cron:
        try:
            CronTrigger.from_crontab(cron)
        except ValueError as exc:
            errors.append(f"Invalid cron expression: {exc}")
    elif body.interval_minutes < MIN_INTERVAL_MINUTES:
        errors.append(f"Interval must be at least {MIN_INTERVAL_MINUTES} minutes")
    if body.rate_limit_seconds < MIN_RATE_LIMIT_SECONDS:
        errors.append(f"Rate limit must be at least {MIN_RATE_LIMIT_SECONDS}s between requests")
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return SourceConfig(
        name=name or "preview", type=body.type, company=body.company.strip(), enabled=body.enabled,
        interval_minutes=body.interval_minutes, cron=cron, rate_limit_seconds=body.rate_limit_seconds,
        options=options,
    )


def _csv_cell(value: Any) -> Any:
    """Neutralise spreadsheet formula injection from scraped text."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


# --------------------------------------------------------------------------- security


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_key
    if expected and not secrets.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


def job_filters(
    q: str | None = Query(None, description="Free text over title, company and description"),
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    skill: list[str] = Query(default=[], description="Repeat for AND, e.g. ?skill=Python&skill=AWS"),
    job_type: str | None = Query(None, description="Full-time, Part-time, Contract, Internship, Temporary"),
    remote: bool | None = None,
    region: str | None = Query(None, description="e.g. 'North America', 'Europe', 'Asia Pacific'"),
    role_category: str | None = Query(None, description="e.g. 'Engineering', 'Sales & Business Development'"),
    experience_level: str | None = Query(None, description="e.g. 'Fresher / 0-1 yr', '3-5 yrs'"),
    source: str | None = None,
    posted_after: datetime | None = None,
    min_salary: float | None = Query(None, description="Jobs whose salary_max is at least this"),
    ids: list[str] = Query(default=[], description="Only these job ids (e.g. saved jobs)"),
    include_inactive: bool = False,
) -> repo.JobFilters:
    return repo.JobFilters(
        q=q, title=title, company=company, location=location, skills=[s for s in skill if s.strip()],
        job_type=job_type, remote=remote, region=region, role_category=role_category,
        experience_level=experience_level, source=source,
        posted_after=posted_after, min_salary=min_salary, ids=ids[:500], active_only=not include_inactive,
    )


# --------------------------------------------------------------------------- app


def create_app(with_scheduler: bool = False, run_now: bool = False) -> FastAPI:
    init_engine()
    with session_scope() as session:
        stale = repo.fail_stale_runs(session)
        if stale:
            log.warning("Marked %d interrupted scrape runs as failed", stale)
    if not get_settings().api_key:
        log.warning("API_KEY is not set - the API is open to anyone who can reach it")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if with_scheduler:
            scheduler.start_background(run_now=run_now)
        yield
        if with_scheduler:
            scheduler.stop_background()

    app = FastAPI(
        title="JD Collector API",
        version=__version__,
        description="Search job descriptions collected from company career sites.",
        lifespan=lifespan,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    secured = [Depends(require_api_key)]

    # ------------------------------------------------------------------ meta

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__, "auth_required": bool(get_settings().api_key)}

    @app.get("/status", dependencies=secured, tags=["meta"])
    def status(db: Session = Depends(get_db)) -> dict:
        """Cheap endpoint the UI polls: running scrapes, scheduler state and freshness."""
        running_db = [r.source for r in repo.recent_runs(db, status="running", limit=100)]
        latest = repo.recent_runs(db, limit=1)
        return {
            "running": sorted(set(running_sources()) | set(running_db)),
            "scheduler": scheduler.scheduler_info(),
            "data_freshness": db.scalar(select(func.max(JobRecord.last_seen_at))),
            "latest_run_id": latest[0].id if latest else None,
        }

    # ------------------------------------------------------------------ jobs

    @app.get("/jobs", response_model=JobPage, dependencies=secured, tags=["jobs"])
    def list_jobs(
        filters: repo.JobFilters = Depends(job_filters),
        sort: str = Query("-posted_date", enum=list(repo.SORTS)),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        db: Session = Depends(get_db),
    ) -> JobPage:
        rows, total = repo.search_jobs(db, filters, page, page_size, sort)
        return JobPage(
            total=total, page=page, page_size=page_size,
            pages=(total + page_size - 1) // page_size, items=[_summary(r) for r in rows],
        )

    @app.get("/jobs/export.csv", dependencies=secured, tags=["jobs"])
    def export_jobs(
        filters: repo.JobFilters = Depends(job_filters),
        sort: str = Query("-posted_date", enum=list(repo.SORTS)),
        db: Session = Depends(get_db),
    ) -> StreamingResponse:
        rows, _ = repo.search_jobs(db, filters, 1, EXPORT_LIMIT, sort)
        columns = ["job_id", "title", "company", "location", "is_remote", "region", "role_category",
                   "experience_level", "job_type", "salary", "salary_min", "salary_max", "salary_currency",
                   "salary_interval", "skills", "department", "posted_date", "apply_link", "source_website",
                   "source", "is_active", "first_seen_at", "last_seen_at"]
        buf = io.StringIO()
        buf.write("﻿")  # BOM so Excel opens UTF-8 correctly
        writer = csv.writer(buf)
        writer.writerow(columns)
        for r in rows:
            values = [getattr(r, c, None) for c in columns]
            values[columns.index("skills")] = "; ".join(r.skills or [])
            # Citation: the actual site the posting was collected from, for provenance.
            values[columns.index("source_website")] = urlsplit(r.apply_link).netloc
            writer.writerow([_csv_cell(v) for v in values])
        filename = f"jobs-{datetime.utcnow():%Y%m%d-%H%M}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/jobs/{job_id}", response_model=JobDetail, dependencies=secured, tags=["jobs"])
    def get_job(job_id: str, db: Session = Depends(get_db)) -> JobDetail:
        record = repo.get_job(db, job_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Job not found")
        detail = JobDetail.model_validate(record)
        detail.snippet = _summary(record).snippet
        return detail

    # ------------------------------------------------------------------ insights

    @app.get("/facets", dependencies=secured, tags=["insights"])
    def facets(db: Session = Depends(get_db)) -> dict:
        return repo.facets(db)

    @app.get("/companies", response_model=list[CountItem], dependencies=secured, tags=["insights"])
    def companies(db: Session = Depends(get_db)) -> list[CountItem]:
        return [CountItem(name=c, count=n) for c, n in repo.company_counts(db)]

    @app.get("/skills", response_model=list[CountItem], dependencies=secured, tags=["insights"])
    def skills(
        limit: int = Query(50, ge=1, le=500), company: str | None = None, db: Session = Depends(get_db)
    ) -> list[CountItem]:
        return [CountItem(name=s, count=n) for s, n in repo.top_skills(db, limit, company)]

    @app.get("/stats", dependencies=secured, tags=["insights"])
    def stats(db: Session = Depends(get_db)) -> dict:
        return repo.stats(db)

    @app.get("/insights/timeline", dependencies=secured, tags=["insights"])
    def timeline(
        days: int = Query(30, ge=7, le=180), company: str | None = None, db: Session = Depends(get_db)
    ) -> list[dict]:
        return repo.posted_timeline(db, days, company)

    # ------------------------------------------------------------------ monitoring

    @app.get("/runs", response_model=list[RunOut], dependencies=secured, tags=["monitoring"])
    def runs(
        source: str | None = None, status: str | None = None,
        limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
    ) -> list[RunOut]:
        return [RunOut.model_validate(r) for r in repo.recent_runs(db, source, limit, status)]

    @app.post("/scrape", status_code=202, dependencies=secured, tags=["monitoring"])
    def trigger_scrape(background: BackgroundTasks, source: list[str] = Query(default=[])) -> dict:
        everything = {s.name: s for s in load_sources(include_disabled=True)}
        unknown = [name for name in source if name not in everything]
        if unknown:
            raise HTTPException(status_code=404, detail=f"Unknown sources: {unknown}")
        # Named sources run even when disabled (manual run); no names = all enabled sources.
        selected = [everything[n] for n in source] if source else [s for s in everything.values() if s.enabled]
        busy = set(running_sources())
        queued = [s for s in selected if s.name not in busy]
        if queued:
            background.add_task(run_sources, queued)
        return {"queued": [s.name for s in queued], "already_running": sorted(busy & {s.name for s in selected})}

    # ------------------------------------------------------------------ catalog
    #
    # The curated, pre-verified directory of company career pages (config/catalog.yaml).
    # Browsing it never scrapes anything; an entry only becomes an active source once added.

    @app.get("/catalog", dependencies=secured, tags=["catalog"])
    def catalog(
        region: str | None = None, industry: str | None = None,
        type_: str | None = Query(None, alias="type"), q: str | None = None,
    ) -> list[dict]:
        existing = {s.name for s in load_sources(include_disabled=True)}
        entries = filter_catalog(load_catalog(), region=region, industry=industry, type_=type_, q=q)
        return [{**e.as_dict(), "already_added": e.name in existing} for e in entries]

    @app.get("/catalog/regions", dependencies=secured, tags=["catalog"])
    def catalog_regions() -> dict:
        """Regions and industries present in the catalog, for building filter dropdowns."""
        entries = load_catalog()
        present = {e.region for e in entries}
        return {
            "regions": [r for r in REGIONS if r in present] + sorted(present - set(REGIONS)),
            "industries": sorted({e.industry for e in entries}),
            "total": len(entries),
        }

    @app.post("/catalog/add", dependencies=secured, tags=["catalog"])
    def add_from_catalog(body: CatalogAddIn) -> dict:
        by_name = catalog_by_name()
        unknown = [n for n in body.names if n not in by_name]
        existing = {s.name for s in load_sources(include_disabled=True)}
        added, skipped = [], []
        for name in body.names:
            if name in unknown:
                continue
            if name in existing:
                skipped.append(name)
                continue
            save_source(by_name[name].to_source())
            existing.add(name)
            added.append(name)
        if added:
            scheduler.reload_background()
        return {"added": added, "skipped": skipped, "unknown": unknown}

    # ------------------------------------------------------------------ sources

    @app.get("/source-types", dependencies=secured, tags=["sources"])
    def source_types() -> list[dict]:
        return [cls.describe() for cls in SCRAPERS.values()]

    @app.get("/sources", dependencies=secured, tags=["sources"])
    def sources(db: Session = Depends(get_db)) -> list[dict]:
        last_runs = repo.latest_runs_by_source(db)
        counts = repo.active_counts_by_source(db)
        sched = scheduler.scheduler_info()
        busy = set(running_sources())
        out = []
        for s in load_sources(include_disabled=True):
            last = last_runs.get(s.name)
            out.append({
                "name": s.name, "type": s.type, "company": s.company, "enabled": s.enabled,
                "interval_minutes": s.interval_minutes, "cron": s.cron,
                "rate_limit_seconds": s.rate_limit_seconds, "options": s.options,
                "schedule": s.cron or f"every {s.interval_minutes} min",
                "active_jobs": counts.get(s.name, 0),
                "running": s.name in busy or (last is not None and last.status == "running"),
                "last_run": RunOut.model_validate(last).model_dump() if last else None,
                "next_run": sched["jobs"].get(s.name),
            })
        return out

    @app.post("/sources", status_code=201, dependencies=secured, tags=["sources"])
    def create_source(body: SourceIn) -> dict:
        source = _to_source(body)
        try:
            save_source(source)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        scheduler.reload_background()
        return {"name": source.name}

    @app.put("/sources/{name}", dependencies=secured, tags=["sources"])
    def update_source(name: str, body: SourceIn) -> dict:
        source = _to_source(body)
        try:
            save_source(source, original_name=name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown source '{name}'") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        scheduler.reload_background()
        return {"name": source.name}

    @app.delete("/sources/{name}", dependencies=secured, tags=["sources"])
    def remove_source(name: str, delete_jobs: bool = False, db: Session = Depends(get_db)) -> dict:
        if name in running_sources():
            raise HTTPException(status_code=409, detail="This source is being scraped right now; try again shortly")
        try:
            delete_source(name)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown source '{name}'") from exc
        removed = 0
        if delete_jobs:
            removed = repo.delete_source_jobs(db, name)
            db.commit()
        scheduler.reload_background()
        return {"deleted": name, "jobs_deleted": removed}

    @app.post("/sources/preview", dependencies=secured, tags=["sources"])
    def preview(body: SourceIn) -> dict:
        """Test a source definition: scrape a sample, normalize it, store nothing."""
        return preview_source(_to_source(body, check_name=False))

    return app
