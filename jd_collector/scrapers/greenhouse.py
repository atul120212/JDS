"""Greenhouse job boards (boards-api.greenhouse.io) - used by many large companies."""

from __future__ import annotations

import html
from typing import Iterator

from jd_collector.models import RawJob
from jd_collector.scrapers.base import BaseScraper, OptionField, register

API = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


@register
class GreenhouseScraper(BaseScraper):
    type_name = "greenhouse"
    label = "Greenhouse"
    description = "Careers pages hosted on boards.greenhouse.io / job-boards.greenhouse.io"
    single_request = True
    fields = (
        OptionField("board_token", "Board token", required=True,
                    help="The part after boards.greenhouse.io/ — e.g. 'stripe'"),
    )

    def fetch_jobs(self) -> Iterator[RawJob]:
        token = self.require_option("board_token")
        data = self.get_json(API.format(token=token), params={"content": "true"})
        for job in data.get("jobs") or []:
            departments = [d.get("name") for d in job.get("departments") or [] if d.get("name")]
            yield self.new_job(
                external_id=str(job.get("id")),
                title=job.get("title"),
                url=job.get("absolute_url"),
                apply_url=job.get("absolute_url"),
                location=(job.get("location") or {}).get("name"),
                # Greenhouse returns the HTML content entity-escaped.
                description_html=html.unescape(job.get("content") or ""),
                employment_type=self._metadata(job, "employment type", "employment_type", "job type"),
                department=", ".join(departments) or None,
                posted_at=job.get("first_published") or job.get("updated_at"),
                marker=job.get("updated_at"),
                raw=job,
            )

    @staticmethod
    def _metadata(job: dict, *names: str) -> str | None:
        for item in job.get("metadata") or []:
            if str(item.get("name", "")).strip().lower() in names and item.get("value"):
                value = item["value"]
                return ", ".join(map(str, value)) if isinstance(value, list) else str(value)
        return None
