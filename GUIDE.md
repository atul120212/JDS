# JD Collector — The Simple Guide

This guide explains the project in plain language: what it does, how it works step by step, what tools it's built with and why, and how to set it up and run it.

If you want deeper technical details (every API endpoint, every config option), see [README.md](README.md). This guide is the easy version — read this first.

---

## 1. What does this project do?

Companies post job openings on their own "Careers" pages (like `careers.stripe.com`). If you wanted to search across **many** companies at once, you'd have to visit each site separately.

**JD Collector visits those career pages for you, automatically, on a schedule** — and puts every job it finds into one searchable place: a web page where you can filter by skill, location, salary, experience level, and more.

Think of it like a price-comparison website, but for jobs instead of products.

---

## 2. The whole flow, step by step

Here's everything that happens, from a company's career page to your screen:

```
 1. A list of companies           config/sources.yaml
    you want to watch         ─────────────────────────┐
                                                          │
 2. Every few hours, the                                 ▼
    scheduler wakes up and      ┌─────────────────────────────────┐
    visits each company's   ──► │   The Scraper (one per company)  │
    career page                 │   fetches the raw job listings   │
                                 └─────────────────────────────────┘
                                                          │
 3. The raw, messy data                                  ▼
    (different for every        ┌─────────────────────────────────┐
    company) gets cleaned   ──► │   The Normalizer                 │
    up into one consistent      │   title, company, location,      │
    shape                       │   salary, skills, region, etc.   │
                                 └─────────────────────────────────┘
                                                          │
 4. The cleaned job gets                                 ▼
    saved. If it's a job        ┌─────────────────────────────────┐
    we already have, we     ──► │   The Database (SQLite file)     │
    just note "still open"      │   one row per job                │
                                 └─────────────────────────────────┘
                                                          │
 5. You open the website,                                ▼
    search/filter, and          ┌─────────────────────────────────┐
    click a job to see      ──► │   The Web App + API              │
    the full description        │   search, filters, charts        │
                                 └─────────────────────────────────┘
```

**In short:** `scrape → clean up → save → search`, repeated automatically.

A few extra things happen along the way, explained simply:

- **"Normalizing"** means taking messy text (every company writes job posts differently) and pulling out the useful bits in a consistent way — the job title, the location, whether it's remote, the salary if mentioned, which skills are needed (Python? AWS? Excel?), roughly how many years of experience it wants, and which broad region it's in (North America, Europe, Asia Pacific, etc.). This happens automatically using pattern-matching — no AI model needed, just careful rules.
- **"Incremental"** means it doesn't start from scratch every time. If a job is still posted, it just updates "last seen". If a job disappears from the company's site, it's marked closed (but kept in history, not deleted).
- **Politeness:** before scraping any site, it checks that site's `robots.txt` file (a standard file websites use to say "please don't crawl this part") and respects it. It also doesn't hammer a site with requests — it waits a bit between each one, and backs off if a site is struggling.

---

## 3. The tools this project is built with (and why)

You don't need to know these to *use* the project, but here's what's under the hood, explained simply:

| Tool | What it is, in one line | Why it's used here |
|---|---|---|
| **Python** | A popular, easy-to-read programming language | The whole project is written in it — scraping, cleaning data, and the server |
| **requests** | A Python tool for downloading web pages, like a browser without the visual part | Used to actually fetch each company's career page / API |
| **BeautifulSoup** | A Python tool for reading messy HTML and pulling out the parts you want | Used to read a job page and find the title, description, etc. |
| **SQLite** | A simple database that lives in a single file on your computer (no separate server to install) | Stores every job collected — easy to set up, good enough for this scale |
| **SQLAlchemy** | A Python tool that lets you talk to a database using Python code instead of writing raw database commands | Used to save/read/search jobs in the database |
| **FastAPI** | A Python tool for building a web API (a way for the website to ask the server for data) quickly | Powers everything the web page asks for: "give me jobs matching Python", "give me the stats", etc. |
| **APScheduler** | A Python tool for running a task automatically on a timer (e.g. "every 6 hours") | Used to re-scrape every company on a schedule, without you doing it manually |
| **HTML / CSS / JavaScript** | The three building blocks of any web page | The search website itself — no fancy framework, just plain, fast, simple code |
| **Uvicorn** | A program that runs a Python web server | Actually runs the FastAPI server so your browser can reach it |

**Why no big frameworks or heavy tools?** Everything here is intentionally simple and standard. One Python project, one database file, no accounts to create, nothing to install beyond what's in `requirements.txt`. You can read almost any file in this project and understand what it does without needing to learn a new framework first.

---

## 4. What's in the project (folder map)

