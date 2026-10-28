"""A polite, resilient HTTP client shared by all scrapers.

Features
- robots.txt checks (cached per host)
- per-host rate limiting (minimum interval between requests, thread safe)
- retries with exponential backoff + jitter, honouring ``Retry-After``
- short-lived response cache
- user-agent and proxy rotation
"""

from __future__ import annotations

import itertools
import logging
import random
import threading
import time
from collections import defaultdict
from typing import Any
from urllib import robotparser
from urllib.parse import urlencode, urlsplit

import requests

from jd_collector.config import Settings, get_settings

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
ROBOTS_AGENT = "JDCollectorBot"


class FetchError(Exception):
    """Raised when a URL cannot be fetched (after retries)."""


class RobotsDisallowed(FetchError):
    """Raised when robots.txt forbids fetching a URL."""


class PoliteHttpClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._local = threading.local()
        self._ua_cycle = itertools.cycle(self.settings.user_agents)
        self._proxy_cycle = itertools.cycle(self.settings.proxies) if self.settings.proxies else None
        self._rotation_lock = threading.Lock()

        self._host_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._host_last: dict[str, float] = {}
        self._robots: dict[str, robotparser.RobotFileParser | None] = {}
        self._robots_lock = threading.Lock()

        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------ public API

    def get_json(self, url: str, params: dict[str, Any] | None = None, min_interval: float | None = None) -> Any:
        return self._request("GET", url, params, None, min_interval, as_json=True)

    def get_text(self, url: str, params: dict[str, Any] | None = None, min_interval: float | None = None) -> str:
        return self._request("GET", url, params, None, min_interval, as_json=False)

    def post_json(self, url: str, fields: dict[str, str], min_interval: float | None = None) -> Any:
        """POST ``fields`` as multipart/form-data and parse the JSON response.

        For scrapers whose source has no GET-able listing endpoint (e.g. a search API that
        only accepts POST). Not cached - search results page through different bodies, so a
        URL-only cache key would be meaningless here.
        """
        return self._request("POST", url, None, fields, min_interval, as_json=True, cacheable=False)

    # ------------------------------------------------------------------ internals

    @property
    def session(self) -> requests.Session:
        # requests.Session is not guaranteed thread safe -> one per thread.
        if not hasattr(self._local, "session"):
            self._local.session = requests.Session()
        return self._local.session

    def _next_identity(self) -> tuple[str, dict[str, str] | None]:
        with self._rotation_lock:
            ua = next(self._ua_cycle)
            proxy = next(self._proxy_cycle) if self._proxy_cycle else None
        return ua, ({"http": proxy, "https": proxy} if proxy else None)

    def _request(
        self, method: str, url: str, params: dict[str, Any] | None, fields: dict[str, str] | None,
        min_interval: float | None, as_json: bool, cacheable: bool = True,
    ) -> Any:
        full_url = f"{url}?{urlencode(params)}" if params else url
        cache_key = f"{'json' if as_json else 'text'}:{full_url}" if cacheable else None
        if cache_key:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        if self.settings.respect_robots and not self.allowed_by_robots(full_url):
            raise RobotsDisallowed(f"robots.txt disallows {full_url}")

        interval = self.settings.default_rate_limit if min_interval is None else min_interval
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            self._wait_for_slot(full_url, interval)
            ua, proxies = self._next_identity()
            headers = {
                "User-Agent": ua,
                "Accept": "application/json" if as_json else "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
            }
            try:
                if method == "POST":
                    # Sent as multipart/form-data (via `files=`, each value wrapped with no
                    # filename) rather than x-www-form-urlencoded - that's what the search
                    # APIs this is built for expect.
                    resp = self.session.post(
                        full_url, headers=headers, proxies=proxies, timeout=self.settings.request_timeout,
                        files={k: (None, v) for k, v in (fields or {}).items()},
                    )
                else:
                    resp = self.session.get(
                        full_url, headers=headers, proxies=proxies, timeout=self.settings.request_timeout
                    )
            except requests.RequestException as exc:
                last_error = exc
                log.warning("%s %s failed (attempt %d): %s", method, full_url, attempt + 1, exc)
                self._backoff(attempt)
                continue

            if resp.status_code in RETRY_STATUSES:
                last_error = FetchError(f"HTTP {resp.status_code} for {full_url}")
                log.warning("%s %s -> %d (attempt %d)", method, full_url, resp.status_code, attempt + 1)
                self._backoff(attempt, resp.headers.get("Retry-After"))
                continue
            if resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code} for {full_url}")

            try:
                result = resp.json() if as_json else resp.text
            except ValueError as exc:
                raise FetchError(f"Invalid JSON from {full_url}: {exc}") from exc

            if not as_json and not result.strip():
                # A "200 OK" with a completely empty body is never useful content for a
                # scraper, and in practice is sometimes a one-off artifact of reusing a kept-
                # alive connection right after a different request on it (e.g. the robots.txt
                # check just before) rather than a real empty page. Worth one retry on a fresh
                # connection before giving up.
                last_error = FetchError(f"Empty response body for {full_url}")
                log.warning("%s %s -> 200 with an empty body (attempt %d)", method, full_url, attempt + 1)
                self._backoff(attempt)
                continue

            if cache_key:
                self._cache_put(cache_key, result)
            return result

        raise FetchError(f"Giving up on {method} {full_url} after {self.settings.max_retries + 1} attempts: {last_error}")

    def _backoff(self, attempt: int, retry_after: str | None = None) -> None:
        if attempt >= self.settings.max_retries:
            return
        delay = min(60.0, 2 ** attempt) + random.uniform(0, 0.5)
        if retry_after:
            try:
                delay = max(delay, min(120.0, float(retry_after)))
            except ValueError:
                pass
        time.sleep(delay)

    def _wait_for_slot(self, url: str, interval: float) -> None:
        if interval <= 0:
            return
        host = urlsplit(url).netloc
        with self._host_locks[host]:
            last = self._host_last.get(host)
            if last is not None:
                wait = interval - (time.monotonic() - last)
                if wait > 0:
                    time.sleep(wait)
            self._host_last[host] = time.monotonic()

    def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        with self._robots_lock:
            if base not in self._robots:
                self._robots[base] = self._load_robots(base)
            parser = self._robots[base]
        return True if parser is None else parser.can_fetch(ROBOTS_AGENT, url)

    def _load_robots(self, base: str) -> robotparser.RobotFileParser | None:
        try:
            resp = self.session.get(
                f"{base}/robots.txt",
                headers={"User-Agent": self.settings.user_agents[0]},
                timeout=self.settings.request_timeout,
            )
        except requests.RequestException as exc:
            log.info("Could not load robots.txt for %s (%s); assuming allowed", base, exc)
            return None
        if resp.status_code >= 400:
            return None  # no robots.txt -> everything allowed
        parser = robotparser.RobotFileParser()
        parser.parse(resp.text.splitlines())
        return parser

    def _cache_get(self, key: str) -> Any:
        if self.settings.cache_ttl <= 0:
            return None
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry and entry[0] > time.monotonic():
                return entry[1]
            self._cache.pop(key, None)
        return None

    def _cache_put(self, key: str, value: Any) -> None:
        if self.settings.cache_ttl <= 0:
            return
        with self._cache_lock:
            if len(self._cache) > 2000:  # keep memory bounded
                self._cache.clear()
            self._cache[key] = (time.monotonic() + self.settings.cache_ttl, value)
