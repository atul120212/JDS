"""Application settings (environment / .env) and source definitions (YAML)."""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DEFAULT_USER_AGENT = "JDCollectorBot/1.0 (+https://example.com/jd-collector)"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


def _resolve_db_url(url: str) -> str:
    """Make relative SQLite paths relative to the project directory."""
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith("sqlite:////") and ":memory:" not in url:
        path = Path(url[len(prefix):])
        if not path.is_absolute():
            return prefix + (BASE_DIR / path).as_posix()
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    sources_file: Path
    catalog_file: Path
    log_dir: Path
    log_level: str
    api_key: str | None
    alert_webhook_url: str | None
    user_agents: tuple[str, ...]
    proxies: tuple[str, ...]
    request_timeout: float
    max_retries: int
    default_rate_limit: float
    cache_ttl: int
    respect_robots: bool
    max_workers: int
    store_raw: bool
    min_description_length: int


@lru_cache
def get_settings() -> Settings:
    agents = [a.strip() for a in (_env("USER_AGENTS", DEFAULT_USER_AGENT) or "").split("||") if a.strip()]
    proxies = [p.strip() for p in (_env("PROXIES", "") or "").split(",") if p.strip()]
    is_vercel = bool(os.getenv("VERCEL"))
    default_db = "sqlite:////tmp/jd_collector.db" if is_vercel else "sqlite:///data/jd_collector.db"
    default_log = "/tmp/logs" if is_vercel else "logs"
    return Settings(
        database_url=_resolve_db_url(_env("DATABASE_URL", default_db)),
        sources_file=_resolve(_env("SOURCES_FILE", "config/sources.yaml")),
        catalog_file=_resolve(_env("CATALOG_FILE", "config/catalog.yaml")),
        log_dir=_resolve(_env("LOG_DIR", default_log)),
        log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        api_key=_env("API_KEY"),
        alert_webhook_url=_env("ALERT_WEBHOOK_URL"),
        user_agents=tuple(agents or [DEFAULT_USER_AGENT]),
        proxies=tuple(proxies),
        request_timeout=float(_env("REQUEST_TIMEOUT", "20")),
        max_retries=int(_env("MAX_RETRIES", "4")),
        default_rate_limit=float(_env("DEFAULT_RATE_LIMIT_SECONDS", "1.0")),
        cache_ttl=int(_env("CACHE_TTL_SECONDS", "300")),
        respect_robots=_env_bool("RESPECT_ROBOTS", True),
        max_workers=int(_env("MAX_WORKERS", "4")),
        store_raw=_env_bool("STORE_RAW", True),
        min_description_length=int(_env("MIN_DESCRIPTION_LENGTH", "30")),
    )


# --------------------------------------------------------------------------- sources

_COMMON_KEYS = {"name", "type", "company", "enabled", "interval_minutes", "cron", "rate_limit_seconds"}


@dataclass
class SourceConfig:
    """One scrape target. Scraper-specific keys end up in ``options``."""

    name: str
    type: str
    company: str
    enabled: bool = True
    interval_minutes: int = 360
    cron: str | None = None
    rate_limit_seconds: float = 1.0
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)


def parse_sources(data: dict[str, Any]) -> list[SourceConfig]:
    defaults = data.get("defaults") or {}
    sources: list[SourceConfig] = []
    seen: set[str] = set()
    for entry in data.get("sources") or []:
        merged = {**defaults, **entry}
        missing = [k for k in ("name", "type", "company") if not merged.get(k)]
        if missing:
            raise ValueError(f"Source {entry!r} is missing required keys: {missing}")
        if merged["name"] in seen:
            raise ValueError(f"Duplicate source name: {merged['name']}")
        seen.add(merged["name"])
        sources.append(
            SourceConfig(
                name=str(merged["name"]),
                type=str(merged["type"]).lower(),
                company=str(merged["company"]),
                enabled=bool(merged.get("enabled", True)),
                interval_minutes=int(merged.get("interval_minutes", 360)),
                cron=merged.get("cron"),
                rate_limit_seconds=float(merged.get("rate_limit_seconds", 1.0)),
                options={k: v for k, v in merged.items() if k not in _COMMON_KEYS},
            )
        )
    return sources


def load_sources(path: Path | None = None, include_disabled: bool = False) -> list[SourceConfig]:
    path = path or get_settings().sources_file
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    sources = parse_sources(data)
    return sources if include_disabled else [s for s in sources if s.enabled]


# --------------------------------------------------------------------------- editing sources.yaml

SOURCE_NAME_RX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_write_lock = threading.Lock()


def _round_trip_yaml():
    from ruamel.yaml import YAML  # comment-preserving YAML

    rt = YAML()
    rt.preserve_quotes = True
    rt.width = 4096
    rt.indent(mapping=2, sequence=4, offset=2)
    return rt


def source_entry(source: SourceConfig) -> dict[str, Any]:
    """The YAML mapping for a source (common keys first, then scraper options)."""
    entry: dict[str, Any] = {"name": source.name, "type": source.type, "company": source.company}
    if not source.enabled:
        entry["enabled"] = False
    if source.cron:
        entry["cron"] = source.cron
    else:
        entry["interval_minutes"] = source.interval_minutes
    entry["rate_limit_seconds"] = source.rate_limit_seconds
    entry.update(source.options)
    return entry


def save_source(source: SourceConfig, original_name: str | None = None, path: Path | None = None) -> None:
    """Add a source (``original_name`` None) or replace an existing one, keeping file comments."""
    from ruamel.yaml.comments import CommentedMap

    path = path or get_settings().sources_file
    rt = _round_trip_yaml()
    with _write_lock:
        with open(path, encoding="utf-8") as fh:
            doc = rt.load(fh) or CommentedMap()
        if doc.get("sources") is None:
            doc["sources"] = []
        seq = doc["sources"]
        names = [str(item.get("name")) for item in seq]
        target = original_name or source.name
        if source.name != target and source.name in names:
            raise ValueError(f"A source named '{source.name}' already exists")

        new_entry = CommentedMap(source_entry(source))
        if original_name is None:
            if source.name in names:
                raise ValueError(f"A source named '{source.name}' already exists")
            seq.append(new_entry)
        else:
            if target not in names:
                raise KeyError(target)
            seq[names.index(target)] = new_entry

        parse_sources(json.loads(json.dumps(doc)))  # validate the whole file before writing
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            rt.dump(doc, fh)
        os.replace(tmp, path)


def delete_source(name: str, path: Path | None = None) -> None:
    path = path or get_settings().sources_file
    rt = _round_trip_yaml()
    with _write_lock:
        with open(path, encoding="utf-8") as fh:
            doc = rt.load(fh)
        seq = (doc or {}).get("sources") or []
        names = [str(item.get("name")) for item in seq]
        if name not in names:
            raise KeyError(name)
        del seq[names.index(name)]
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            rt.dump(doc, fh)
        os.replace(tmp, path)
