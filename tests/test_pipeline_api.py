import copy

from conftest import load_fixture
from fastapi.testclient import TestClient

from jd_collector import repository as repo
from jd_collector.config import SourceConfig, get_settings, parse_sources
from jd_collector.pipeline import run_source

GH_URL = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"
SOURCE = SourceConfig(name="stripe", type="greenhouse", company="Stripe", options={"board_token": "stripe"})


def test_pipeline_incremental_and_deactivation(db, fake_client):
    data = load_fixture("greenhouse.json")

    first = run_source(SOURCE, fake_client({GH_URL: data}))
    assert (first.status, first.fetched, first.new, first.invalid) == ("success", 3, 2, 1)

    second = run_source(SOURCE, fake_client({GH_URL: data}))
    assert (second.new, second.updated, second.unchanged, second.deactivated) == (0, 0, 2, 0)

    changed = copy.deepcopy(data)
    changed["jobs"][0]["title"] = "Staff Backend Engineer, Payments"
    del changed["jobs"][1]  # the internship closed
    third = run_source(SOURCE, fake_client({GH_URL: changed}))
    assert (third.updated, third.deactivated) == (1, 1)

    with db.session_scope() as s:
        rows, total = repo.search_jobs(s, repo.JobFilters())
        assert total == 1 and rows[0].title.startswith("Staff")
        _, all_total = repo.search_jobs(s, repo.JobFilters(active_only=False))
        assert all_total == 2
        runs = repo.recent_runs(s, "stripe")
        assert len(runs) == 3 and all(r.status == "success" for r in runs)


def test_pipeline_records_failures(db, fake_client):
    result = run_source(SOURCE, fake_client({}))  # no route -> scraper raises
    assert result.status == "failed" and "KeyError" in result.error
    with db.session_scope() as s:
        assert repo.recent_runs(s)[0].status == "failed"


def test_parse_sources_validation():
    sources = parse_sources({"defaults": {"interval_minutes": 60},
                             "sources": [{"name": "a", "type": "Lever", "company": "A", "site": "a"}]})
    assert sources[0].type == "lever" and sources[0].interval_minutes == 60 and sources[0].option("site") == "a"
    for bad in ({"sources": [{"name": "a", "type": "lever"}]},
                {"sources": [{"name": "a", "type": "x", "company": "A"}] * 2}):
        try:
            parse_sources(bad)
            raise AssertionError("expected ValueError")
        except ValueError:
            pass


def _client():
    from jd_collector.api import create_app

    return TestClient(create_app())


def test_api_search_and_detail(db, fake_client):
    run_source(SOURCE, fake_client({GH_URL: load_fixture("greenhouse.json")}))
    client = _client()

    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/").status_code == 200

    page = client.get("/jobs").json()
    assert page["total"] == 2 and page["pages"] == 1

    assert client.get("/jobs", params={"skill": ["kafka", "AWS"]}).json()["total"] == 1
    assert client.get("/jobs", params={"remote": True}).json()["items"][0]["job_type"] == "Internship"
    assert client.get("/jobs", params={"q": "payments backbone"}).json()["total"] == 1
    assert client.get("/jobs", params={"min_salary": 200000}).json()["total"] == 1
    assert client.get("/jobs", params={"location": "san francisco"}).json()["total"] == 1
    assert client.get("/jobs", params={"q": "100%_"}).json()["total"] == 0  # LIKE wildcards escaped
    paged = client.get("/jobs", params={"page_size": 1, "page": 2, "sort": "title"}).json()
    assert len(paged["items"]) == 1 and paged["pages"] == 2

    job_id = page["items"][0]["job_id"]
    detail = client.get(f"/jobs/{job_id}").json()
    assert detail["description"] and detail["job_id"] == job_id
    assert client.get("/jobs/does-not-exist").status_code == 404

    assert client.get("/companies").json() == [{"name": "Stripe", "count": 2}]
    assert any(s["name"] == "Python" for s in client.get("/skills").json())
    assert client.get("/stats").json()["active_jobs"] == 2
    assert client.get("/runs").json()[0]["new"] == 2


