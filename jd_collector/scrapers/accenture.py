"""Accenture's own career-site search (not a third-party ATS).

Found by inspecting network calls on accenture.com/<site>/careers/jobsearch: a single POST
endpoint returns full job data - including a clean description and an explicit years-of-
experience line - in one page per request, no separate detail fetch needed. Confirmed
allowed by accenture.com/robots.txt.
"""

from __future__ import annotations

from typing import Any, Iterator

from jd_collector.models import RawJob
from jd_collector.scrapers.base import BaseScraper, OptionField, register

API = "https://www.accenture.com/api/accenture/elastic/findjobs"
PAGE_SIZE = 100


@register
class AccentureScraper(BaseScraper):
    type_name = "accenture"
    label = "Accenture careers"
    description = "Accenture's own career site search (accenture.com/<site>/careers)"
    fields = (
        OptionField("job_country", "Country", required=True, default="India",
                    help="Exact country name as Accenture lists it, e.g. 'India', 'United States'"),
        OptionField("country_site", "Country site code", required=True, default="in-en",
                    help="The locale segment in Accenture job URLs, e.g. 'in-en', 'us-en', 'gb-en'"),
        OptionField("keyword", "Keyword filter", help="Optional: only jobs matching this keyword"),
        OptionField("max_jobs", "Max jobs per run", kind="number", default=500,
                    help="This site lists thousands of roles; keep this bounded"),
    )

    def fetch_jobs(self) -> Iterator[RawJob]:
        country = self.require_option("job_country")
        site = self.source.option("country_site", "in-en")
        keyword = self.source.option("keyword", "") or ""
        max_jobs = int(self.source.option("max_jobs", 500) or 0)

        start, count = 0, 0
        while True:
            data = self.post_json(API, {
                "startIndex": str(start), "maxResultSize": str(PAGE_SIZE), "jobKeyword": keyword,
                "jobCountry": country, "jobLanguage": "en", "countrySite": site,
                "sortBy": "2", "searchType": "vectorSearch", "jobFilters": "[]",
            })
            jobs = data.get("data") or []
            if not jobs:
                break
            for job in jobs:
                if max_jobs and count >= max_jobs:
                    self.complete = False
                    return
                count += 1
                yield self._to_raw(job, site)
            start += PAGE_SIZE
            if len(jobs) < PAGE_SIZE:
                break

    def _to_raw(self, job: dict[str, Any], site: str) -> RawJob:
        req_id = job.get("requisitionId") or job.get("guid")
        url = (job.get("jobDetailUrl") or "").replace("{0}", site) or None
        locations = job.get("location") or []
        location = "; ".join(locations) if locations else (job.get("feedCity") or job.get("country"))
        skills = [s for group in (job.get("skill"), job.get("function")) for s in (group or [])]
        # "Experience: 12-14 years" etc. is already stated plainly; let it also flow into the
        # description so skills/experience-level extraction can find it there too.
        description = job.get("jobDescriptionClean") or job.get("jobDescription") or ""
        if job.get("yearsOfExperience"):
            description = f"{job['yearsOfExperience']}\n\n{description}"
        return self.new_job(
            external_id=str(req_id) if req_id else None,
            title=job.get("title"),
            url=url,
            apply_url=url,
            location=location,
            description_text=description,
            employment_type=job.get("employeeType") or job.get("jobScheduleDescription"),
            department=job.get("careerLevel"),
            posted_at=job.get("updateDate"),
            remote=bool(job.get("remoteType")) or None,
            extra_skills=skills,
            marker=job.get("updateDate"),
            raw=job,
        )
