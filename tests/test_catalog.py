"""The real config/catalog.yaml: schema validity, and the API/CLI surface built on it."""

from collections import Counter

import pytest
from fastapi.testclient import TestClient

from jd_collector.catalog import REGIONS, catalog_by_name, filter_catalog, load_catalog
from jd_collector.scrapers import SCRAPERS


def test_real_catalog_loads_and_every_entry_validates():
    entries = load_catalog()
    assert len(entries) >= 100, "the shipped catalog should be a substantial, ready-to-use list"

    names = [e.name for e in entries]
    assert len(names) == len(set(names)), "catalog entry names must be unique"
    assert all(e.region in REGIONS for e in entries)
    assert all(e.type in SCRAPERS for e in entries)

    # Every entry's options must pass that scraper type's own validation (catches typos/missing fields).
    bad = []
    for e in entries:
        _, errors = SCRAPERS[e.type].clean_options(e.options)
        if errors:
            bad.append((e.name, errors))
    assert not bad, bad

    by_region = Counter(e.region for e in entries)
    # A "ready to use" directory organized by region should actually cover more than one region.
    assert len(by_region) >= 4


def test_catalog_entry_builds_a_valid_source():
    entries = catalog_by_name()
    stripe = next((e for e in entries.values() if e.options.get("board_token") == "stripe"), None)
    assert stripe is not None
    source = stripe.to_source()
    assert source.name == stripe.name and source.enabled is True and source.option("board_token") == "stripe"


def test_filter_catalog():
    entries = load_catalog()
    na = filter_catalog(entries, region="North America")
    assert na and all(e.region == "North America" for e in na)
    assert filter_catalog(entries, region="Nowhere") == []

    q = filter_catalog(entries, q="fintech")
    assert q and all("fintech" in e.industry.lower() or "fintech" in e.company.lower() for e in q)

    gh_only = filter_catalog(entries, type_="greenhouse")
    assert gh_only and all(e.type == "greenhouse" for e in gh_only)


# --------------------------------------------------------------------------- API


@pytest.fixture
def client(db, tmp_path, monkeypatch):
    sources = tmp_path / "sources.yaml"
    sources.write_text("sources: []\n", encoding="utf-8")
    monkeypatch.setenv("SOURCES_FILE", str(sources))
    # Use a tiny catalog for the API tests so they don't depend on the shipped list's contents.
    catalog = tmp_path / "catalog.yaml"
    catalog.write_text(
        "entries:\n"
        "  - name: stripe\n    company: Stripe\n    type: greenhouse\n"
        "    region: North America\n    industry: Fintech\n    board_token: stripe\n"
        "  - name: revolut\n    company: Revolut\n    type: greenhouse\n"
        "    region: Europe\n    industry: Fintech\n    board_token: revolut\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CATALOG_FILE", str(catalog))
    from jd_collector.config import get_settings

    get_settings.cache_clear()
    from jd_collector.api import create_app

    with TestClient(create_app()) as c:
        c.sources_path = sources
        yield c


def test_catalog_api_list_and_regions(client):
    rows = client.get("/catalog").json()
    assert {r["name"] for r in rows} == {"stripe", "revolut"}
    assert all(r["already_added"] is False for r in rows)

    na_only = client.get("/catalog", params={"region": "North America"}).json()
    assert [r["name"] for r in na_only] == ["stripe"]

    meta = client.get("/catalog/regions").json()
    assert meta["total"] == 2 and set(meta["regions"]) == {"North America", "Europe"}


def test_catalog_add_endpoint(client):
    r = client.post("/catalog/add", json={"names": ["stripe", "nope"]})
    assert r.status_code == 200
    body = r.json()
    assert body == {"added": ["stripe"], "skipped": [], "unknown": ["nope"]}

    # idempotent: adding again skips rather than erroring
    r2 = client.post("/catalog/add", json={"names": ["stripe", "revolut"]})
    assert r2.json() == {"added": ["revolut"], "skipped": ["stripe"], "unknown": []}

    rows = client.get("/catalog").json()
    assert {r["name"]: r["already_added"] for r in rows} == {"stripe": True, "revolut": True}

    sources = client.get("/sources").json()
    assert {s["name"] for s in sources} == {"stripe", "revolut"}
    assert next(s for s in sources if s["name"] == "stripe")["options"]["board_token"] == "stripe"
