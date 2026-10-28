"""API endpoints used by the web UI: source management, preview, export, facets, status."""

import csv
import io
import threading

import pytest
from conftest import load_fixture
from fastapi.testclient import TestClient

from jd_collector import pipeline, scheduler
from jd_collector.config import SourceConfig, get_settings, load_sources
from jd_collector.pipeline import preview_source, run_source

GH_URL = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"
STRIPE = SourceConfig(name="stripe", type="greenhouse", company="Stripe", options={"board_token": "stripe"})

SOURCES_YAML = """\
# Top comment that must survive edits
defaults:
  interval_minutes: 360

sources:
  # Big companies
  - name: stripe
    type: greenhouse
    company: Stripe
    board_token: stripe
"""


@pytest.fixture
def client(db, tmp_path, monkeypatch):
    path = tmp_path / "sources.yaml"
    path.write_text(SOURCES_YAML, encoding="utf-8")
    monkeypatch.setenv("SOURCES_FILE", str(path))
    get_settings.cache_clear()
    from jd_collector.api import create_app

    with TestClient(create_app()) as c:
        c.sources_path = path
        yield c


def test_source_crud_preserves_comments(client):
    body = {"name": "ramp", "type": "ashby", "company": "Ramp", "interval_minutes": 720, "options": {"board": "ramp"}}
    assert client.post("/sources", json=body).status_code == 201
    assert client.post("/sources", json=body).status_code == 409  # duplicate

    names = [s["name"] for s in client.get("/sources").json()]
    assert names == ["stripe", "ramp"]
    text = client.sources_path.read_text(encoding="utf-8")
    assert "# Top comment that must survive edits" in text and "# Big companies" in text

    body.update(enabled=False, cron="0 6 * * *")
    assert client.put("/sources/ramp", json=body).status_code == 200
    ramp = next(s for s in load_sources(client.sources_path, include_disabled=True) if s.name == "ramp")
    assert ramp.enabled is False and ramp.cron == "0 6 * * *" and ramp.option("board") == "ramp"

    # rename
    body["name"] = "ramp-co"
    assert client.put("/sources/ramp", json=body).status_code == 200
    assert {s.name for s in load_sources(client.sources_path, include_disabled=True)} == {"stripe", "ramp-co"}

    assert client.delete("/sources/ramp-co").json()["deleted"] == "ramp-co"
    assert client.delete("/sources/ramp-co").status_code == 404
    assert "# Big companies" in client.sources_path.read_text(encoding="utf-8")


def test_source_validation_messages(client):
    r = client.post("/sources", json={"name": "Bad Name!", "type": "css", "company": "", "interval_minutes": 5,
                                      "rate_limit_seconds": 0, "cron": "nope", "options": {"item_selector": "div[["}})
    assert r.status_code == 422
    errors = " | ".join(r.json()["detail"])
    for expected in ("Company is required", "Source ID may only use", "Listing page URL is required",
                     "Job item selector is invalid", "Title selector is required", "Invalid cron",
                     "Rate limit must be at least"):
        assert expected in errors, errors
    r = client.post("/sources", json={"name": "x", "type": "nope", "company": "X"})
    assert "Unknown type" in r.json()["detail"][0]


def test_source_types_describe_fields(client):
    types = {t["type"]: t for t in client.get("/source-types").json()}
    assert {"greenhouse", "lever", "ashby", "smartrecruiters", "jsonld", "css"} <= set(types)
    gh = types["greenhouse"]["fields"][0]
    assert gh["key"] == "board_token" and gh["required"] is True
    assert types["lever"]["fields"][1]["choices"] == ["us", "eu"]


def test_sources_listing_includes_last_run_and_counts(client, fake_client):
    run_source(STRIPE, fake_client({GH_URL: load_fixture("greenhouse.json")}))
    src = client.get("/sources").json()[0]
    assert src["active_jobs"] == 2
    assert src["last_run"]["status"] == "success" and src["last_run"]["new"] == 2
    assert src["running"] is False


