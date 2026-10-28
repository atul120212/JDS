"""Command line interface: ``python -m jd_collector <command>``."""

from __future__ import annotations

import argparse
import json
import sys

from jd_collector.config import load_sources, save_source
from jd_collector.logging_setup import setup_logging


def cmd_init_db(_args: argparse.Namespace) -> int:
    from jd_collector.db import init_engine

    engine = init_engine()
    print(f"Database ready: {engine.url.render_as_string(hide_password=True)}")
    return 0


def cmd_sources(_args: argparse.Namespace) -> int:
    for s in load_sources(include_disabled=True):
        state = "enabled " if s.enabled else "disabled"
        schedule = s.cron or f"every {s.interval_minutes} min"
        print(f"{state}  {s.name:<20} {s.type:<16} {s.company:<24} {schedule}")
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    from jd_collector.db import init_engine
    from jd_collector.pipeline import run_sources

    init_engine()
    sources = load_sources(include_disabled=bool(args.source))
    if args.source:
        by_name = {s.name: s for s in sources}
        missing = [n for n in args.source if n not in by_name]
        if missing:
            print(f"Unknown sources: {', '.join(missing)}", file=sys.stderr)
            return 2
        sources = [by_name[n] for n in args.source]
    results = run_sources(sources, max_workers=args.workers)

    print(f"\n{'source':<20} {'status':<8} {'fetched':>7} {'new':>5} {'upd':>5} {'same':>5} {'bad':>5} {'closed':>6}")
    for r in results:
        print(f"{r.source:<20} {r.status:<8} {r.fetched:>7} {r.new:>5} {r.updated:>5} "
              f"{r.unchanged:>5} {r.invalid:>5} {r.deactivated:>6}")
        if r.error:
            print(f"  error: {r.error}")
    return 0 if all(r.status == "success" for r in results) else 1


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from jd_collector.api import create_app

    print(f"JD Collector UI: http://{args.host}:{args.port}/   (API docs: /docs)")
    app = create_app(with_scheduler=args.with_scheduler, run_now=args.run_now)
    uvicorn.run(app, host=args.host, port=args.port, log_config=None)
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    from jd_collector.db import init_engine
    from jd_collector.scheduler import run_scheduler

    init_engine()
    run_scheduler(run_now=args.run_now)
    return 0


def cmd_stats(_args: argparse.Namespace) -> int:
    from jd_collector import repository as repo
    from jd_collector.db import session_scope

    with session_scope() as session:
        print(json.dumps(repo.stats(session), indent=2, default=str))
    return 0


def cmd_reclassify(_args: argparse.Namespace) -> int:
    from jd_collector import repository as repo
    from jd_collector.db import session_scope

    with session_scope() as session:
        n = repo.reclassify_all(session)
    print(f"Reclassified {n} jobs (region, role category, job type, skills)")
    return 0


def cmd_catalog_list(args: argparse.Namespace) -> int:
    from jd_collector.catalog import filter_catalog, load_catalog

    entries = filter_catalog(load_catalog(), region=args.region, industry=args.industry, type_=args.type, q=args.q)
    if not entries:
        print("No matching catalog entries.", file=sys.stderr)
        return 0
    existing = {s.name for s in load_sources(include_disabled=True)}
    for e in sorted(entries, key=lambda e: (e.region, e.company.lower())):
        tag = " [already added]" if e.name in existing else ""
        print(f"{e.region:<22} {e.name:<22} {e.type:<12} {e.company:<28} {e.industry}{tag}")
    return 0


def cmd_catalog_add(args: argparse.Namespace) -> int:
    from jd_collector.catalog import catalog_by_name

    by_name = catalog_by_name()
    missing = [n for n in args.names if n not in by_name]
    if missing:
        print(f"Unknown catalog entries: {', '.join(missing)}", file=sys.stderr)
        print("Run 'jd_collector catalog list' to see available names.", file=sys.stderr)
        return 2
    existing = {s.name for s in load_sources(include_disabled=True)}
    added, skipped = [], []
    for name in args.names:
        if name in existing:
            skipped.append(name)
            continue
        save_source(by_name[name].to_source())
        added.append(name)
    if added:
        print(f"Added: {', '.join(added)}")
    if skipped:
        print(f"Already a source, skipped: {', '.join(skipped)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jd_collector", description="Job Description Collector")
    parser.add_argument("--log-level", default=None, help="DEBUG, INFO, WARNING ...")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create database tables").set_defaults(func=cmd_init_db)
    sub.add_parser("sources", help="list configured sources").set_defaults(func=cmd_sources)

    p = sub.add_parser("scrape", help="scrape now (all enabled sources, or the ones named)")
    p.add_argument("--source", "-s", action="append", help="source name; repeatable")
    p.add_argument("--workers", "-w", type=int, default=None, help="parallel sources")
    p.set_defaults(func=cmd_scrape)

    p = sub.add_parser("serve", help="run the REST API + web UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--with-scheduler", action="store_true",
                   help="also scrape every source on its schedule inside this server process")
    p.add_argument("--run-now", action="store_true", help="with --with-scheduler: scrape all sources on start")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("schedule", help="run the periodic scraper")
    p.add_argument("--run-now", action="store_true", help="scrape every source immediately on start")
    p.set_defaults(func=cmd_schedule)

    sub.add_parser("stats", help="print database statistics").set_defaults(func=cmd_stats)
    sub.add_parser("reclassify", help="recompute region/role/job-type/skills for stored jobs "
                   "without re-scraping (run after upgrading)").set_defaults(func=cmd_reclassify)

    catalog = sub.add_parser("catalog", help="browse and add from the curated company directory")
    catalog_sub = catalog.add_subparsers(dest="catalog_command", required=True)

    p = catalog_sub.add_parser("list", help="list catalog entries")
    p.add_argument("--region", help="e.g. 'North America', 'Europe', 'Asia Pacific'")
    p.add_argument("--industry")
    p.add_argument("--type", help="greenhouse, lever or ashby")
    p.add_argument("--q", help="search company/industry")
    p.set_defaults(func=cmd_catalog_list)

    p = catalog_sub.add_parser("add", help="add one or more catalog entries as sources")
    p.add_argument("names", nargs="+", help="catalog entry names, as shown by 'catalog list'")
    p.set_defaults(func=cmd_catalog_add)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(args.log_level)
    return args.func(args)
