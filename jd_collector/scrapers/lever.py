"""Lever postings API (api.lever.co)."""

from __future__ import annotations

from typing import Iterator

from jd_collector.models import RawJob
from jd_collector.scrapers.base import BaseScraper, OptionField, register

HOSTS = {"us": "https://api.lever.co", "eu": "https://api.eu.lever.co"}


@register
class LeverScraper(BaseScraper):
    type_name = "lever"
    label = "Lever"
    description = "Careers pages hosted on jobs.lever.co"
    single_request = True
    fields = (
        OptionField("site", "Site name", required=True, help="The part after jobs.lever.co/ — e.g. 'palantir'"),
        OptionField("region", "Region", kind="select", default="us", choices=("us", "eu"),
                    help="Use 'eu' for jobs.eu.lever.co"),
    )

    def fetch_jobs(self) -> Iterator[RawJob]:
        site = self.require_option("site")
        host = HOSTS.get(str(self.source.option("region", "us")).lower(), HOSTS["us"])
        postings = self.get_json(f"{host}/v0/postings/{site}", params={"mode": "json"})
        for p in postings or []:
            cats = p.get("categories") or {}
            parts = [p.get("description") or ""]
            for section in p.get("lists") or []:
                parts.append(f"<h3>{section.get('text', '')}</h3><ul>{section.get('content', '')}</ul>")
            parts.append(p.get("additional") or "")

            salary = None
            rng = p.get("salaryRange")
            if rng and (rng.get("min") or rng.get("max")):
                salary = {
                    "min": rng.get("min"),
                    "max": rng.get("max"),
                    "currency": rng.get("currency"),
                    "interval": rng.get("interval"),
                }

            workplace = (p.get("workplaceType") or "").lower()
            location = cats.get("location") or ", ".join(cats.get("allLocations") or []) or None
            yield self.new_job(
                external_id=p.get("id"),
                title=p.get("text"),
                url=p.get("hostedUrl"),
                apply_url=p.get("applyUrl") or p.get("hostedUrl"),
                location=location,
                description_html="\n".join(parts),
                employment_type=cats.get("commitment"),
                department=cats.get("team") or cats.get("department"),
                posted_at=p.get("createdAt"),
                remote=True if workplace == "remote" else (False if workplace in {"onsite", "on-site"} else None),
                salary=salary,
                raw=p,
            )
