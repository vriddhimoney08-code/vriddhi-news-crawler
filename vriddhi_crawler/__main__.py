"""CLI Entry point for vriddhi_crawler."""
from __future__ import annotations

import argparse
import sys

from .config import PORT
from .controlpanel import create_starter_excel
from .db import (
    get_analysts,
    get_dashboard_stats,
    get_macro_stories_for_analyst,
    get_unsent_stories_for_analyst,
    init_db,
    mark_sent,
)
from .pdf import generate_analyst_digest, generate_macro_digest
from .pipeline import Pipeline
from .whatsapp import send_whatsapp_digest, send_whatsapp_macro_digest


def main():
    parser = argparse.ArgumentParser(description="Vriddhi Watchlist News Crawler & Terminal")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # init
    subparsers.add_parser("init", help="Initialize database and starter control panel Excel")

    # server
    server_parser = subparsers.add_parser("server", help="Launch the local Web Dashboard on port 3009")
    server_parser.add_argument("--port", type=int, default=PORT, help=f"Port to bind (default: {PORT})")

    # crawl
    crawl_parser = subparsers.add_parser("crawl", help="Run crawler across sources")
    crawl_parser.add_argument("--only", type=str, default="exchanges,publishers,search", help="Comma-separated groups")
    crawl_parser.add_argument("--force", action="store_true", help="Force crawl ignoring interval")

    # preview
    preview_parser = subparsers.add_parser("preview", help="Render PDFs/HTML digests into data/digests/")
    preview_parser.add_argument("--only", type=str, help="Analyst name")

    # dispatch / digest
    dispatch_parser = subparsers.add_parser("dispatch", help="Send morning digests via WhatsApp to analysts")
    dispatch_parser.add_argument("--send-whatsapp", action="store_true", help="Flag for cron compatibility")
    digest_parser = subparsers.add_parser("digest", help="Alias for dispatch")
    digest_parser.add_argument("--send-whatsapp", action="store_true", help="Flag for cron compatibility")

    # run-daily
    subparsers.add_parser("run-daily", help="Run crawl cycle and immediately dispatch morning digests via WhatsApp")

    # macro-dispatch / macro-digest
    macro_disp = subparsers.add_parser("macro-dispatch", help="Run macro crawl and dispatch Evening Sectorial Briefings via WhatsApp")
    macro_disp.add_argument("--send-whatsapp", action="store_true", help="Flag for cron compatibility")
    macro_dig = subparsers.add_parser("macro-digest", help="Alias for macro-dispatch")
    macro_dig.add_argument("--send-whatsapp", action="store_true", help="Flag for cron compatibility")

    # status
    subparsers.add_parser("status", help="Print operational dashboard stats")

    args = parser.parse_args()

    if args.command == "init":
        print("Initializing database...")
        init_db(seed_defaults=True)
        print("Generating starter control_panel.xlsx...")
        create_starter_excel()
        print("Initialization complete! Database at data/crawler.db, Excel at control_panel.xlsx")

    elif args.command == "crawl":
        print(f"Starting crawl for groups: {args.only}...")
        groups = [g.strip() for g in args.only.split(",") if g.strip()]
        res = Pipeline().run_crawl(groups=groups, force=args.force)
        print(f"Crawl finished: {res['items_found']} items found, {res['stories_saved']} new stories saved.")
        if res["errors"]:
            print(f"Warnings/Errors: {res['errors']}")

    elif args.command == "preview":
        init_db(seed_defaults=True)
        analysts = get_analysts()
        for a in analysts:
            if args.only and args.only.lower() not in a.name.lower():
                continue
            stories = get_unsent_stories_for_analyst(a.id)
            path, _ = generate_analyst_digest(a.id, a.name, stories)
            print(f"Generated digest for {a.name} ({len(stories)} stories): {path}")

    elif args.command in ("dispatch", "run-daily", "digest"):
        init_db(seed_defaults=True)
        if args.command in ("run-daily", "digest"):
            print("=== [CRON] Starting Daily Crawl Cycle before Morning Dispatch ===")
            c_res = Pipeline().run_crawl(groups=["exchanges", "publishers", "search"])
            print(f"Crawl complete: Found {c_res['items_found']}, Saved {c_res['stories_saved']} fresh stories.")

        print("=== [CRON] Dispatching Morning Digests via WhatsApp ===")

        analysts = get_analysts()
        for a in analysts:
            stories = get_unsent_stories_for_analyst(a.id)
            if not stories:
                print(f"[{a.name}] Ledger is clean, no unsent stories.")
                continue

            file_path, _ = generate_analyst_digest(a.id, a.name, stories)
            res = send_whatsapp_digest(analyst_name=a.name, analyst_phone=a.phone, stories=stories, pdf_path=file_path)
            mark_sent([s["id"] for s in stories], a.id)
            print(f"[{a.name}] Result: {res.get('status')} -> {res.get('message')}")

    elif args.command in ("macro-dispatch", "macro-digest"):
        init_db(seed_defaults=True)
        print("=== [CRON] Starting Evening 5:30 PM Macro & Sector Briefing Cycle ===")

        print("Crawling macro sources (PIB, RBI, SEBI, official gazettes)...")
        from .sources.macro import MacroPipeline
        MacroPipeline().run_macro_crawl(hours=48)

        analysts = get_analysts()
        for a in analysts:
            stories = get_macro_stories_for_analyst(a.id, hours=24, limit=30)
            if not stories:
                print(f"[{a.name}] No policy updates today.")
                continue
            file_path, _ = generate_macro_digest(a.id, a.name, stories)
            res = send_whatsapp_macro_digest(
                analyst_name=a.name,
                analyst_phone=a.phone,
                stories=stories,
                pdf_path=file_path,
            )
            print(f"[{a.name}] Result: {res.get('status')} -> {res.get('message')}")

    elif args.command == "status":
        stats = get_dashboard_stats()
        print("=== Vriddhi News Crawler Status ===")
        print(f"Total Stories Crawled: {stats['total_stories']}")
        print(f"Exchange Disclosures:  {stats['total_filings']}")
        print(f"Tracked Companies:     {stats['total_companies']}")
        print(f"Registered Analysts:   {stats['total_analysts']}")
        print(f"System Health:         {stats['status']}")

    else:
        # Default: Start Web Dashboard on port 3009
        print(f"Starting Vriddhi Web Dashboard on http://localhost:{PORT} ...")
        from .server import start
        start()


if __name__ == "__main__":
    main()
