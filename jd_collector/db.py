"""SQLAlchemy models and engine/session management (SQLite by default, PostgreSQL supported)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, create_engine, event, inspect, text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import NullPool, StaticPool

from jd_collector.config import get_settings


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    external_id: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(500), index=True)
    company: Mapped[str] = mapped_column(String(200), index=True)
    location: Mapped[str | None] = mapped_column(String(500), index=True)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    region: Mapped[str | None] = mapped_column(String(30), index=True)
    role_category: Mapped[str | None] = mapped_column(String(40), index=True)
    experience_level: Mapped[str | None] = mapped_column(String(20), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    salary: Mapped[str | None] = mapped_column(String(200))
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float, index=True)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    salary_interval: Mapped[str | None] = mapped_column(String(10))
    job_type: Mapped[str | None] = mapped_column(String(30), index=True)
    department: Mapped[str | None] = mapped_column(String(300))
    posted_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    apply_link: Mapped[str] = mapped_column(Text)
    source_marker: Mapped[str | None] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    raw: Mapped[Any | None] = mapped_column(JSON, nullable=True)  # original payload, kept as a backup

    skill_rows: Mapped[list["JobSkill"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )

    __table_args__ = (
        Index("ix_jobs_company_location", "company", "location"),
        Index("ix_jobs_source_active", "source", "is_active"),
    )


class JobSkill(Base):
    """One row per (job, skill) so skill filters use an index on any database."""

    __tablename__ = "job_skills"

    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.job_id", ondelete="CASCADE"), primary_key=True)
    skill: Mapped[str] = mapped_column(String(100), primary_key=True)
    skill_lower: Mapped[str] = mapped_column(String(100), index=True)

    job: Mapped[JobRecord] = relationship(back_populates="skill_rows")


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # running | success | failed
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    fetched: Mapped[int] = mapped_column(Integer, default=0)
    new: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    unchanged: Mapped[int] = mapped_column(Integer, default=0)
    invalid: Mapped[int] = mapped_column(Integer, default=0)
    deactivated: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)


# --------------------------------------------------------------------------- engine

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_engine(url: str | None = None) -> Engine:
    """(Re)create the engine and ensure all tables exist."""
    global _engine, _session_factory
    url = url or get_settings().database_url
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    is_memory = False
    if url.startswith("sqlite"):
        # SQLite allows only one writer at a time; when several sources scrape in parallel
        # (ThreadPoolExecutor in pipeline.py), each on its own session, their commits
        # legitimately queue up behind each other. `timeout` is SQLite's own busy-wait: it
        # blocks and retries internally up to this many seconds before raising "database is
        # locked", so a commit simply waits its turn instead of failing - no risk of losing
        # a batch that was about to be committed, unlike an application-level retry would be.
        # `pipeline.py` also serializes its own writes with a lock for the same reason.
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 120}
        db_path = url.split("///", 1)[-1]
        is_memory = not db_path or ":memory:" in db_path
        if not is_memory:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            # SQLite connections are cheap local file handles, not worth pooling like a
            # networked DB's - and empirically, SQLAlchemy's default QueuePool reusing them
            # across threads here caused rare, reproducible hangs under concurrent writers
            # (confirmed via thread-stack dumps) that neither a longer busy-timeout nor the
            # write lock above resolved; a fresh connection per checkout does not hang.
            kwargs["poolclass"] = NullPool
        else:
            # NullPool would hand an in-memory database a *fresh, empty* database on every
            # checkout; it needs the opposite - one connection, kept alive for the engine's
            # lifetime - which StaticPool provides.
            kwargs["poolclass"] = StaticPool

    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):
        @event.listens_for(_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            try:
                cur.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass  # WAL mode may not be supported on in-memory or some serverless volumes
            try:
                cur.execute("PRAGMA foreign_keys=ON")
            except Exception:
                pass
            cur.close()

    Base.metadata.create_all(_engine)
    _migrate(_engine)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


# --------------------------------------------------------------------------- lightweight migrations
#
# create_all() only creates missing *tables*; it never adds a column to a table that already
# exists. Columns added to JobRecord after its first release are retrofitted here instead, so
# a database from an earlier version of this project upgrades in place. Safe to run on every
# startup: each step is skipped once already applied.

_ADDED_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "jobs": (("region", "VARCHAR(30)"), ("role_category", "VARCHAR(40)"), ("experience_level", "VARCHAR(20)")),
}


def _migrate(engine: Engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            if table not in tables:
                continue  # a brand-new table from create_all() already has every column
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl_type in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_{name} ON {table} ({name})"))


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
