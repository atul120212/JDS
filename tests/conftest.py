from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Tests never touch the network or the real database.
os.environ["RESPECT_ROBOTS"] = "false"
os.environ["ALERT_WEBHOOK_URL"] = ""
os.environ["API_KEY"] = ""


def load_fixture(name: str) -> Any:
    text = (FIXTURES / name).read_text(encoding="utf-8")
    return json.loads(text) if name.endswith(".json") else text


class FakeClient:
    """Serves fixtures by URL. Routes are matched on the URL without query string."""

    def __init__(self, routes: dict[str, Any]):
        self.routes = dict(routes)
        self.calls: list[str] = []

    def _lookup(self, url: str, fields: dict | None = None) -> Any:
        self.calls.append(url)
        value = None
        found = False
        if url in self.routes:
            value, found = self.routes[url], True
        else:
            for prefix, v in self.routes.items():
                if prefix.endswith("*") and url.startswith(prefix[:-1]):
                    value, found = v, True
                    break
        if not found:
            raise KeyError(f"No fake route for {url}")
        # A route may be a callable(fields) -> response, for endpoints whose answer depends
        # on the POST body (e.g. pagination by startIndex) rather than just the URL.
        return value(fields or {}) if callable(value) else value

    def get_json(self, url, params=None, min_interval=None):
        return self._lookup(url)

    def get_text(self, url, params=None, min_interval=None):
        return self._lookup(url)

    def post_json(self, url, fields, min_interval=None):
        return self._lookup(url, fields)


@pytest.fixture
def fake_client():
    return FakeClient


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Fresh SQLite database per test."""
    from jd_collector import config, db as db_module

    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("DATABASE_URL", url)
    config.get_settings.cache_clear()
    db_module.init_engine(url)
    yield db_module
    if db_module._engine is not None:
        db_module._engine.dispose()
    config.get_settings.cache_clear()
