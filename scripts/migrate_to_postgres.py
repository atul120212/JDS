"""Migrate data from local SQLite database (data/jd_collector.db) to PostgreSQL (e.g. Neon.tech).

Usage:
    python scripts/migrate_to_postgres.py --target "postgresql://user:password@host/dbname?sslmode=require"
Or set DATABASE_URL environment variable and run:
    python scripts/migrate_to_postgres.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add project root to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import create_engine, select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from jd_collector.db import Base, JobRecord, JobSkill, ScrapeRun


def clean_pg_url(url: str) -> str:
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def migrate(sqlite_path: Path, pg_url: str, chunk_size: int = 500) -> None:
    if not sqlite_path.exists():
        print(f"Error: SQLite database not found at {sqlite_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Connecting to SQLite: {sqlite_path}")
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path.as_posix()}")

    pg_url = clean_pg_url(pg_url)
    print("Connecting to PostgreSQL...")
    pg_engine = create_engine(pg_url, pool_pre_ping=True)

    print("Creating tables on PostgreSQL (if not present)...")
    Base.metadata.create_all(pg_engine)

    with Session(sqlite_engine) as src_session, Session(pg_engine) as dst_session:
        # 1. Migrate Jobs
        total_jobs = src_session.scalar(select(func.count()).select_from(JobRecord)) or 0
        print(f"\nMigrating {total_jobs} jobs in batches of {chunk_size}...")
        
        offset = 0
        migrated_jobs = 0
        job_cols = [c.name for c in JobRecord.__table__.columns]
        
        while offset < total_jobs:
            stmt = select(JobRecord).order_by(JobRecord.job_id).offset(offset).limit(chunk_size)
            rows = src_session.scalars(stmt).all()
            if not rows:
                break
            
            payload = []
            for r in rows:
                row_dict = {col: getattr(r, col) for col in job_cols}
                payload.append(row_dict)
            
            insert_stmt = pg_insert(JobRecord).values(payload).on_conflict_do_nothing(index_elements=["job_id"])
            dst_session.execute(insert_stmt)
            dst_session.commit()
            
            offset += len(rows)
            migrated_jobs += len(rows)
            print(f"  Jobs: {migrated_jobs}/{total_jobs} ({(migrated_jobs / total_jobs * 100):.1f}%)", end="\r")

        print(f"\n  Finished migrating {migrated_jobs} jobs.")

        # 2. Migrate JobSkills
        total_skills = src_session.scalar(select(func.count()).select_from(JobSkill)) or 0
        print(f"\nMigrating {total_skills} job skills in batches of {chunk_size * 2}...")
        
        offset = 0
        migrated_skills = 0
        skill_cols = [c.name for c in JobSkill.__table__.columns]
        skill_chunk = chunk_size * 2
        
        while offset < total_skills:
            stmt = select(JobSkill).order_by(JobSkill.job_id, JobSkill.skill).offset(offset).limit(skill_chunk)
            rows = src_session.scalars(stmt).all()
            if not rows:
                break
            
            payload = [{col: getattr(r, col) for col in skill_cols} for r in rows]
            insert_stmt = pg_insert(JobSkill).values(payload).on_conflict_do_nothing(index_elements=["job_id", "skill"])
            dst_session.execute(insert_stmt)
            dst_session.commit()
            
            offset += len(rows)
            migrated_skills += len(rows)
            print(f"  Job Skills: {migrated_skills}/{total_skills} ({(migrated_skills / total_skills * 100):.1f}%)", end="\r")

        print(f"\n  Finished migrating {migrated_skills} job skills.")

        # 3. Migrate ScrapeRuns
        total_runs = src_session.scalar(select(func.count()).select_from(ScrapeRun)) or 0
        print(f"\nMigrating {total_runs} scrape runs...")
        
        if total_runs > 0:
            run_cols = [c.name for c in ScrapeRun.__table__.columns]
            rows = src_session.scalars(select(ScrapeRun).order_by(ScrapeRun.id)).all()
            payload = [{col: getattr(r, col) for col in run_cols} for r in rows]
            insert_stmt = pg_insert(ScrapeRun).values(payload).on_conflict_do_nothing(index_elements=["id"])
            dst_session.execute(insert_stmt)
            dst_session.commit()
            print(f"  Finished migrating {len(payload)} scrape runs.")

    print("\nSUCCESS: All data successfully migrated to PostgreSQL!\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate local SQLite to PostgreSQL")
    parser.add_argument(
        "--target",
        default=os.getenv("DATABASE_URL"),
        help="Target PostgreSQL connection URL. Defaults to DATABASE_URL environment variable.",
    )
    parser.add_argument(
        "--sqlite-path",
        default=str(ROOT_DIR / "data" / "jd_collector.db"),
        help="Path to SQLite database file. Defaults to data/jd_collector.db",
    )
    args = parser.parse_args()

    if not args.target:
        print("Error: No target PostgreSQL URL provided. Pass --target <URL> or set DATABASE_URL.", file=sys.stderr)
        sys.exit(1)

    migrate(Path(args.sqlite_path), args.target)


if __name__ == "__main__":
    main()
