"""PoliteHttpClient: the POST path added for scrapers like Accenture, and that GET still works
the same way afterwards. Network calls are mocked - no real HTTP involved.
"""
from unittest.mock import MagicMock, patch

import pytest

from jd_collector.config import get_settings
from jd_collector.http_client import FetchError, PoliteHttpClient, RobotsDisallowed


def _settings(**overrides):
    base = get_settings()
    return base.__class__(**{**base.__dict__, "respect_robots": False, "default_rate_limit": 0,
                             "max_retries": 2, **overrides})


def _resp(status=200, json_body=None, text_body=""):
    r = MagicMock()
    r.status_code = status
    r.headers = {}
    r.json.return_value = json_body
    r.text = text_body
    return r


@pytest.fixture
def client():
    return PoliteHttpClient(_settings())


def test_post_json_sends_multipart_fields(client):
    ok = _resp(json_body={"data": []})
    with patch.object(client.session, "post", return_value=ok) as post:
        result = client.post_json("https://example.com/api/search", {"startIndex": "0", "jobCountry": "India"})
    assert result == {"data": []}
    _, kwargs = post.call_args
    assert kwargs["files"] == {"startIndex": (None, "0"), "jobCountry": (None, "India")}


def test_post_json_is_not_cached(client):
    ok = _resp(json_body={"data": [1]})
    with patch.object(client.session, "post", return_value=ok) as post:
        client.post_json("https://example.com/api/search", {"startIndex": "0"})
        client.post_json("https://example.com/api/search", {"startIndex": "0"})
    assert post.call_count == 2  # same URL+body, but POST results are never cached


def test_post_json_retries_on_server_error_then_succeeds(client):
    fail = _resp(status=500)
    ok = _resp(json_body={"data": [1]})
    with patch.object(client.session, "post", side_effect=[fail, ok]), patch("time.sleep"):
        result = client.post_json("https://example.com/api/search", {"a": "b"})
    assert result == {"data": [1]}


def test_post_json_gives_up_after_max_retries(client):
    fail = _resp(status=503)
    with patch.object(client.session, "post", return_value=fail), patch("time.sleep"):
        with pytest.raises(FetchError):
            client.post_json("https://example.com/api/search", {"a": "b"})


def test_get_json_unaffected_by_post_support(client):
    ok = _resp(json_body={"jobs": []})
    with patch.object(client.session, "get", return_value=ok) as get:
        result = client.get_json("https://example.com/jobs")
    assert result == {"jobs": []}
    get.assert_called_once()


def test_robots_txt_blocks_post_too():
    c = PoliteHttpClient(_settings(respect_robots=True))
    with patch.object(c, "allowed_by_robots", return_value=False):
        with pytest.raises(RobotsDisallowed):
            c.post_json("https://example.com/api/search", {"a": "b"})
