"""Generic scraper for any career site that publishes schema.org ``JobPosting`` data, or a
sitemap of its job pages.

Most career sites embed this for Google for Jobs, so this one scraper covers many company
sites without custom parsing code - including the (less common, but not rare) ones that use
inline HTML microdata (``itemprop``) instead of a JSON-LD ``<script>`` block.

It also understands ``sitemap.xml`` / ``sitemap_index.xml``: when a given URL turns out to be
one (detected by its own content, not its extension), its ``<loc>`` entries become the pages
to check, instead of `<a href>` links on an HTML listing page - useful for sites whose listing
page is client-rendered (so it has no job links in its raw HTML) but that still publish a
sitemap of individual job pages for search engines, which usually *are* plain server-rendered
HTML. A sitemap index (a sitemap of sitemaps) is one level further: its entries are treated as
more sitemaps, not job pages.

Options
- start_urls:    listing pages, sitemaps, or job pages to begin with (required)
- link_pattern:  regex; links (or sitemap entries) matching it are followed as job pages
- max_pages:     upper bound on pages fetched per run (default 50)
- refetch_known: re-download job pages that are already stored (default false)
"""

from __future__ import annotations

import html as html_lib
import json
import re
from collections import deque
from typing import Any, Iterator
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from bs4.element import Tag

from jd_collector.models import RawJob
from jd_collector.scrapers.base import BaseScraper, OptionField, register

_SITEMAP_LOC_RX = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.I)


def _sitemap_kind(text: str) -> str | None:
    """'index' (a sitemap of sitemaps), 'urlset' (a sitemap of pages), or None (not a sitemap)."""
    head = text[:800].lower()
    if "<sitemapindex" in head:
        return "index"
    if "<urlset" in head:
        return "urlset"
    return None


def _sitemap_locs(text: str) -> list[str]:
    return [html_lib.unescape(m) for m in _SITEMAP_LOC_RX.findall(text)]


