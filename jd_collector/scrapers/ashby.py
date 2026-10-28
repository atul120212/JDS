"""Ashby public job board API (api.ashbyhq.com) - popular with startups."""

from __future__ import annotations

from typing import Iterator

from jd_collector.models import RawJob
from jd_collector.scrapers.base import BaseScraper, OptionField, register

API = "https://api.ashbyhq.com/posting-api/job-board/{board}"


@register
class AshbyScraper(BaseScraper):
    type_name = "ashby"
    label = "Ashby"
    description = "Careers pages hosted on jobs.ashbyhq.com (common for startups)"
    single_request = True
    fields = (
        OptionField("board", "Board name", required=True, help="The part after jobs.ashbyhq.com/ — e.g. 'ramp'"),
    )

    def fetch_jobs(self) -> Iterator[RawJob]:
        board = self.require_option("board")
        data = self.get_json(API.format(board=board), params={"includeCompensation": "true"})
        for job in data.get("jobs") or []:
            if job.get("isListed") is False:
                continue
            locations = [job.get("location")] + [
                s.get("location") for s in job.get("secondaryLocations") or [] if isinstance(s, dict)
            ]
            yield self.new_job(
                external_id=job.get("id"),
                title=job.get("title"),
                url=job.get("jobUrl"),
                apply_url=job.get("applyUrl") or job.get("jobUrl"),
                location="; ".join(loc for loc in locations if loc) or None,
                description_html=job.get("descriptionHtml"),
                description_text=job.get("descriptionPlain"),
                employment_type=job.get("employmentType"),
                department=job.get("department") or job.get("team"),
                posted_at=job.get("publishedAt"),
                remote=job.get("isRemote"),
                salary=self._salary(job.get("compensation") or {}),
                raw=job,
            )

    @staticmethod
    def _salary(comp: dict) -> dict | None:
        for component in comp.get("summaryComponents") or []:
            if component.get("compensationType") == "Salary":
                return {
                    "min": component.get("minValue"),
                    "max": component.get("maxValue"),
                    "currency": component.get("currencyCode"),
                    "interval": component.get("interval"),
                    "text": comp.get("compensationTierSummary"),
                }
        summary = comp.get("compensationTierSummary") or comp.get("scrapeableCompensationSalarySummary")
        return {"text": summary} if summary else None
