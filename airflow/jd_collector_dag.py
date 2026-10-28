"""Optional Apache Airflow DAG: one task per enabled source, scraped daily.

Copy this file into your Airflow ``dags/`` folder and make sure the JD-Collector
project is importable (e.g. ``pip install -e /path/to/JD-Collector`` or PYTHONPATH).
The built-in scheduler (``python -m jd_collector schedule``) is a simpler alternative.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator

from jd_collector.config import load_sources


def _scrape(source_name: str) -> dict:
    from jd_collector.db import init_engine
    from jd_collector.pipeline import run_source

    init_engine()
    source = next(s for s in load_sources() if s.name == source_name)
    result = run_source(source)
    if result.status != "success":
        raise RuntimeError(result.error)
    return result.as_dict()


with DAG(
    dag_id="jd_collector",
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    max_active_tasks=4,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=15)},
    tags=["scraping"],
) as dag:
    for src in load_sources():
        PythonOperator(task_id=f"scrape_{src.name}", python_callable=_scrape, op_args=[src.name])