def extract_jsonld_jobs(html: str) -> list[dict[str, Any]]:
    """Return every JobPosting object found in the page's JSON-LD blocks."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, dict):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if "JobPosting" in kinds:
                found.append(node)
            for key in ("@graph", "itemListElement", "item"):
                if key in node:
                    walk(node[key])

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        text = script.string or script.get_text()
        if not text or not text.strip():
            continue
        try:
            walk(json.loads(text, strict=False))
        except json.JSONDecodeError:
            continue
    return found


def _microdata_object(scope: Tag) -> dict[str, Any]:
    """Read one schema.org microdata item (an ``itemscope`` element) into a plain dict, using
    the same property names JSON-LD would - so it feeds the same mapping code either way.
    """
    data: dict[str, Any] = {}
    for el in scope.find_all(attrs={"itemprop": True}):
        # Only properties owned by `scope` itself: walk up from `el` and stop at the first
        # itemscope found. If that isn't `scope`, `el` belongs to a nested object instead,
        # and is picked up when that nested itemscope is visited as `el`'s own value below.
        owner = el.parent
        while owner is not None and owner is not scope and not owner.has_attr("itemscope"):
            owner = owner.parent
        if owner is not scope:
            continue

        name = el.get("itemprop")
        if el.has_attr("itemscope"):
            value: Any = _microdata_object(el)
        elif el.name == "meta":
            value = el.get("content")
        elif el.name in ("a", "link"):
            value = el.get("href")
        elif el.name == "time":
            value = el.get("datetime") or el.get_text(strip=True)
        else:
            value = el.get("content") or el.get_text(" ", strip=True)

        if name in data:
            if not isinstance(data[name], list):
                data[name] = [data[name]]
            data[name].append(value)
        else:
            data[name] = value
    return data


def extract_microdata_jobs(html: str) -> list[dict[str, Any]]:
    """Return every JobPosting found as schema.org HTML microdata (``itemscope``/``itemprop``),
    normalized into the same shape ``extract_jsonld_jobs`` returns.
    """
    soup = BeautifulSoup(html, "html.parser")
    found = []
    for scope in soup.find_all(attrs={"itemscope": True}):
        itemtype = (scope.get("itemtype") or "").rstrip("/")
        if itemtype.rsplit("/", 1)[-1] == "JobPosting":
            found.append(_microdata_object(scope))
    return found


def extract_structured_jobs(html: str) -> list[dict[str, Any]]:
    """JSON-LD first (the common case); HTML microdata only if a page has no JSON-LD at all."""
    return extract_jsonld_jobs(html) or extract_microdata_jobs(html)


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _longest_text(value: Any) -> str | None:
    """schema.org defines ``title``/``description`` as single Text values, but some templates
    mark up the same itemprop name twice on a page (e.g. once for real job content, once for
    a reused company blurb elsewhere on the page) - found scraping real SAP SuccessFactors
    sites. When that happens, ``_microdata_object`` faithfully reports what's on the page: a
    list. The richest (longest) candidate is reliably the real content; a boilerplate snippet
    reused on every page is short and identical everywhere.
    """
    if isinstance(value, list):
        candidates = [v for v in value if isinstance(v, str)]
        return max(candidates, key=len) if candidates else None
    return value if isinstance(value, str) else None


def _name(value: Any) -> str | None:
    value = _first(value)
    if isinstance(value, dict):
        return value.get("name")
    return str(value) if value else None


def _location(posting: dict[str, Any]) -> str | None:
    locations = posting.get("jobLocation")
    locations = locations if isinstance(locations, list) else [locations]
    out = []
    for loc in locations:
        if not loc:
            continue
        if isinstance(loc, str):
            out.append(loc)
            continue
        addr = loc.get("address") or {}
        if isinstance(addr, str):
            out.append(addr)
            continue
        parts = [addr.get("addressLocality"), addr.get("addressRegion"), _name(addr.get("addressCountry"))]
        text = ", ".join(p for p in parts if p)
        if text:
            out.append(text)
    req = posting.get("applicantLocationRequirements")
    if not out and req:
        out.append(_name(req) or "")
    return "; ".join(dict.fromkeys(o for o in out if o)) or None


def _salary(posting: dict[str, Any]) -> dict[str, Any] | None:
    base = _first(posting.get("baseSalary") or posting.get("estimatedSalary"))
    if not isinstance(base, dict):
        return None
    value = base.get("value")
    if isinstance(value, dict):
        lo = value.get("minValue", value.get("value"))
        hi = value.get("maxValue", value.get("value"))
        unit = value.get("unitText")
    else:
        lo = hi = value
        unit = base.get("unitText")
    if lo is None and hi is None:
        return None
    return {"min": lo, "max": hi, "currency": base.get("currency"), "interval": unit}


def jsonld_to_raw(scraper: BaseScraper, posting: dict[str, Any], page_url: str, index: int = 0) -> RawJob:
    identifier = posting.get("identifier")
    ident_value = identifier.get("value") if isinstance(identifier, dict) else identifier
    raw_url = _first(posting.get("url"))
    url = urljoin(page_url, raw_url) if raw_url else page_url
    employment = posting.get("employmentType")
    skills = posting.get("skills") or []
    if isinstance(skills, str):
        skills = [s.strip() for s in re.split(r"[,;\n]", skills)]
    posted_at = _first(posting.get("datePosted"))
    return scraper.new_job(
        external_id=url if raw_url or index == 0 else str(ident_value or f"{page_url}#{index}"),
        company=_name(posting.get("hiringOrganization")),
        title=_longest_text(posting.get("title")),
        url=url,
        apply_url=url,
        location=_location(posting),
        description_html=_longest_text(posting.get("description")),
        employment_type=", ".join(employment) if isinstance(employment, list) else employment,
        department=posting.get("occupationalCategory") if isinstance(posting.get("occupationalCategory"), str) else None,
        posted_at=posted_at,
        remote=True if str(posting.get("jobLocationType", "")).upper() == "TELECOMMUTE" else None,
        salary=_salary(posting),
        extra_skills=[s for s in skills if isinstance(s, str)],
        marker=posted_at,
        raw=posting,
    )


@register
class JsonLdScraper(BaseScraper):
    type_name = "jsonld"
    label = "Structured data (JSON-LD / microdata / sitemap)"
    description = ("Any careers site that publishes schema.org JobPosting data (JSON-LD or HTML "
                   "microdata, most do for Google Jobs) - or a sitemap.xml of its job pages")
    fields = (
        OptionField("start_urls", "Start URLs", kind="urls", required=True,
                    help="Listing page(s), job pages, or a sitemap.xml / sitemap_index.xml - one per line"),
        OptionField("link_pattern", "Job link pattern", kind="regex",
                    help=r"Regex for job links (or sitemap entries) to follow, e.g. /jobs/[^/]+$"),
        OptionField("max_pages", "Max pages per run", kind="number", default=50),
        OptionField("refetch_known", "Re-download known jobs", kind="bool", default=False,
                    help="Off = only fetch job pages not collected yet (faster, gentler)"),
    )

    def fetch_jobs(self) -> Iterator[RawJob]:
        start_urls = self.require_option("start_urls")
        start_urls = [start_urls] if isinstance(start_urls, str) else list(start_urls)
        pattern = self.source.option("link_pattern")
        link_rx = re.compile(pattern) if pattern else None
        max_pages = int(self.source.option("max_pages", 50))
        refetch = bool(self.source.option("refetch_known", False))

        # Each queued entry is (url, is_seed, skip_eligible):
        # - is_seed: one of the configured start_urls - a fetch failure here aborts the run,
        #   same as a broken config; a failure on anything discovered along the way is just
        #   logged and skipped, since losing one job (or one sub-sitemap) shouldn't lose the rest.
        # - skip_eligible: this URL is itself a candidate job page, so the "already have it,
        #   unchanged" shortcut applies. True for sitemap <urlset> entries and <a href> links
        #   found on a listing page; False for seeds and for <sitemapindex> entries (more
        #   sitemaps, not jobs).
        queue: deque[tuple[str, bool, bool]] = deque((u, True, False) for u in start_urls)
        visited: set[str] = set()
        while queue:
            url, is_seed, skip_eligible = queue.popleft()
            if url in visited:
                continue
            if len(visited) >= max_pages:
                self.complete = False
                break
            visited.add(url)

            if skip_eligible and not refetch and url in self.known_markers:
                yield self.new_job(external_id=url, url=url, unchanged=True)
                continue

            try:
                content = self.get_text(url)
            except Exception as exc:  # one broken page must not stop the whole source
                self.log.warning("Skipping %s: %s", url, exc)
                if is_seed:
                    raise
                continue

            sitemap_kind = _sitemap_kind(content)
            if sitemap_kind == "index":
                # A <sitemapindex> entry is another sitemap, not a job page - link_pattern
                # describes job URLs, so it must not filter these out too.
                for loc in _sitemap_locs(content):
                    if loc not in visited:
                        queue.append((loc, False, False))
                continue
            if sitemap_kind == "urlset":
                # A <urlset> entry is a page to visit next (usually a job page, but still run
                # through the same content-sniffing above in case it's yet another sitemap).
                for loc in _sitemap_locs(content):
                    if (not link_rx or link_rx.search(loc)) and loc not in visited:
                        queue.append((loc, False, True))
                continue

            for i, posting in enumerate(extract_structured_jobs(content)):
                yield jsonld_to_raw(self, posting, url, i)

            if not skip_eligible and link_rx:
                for link in self._links(content, url, link_rx):
                    if link not in visited:
                        queue.append((link, False, True))

    @staticmethod
    def _links(html: str, base_url: str, link_rx: re.Pattern) -> list[str]:
        host = urlsplit(base_url).netloc
        soup = BeautifulSoup(html, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(base_url, a["href"]).split("#")[0]
            if urlsplit(href).netloc == host and link_rx.search(href):
                links.append(href)
        return list(dict.fromkeys(links))
