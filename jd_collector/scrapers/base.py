"""Scraper base class and registry."""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, ClassVar, Iterator, Protocol

import soupsieve

from jd_collector.config import SourceConfig
from jd_collector.models import RawJob


@dataclass(frozen=True)
class OptionField:
    """Describes one scraper option, so the UI can render a form and the API can validate it.

    kind: text | url | urls | number | bool | select | regex | selector
    """

    key: str
    label: str
    kind: str = "text"
    required: bool = False
    help: str = ""
    default: Any = None
    choices: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["choices"] = list(self.choices)
        return data

    def clean(self, value: Any) -> tuple[Any, str | None]:
        """Return (cleaned value or None when empty, error message)."""
        if isinstance(value, str):
            value = value.strip()
        if value in (None, "", []):
            return None, (f"{self.label} is required" if self.required else None)
        try:
            if self.kind == "number":
                num = float(value)
                if num < 0:
                    return None, f"{self.label} must be 0 or more"
                return (int(num) if num.is_integer() else num), None
            if self.kind == "bool":
                return (value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes", "on"}), None
            if self.kind == "select":
                return (value, None) if value in self.choices else (None, f"{self.label} must be one of {list(self.choices)}")
            if self.kind == "urls":
                items = value if isinstance(value, list) else re.split(r"[\s,]+", str(value))
                urls = [str(u).strip() for u in items if str(u).strip()]
                bad = [u for u in urls if not re.match(r"^https?://", u)]
                return (None, f"{self.label}: not a valid URL: {bad[0]}") if bad else (urls, None)
            if self.kind == "url":
                return (value, None) if re.match(r"^https?://", str(value)) else (None, f"{self.label} must start with http:// or https://")
            if self.kind == "regex":
                re.compile(str(value))
            if self.kind == "selector":
                soupsieve.compile(str(value))
        except (ValueError, TypeError, re.error, soupsieve.SelectorSyntaxError) as exc:
            return None, f"{self.label} is invalid: {exc}"
        return str(value), None


class HttpClient(Protocol):
    def get_json(self, url: str, params: dict[str, Any] | None = None, min_interval: float | None = None) -> Any: ...

    def get_text(self, url: str, params: dict[str, Any] | None = None, min_interval: float | None = None) -> str: ...

    def post_json(self, url: str, fields: dict[str, str], min_interval: float | None = None) -> Any: ...


class BaseScraper(ABC):
    """Subclasses implement ``fetch_jobs`` for one kind of job site.

    ``known_markers`` maps external_id -> stored source marker, so scrapers that need a
    request per job can skip unchanged postings (incremental scraping). Set
    ``self.complete = False`` when the listing was truncated (e.g. ``max_jobs``) so the
    pipeline does not mark the jobs it didn't see as closed.
    """

    type_name: ClassVar[str]
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    fields: ClassVar[tuple[OptionField, ...]] = ()
    # True when the whole listing arrives in one request, so a preview can scan all of it cheaply.
    single_request: ClassVar[bool] = False

    @classmethod
    def clean_options(cls, options: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        cleaned: dict[str, Any] = {}
        errors: list[str] = []
        for f in cls.fields:
            value, error = f.clean(options.get(f.key))
            if error:
                errors.append(error)
            elif value is not None:
                cleaned[f.key] = value
        return cleaned, errors

    @classmethod
    def describe(cls) -> dict[str, Any]:
        return {
            "type": cls.type_name,
            "label": cls.label or cls.type_name,
            "description": cls.description,
            "fields": [f.as_dict() for f in cls.fields],
        }

    def __init__(self, source: SourceConfig, client: HttpClient, known_markers: dict[str, str] | None = None):
        self.source = source
        self.client = client
        self.known_markers = known_markers or {}
        self.complete = True
        self.log = logging.getLogger(f"jd_collector.scrapers.{source.name}")

    @abstractmethod
    def fetch_jobs(self) -> Iterator[RawJob]:
        """Yield RawJob objects for every currently open posting."""

    # helpers ---------------------------------------------------------------

    def require_option(self, key: str) -> Any:
        value = self.source.option(key)
        if value in (None, "", []):
            raise ValueError(f"Source '{self.source.name}' ({self.type_name}) requires option '{key}'")
        return value

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        return self.client.get_json(url, params=params, min_interval=self.source.rate_limit_seconds)

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        return self.client.get_text(url, params=params, min_interval=self.source.rate_limit_seconds)

    def post_json(self, url: str, fields: dict[str, str]) -> Any:
        return self.client.post_json(url, fields, min_interval=self.source.rate_limit_seconds)

    def new_job(self, **fields: Any) -> RawJob:
        return RawJob(source=self.source.name, company=fields.pop("company", None) or self.source.company, **fields)


SCRAPERS: dict[str, type[BaseScraper]] = {}


def register(cls: type[BaseScraper]) -> type[BaseScraper]:
    SCRAPERS[cls.type_name] = cls
    return cls


def build_scraper(source: SourceConfig, client: HttpClient, known_markers: dict[str, str] | None = None) -> BaseScraper:
    try:
        cls = SCRAPERS[source.type]
    except KeyError:
        raise ValueError(f"Unknown source type '{source.type}'. Available: {sorted(SCRAPERS)}") from None
    return cls(source, client, known_markers)
