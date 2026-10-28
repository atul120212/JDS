"""Database reads and writes for jobs and scrape runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.orm import Session

from jd_collector.db import JobRecord, JobSkill, ScrapeRun
from jd_collector.experience import EXPERIENCE_LEVELS, detect_experience_level
from jd_collector.models import JobPosting
from jd_collector.normalize import detect_job_type, extract_skills
from jd_collector.regions import detect_region
from jd_collector.roles import detect_role_category

_FIELDS = (
    "source", "external_id", "title", "company", "location", "is_remote", "region", "role_category",
    "experience_level", "description", "skills", "salary", "salary_min", "salary_max", "salary_currency",
    "salary_interval", "job_type", "department", "posted_date", "apply_link", "raw",
)


# --------------------------------------------------------------------------- writes


def known_markers(session: Session, source: str) -> dict[str, str]:
    """external_id -> stored source marker for active jobs of a source."""
    rows = session.execute(
        select(JobRecord.external_id, JobRecord.source_marker).where(
            JobRecord.source == source, JobRecord.is_active.is_(True), JobRecord.external_id.is_not(None)
        )
    )
    return {ext: marker or "" for ext, marker in rows}


def _set_skills(record: JobRecord, skills: list[str]) -> None:
    wanted = {s: s.lower() for s in dict.fromkeys(skills)}
    for row in list(record.skill_rows):
        if row.skill not in wanted:
            record.skill_rows.remove(row)
    existing = {row.skill for row in record.skill_rows}
    for skill, lower in wanted.items():
        if skill not in existing:
            record.skill_rows.append(JobSkill(skill=skill, skill_lower=lower))


def upsert_job(session: Session, posting: JobPosting, now: datetime) -> str:
    """Insert or update a job. Returns 'new', 'updated' or 'unchanged'."""
    digest = posting.content_hash()
    record = session.get(JobRecord, posting.job_id)
    if record is None:
        record = JobRecord(job_id=posting.job_id, first_seen_at=now)
        for name in _FIELDS:
            setattr(record, name, getattr(posting, name))
        record.source_marker = posting.source_marker
        record.content_hash = digest
        record.is_active = True
        record.last_seen_at = record.updated_at = now
        _set_skills(record, posting.skills)
        session.add(record)
        return "new"

    reactivated = not record.is_active
    record.is_active = True
    record.last_seen_at = now
    record.source_marker = posting.source_marker
    if record.content_hash == digest:
        return "updated" if reactivated else "unchanged"
    for name in _FIELDS:
        setattr(record, name, getattr(posting, name))
    record.content_hash = digest
    record.updated_at = now
    _set_skills(record, posting.skills)
    return "updated"


def reclassify_all(session: Session, batch_size: int = 500) -> int:
    """Recompute region, role category, experience level, job type and skills for every stored
    job from its already-stored title/location/description - no re-scraping involved. Useful
    after upgrading the classification rules (for example, after first adding region/role
    support to an existing database). Returns the number of jobs updated.
    """
    updated = 0
    offset = 0
    while True:
        rows = session.scalars(
            select(JobRecord).order_by(JobRecord.job_id).offset(offset).limit(batch_size)
        ).all()
        if not rows:
            break
        for row in rows:
            row.region = detect_region(row.location, row.is_remote)
            row.role_category = detect_role_category(row.title, row.description)
            row.experience_level = detect_experience_level(row.title, row.description)
            # The original structured "employment type" hint from the source (e.g. Greenhouse's
            # own metadata) isn't persisted, only the job_type it resolved to - so that resolved
            # value is reused as the hint here. This can still improve a None into a detected
            # value from title/description, but never discards an already-correct one.
            row.job_type = detect_job_type(row.job_type, row.title, row.description)
            skills = [s for s in extract_skills(f"{row.title}\n{row.description}") if s.lower() != row.company.lower()]
            _set_skills(row, skills)
            # Keep content_hash consistent with the row's new content, so the next real scrape
            # doesn't see a false "updated" just because local reclassification changed it.
            row.content_hash = JobPosting(
                job_id=row.job_id, source=row.source, title=row.title, company=row.company,
                location=row.location, is_remote=row.is_remote, region=row.region, role_category=row.role_category,
                experience_level=row.experience_level, description=row.description, skills=skills,
                salary=row.salary, job_type=row.job_type, department=row.department, apply_link=row.apply_link,
            ).content_hash()
            updated += 1
        session.commit()
        offset += batch_size
    return updated


def touch_job(session: Session, job_id: str, now: datetime) -> bool:
    result = session.execute(
        update(JobRecord).where(JobRecord.job_id == job_id).values(last_seen_at=now, is_active=True)
    )
    return result.rowcount > 0


def deactivate_missing(session: Session, source: str, run_started: datetime) -> int:
    """Mark jobs of ``source`` that were not seen in the current run as closed."""
    result = session.execute(
        update(JobRecord)
        .where(JobRecord.source == source, JobRecord.is_active.is_(True), JobRecord.last_seen_at < run_started)
        .values(is_active=False)
    )
    return result.rowcount or 0


def last_successful_run(session: Session, source: str, exclude_id: int | None = None) -> ScrapeRun | None:
    stmt = select(ScrapeRun).where(ScrapeRun.source == source, ScrapeRun.status == "success")
    if exclude_id is not None:
        stmt = stmt.where(ScrapeRun.id != exclude_id)
    return session.scalars(stmt.order_by(ScrapeRun.started_at.desc()).limit(1)).first()


# --------------------------------------------------------------------------- reads


@dataclass
class JobFilters:
    q: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    skills: list[str] = field(default_factory=list)
    job_type: str | None = None
    remote: bool | None = None
    region: str | None = None
    role_category: str | None = None
    experience_level: str | None = None
    source: str | None = None
    posted_after: datetime | None = None
    min_salary: float | None = None
    ids: list[str] = field(default_factory=list)
    active_only: bool = True


SORTS: dict[str, Any] = {
    "-posted_date": (JobRecord.posted_date.is_(None), JobRecord.posted_date.desc()),
    "posted_date": (JobRecord.posted_date.is_(None), JobRecord.posted_date.asc()),
    "-updated_at": (JobRecord.updated_at.desc(),),
    "-first_seen_at": (JobRecord.first_seen_at.desc(),),
    "title": (JobRecord.title.asc(),),
    "company": (JobRecord.company.asc(), JobRecord.title.asc()),
    "-salary_max": (JobRecord.salary_max.is_(None), JobRecord.salary_max.desc()),
}


def _like(column, value: str):
    escaped = value.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return func.lower(column).like(f"%{escaped}%", escape="\\")


def _apply_filters(stmt: Select, f: JobFilters) -> Select:
    if f.active_only:
        stmt = stmt.where(JobRecord.is_active.is_(True))
    if f.q:
        for term in f.q.split():
            stmt = stmt.where(
                or_(_like(JobRecord.title, term), _like(JobRecord.company, term), _like(JobRecord.description, term))
            )
    if f.title:
        stmt = stmt.where(_like(JobRecord.title, f.title))
    if f.company:
        stmt = stmt.where(_like(JobRecord.company, f.company))
    if f.location:
        stmt = stmt.where(_like(JobRecord.location, f.location))
    for skill in f.skills:
        stmt = stmt.where(
            JobRecord.job_id.in_(select(JobSkill.job_id).where(JobSkill.skill_lower == skill.strip().lower()))
        )
    if f.job_type:
        stmt = stmt.where(func.lower(JobRecord.job_type) == f.job_type.lower())
    if f.remote is not None:
        stmt = stmt.where(JobRecord.is_remote.is_(f.remote))
    if f.region:
        stmt = stmt.where(JobRecord.region == f.region)
    if f.role_category:
        stmt = stmt.where(JobRecord.role_category == f.role_category)
    if f.experience_level:
        stmt = stmt.where(JobRecord.experience_level == f.experience_level)
    if f.source:
        stmt = stmt.where(JobRecord.source == f.source)
    if f.posted_after:
        stmt = stmt.where(JobRecord.posted_date >= f.posted_after)
    if f.min_salary is not None:
        stmt = stmt.where(JobRecord.salary_max >= f.min_salary)
    if f.ids:
        stmt = stmt.where(JobRecord.job_id.in_(f.ids))
    return stmt


def search_jobs(
    session: Session, filters: JobFilters, page: int = 1, page_size: int = 20, sort: str = "-posted_date"
) -> tuple[list[JobRecord], int]:
    stmt = _apply_filters(select(JobRecord), filters)
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    order = SORTS.get(sort, SORTS["-posted_date"])
    rows = session.scalars(stmt.order_by(*order, JobRecord.job_id).offset((page - 1) * page_size).limit(page_size))
    return list(rows), total


def get_job(session: Session, job_id: str) -> JobRecord | None:
    return session.get(JobRecord, job_id)


def company_counts(session: Session, active_only: bool = True) -> list[tuple[str, int]]:
    stmt = select(JobRecord.company, func.count()).group_by(JobRecord.company).order_by(func.count().desc())
    if active_only:
        stmt = stmt.where(JobRecord.is_active.is_(True))
    return [(c, n) for c, n in session.execute(stmt)]


def top_skills(session: Session, limit: int = 50, company: str | None = None) -> list[tuple[str, int]]:
    stmt = (
        select(JobSkill.skill, func.count())
        .join(JobRecord, JobRecord.job_id == JobSkill.job_id)
        .where(JobRecord.is_active.is_(True))
        .group_by(JobSkill.skill)
        .order_by(func.count().desc())
        .limit(limit)
    )
    if company:
        stmt = stmt.where(_like(JobRecord.company, company))
    return [(s, n) for s, n in session.execute(stmt)]


def stats(session: Session) -> dict[str, Any]:
    total = session.scalar(select(func.count()).select_from(JobRecord)) or 0
    active = session.scalar(select(func.count()).select_from(JobRecord).where(JobRecord.is_active.is_(True))) or 0
    remote = session.scalar(
        select(func.count()).select_from(JobRecord).where(JobRecord.is_active.is_(True), JobRecord.is_remote.is_(True))
    ) or 0
    by_source = {
        s: n
        for s, n in session.execute(
            select(JobRecord.source, func.count()).where(JobRecord.is_active.is_(True)).group_by(JobRecord.source)
        )
    }
    by_type = {
        (t or "Unknown"): n
        for t, n in session.execute(
            select(JobRecord.job_type, func.count()).where(JobRecord.is_active.is_(True)).group_by(JobRecord.job_type)
        )
    }
    by_region = {
        (r or "Not specified"): n
        for r, n in session.execute(
            select(JobRecord.region, func.count()).where(JobRecord.is_active.is_(True)).group_by(JobRecord.region)
        )
    }
    last_seen = session.scalar(select(func.max(JobRecord.last_seen_at)))
    with_salary = session.scalar(
        select(func.count()).select_from(JobRecord)
        .where(JobRecord.is_active.is_(True), JobRecord.salary_max.is_not(None))
    ) or 0
    new_24h = session.scalar(
        select(func.count()).select_from(JobRecord)
        .where(JobRecord.is_active.is_(True), JobRecord.first_seen_at >= datetime.utcnow() - timedelta(hours=24))
    ) or 0
    return {
        "total_jobs": total,
        "active_jobs": active,
        "remote_jobs": remote,
        "with_salary": with_salary,
        "new_24h": new_24h,
        "companies": len(company_counts(session)),
        "by_source": by_source,
        "by_job_type": by_type,
        "by_region": by_region,
        "data_freshness": last_seen,
    }


def recent_runs(session: Session, source: str | None = None, limit: int = 50,
                status: str | None = None) -> list[ScrapeRun]:
    stmt = select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit)
    if source:
        stmt = stmt.where(ScrapeRun.source == source)
    if status:
        stmt = stmt.where(ScrapeRun.status == status)
    return list(session.scalars(stmt))


def latest_runs_by_source(session: Session) -> dict[str, ScrapeRun]:
    latest = (
        select(ScrapeRun.source, func.max(ScrapeRun.id).label("max_id")).group_by(ScrapeRun.source).subquery()
    )
    rows = session.scalars(select(ScrapeRun).join(latest, ScrapeRun.id == latest.c.max_id))
    return {r.source: r for r in rows}


def active_counts_by_source(session: Session) -> dict[str, int]:
    return dict(session.execute(
        select(JobRecord.source, func.count()).where(JobRecord.is_active.is_(True)).group_by(JobRecord.source)
    ).all())


def fail_stale_runs(session: Session, older_than: timedelta = timedelta(hours=2)) -> int:
    """Runs stuck in 'running' (e.g. the process was killed) are marked failed."""
    result = session.execute(
        update(ScrapeRun)
        .where(ScrapeRun.status == "running", ScrapeRun.started_at < datetime.utcnow() - older_than)
        .values(status="failed", error="Interrupted: the process stopped before the run finished",
                finished_at=datetime.utcnow())
    )
    return result.rowcount or 0


def delete_source_jobs(session: Session, source: str) -> int:
    ids = select(JobRecord.job_id).where(JobRecord.source == source)
    session.execute(delete(JobSkill).where(JobSkill.job_id.in_(ids)))
    result = session.execute(delete(JobRecord).where(JobRecord.source == source))
    return result.rowcount or 0


def facets(session: Session, location_limit: int = 40, skill_limit: int = 300) -> dict[str, Any]:
    active = JobRecord.is_active.is_(True)

    def counts(column, limit: int | None = None):
        stmt = (select(column, func.count()).where(active, column.is_not(None))
                .group_by(column).order_by(func.count().desc(), column))
        if limit:
            stmt = stmt.limit(limit)
        return [{"name": name, "count": n} for name, n in session.execute(stmt)]

    return {
        "companies": counts(JobRecord.company),
        "sources": counts(JobRecord.source),
        "job_types": counts(JobRecord.job_type),
        "regions": counts(JobRecord.region),
        "role_categories": counts(JobRecord.role_category),
        # Natural progression (Fresher -> 12+), not count order - more useful in a dropdown.
        "experience_levels": sorted(
            counts(JobRecord.experience_level),
            key=lambda r: EXPERIENCE_LEVELS.index(r["name"]) if r["name"] in EXPERIENCE_LEVELS else 99,
        ),
        "locations": counts(JobRecord.location, location_limit),
        "skills": [{"name": s, "count": n} for s, n in top_skills(session, skill_limit)],
    }


def posted_timeline(session: Session, days: int = 30, company: str | None = None) -> list[dict[str, Any]]:
    """Open jobs per posting day for the last ``days`` days (zero-filled)."""
    start = (datetime.utcnow() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    day = func.date(JobRecord.posted_date)
    stmt = (select(day, func.count())
            .where(JobRecord.is_active.is_(True), JobRecord.posted_date >= start)
            .group_by(day))
    if company:
        stmt = stmt.where(_like(JobRecord.company, company))
    found = {str(d)[:10]: n for d, n in session.execute(stmt)}
    out = []
    for i in range(days):
        key = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        out.append({"date": key, "count": found.get(key, 0)})
    return out
