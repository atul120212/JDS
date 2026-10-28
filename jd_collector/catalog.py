"""A curated, pre-verified directory of company career pages, organized by region.

This is the "ready to use" list: every entry was checked against the company's real
career-page API (not guessed from its homepage) before being added, so picking one from
here and adding it works immediately. It ships in ``config/catalog.yaml``, separate from
``config/sources.yaml`` (the sources actually being scraped) - browsing the catalog never
scrapes anything by itself; an entry only starts being collected once it's added as a source.

Regions use the same vocabulary as the per-job ``region`` field in regions.py (so filtering
jobs by region and browsing the catalog by region line up), tagging each company by where it
is headquartered - not a guarantee that every one of its open roles is in that region.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from jd_collector.config import SourceConfig, get_settings
from jd_collector.regions import REGIONS

_COMMON_KEYS = {"name", "company", "type", "region", "industry"}


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    company: str
    type: str
    region: str
    industry: str
    options: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "company": self.company, "type": self.type,
                "region": self.region, "industry": self.industry, "options": dict(self.options)}

    def to_source(self, **overrides: Any) -> SourceConfig:
        """Build a ready-to-save SourceConfig from this entry."""
        fields: dict[str, Any] = {
            "name": self.name, "type": self.type, "company": self.company, "enabled": True,
            "interval_minutes": 360, "cron": None, "rate_limit_seconds": 1.0, "options": dict(self.options),
        }
        fields.update(overrides)
        return SourceConfig(**fields)


def _parse(data: dict[str, Any]) -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    seen: set[str] = set()
    for raw in data.get("entries") or []:
        missing = [k for k in ("name", "company", "type", "region", "industry") if not raw.get(k)]
        if missing:
            raise ValueError(f"Catalog entry {raw!r} is missing: {missing}")
        if raw["name"] in seen:
            raise ValueError(f"Duplicate catalog entry name: {raw['name']}")
        seen.add(raw["name"])
        entries.append(CatalogEntry(
            name=str(raw["name"]), company=str(raw["company"]), type=str(raw["type"]).lower(),
            region=str(raw["region"]), industry=str(raw["industry"]),
            options={k: v for k, v in raw.items() if k not in _COMMON_KEYS},
        ))
    return entries


def load_catalog(path: Path | None = None) -> list[CatalogEntry]:
    path = path or get_settings().catalog_file
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return _parse(data)


def catalog_by_name(path: Path | None = None) -> dict[str, CatalogEntry]:
    return {e.name: e for e in load_catalog(path)}


def filter_catalog(
    entries: list[CatalogEntry], region: str | None = None, industry: str | None = None,
    type_: str | None = None, q: str | None = None,
) -> list[CatalogEntry]:
    out = entries
    if region:
        out = [e for e in out if e.region == region]
    if industry:
        out = [e for e in out if e.industry.lower() == industry.lower()]
    if type_:
        out = [e for e in out if e.type == type_.lower()]
    if q:
        needle = q.strip().lower()
        out = [e for e in out if needle in e.company.lower() or needle in e.name.lower() or needle in e.industry.lower()]
    return out


__all__ = ["CatalogEntry", "load_catalog", "catalog_by_name", "filter_catalog", "REGIONS"]
