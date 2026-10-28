"""Data shapes: ``RawJob`` (what a scraper emits) and ``JobPosting`` (the unified schema)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

JOB_TYPES = ("Full-time", "Part-time", "Contract", "Internship", "Temporary")


@dataclass
class RawJob:
    """Source-specific job data before normalization.

    Scrapers fill in whatever they can find; the normalizer handles the rest.
    ``unchanged=True`` means the scraper determined (via ``marker``) that the job is
    already stored and up to date, so only its "last seen" timestamp is refreshed.
    """

    source: str
    company: str
    external_id: str | None = None
    title: str | None = None
    url: str | None = None
    apply_url: str | None = None
    location: str | None = None
    description_html: str | None = None
    description_text: str | None = None
    employment_type: str | None = None
    department: str | None = None
    posted_at: Any = None
    remote: bool | None = None
    salary: dict[str, Any] | None = None  # keys: min, max, currency, interval, text
    extra_skills: list[str] = field(default_factory=list)
    marker: str | None = None  # source-side "last updated" value for incremental scraping
    unchanged: bool = False
    raw: dict[str, Any] | None = None


class JobPosting(BaseModel):
    """The unified job description schema stored in the database."""

    job_id: str = Field(description="Stable hash of source + external id / URL")
    source: str
    external_id: str | None = None
    title: str
    company: str
    location: str | None = None
    is_remote: bool = False
    region: str | None = Field(default=None, description="Best-effort region derived from location; see regions.py")
    role_category: str | None = Field(default=None, description="Best-effort role family derived from title; see roles.py")
    experience_level: str | None = Field(default=None, description="Best-effort YOE bucket; see experience.py")
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    salary: str | None = Field(default=None, description="Human readable salary range")
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_interval: str | None = None  # year | month | week | day | hour
    job_type: str | None = None  # one of JOB_TYPES
    department: str | None = None
    posted_date: datetime | None = None
    apply_link: str
    source_marker: str | None = None
    raw: dict[str, Any] | None = None

    def content_hash(self) -> str:
        """Hash of the user-visible fields; used to detect real updates."""
        payload = self.model_dump(
            include={
                "title", "company", "location", "is_remote", "region", "role_category", "experience_level",
                "description", "skills", "salary", "job_type", "department", "apply_link",
            }
        )
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
