"""init_engine() must retrofit region/role_category/experience_level onto a database created
before they existed, without losing data - this is what happens the first time an upgraded
install points at an old DB.
"""

import sqlite3

from sqlalchemy import inspect

from jd_collector import db as db_module


def _make_legacy_db(path):
    """A minimal stand-in for the pre-region/role_category 'jobs' table, with one row."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE jobs (job_id VARCHAR(64) PRIMARY KEY, title VARCHAR(500), "
        "company VARCHAR(200), is_active BOOLEAN)"
    )
    conn.execute("INSERT INTO jobs (job_id, title, company, is_active) VALUES ('abc', 'Engineer', 'Acme', 1)")
    conn.commit()
    conn.close()


def test_migration_adds_columns_and_indexes_without_losing_data(tmp_path):
    db_path = tmp_path / "legacy.db"
    _make_legacy_db(db_path)

    engine = db_module.init_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        inspector = inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("jobs")}
        assert {"region", "role_category", "experience_level"} <= columns

        index_names = {ix["name"] for ix in inspector.get_indexes("jobs")}
        assert {"ix_jobs_region", "ix_jobs_role_category", "ix_jobs_experience_level"} <= index_names

        with engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT job_id, title, company, region FROM jobs").fetchone()
            assert row == ("abc", "Engineer", "Acme", None)
    finally:
        engine.dispose()


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "legacy2.db"
    _make_legacy_db(db_path)
    db_module.init_engine(f"sqlite:///{db_path.as_posix()}")
    engine = db_module.init_engine(f"sqlite:///{db_path.as_posix()}")  # run again: must not error
    try:
        inspector = inspect(engine)
        assert {"region", "role_category", "experience_level"} <= {c["name"] for c in inspector.get_columns("jobs")}
    finally:
        engine.dispose()


def test_fresh_database_has_columns_without_migration(tmp_path):
    db_path = tmp_path / "fresh.db"
    engine = db_module.init_engine(f"sqlite:///{db_path.as_posix()}")
    try:
        columns = {c["name"] for c in inspect(engine).get_columns("jobs")}
        assert {"region", "role_category", "experience_level"} <= columns
    finally:
        engine.dispose()