def test_preview_does_not_store(db, fake_client):
    from jd_collector import repository as repo

    result = preview_source(STRIPE, fake_client({GH_URL: load_fixture("greenhouse.json")}))
    assert result["ok"] and result["valid"] == 2 and result["invalid"] == 1 and result["complete"]
    assert result["samples"][0]["title"] == "Senior Backend Engineer, Payments"
    assert result["issues"][0]["issue"] == "missing title"
    with db.session_scope() as s:
        assert repo.search_jobs(s, repo.JobFilters())[1] == 0

    failed = preview_source(STRIPE, fake_client({}))
    assert failed["ok"] is False and "KeyError" in failed["error"]


def test_preview_endpoint_validates_first(client):
    r = client.post("/sources/preview", json={"type": "greenhouse", "company": "X", "options": {}})
    assert r.status_code == 422 and "Board token is required" in r.json()["detail"]


def test_export_facets_timeline_and_ids(client, fake_client):
    run_source(STRIPE, fake_client({GH_URL: load_fixture("greenhouse.json")}))

    r = client.get("/jobs/export.csv", params={"skill": "Kafka"})
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    header, row = rows[0], rows[1]
    assert header[0] == "job_id" and len(rows) == 2 and "Kafka" in row[header.index("skills")]
    assert row[header.index("experience_level")] == "5-8 yrs"
    assert row[header.index("source_website")] == "stripe.com"  # citation: the site the job was collected from

    facets = client.get("/facets").json()
    assert facets["companies"] == [{"name": "Stripe", "count": 2}]
    assert any(s["name"] == "Python" for s in facets["skills"])

    timeline = client.get("/insights/timeline", params={"days": 7}).json()
    assert len(timeline) == 7 and all(set(d) == {"date", "count"} for d in timeline)

    job_id = client.get("/jobs").json()["items"][0]["job_id"]
    picked = client.get("/jobs", params={"ids": [job_id, "missing"]}).json()
    assert picked["total"] == 1 and picked["items"][0]["job_id"] == job_id

    stats = client.get("/stats").json()
    assert stats["new_24h"] == 2 and stats["with_salary"] == 1


def test_csv_cells_are_formula_safe():
    from jd_collector.api import _csv_cell

    assert _csv_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _csv_cell("Engineer") == "Engineer" and _csv_cell(5) == 5


def test_status_and_scrape_unknown(client):
    st = client.get("/status").json()
    assert st["running"] == [] and st["scheduler"]["running"] is False
    assert client.post("/scrape", params={"source": "nope"}).status_code == 404
    assert client.get("/health").json()["auth_required"] is False


def test_same_source_never_runs_twice(db):
    started, release = threading.Event(), threading.Event()

    class SlowClient:
        def get_json(self, url, params=None, min_interval=None):
            started.set()
            release.wait(5)
            return {"jobs": []}

    t = threading.Thread(target=run_source, args=(STRIPE, SlowClient()))
    t.start()
    assert started.wait(5)
    assert pipeline.running_sources() == ["stripe"]
    assert run_source(STRIPE, SlowClient()).status == "skipped"
    release.set()
    t.join(5)
    assert pipeline.running_sources() == []


def test_scheduler_jobs_are_not_paused():
    from apscheduler.schedulers.background import BackgroundScheduler

    sched = scheduler._new_scheduler(BackgroundScheduler)
    sources = [STRIPE, SourceConfig(name="b", type="lever", company="B", cron="0 6 * * *", options={"site": "b"})]
    sched.start(paused=True)
    try:
        scheduler._sync_jobs(sched, sources, client=None)
        jobs = {j.id: j for j in sched.get_jobs()}
        assert all(j.next_run_time is not None for j in jobs.values())  # None would mean paused
        # changing the schedule reschedules; removing a source removes its job
        sources[0] = SourceConfig(name="stripe", type="greenhouse", company="Stripe", interval_minutes=60,
                                  options={"board_token": "stripe"})
        scheduler._sync_jobs(sched, sources[:1], client=None)
        assert [j.id for j in sched.get_jobs()] == ["scrape:stripe"]
        assert "1:00:00" in str(sched.get_job("scrape:stripe").trigger)
    finally:
        sched.shutdown(wait=False)