```
JD-Collector/
│
├── jd_collector/              The actual program
│   ├── scrapers/              One file per company/site type (Greenhouse, Lever, Accenture, ...)
│   ├── static/                The web page (HTML/CSS/JavaScript)
│   ├── normalize.py           Cleans up messy scraped data into a consistent shape
│   ├── regions.py             Figures out which region a job is in (North America, Europe, ...)
│   ├── roles.py                Figures out the job's category (Engineering, Sales, Design, ...)
│   ├── experience.py          Figures out the years of experience needed
│   ├── db.py                  Database setup
│   ├── repository.py          All the database search/save code
│   ├── pipeline.py            Runs one scrape: fetch → clean → save
│   ├── scheduler.py           Runs scrapes automatically on a timer
│   ├── api.py                 The web API (what the website talks to)
│   ├── catalog.py             The ready-made list of companies you can add with one click
│   └── cli.py                 The `python -m jd_collector ...` commands
│
├── config/
│   ├── sources.yaml           The companies you're currently collecting from
│   └── catalog.yaml           148 more companies, ready to add
│
├── data/
│   └── jd_collector.db        The database file — all your collected jobs live here
│
├── tests/                     Automated checks that make sure nothing is broken
├── README.md                  The detailed technical reference
└── GUIDE.md                   This file
```

---

## 5. Setup guide (do this once)

You need **Python** installed (3.11 or newer). If you already ran this project before, you can skip to [Section 6](#6-running-guide) — it's already set up.

**Step 1 — Open a terminal in the project folder**

```powershell
cd D:\workshop\JD-Collector
```

**Step 2 — Create a private Python environment** (keeps this project's tools separate from everything else on your computer)

```powershell
python -m venv .venv
.venv\Scripts\activate
```

You'll know it worked because your terminal prompt now starts with `(.venv)`.

**Step 3 — Install everything the project needs**

```powershell
pip install -r requirements.txt
```

This downloads all the tools listed in the table above. It only needs to be done once (or again if `requirements.txt` changes).

**Step 4 — (Optional) Settings file**

```powershell
copy .env.example .env
```

Every setting already has a sensible default, so this step is optional. Open `.env` only if you want to change something — for example, to protect the website with a password (`API_KEY`), or to get an alert message when a scrape fails (`ALERT_WEBHOOK_URL`).

That's it — setup is done.

---

## 6. Running guide

### The easiest way: one command does everything

```powershell
cd D:\workshop\JD-Collector
.venv\Scripts\activate
python -m jd_collector serve --with-scheduler
```

Then open your browser to **http://127.0.0.1:8000/**

This single command:
- Starts the website
- Starts the API (what the website talks to behind the scenes)
- Starts the automatic scraper, so every company on your list gets re-checked every few hours, forever, while this is running

Leave this running in its terminal window. To stop it, click into that terminal and press `Ctrl+C`.

### Using the website

| Page | What you do there |
|---|---|
| **Jobs** | Search and filter jobs — by keyword, company, location, skill, remote/on-site, job type, years of experience, salary. Click any job to read the full description and apply. |
| **Saved** | Jobs you've bookmarked, kept in your browser. |
| **Insights** | Charts: how many jobs, which skills are most requested, which companies are hiring, by region, by experience level, and more. |
| **Sources** | See which companies you're collecting from, add new ones (paste a careers URL, or pick from the ready-made list of 148), turn sources on/off, or scrape one right now instead of waiting. |
| **Runs** | A log of every scrape: how many jobs it found, how many were new, and any errors. |

**To add a new company:** go to **Sources → Browse catalog**, pick one or more companies from the list, and click **Add & scrape**. Done — no technical setup needed.

### Using the command line (optional — for when you don't need the website)

All of these also work, if you just want to run things from the terminal without the web page:

```powershell
python -m jd_collector sources          # list the companies you're collecting from
python -m jd_collector scrape           # scrape all of them right now
python -m jd_collector scrape -s stripe # scrape just one company (by its short name)
python -m jd_collector stats            # print quick numbers: how many jobs, by company, etc.
python -m jd_collector catalog list     # browse the 148 ready-made companies
python -m jd_collector catalog add wipro deloitte-us   # add some of them
```

### Running it in the background permanently (no website, just collecting)

If you only care about the data being collected (e.g. you'll look at the database file directly, or in a different tool), you don't need the website at all:

```powershell
python -m jd_collector schedule --run-now
```

This scrapes every company immediately, then keeps re-scraping on schedule, forever, with no web page involved.

---

## 7. A typical first session

1. Run `python -m jd_collector serve --with-scheduler`.
2. Open http://127.0.0.1:8000/ — you'll see jobs from the companies already set up.
3. Go to **Sources → Browse catalog**, search for a company you're interested in, select it, click **Add & scrape**. Wait a minute — a notification will tell you when it's done.
4. Go to **Jobs**, and use the filters on the left (try **Region**, **Experience needed**, or type a skill like "Python").
5. Click a job to read the full description, and click **Apply on company site** to actually apply.
6. Go to **Insights** to see the bigger picture — which skills are most in demand, etc.

That's the whole project. Everything else in [README.md](README.md) is extra detail for when you need it.