def test_api_region_and_role_filters(db, fake_client):
    run_source(SOURCE, fake_client({GH_URL: load_fixture("greenhouse.json")}))
    client = _client()

    page = client.get("/jobs").json()
    by_title = {j["title"]: j for j in page["items"]}
    assert by_title["Senior Backend Engineer, Payments"]["region"] == "North America"
    assert by_title["Senior Backend Engineer, Payments"]["role_category"] == "Engineering"
    assert by_title["Software Engineering Intern"]["region"] == "North America"  # "Remote - US" -> US wins
    assert by_title["Senior Backend Engineer, Payments"]["experience_level"] == "5-8 yrs"  # "5+ years" in the body
    assert by_title["Software Engineering Intern"]["experience_level"] == "Fresher / 0-1 yr"

    assert client.get("/jobs", params={"region": "North America"}).json()["total"] == 2
    assert client.get("/jobs", params={"region": "Europe"}).json()["total"] == 0
    assert client.get("/jobs", params={"role_category": "Engineering"}).json()["total"] == 2
    assert client.get("/jobs", params={"experience_level": "Fresher / 0-1 yr"}).json()["total"] == 1

    facets = client.get("/facets").json()
    assert {"name": "North America", "count": 2} in facets["regions"]
    assert {"name": "Engineering", "count": 2} in facets["role_categories"]
    assert facets["experience_levels"] == [{"name": "Fresher / 0-1 yr", "count": 1}, {"name": "5-8 yrs", "count": 1}]

    stats = client.get("/stats").json()
    assert stats["by_region"]["North America"] == 2


def test_reclassify_all_recomputes_without_rescraping(db, fake_client):
    run_source(SOURCE, fake_client({GH_URL: load_fixture("greenhouse.json")}))

    with db.session_scope() as s:
        # Simulate a database saved before region/role_category existed: blank them out directly.
        rows, total = repo.search_jobs(s, repo.JobFilters())
        assert total == 2
        for row in rows:
            row.region = None
            row.role_category = None
            row.experience_level = None

    with db.session_scope() as s:
        n = repo.reclassify_all(s)
        assert n == 2
        rows, _ = repo.search_jobs(s, repo.JobFilters())
        assert all(r.region is not None for r in rows)
        assert {r.role_category for r in rows} == {"Engineering"}
        assert {r.experience_level for r in rows} == {"5-8 yrs", "Fresher / 0-1 yr"}

    # Reclassifying must keep content_hash consistent: scraping the same data again afterwards
    # must not report these jobs as "updated" just because local reclassification touched them.
    second = run_source(SOURCE, fake_client({GH_URL: load_fixture("greenhouse.json")}))
    assert (second.new, second.updated, second.unchanged) == (0, 0, 2)


def _big_greenhouse_payload(n: int, start_id: int) -> dict:
    """A synthetic Greenhouse response with `n` distinct, valid postings."""
    return {"jobs": [
        {
            "id": start_id + i,
            "title": f"Engineer {start_id + i}",
            "updated_at": "2026-09-30T10:15:00-04:00",
            "absolute_url": f"https://example.com/jobs/{start_id + i}",
            "location": {"name": "Remote"},
            "metadata": [],
            # Mentions real skills so upsert_job's JobSkill child-row relationship is actually
            # exercised (a multi-table flush is what the regression below is really about).
            "content": f"Job description number {i}. Requires Python, AWS and Kubernetes experience.",
        }
        for i in range(n)
    ]}


def test_concurrent_sources_write_to_sqlite_without_locking_errors(db, fake_client):
    """Several sources, each with enough jobs to involve many writes (including the JobSkill
    child-table relationship), scraped in parallel (run_sources' real ThreadPoolExecutor - not
    run_source called directly) against one real SQLite file.

    Regression test for a real, reproducible deadlock this project hit: releasing the
    cross-thread write lock while a flushed-but-uncommitted transaction was still open on that
    thread's connection let another thread's write block on SQLite's own writer lock, which the
    first thread could then never get the Python lock back to release (found via thread-stack
    dumps; see the comment on `_write_lock` in pipeline.py for the full mechanism). A single
    source, or two sources with few enough jobs to never overlap, would not have caught this.
    """
    from jd_collector.pipeline import run_sources

    n = 80
    names = [f"concurrent-{i}" for i in range(4)]
    routes = {
        f"https://boards-api.greenhouse.io/v1/boards/{name}/jobs": _big_greenhouse_payload(n, i * 100_000)
        for i, name in enumerate(names)
    }
    sources = [SourceConfig(name=name, type="greenhouse", company=name, options={"board_token": name})
              for name in names]

    results = run_sources(sources, max_workers=4, client=fake_client(routes))

    assert len(results) == len(names)
    for r in results:
        assert r.status == "success", r.error
        assert r.new == n
    with db.session_scope() as s:
        _, total = repo.search_jobs(s, repo.JobFilters())
        assert total == n * len(names)


def test_api_key_required_when_configured(db, monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    get_settings.cache_clear()
    client = _client()
    assert client.get("/jobs").status_code == 401
    assert client.get("/jobs", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/jobs", headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/health").status_code == 200
