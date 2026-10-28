"""Configurable CSS-selector scraper for custom HTML career pages (no code needed).

Options
- list_url (required), item_selector (required), title_selector (required)
- link_selector:        selector inside an item for the job link (default "a"; the item itself if it is <a>)
- location_selector:    selector inside an item for the location
- next_page_selector:   selector for the "next page" link on listing pages
- description_selector: selector for the description on the job detail page
- fetch_details:        fetch detail pages (default true when description_selector is set)
- max_pages:            listing pages to walk (default 5)
- refetch_known:        re-download detail pages that are already stored (default false)

If a detail page carries JSON-LD JobPosting data, it is used to enrich the job.
"""

from __future__ import annotations

from typing import Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from jd_collector.models import RawJob
from jd_collector.scrapers.base import BaseScraper, OptionField, register
from jd_collector.scrapers.jsonld import extract_jsonld_jobs, jsonld_to_raw


def _text(node: Tag, selector: str | None) -> str | None:
    if not selector:
        return None
    found = node.select_one(selector)
    return found.get_text(" ", strip=True) if found else None


@register
class CssScraper(BaseScraper):
    type_name = "css"
    label = "Custom HTML (CSS selectors)"
    description = "Any HTML careers page, described with CSS selectors"
    fields = (
        OptionField("list_url", "Listing page URL", kind="url", required=True),
        OptionField("item_selector", "Job item selector", kind="selector", required=True,
                    help="Matches one element per job, e.g. div.job-card"),
        OptionField("title_selector", "Title selector", kind="selector", required=True, help="Inside an item, e.g. h3"),
        OptionField("link_selector", "Link selector", kind="selector", default="a", help="Inside an item"),
        OptionField("location_selector", "Location selector", kind="selector", help="Inside an item"),
        OptionField("posted_selector", "Posted date selector", kind="selector", help="Inside an item"),
        OptionField("next_page_selector", "Next page selector", kind="selector", help="e.g. a.next"),
        OptionField("description_selector", "Description selector", kind="selector",
                    help="On the job's own page, e.g. div.job-description"),
        OptionField("fetch_details", "Fetch job pages", kind="bool", default=True),
        OptionField("max_pages", "Max listing pages", kind="number", default=5),
        OptionField("refetch_known", "Re-download known jobs", kind="bool", default=False),
    )

    def fetch_jobs(self) -> Iterator[RawJob]:
        url: str | None = self.require_option("list_url")
        item_sel = self.require_option("item_selector")
        title_sel = self.require_option("title_selector")
        link_sel = self.source.option("link_selector", "a")
        desc_sel = self.source.option("description_selector")
        fetch_details = bool(self.source.option("fetch_details", bool(desc_sel)))
        refetch = bool(self.source.option("refetch_known", False))
        max_pages = int(self.source.option("max_pages", 5))

        pages = 0
        while url and pages < max_pages:
            soup = BeautifulSoup(self.get_text(url), "html.parser")
            pages += 1
            items = soup.select(item_sel)
            if not items and pages == 1:
                self.log.warning("No items matched '%s' on %s - has the page layout changed?", item_sel, url)
            for item in items:
                link_el = item if item.name == "a" else (item.select_one(link_sel) if link_sel else None)
                href = link_el.get("href") if link_el else None
                job_url = urljoin(url, href) if href else None
                if not job_url:
                    continue
                if not refetch and job_url in self.known_markers:
                    yield self.new_job(external_id=job_url, url=job_url, unchanged=True)
                    continue
                job = self.new_job(
                    external_id=job_url,
                    title=_text(item, title_sel),
                    url=job_url,
                    apply_url=job_url,
                    location=_text(item, self.source.option("location_selector")),
                    posted_at=_text(item, self.source.option("posted_selector")),
                    marker="listed",
                    raw={"listing_html": str(item)[:20000]},
                )
                if fetch_details:
                    self._enrich(job, desc_sel)
                yield job

            nxt = soup.select_one(self.source.option("next_page_selector")) if self.source.option("next_page_selector") else None
            next_url = urljoin(url, nxt["href"]) if nxt and nxt.get("href") else None
            url = next_url if next_url != url else None
        if url:
            self.complete = False

    def _enrich(self, job: RawJob, desc_sel: str | None) -> None:
        try:
            html = self.get_text(job.url)
        except Exception as exc:
            self.log.warning("Could not fetch detail page %s: %s", job.url, exc)
            return
        postings = extract_jsonld_jobs(html)
        if postings:
            ld = jsonld_to_raw(self, postings[0], job.url)
            for attr in ("location", "description_html", "employment_type", "posted_at", "remote", "salary", "department"):
                if getattr(job, attr) in (None, "") and getattr(ld, attr) not in (None, ""):
                    setattr(job, attr, getattr(ld, attr))
            job.extra_skills = ld.extra_skills
            job.title = job.title or ld.title
        if desc_sel:
            node = BeautifulSoup(html, "html.parser").select_one(desc_sel)
            if node:
                job.description_html = str(node)
