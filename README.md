# JD Collector

Collects live job openings from company career sites (big companies and startups), normalizes them into one schema, stores them in a database, refreshes them on a schedule and serves them through a REST API and a small search UI.

Built from the design in [1.txt](1.txt).

> **New here?** Read **[GUIDE.md](GUIDE.md)** first — a short, plain-language walkthrough of how everything works and how to set it up. This file is the full technical reference.

## Quick start (Windows / PowerShell)

```powershell
cd D:\workshop\JD-Collector
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # optional, every setting has a default

python -m jd_collector serve --with-scheduler   # web UI + API + automatic scraping, one process
```

Open **http://127.0.0.1:8000/**. Everything can be done from the browser. The API docs are at http://127.0.0.1:8000/docs.

The other commands are for terminal-only or headless use:

```powershell
python -m jd_collector sources  # list configured sources
python -m jd_collector catalog list --region "Europe"   # browse the built-in company catalog
python -m jd_collector catalog add revolut qonto        # add some as sources
python -m jd_collector scrape   # scrape all enabled sources now (or: -s stripe -s ramp)
python -m jd_collector serve    # UI + API without automatic scraping
python -m jd_collector schedule --run-now   # a separate scheduler process
python -m jd_collector stats
python -m jd_collector reclassify   # recompute region/role/job-type/skills on an upgraded DB
```

## Web UI

