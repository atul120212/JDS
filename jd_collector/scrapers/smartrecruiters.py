"""SmartRecruiters public postings API - used by many enterprises.

The listing endpoint has no descriptions, so each posting needs a detail request.
Postings whose ``releasedDate`` matches what is already stored are skipped.
"""

from __future__ import annotations

from typing import Iterator

from jd_collector.models import RawJob
from jd_collector.scrapers.base import BaseScraper, OptionField, register

API = "https://api.smartrecruiters.com/v1/companies/{cid}/postings"
SECTIONS = ("companyDescription", "jobDescription", "qualifications", "additionalInformation")
PAGE_SIZE = 100


@register
class SmartRecruitersScraper(BaseScraper):
    type_name = "smartrecruiters"
    label = "SmartRecruiters"
    description = "Careers pages hosted on jobs.smartrecruiters.com (note: its robots.txt blocks most crawlers)"
    fields = (
        OptionField("company_id", "Company ID", required=True,
                    help="The part after jobs.smartrecruiters.com/ — e.g. 'BoschGroup'"),
        OptionField("max_jobs", "Max jobs per run", kind="number", default=200,
                    help="Each job needs its own request; 0 = no limit"),
    )

    def fetch_jobs(self) -> Iterator[RawJob]:
        cid = self.require_option("company_id")
        max_jobs = int(self.source.option("max_jobs", 0) or 0)
        base = API.format(cid=cid)
        offset, count = 0, 0
        while True:
            page = self.get_json(base, params={"limit": PAGE_SIZE, "offset": offset})
            items = page.get("content") or []
            for item in items:
                if max_jobs and count >= max_jobs:
                    self.complete = False
                    return
                count += 1
                ext_id = str(item.get("id"))
                marker = item.get("releasedDate")
                if marker and self.known_markers.get(ext_id) == marker:
                    yield self.new_job(external_id=ext_id, marker=marker, unchanged=True)
                    continue
                yield self._detail(base, cid, item)
            offset += len(items)
            if not items or offset >= int(page.get("totalFound") or 0):
                break

    def _detail(self, base: str, cid: str, item: dict) -> RawJob:
        ext_id = str(item.get("id"))
        detail = self.get_json(f"{base}/{ext_id}")
        sections = (detail.get("jobAd") or {}).get("sections") or {}
        description = "".join(
            f"<h3>{sec.get('title', '')}</h3>{sec.get('text', '')}"
            for key in SECTIONS
            if (sec := sections.get(key)) and sec.get("text")
        )
        loc = item.get("location") or {}
        location = loc.get("fullLocation") or ", ".join(
            filter(None, [loc.get("city"), loc.get("region"), (loc.get("country") or "").upper()])
        )
        url = detail.get("postingUrl") or f"https://jobs.smartrecruiters.com/{cid}/{ext_id}"
        return self.new_job(
            external_id=ext_id,
            title=item.get("name"),
            url=url,
            apply_url=detail.get("applyUrl") or url,
            location=location or None,
            description_html=description,
            employment_type=(item.get("typeOfEmployment") or {}).get("label"),
            department=(item.get("department") or {}).get("label") or (item.get("function") or {}).get("label"),
            posted_at=item.get("releasedDate"),
            remote=loc.get("remote"),
            marker=item.get("releasedDate"),
            raw={"listing": item, "detail": detail},
        )