| Page | What you can do |
|---|---|
| **Jobs** | Search by keyword. Filter by company, location, **region**, skills (must have all), job type, **role category**, **experience level** (Fresher, 1-3 yrs, ... 12+ yrs), remote/on-site, posting date, minimum salary and source; closed jobs can be included. Sort the results and export them to CSV. Click a job to open the full description, facts, skills, a **"Source & citation"** section (the exact career site it was collected from, linked), and the **Apply** link; its region, role category and experience level are clickable, jumping to other jobs that match. The URL keeps your filters, so a link reopens the same search or job. |
| **Saved** | Bookmarked jobs, stored in this browser, with a CSV export. |
| **Insights** | Headline numbers: open jobs, new in the last 24 h, companies, remote %, salary-listed %, freshness. Charts show posting activity over 30 days (with a table view), top skills, jobs by company, **by region**, **by role category**, **by experience needed**, job types and locations. Click any bar to jump to those jobs. A company filter applies to the activity and skills charts. |
| **Sources** | **Add a company by pasting its careers URL** (detected automatically), or **Browse catalog** to pick from ~140 pre-verified companies organized by region — see [Region, role and the company catalog](#region-role-experience-level-citation-and-the-company-catalog) below. **Test** a source before saving, which fetches a sample and stores nothing. Edit the schedule (interval or cron), enable or disable, delete (optionally with its jobs) and **Scrape now**. Each source shows its last run, open jobs and next scheduled run. Changes are written to `config/sources.yaml`, keeping its comments. |
| **Runs** | Every scrape with its status, duration, and counts (found, new, updated, unchanged, rejected, closed), plus readable error messages. Updates live while scrapes run. |

* **Live status:** the sidebar shows when data was last updated and which sources are scraping. A notification appears when each scrape finishes.
* **Keyboard shortcuts (Jobs page):** `/` search · `j`/`k` next or previous job · `s` save · `Esc` close.
* **Themes:** light, dark, or follow the system, set in Settings or with the theme button. The layout works down to phone width.
* **Settings:** if the server sets `API_KEY`, enter it once in Settings. It's stored only in that browser.
* **Overlap protection:** a source never runs twice at the same time. A manual "Scrape now" during a scheduled run is skipped, not duplicated.

## Architecture

```
config/sources.yaml ──► Scheduler (APScheduler / cron / Airflow)
                              │
                              ▼
 Target sites ◄── PoliteHttpClient ◄── Scrapers (greenhouse, lever, ashby,
 (robots.txt, rate limit,              smartrecruiters, jsonld, css)
  retry/backoff, cache, UA/proxy)          │  RawJob
                                           ▼
                                    Normalizer + validation ──► JobPosting
                                           │
                                           ▼
                        Database (SQLite default / PostgreSQL): jobs, job_skills, scrape_runs
                                           │
                                           ▼
                                FastAPI REST API + web UI
          Logging (logs/jd_collector.log), run history, alerts (log + optional webhook)
```

| Design component (1.txt) | Implementation |
|---|---|
| Scraper module | [jd_collector/scrapers/](jd_collector/scrapers/) — one parser per site type, registered by `type` |
| Anti-blocking / politeness | [jd_collector/http_client.py](jd_collector/http_client.py) — robots.txt, per-host rate limit, exponential backoff + `Retry-After`, response cache, user-agent and proxy rotation |
| Data normalization | [jd_collector/normalize.py](jd_collector/normalize.py) — HTML→text, skills (~120 patterns), salary parsing, job type, remote detection, dates, URL canonicalization, validation; [regions.py](jd_collector/regions.py) and [roles.py](jd_collector/roles.py) for region/role classification |
| Unified schema | [jd_collector/models.py](jd_collector/models.py) `JobPosting` |
| Data storage | [jd_collector/db.py](jd_collector/db.py), [jd_collector/repository.py](jd_collector/repository.py) — indexed on job_id, company, location, title, posted date, skills; raw payload kept as a backup |
| Scheduler | [jd_collector/scheduler.py](jd_collector/scheduler.py) (per-source interval or cron), [airflow/jd_collector_dag.py](airflow/jd_collector_dag.py) |
| API layer + UI | [jd_collector/api.py](jd_collector/api.py) and the single-page web app in [jd_collector/static/](jd_collector/static/) (plain JS, no build step) |
| Logging & monitoring | [jd_collector/logging_setup.py](jd_collector/logging_setup.py), [jd_collector/monitoring.py](jd_collector/monitoring.py), `scrape_runs` table, `/runs` endpoint |
| Pipeline | [jd_collector/pipeline.py](jd_collector/pipeline.py) — parallel sources, batching, incremental upserts |

### Unified job schema

| Field | Description |
|---|---|
| `job_id` | SHA-1 of source + the site's job id (falls back to the canonical URL) |
| `title`, `company`, `location`, `is_remote` | |
| `region` | One of `North America`, `Latin America`, `Europe`, `Middle East & Africa`, `Asia Pacific`, `Remote / Global`, or null — derived from `location`; see below |
| `role_category` | e.g. `Engineering`, `Sales & Business Development`, `Data & AI`, or null — derived from `title`; see below |
| `experience_level` | `Fresher / 0-1 yr`, `1-3 yrs`, `3-5 yrs`, `5-8 yrs`, `8-12 yrs`, `12+ yrs`, or null — derived from the posting's stated years of experience; see below |
| `description` | Full description as clean plain text |
| `skills` | Detected skills (also in the indexed `job_skills` table) |
| `salary`, `salary_min`, `salary_max`, `salary_currency`, `salary_interval` | From structured data, or parsed from the description |
| `job_type` | Full-time, Part-time, Contract, Internship, Temporary (null if unknown) |
| `department`, `posted_date`, `apply_link` | |
| `is_active`, `first_seen_at`, `last_seen_at`, `updated_at` | Lifecycle tracking |
| `raw` | Original source payload (disable with `STORE_RAW=false`) |

### How incremental scraping works

* Every job gets a content hash. Unchanged jobs only refresh `last_seen_at`. Changed jobs are updated, and new jobs are inserted.
* Jobs that disappear from a source after a complete run are marked `is_active = false` (closed). They're kept for history but hidden from the API by default (`include_inactive=true` shows them).
* Scrapers that need one request per job (SmartRecruiters, JSON-LD, CSS) skip jobs they already have, based on a stored source marker or URL.
* If a listing is cut short (for example by `max_jobs` or `max_pages`), closing jobs is skipped for that run so jobs aren't wrongly marked closed.

## Region, role, experience level, citation, and the company catalog

Every job collected gets three extra fields, computed automatically — no setup needed:

* **`region`** — [jd_collector/regions.py](jd_collector/regions.py) reads the job's location text (and whether it's remote) and classifies it into one of six regions: North America, Latin America, Europe, Middle East & Africa, Asia Pacific, or Remote / Global. It recognizes country names, common abbreviations (`US`, `UK`, `UAE`), shorthand regions companies use themselves (`EMEA`, `APAC`, `LATAM`, `AMER`), U.S. states, and a list of major cities. A location with no locatable signal (e.g. just `"Hybrid"`) is left unclassified (`null`) rather than guessed.
* **`role_category`** — [jd_collector/roles.py](jd_collector/roles.py) classifies the job title into a discipline (Engineering, Data & AI, Product, Design, Sales & Business Development, Marketing & Communications, Customer Support & Success, People & Talent, Finance & Accounting, Legal & Compliance, Operations) using an ordered list of rules, most specific first — so "Sales Engineer" lands in Sales, not Engineering, and "Data Scientist" lands in Data & AI, not Engineering. The job's title is checked exhaustively (including a few broad fallback words, like bare "design") before its description is ever consulted — a long description's boilerplate ("...our Finance organization partners with every team...") must never outvote a title that already said plainly what the role is. A title that matches nothing stays unclassified rather than guessed from a weak signal.
* **`experience_level`** — [jd_collector/experience.py](jd_collector/experience.py) looks for an explicit years-of-experience statement ("3-5 years", "5+ yrs", "minimum 2 years", "fresher", "entry level", an internship, ...) in the title and the start of the description, and buckets it into `Fresher / 0-1 yr`, `1-3 yrs`, `3-5 yrs`, `5-8 yrs`, `8-12 yrs` or `12+ yrs`. Written for how both Western tech postings ("5+ years of experience") and Indian IT-services postings ("2-4 Yrs Exp", "Freshers can apply") phrase it. A posting that states no number at all is left unclassified.

All three are best-effort heuristics on free text, not guarantees — treat them the way you'd treat any auto-tagging. Filter and browse by them in the **Jobs** and **Insights** pages, or via the `region` / `role_category` / `experience_level` query params on `GET /jobs`.

If you added these to a database that already had jobs in it (upgrading this project), run:

```powershell
python -m jd_collector reclassify
```

This recomputes `region`, `role_category`, `experience_level`, `job_type` and `skills` for every stored job from its already-saved title/location/description — no re-scraping, works offline. One caveat: a few sites (Lever, Ashby) supply `job_type` from structured metadata that isn't stored anywhere else; `reclassify` can only recover it from the title/description text, which is usually less reliable than the original source data. If the sources are still reachable, prefer a fresh `python -m jd_collector scrape` instead — it repopulates everything, including `job_type`, from live data.

### Citation — where a job came from

Every job keeps its full provenance, visible in the UI and the API, not just the raw title/description text:

* The job drawer has a **"Source & citation"** section: the exact career-site hostname the posting was collected from (a live link to the original listing), the configured source name, and the internal job id.
* `GET /jobs/{job_id}` returns `apply_link` (the direct URL to the original posting) and `source` (which configured source collected it); `GET /sources` lists each source's site type (Greenhouse, Accenture, etc.).
* CSV export (`GET /jobs/export.csv`) includes a `source_website` column (the apply link's hostname) alongside `apply_link` and `source`, so an exported spreadsheet carries citation information per row, not just in the UI.

### The company catalog — ready-to-use career pages by region

[config/catalog.yaml](config/catalog.yaml) ships with **~148 companies**, organized by region and industry, each one **live-verified against its real career-page API** before being added — so picking one and adding it works immediately, no hunting for board tokens. It covers North America, Europe, Asia Pacific, Latin America, Middle East & Africa, and remote-first companies, including several under "IT Services": Accenture (India, USA, UK, Canada, Philippines), HCLTech, Wipro and Deloitte (US).

Browsing the catalog never scrapes anything by itself — a company only becomes an active, scraped source once you add it.

* **UI:** Sources → **Browse catalog** → filter by region, search, check the companies you want, then **Add selected** or **Add & scrape**.
* **API:** `GET /catalog?region=&industry=&type=&q=` to browse (each entry includes `already_added`), `POST /catalog/add` with `{"names": [...]}` to add some.
* **CLI:**
  ```powershell
  python -m jd_collector catalog list --region "Europe"
  python -m jd_collector catalog add revolut qonto
  ```

`region` in the catalog is the company's **headquarters region** (tagged at curation time, same six values as the per-job `region` field above) — not a guarantee every one of its open roles is based there. Add your own companies to `config/catalog.yaml` by hand (or just add them directly as sources via "Add source" / the URL-paste flow); the file's schema is documented in its header comment.

## Adding sources

**Easiest:** pick a company from the [built-in catalog](#region-role-experience-level-citation-and-the-company-catalog) — Sources → Browse catalog in the UI, or `python -m jd_collector catalog add <name>`.

To add a company by hand, edit [config/sources.yaml](config/sources.yaml) (or paste its careers URL into the UI, which detects the type for you). Most company careers pages are hosted on an applicant tracking system (ATS). Find the board id in the careers page URL:

| Careers URL looks like | Use |
|---|---|
| `boards.greenhouse.io/<token>` or `job-boards.greenhouse.io/<token>` | `type: greenhouse`, `board_token: <token>` |
| `jobs.lever.co/<site>` | `type: lever`, `site: <site>` (`region: eu` for `jobs.eu.lever.co`) |
| `jobs.ashbyhq.com/<board>` | `type: ashby`, `board: <board>` |
| `jobs.smartrecruiters.com/<CompanyId>` | `type: smartrecruiters`, `company_id: <CompanyId>` |
| `accenture.com/<site>/careers/jobsearch` | `type: accenture`, `job_country`, `country_site` (e.g. `in-en`, `us-en`, `gb-en`) |
| Custom site with schema.org `JobPosting` data - JSON-LD **or** HTML microdata (most sites have one, for Google Jobs) | `type: jsonld`, `start_urls`, `link_pattern` |
| A client-rendered listing page with no job links in its HTML, but a `sitemap.xml` of job pages (common - look for `Sitemap:` in `robots.txt`, or just try `/sitemap.xml`) | `type: jsonld`, `start_urls: [<the sitemap URL>]`, `link_pattern` to pick out job URLs |
| Custom HTML site without structured data | `type: css` with CSS selectors |

New site types are added with a class in `jd_collector/scrapers/` that subclasses `BaseScraper`, uses `@register`, and yields `RawJob`s. It also needs to be imported in `scrapers/__init__.py`.

**JavaScript-heavy sites:** most single-page-app careers sites load their jobs from one of the ATS APIs above, embed JSON-LD or microdata, or publish a sitemap of job pages even though the listing itself is client-rendered (the `jsonld` type handles all of these - see the sitemap row above). Check the browser's network tab and view-source first. Only if none of those apply, add a scraper that renders pages with Selenium or Playwright.

> **Note:** `api.smartrecruiters.com/robots.txt` currently disallows generic crawlers, so the sample `bosch` source is disabled. The collector respects robots.txt (`RESPECT_ROBOTS=true`) and records a run blocked by robots.txt as a failure, with an alert.

### Other IT-services companies (TCS, Cognizant, Infosys, ...)

Accenture, HCLTech, Wipro and Deloitte are all included (`accenture-*`, `hcltech`, `wipro`, `deloitte-us` above) - each one found by inspecting the site's actual network calls and page source, not guessed:

* **Accenture** runs its own, plainly reachable JSON search API (`type: accenture`).
* **HCLTech, Wipro** both run SAP SuccessFactors "Career Site Builder." Its listing API (`POST .../services/recruiting/v1/jobs`) works with no authentication, but both sites' `robots.txt` disallows `/services/` - so it's never used. Instead, their `sitemap.xml` (not disallowed) lists every job's own page directly, and those pages are plain server-rendered HTML with schema.org **microdata** (not JSON-LD, but `jsonld.py` reads both) - fully `robots.txt`-compliant, no browser needed. One real limitation found this way: neither site marks up a structured location on its job pages, so `location`/`region` are usually empty for these two sources specifically; everything else (title, description, skills, experience level) comes through normally.
* **Deloitte (US)** runs on Avature; its `robots.txt` explicitly *allows* `/careers` and declares a `sitemap.xml` of its own job pages, which have full, proper JSON-LD - the most straightforward of the four.

The rest were investigated the same way and don't currently have an equivalent option, for different reasons each:

* **TCS**: `ibegin.tcsapps.com` does have a real search API (`POST .../api/en-IN/search/jobs`), but it requires an `XSRF-TOKEN` cookie that the site only issues after its WAF (F5-style bot protection) lets a request through - in testing, a plain HTTP client never received it even after loading the page and its supporting endpoints first, only a real browser session did. That's bot-detection, not a cookie formality, and this project doesn't build workarounds for it. Its `sitemap.xml` just redirects back to the app shell - no escape hatch there either.
* **Cognizant**: its careers domain returns HTTP 403 to a plain request (bot-protected); its sitemap.xml is reachable but only lists generic marketing pages, not jobs.
* **Infosys**: has a real backend API, but it's gated behind an API gateway that didn't respond the same way outside a full browser session; its `sitemap.xml` is just the SPA shell.
* **TechMahindra, Capgemini**: no job-data API calls were visible even after waiting and interacting with the page; Capgemini's sitemap is its WordPress blog/marketing sitemap, unrelated to job postings.

None of these were worked around with browser automation or detection evasion, which this project avoids. If you can find a stable public endpoint for one of these that isn't `robots.txt`-disallowed - including a sitemap, which is worth checking for any site like this - a `jsonld` or `css` source may work directly, or a dedicated scraper can be added the same way `accenture.py` was.

## API

All endpoints except `/` and `/health` require `X-API-Key: <API_KEY>` when `API_KEY` is set.

| Endpoint | Purpose |
|---|---|
| `GET /jobs` | Search: `q`, `title`, `company`, `location`, `region`, `role_category`, `experience_level`, `skill` (repeat for AND), `job_type`, `remote`, `source`, `posted_after`, `min_salary`, `include_inactive`, `sort` (`-posted_date`, `-salary_max`, `-first_seen_at`, `title`, `company`…), `page`, `page_size` (max 100) |
| `GET /jobs/{job_id}` | Full job including description |
| `GET /companies` | Open jobs per company |
| `GET /skills?limit=&company=` | Most requested skills |
| `GET /stats` | Totals, per source/type, data freshness |
| `GET /runs?source=` | Scrape history: counts, durations, errors |
| `GET /sources` | Sources with last run, open-job count and next scheduled run |
| `POST /sources`, `PUT /sources/{name}`, `DELETE /sources/{name}?delete_jobs=` | Manage sources (writes `config/sources.yaml`) |
| `POST /sources/preview` | Test a source definition without storing anything |
| `GET /source-types` | Site types and their settings (drives the UI form) |
| `POST /scrape?source=` | Trigger a background scrape (skips sources already running) |
| `GET /status` | Running scrapes, scheduler state, data freshness |
| `GET /facets`, `GET /insights/timeline` | Filter options (including `regions`, `role_categories`) and posting activity for the UI |
| `GET /jobs/export.csv` | Same filters as `/jobs`, as CSV (up to 10,000 rows) |
| `GET /catalog?region=&industry=&type=&q=` | Browse the curated company directory (see [above](#region-role-experience-level-citation-and-the-company-catalog)) |
| `GET /catalog/regions` | Regions/industries present in the catalog, for building filter dropdowns |
| `POST /catalog/add` | Add catalog entries as sources: body `{"names": ["stripe", "revolut"]}` |

Example: `GET /jobs?skill=Python&skill=Kubernetes&remote=true&region=Europe&sort=-salary_max`

## Configuration (.env)

See [.env.example](.env.example). The main settings are:

* `DATABASE_URL`: the database to use. SQLite is the default. For PostgreSQL, use `postgresql+psycopg://user:pass@host/db` after running `pip install "psycopg[binary]"`.
* `API_KEY`: protects the API.
* `ALERT_WEBHOOK_URL`: a Slack-compatible webhook. It receives alerts for failed runs, a source returning 0 jobs, a job-count drop of more than 50%, or more than 50% of jobs failing validation.
* `DEFAULT_RATE_LIMIT_SECONDS`: the minimum delay between requests to the same host. A per-source `rate_limit_seconds` overrides it.
* `MAX_RETRIES`, `REQUEST_TIMEOUT`, `CACHE_TTL_SECONDS`, `USER_AGENTS` (separated by `||`), `PROXIES` (separated by commas): HTTP client behaviour.
* `MAX_WORKERS`: how many sources are scraped in parallel.

## Scheduling options

1. **Built in:** `python -m jd_collector serve --with-scheduler` (or a separate `python -m jd_collector schedule`) runs each source on its own `interval_minutes` or `cron` schedule. Overlapping runs of the same source are prevented. With `--with-scheduler`, source edits made in the UI take effect immediately.
2. **OS cron / Windows Task Scheduler:** run `python -m jd_collector scrape` periodically.
3. **Airflow:** use [airflow/jd_collector_dag.py](airflow/jd_collector_dag.py), which creates one task per source.

## Docker (PostgreSQL + web UI + scheduler)

```bash
cp .env.example .env
docker compose up --build
```

## Tests

```powershell
.venv\Scripts\python -m pytest
```

The tests cover the parsers for every scraper type against saved sample responses in `tests/fixtures/`, plus normalization rules, region/role/experience classification, the HTTP client's POST path, incremental and deactivation logic, failure tracking, database migrations, the shipped catalog (every entry's options are validated), the API filters and pagination, and API-key enforcement. No network access is needed — except `tests/test_catalog.py::test_real_catalog_loads_and_every_entry_validates`, which only checks the catalog file's structure locally and doesn't call the companies' APIs either.

## Scraping responsibly

Only collect from sites whose terms allow it. Keep rate limits conservative, and don't turn off robots.txt checks for sites you don't have permission to crawl.

# JDS
