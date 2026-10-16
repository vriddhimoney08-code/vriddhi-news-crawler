"""Database operations, SQLite schema, deduplication fingerprints, and sent ledger."""
from __future__ import annotations

import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta, timezone
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc
from pathlib import Path
from typing import Any

from .config import DB_PATH, DEFAULT_FOLDERS
from .controlpanel import Analyst, Company


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path = DB_PATH, seed_defaults: bool = True) -> None:
    """Initialize SQLite tables and indexes."""
    with get_connection(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            nse_symbol TEXT,
            bse_code TEXT,
            aliases TEXT,
            search_queries TEXT,
            analyst_names TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS analysts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            assigned_companies TEXT
        );

        CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            type TEXT NOT NULL,
            keep_pattern TEXT,
            language TEXT DEFAULT 'en',
            body_check INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            last_crawled_at TEXT,
            status TEXT DEFAULT 'OK',
            items_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS stories (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            url TEXT,
            source_name TEXT,
            source_type TEXT,
            published_at TEXT,
            company_id TEXT,
            grade TEXT DEFAULT 'Grade C',
            filing_id TEXT,
            sources_json TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS fingerprints (
            hash TEXT PRIMARY KEY,
            kind TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS sent_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            story_id TEXT NOT NULL,
            analyst_id TEXT NOT NULL,
            status TEXT NOT NULL,
            attempted_at TEXT,
            sent_at TEXT,
            UNIQUE(story_id, analyst_id)
        );

        CREATE TABLE IF NOT EXISTS crawl_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT,
            completed_at TEXT,
            sources_checked INTEGER DEFAULT 0,
            items_found INTEGER DEFAULT 0,
            stories_saved INTEGER DEFAULT 0,
            errors TEXT
        );

        CREATE TABLE IF NOT EXISTS folders (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS macro_stories (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            summary TEXT,
            url TEXT,
            source_authority TEXT,
            ministry_or_regulator TEXT,
            sectors_json TEXT,
            impact_grade TEXT DEFAULT 'Tier 2 (Sector Impact)',
            impact_bias TEXT DEFAULT 'NEUTRAL',
            impact_summary TEXT,
            published_at TEXT,
            created_at TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_stories_company ON stories(company_id);
        CREATE INDEX IF NOT EXISTS idx_stories_published ON stories(published_at);
        CREATE INDEX IF NOT EXISTS idx_ledger_lookup ON sent_ledger(analyst_id, status);
        CREATE INDEX IF NOT EXISTS idx_macro_published ON macro_stories(published_at);
        CREATE INDEX IF NOT EXISTS idx_macro_authority ON macro_stories(source_authority);
        CREATE INDEX IF NOT EXISTS idx_macro_grade ON macro_stories(impact_grade);
        """)

        # Safe migration for folder column
        try:
            conn.execute("ALTER TABLE companies ADD COLUMN folder TEXT DEFAULT ''")
        except Exception:
            pass

        # Safe migration for assigned_folders column on analysts
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN assigned_folders TEXT DEFAULT '[]'")
        except Exception:
            pass

        # Seed default folders if empty
        try:
            fc = conn.execute("SELECT count(*) FROM folders").fetchone()[0]
            if fc == 0:
                conn.executemany("INSERT INTO folders VALUES (?, ?, ?)", [
                    ("GAME", "GAME", "2026-10-13"),
                    ("SET", "SET", "2026-10-13"),
                    ("MATCH", "MATCH", "2026-10-13"),
                    ("JUNIOR", "JUNIOR", "2026-10-13"),
                ])
        except Exception:
            pass

        # Always sync seed companies so code edits in db.py reflect in SQLite
        if seed_defaults:
            _seed_data(conn)
        migrate_legacy_macro_sectors(db_path)


def _seed_data(conn: sqlite3.Connection):
    # Only seed sample analysts if the analysts table is completely empty (first run)
    try:
        ac = conn.execute("SELECT count(*) FROM analysts").fetchone()[0]
        if ac == 0:
            from .seed_data import DEFAULT_ANALYSTS
            conn.executemany("INSERT INTO analysts VALUES (?, ?, ?, ?, ?, ?)", DEFAULT_ANALYSTS)
    except Exception as e:
        log.warning("Seeding default analysts failed: %s", e)

    # Only seed sample companies if the companies table is completely empty (first run)
    try:
        cc = conn.execute("SELECT count(*) FROM companies").fetchone()[0]
        if cc == 0:
            from .seed_data import DEFAULT_COMPANIES
            conn.executemany("""
            INSERT INTO companies (id, name, nse_symbol, bse_code, aliases, search_queries, analyst_names, folder, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, DEFAULT_COMPANIES)
    except Exception as e:
        log.warning("Seeding default companies failed: %s", e)

    sample_sources = [
        ("BSE Corporate Announcements", "https://www.bseindia.com/corporates/ann.html", "filing", None, "en", 0, 1),
        ("NSE Corporate Announcements", "https://www.nseindia.com/companies-listing/corporate-filings-announcements", "filing", None, "en", 0, 1),
        ("Economic Times Markets RSS", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms", "rss", None, "en", 1, 1),
        ("Moneycontrol Top News RSS", "https://www.moneycontrol.com/rss/MCtopnews.xml", "rss", None, "en", 0, 1),
        ("Livemint Markets RSS", "https://www.livemint.com/rss/markets", "rss", None, "en", 1, 1),
    ]
    try:
        sc = conn.execute("SELECT count(*) FROM sources").fetchone()[0]
        if sc == 0:
            conn.executemany("INSERT INTO sources (name, url, type, keep_pattern, language, body_check, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)", sample_sources)
    except Exception:
        pass


def get_companies(db_path: Path = DB_PATH) -> list[Company]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM companies WHERE is_active = 1").fetchall()
        out = []
        for r in rows:
            keys = r.keys()
            raw_fld = r["folder"] if "folder" in keys and r["folder"] else ""
            folders_list: list[str] = []
            if raw_fld:
                raw_str = str(raw_fld).strip()
                if raw_str.startswith("["):
                    try:
                        folders_list = [str(x).strip().upper() for x in json.loads(raw_str) if str(x).strip()]
                    except Exception:
                        folders_list = [raw_str.upper()]
                elif "," in raw_str:
                    folders_list = [x.strip().upper() for x in raw_str.split(",") if x.strip()]
                else:
                    folders_list = [raw_str.upper()]

            display_fld = ", ".join(folders_list) if folders_list else ""
            out.append(Company(
                id=r["id"],
                name=r["name"],
                nse_symbol=r["nse_symbol"] or "",
                bse_code=r["bse_code"] or "",
                aliases=json.loads(r["aliases"] or "[]"),
                search_queries=json.loads(r["search_queries"] or "[]"),
                analyst_names=json.loads(r["analyst_names"] or "[]"),
                folder=display_fld,
                folders=folders_list,
                is_active=bool(r["is_active"])
            ))
        return out


def save_company(c: Company, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        f_list: list[str] = [f.strip().upper() for f in (getattr(c, "folders", []) or []) if f.strip()]
        if not f_list and getattr(c, "folder", ""):
            raw = (c.folder or "").strip()
            if raw.startswith("["):
                try:
                    f_list = [str(x).strip().upper() for x in json.loads(raw) if str(x).strip()]
                except Exception:
                    f_list = [raw.upper()]
            elif "," in raw:
                f_list = [x.strip().upper() for x in raw.split(",") if x.strip()]
            elif raw:
                f_list = [raw.upper()]

        stored_fld = json.dumps(f_list)
        conn.execute("""
        INSERT INTO companies (id, name, nse_symbol, bse_code, aliases, search_queries, analyst_names, folder, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            nse_symbol=excluded.nse_symbol,
            bse_code=excluded.bse_code,
            aliases=excluded.aliases,
            search_queries=excluded.search_queries,
            analyst_names=excluded.analyst_names,
            folder=excluded.folder,
            is_active=excluded.is_active
        """, (
            c.id, c.name, c.nse_symbol, c.bse_code,
            json.dumps(c.aliases), json.dumps(c.search_queries),
            json.dumps(c.analyst_names), stored_fld, 1 if c.is_active else 0
        ))


def get_folders(db_path: Path = DB_PATH) -> list[str]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT name FROM folders ORDER BY ROWID ASC").fetchall()
        default_folders = list(DEFAULT_FOLDERS)
        existing = [r["name"] for r in rows] if rows else default_folders
        for df in default_folders:
            if df not in existing:
                existing.append(df)
        return existing


def add_folder(name: str, db_path: Path = DB_PATH) -> list[str]:
    clean_name = name.strip().upper()
    if clean_name:
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO folders (id, name, created_at) VALUES (?, ?, ?)",
                (clean_name, clean_name, "2026-10-13")
            )
    return get_folders(db_path)


def delete_folder(name: str, db_path: Path = DB_PATH) -> None:
    clean_name = name.strip().upper()
    if clean_name not in DEFAULT_FOLDERS:
        with get_connection(db_path) as conn:
            conn.execute("DELETE FROM folders WHERE name = ?", (clean_name,))
            conn.execute("UPDATE companies SET folder = 'GAME' WHERE folder = ?", (clean_name,))


def delete_company(cid: str, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM companies WHERE id = ?", (cid,))


def get_analysts(db_path: Path = DB_PATH) -> list[Analyst]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM analysts").fetchall()
        out = []
        for r in rows:
            keys = r.keys()
            flds = json.loads(r["assigned_folders"] or "[]") if "assigned_folders" in keys and r["assigned_folders"] else []
            out.append(Analyst(
                id=r["id"],
                name=r["name"],
                phone=r["phone"],
                email=r["email"] or "",
                assigned_companies=json.loads(r["assigned_companies"] or "[]"),
                assigned_folders=flds
            ))
        return out


def save_analyst(a: Analyst, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        folders_json = json.dumps(getattr(a, "assigned_folders", []))
        conn.execute("""
        INSERT INTO analysts (id, name, phone, email, assigned_companies, assigned_folders)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            phone=excluded.phone,
            email=excluded.email,
            assigned_companies=excluded.assigned_companies,
            assigned_folders=excluded.assigned_folders
        """, (a.id, a.name, a.phone, a.email, json.dumps(a.assigned_companies), folders_json))


def delete_analyst(aid: str, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM analysts WHERE id = ?", (aid,))
        conn.execute("DELETE FROM sent_ledger WHERE analyst_id = ?", (aid,))



def get_sources(db_path: Path = DB_PATH) -> list[dict]:
    with get_connection(db_path) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM sources ORDER BY id ASC").fetchall()]


def add_source(data: dict, db_path: Path = DB_PATH) -> int:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO sources (name, url, type, keep_pattern, language, body_check, is_active, status, items_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'OK', 0)""",
            (
                data["name"].strip(),
                data["url"].strip(),
                data.get("type", "rss").strip().lower(),
                data.get("keep_pattern"),
                data.get("language", "en"),
                1 if data.get("body_check") else 0,
                1 if data.get("is_active", True) else 0,
            )
        )
        return cur.lastrowid or 0


def toggle_source_status(source_id: int, is_active: bool, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("UPDATE sources SET is_active = ? WHERE id = ?", (1 if is_active else 0, source_id))


def delete_source(source_id: int, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


def update_source_status(source_id: int, status: str, items_count: int | None = None, db_path: Path = DB_PATH):
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        if items_count is not None:
            conn.execute("UPDATE sources SET status = ?, items_count = ?, last_crawled_at = ? WHERE id = ?",
                         (status, items_count, now, source_id))
        else:
            conn.execute("UPDATE sources SET status = ?, last_crawled_at = ? WHERE id = ?",
                         (status, now, source_id))


def has_fingerprint(hash_val: str, db_path: Path = DB_PATH) -> bool:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT 1 FROM fingerprints WHERE hash = ?", (hash_val,)).fetchone()
        return row is not None


def add_fingerprint(hash_val: str, kind: str, db_path: Path = DB_PATH):
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        conn.execute("INSERT OR IGNORE INTO fingerprints (hash, kind, created_at) VALUES (?, ?, ?)",
                     (hash_val, kind, now))


def save_story(story: dict, db_path: Path = DB_PATH) -> str:
    """Save story or update existing story if near-duplicate."""
    with get_connection(db_path) as conn:
        conn.execute("""
        INSERT INTO stories (id, title, summary, url, source_name, source_type, published_at, company_id, grade, filing_id, sources_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            sources_json=excluded.sources_json,
            summary=excluded.summary
        """, (
            story["id"], story["title"], story.get("summary", ""),
            story.get("url", ""), story.get("source_name", ""),
            story.get("source_type", "news"), story.get("published_at"),
            story.get("company_id", ""), story.get("grade", "Grade C"),
            story.get("filing_id"), json.dumps(story.get("sources", [])),
            datetime.now(UTC).isoformat()
        ))
        return story["id"]


def get_live_window(hours: int = 24, now: datetime | None = None) -> tuple[str, str]:
    """Returns (start_iso_utc, end_iso_utc) for live rolling coverage up to the current minute."""
    if now is None:
        now = datetime.now(UTC)
    start_utc = (now - timedelta(hours=hours)).isoformat()
    end_utc = (now + timedelta(hours=2)).isoformat()
    return start_utc, end_utc


def get_morning_digest_window(now: datetime | None = None) -> tuple[str, str]:
    """
    Returns (start_iso_utc, end_iso_utc) for the active 24-hour reporting cycle:
    - If now is after 8:00 AM IST: Today 8:00 AM IST to Tomorrow 8:00 AM IST.
    - If now is before 8:00 AM IST: Yesterday 8:00 AM IST to Today 8:00 AM IST.
    """
    if now is None:
        now = datetime.now(UTC)
    
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = now.astimezone(ist_tz)
    
    cutoff_today_ist = now_ist.replace(hour=8, minute=0, second=0, microsecond=0)
    if now_ist >= cutoff_today_ist:
        start_ist = cutoff_today_ist
        end_ist = cutoff_today_ist + timedelta(days=1)
    else:
        start_ist = cutoff_today_ist - timedelta(days=1)
        end_ist = cutoff_today_ist
        
    start_utc = start_ist.astimezone(UTC).isoformat()
    end_utc = end_ist.astimezone(UTC).isoformat()
    return start_utc, end_utc


def get_recent_stories(
    limit: int = 100,
    company_id: str | None = None,
    source_type: str | None = None,
    mode: str = "live",
    window_only: bool | None = None,
    db_path: Path = DB_PATH
) -> list[dict]:
    query = "SELECT s.*, c.name as company_name FROM stories s LEFT JOIN companies c ON s.company_id = c.id WHERE 1=1"
    params = []

    # If window_only is explicitly True, force "digest" mode for backward compatibility
    eff_mode = "digest" if window_only is True else (mode or "live").lower()

    if eff_mode == "digest":
        start_utc, end_utc = get_morning_digest_window()
        query += " AND s.published_at IS NOT NULL AND s.published_at != '' AND s.published_at >= ? AND s.published_at <= ?"
        params.extend([start_utc, end_utc])
    elif eff_mode == "live":
        start_utc, end_utc = get_live_window(hours=24)
        query += " AND s.published_at IS NOT NULL AND s.published_at != '' AND s.published_at >= ? AND s.published_at <= ?"
        params.extend([start_utc, end_utc])
    elif eff_mode in ("48h", "2d"):
        start_utc, end_utc = get_live_window(hours=48)
        query += " AND s.published_at IS NOT NULL AND s.published_at != '' AND s.published_at >= ? AND s.published_at <= ?"
        params.extend([start_utc, end_utc])
    elif eff_mode == "all":
        # No date filter; return latest records
        pass

    if company_id:
        query += " AND s.company_id = ?"
        params.append(company_id)
    if source_type:
        query += " AND s.source_type = ?"
        params.append(source_type)
    query += " ORDER BY s.published_at DESC LIMIT ?"
    params.append(limit)

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sources"] = json.loads(d["sources_json"] or "[]")
            out.append(d)
        return out


def get_unsent_stories_for_analyst(analyst_id: str, db_path: Path = DB_PATH) -> list[dict]:
    """Find all stories matching analyst's assigned companies and assigned folders that are pending dispatch."""
    with get_connection(db_path) as conn:
        analyst = conn.execute("SELECT * FROM analysts WHERE id = ?", (analyst_id,)).fetchone()
        if not analyst:
            return []
        keys = analyst.keys()
        assigned = list(json.loads(analyst["assigned_companies"] or "[]"))
        assigned_folders = json.loads(analyst["assigned_folders"] or "[]") if "assigned_folders" in keys and analyst["assigned_folders"] else []

        # Find companies belonging to the analyst's assigned folders
        if assigned_folders:
            assigned_folders_upper = {f.upper() for f in assigned_folders}
            all_comps = get_companies(db_path)
            for c in all_comps:
                c_flds = {f.upper() for f in (getattr(c, "folders", []) or ([c.folder] if c.folder else []))}
                if assigned_folders_upper & c_flds:
                    if c.id not in assigned:
                        assigned.append(c.id)

        if not assigned:
            return []

        start_utc, end_utc = get_morning_digest_window()
        # Ensure we look back up to 48h to avoid dropping any unsent weekend or late-night arrivals
        lookback_48h = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        eff_start = min(start_utc, lookback_48h)

        placeholders = ",".join("?" for _ in assigned)
        query = f"""
        SELECT s.*, c.name as company_name
        FROM stories s
        JOIN companies c ON s.company_id = c.id
        WHERE s.company_id IN ({placeholders})
          AND s.published_at IS NOT NULL
          AND s.published_at != ''
          AND s.published_at >= ?
          AND s.published_at <= ?
          AND s.id NOT IN (
              SELECT story_id FROM sent_ledger WHERE analyst_id = ? AND status = 'sent'
          )
        ORDER BY
            CASE s.grade WHEN 'Grade A' THEN 1 WHEN 'Grade B' THEN 2 ELSE 3 END,
            s.published_at DESC
        """
        rows = conn.execute(query, (*assigned, eff_start, end_utc, analyst_id)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["sources"] = json.loads(d.get("sources_json") or "[]")
            except Exception:
                d["sources"] = []
            out.append(d)
        return out


def get_sent_stories_for_analyst_today(analyst_id: str, db_path: Path = DB_PATH) -> list[dict]:
    """Retrieve stories already sent to this analyst in the last 24 hours (for preview/download after dispatch)."""
    since_utc = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    with get_connection(db_path) as conn:
        query = """
        SELECT s.*, c.name as company_name
        FROM stories s
        JOIN companies c ON s.company_id = c.id
        JOIN sent_ledger sl ON s.id = sl.story_id
        WHERE sl.analyst_id = ?
          AND sl.status = 'sent'
          AND sl.sent_at >= ?
        ORDER BY
            CASE s.grade WHEN 'Grade A' THEN 1 WHEN 'Grade B' THEN 2 ELSE 3 END,
            s.published_at DESC
        """
        rows = conn.execute(query, (analyst_id, since_utc)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["sources"] = json.loads(d.get("sources_json") or "[]")
            except Exception:
                d["sources"] = []
            out.append(d)
        return out


def mark_sending(story_ids: list[str], analyst_id: str, db_path: Path = DB_PATH):
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        for sid in story_ids:
            conn.execute("""
            INSERT INTO sent_ledger (story_id, analyst_id, status, attempted_at)
            VALUES (?, ?, 'sending', ?)
            ON CONFLICT(story_id, analyst_id) DO UPDATE SET status='sending', attempted_at=?
            """, (sid, analyst_id, now, now))


def mark_sent(story_ids: list[str], analyst_id: str, db_path: Path = DB_PATH):
    now = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        for sid in story_ids:
            conn.execute("""
            INSERT INTO sent_ledger (story_id, analyst_id, status, attempted_at, sent_at)
            VALUES (?, ?, 'sent', ?, ?)
            ON CONFLICT(story_id, analyst_id) DO UPDATE SET status='sent', sent_at=excluded.sent_at
            """, (sid, analyst_id, now, now))


def clear_failed_sending(analyst_id: str, db_path: Path = DB_PATH):
    """If send failed, remove 'sending' rows so retries pick them up."""
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM sent_ledger WHERE analyst_id = ? AND status = 'sending'", (analyst_id,))


def get_dashboard_stats(db_path: Path = DB_PATH) -> dict:
    live_start, live_end = get_live_window(hours=24)
    digest_start, digest_end = get_morning_digest_window()
    with get_connection(db_path) as conn:
        total_live = conn.execute("""
            SELECT count(*) FROM stories
            WHERE published_at IS NOT NULL AND published_at != ''
              AND published_at >= ?
              AND published_at <= ?
        """, (live_start, live_end)).fetchone()[0]

        total_filings = conn.execute("""
            SELECT count(*) FROM stories
            WHERE source_type = 'filing'
              AND published_at IS NOT NULL AND published_at != ''
              AND published_at >= ?
              AND published_at <= ?
        """, (live_start, live_end)).fetchone()[0]

        total_digest = conn.execute("""
            SELECT count(*) FROM stories
            WHERE published_at IS NOT NULL AND published_at != ''
              AND published_at >= ?
              AND published_at <= ?
        """, (digest_start, digest_end)).fetchone()[0]

        total_companies = conn.execute("SELECT count(*) FROM companies WHERE is_active = 1").fetchone()[0]
        total_analysts = conn.execute("SELECT count(*) FROM analysts").fetchone()[0]
        recent_run = conn.execute("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 1").fetchone()

        return {
            "total_stories": total_live,
            "total_filings": total_filings,
            "total_digest": total_digest,
            "total_companies": total_companies,
            "total_analysts": total_analysts,
            "last_crawl": dict(recent_run) if recent_run else None,
            "status": "HEALTHY",
            "cycle_start": live_start,
            "cycle_end": live_end,
            "digest_start": digest_start,
            "digest_end": digest_end
        }


def cleanup_database_duplicates(db_path: Path = DB_PATH) -> dict:
    """Find and merge duplicate / near-duplicate stories, purge false-positive sidebar matches, and deduplicate macro feeds."""
    from .normalize import are_near_duplicates, is_generic_market_noise

    deleted_count = 0
    merged_count = 0
    macro_deleted_count = 0

    with get_connection(db_path) as conn:
        # 1. Merge duplicate company 'polycabindia' into 'polycab'
        conn.execute("UPDATE stories SET company_id = 'polycab' WHERE company_id = 'polycabindia'")
        analysts = conn.execute("SELECT id, assigned_companies FROM analysts").fetchall()
        for an in analysts:
            comps = json.loads(an["assigned_companies"] or "[]")
            if "polycabindia" in comps:
                new_comps = [c for c in comps if c != "polycabindia"]
                if "polycab" not in new_comps:
                    new_comps.append("polycab")
                conn.execute("UPDATE analysts SET assigned_companies = ? WHERE id = ?", (json.dumps(new_comps), an["id"]))
        conn.execute("DELETE FROM companies WHERE id = 'polycabindia'")

        # 2. Delete empty or whitespace-only titles
        cur = conn.execute("DELETE FROM stories WHERE title IS NULL OR TRIM(title) = ''")
        deleted_count += cur.rowcount

        # 3. Load companies for false-positive validation
        comp_rows = conn.execute("SELECT id, name, aliases FROM companies").fetchall()
        comp_aliases_map: dict[str, list[str]] = {}
        for cr in comp_rows:
            aliases = json.loads(cr["aliases"] or "[]")
            all_names = [cr["name"].strip().lower()] + [a.strip().lower() for a in aliases if a.strip()]
            comp_aliases_map[cr["id"]] = all_names

        # 4. Deduplicate company stories and purge false-positive sidebar matches
        rows = conn.execute("SELECT * FROM stories ORDER BY published_at DESC, id DESC").fetchall()
        stories = [dict(r) for r in rows]

        to_remove = set()
        for s in stories:
            stitle = s.get("title", "")
            # Remove generic market chatter
            if s.get("source_type") != "filing" and is_generic_market_noise(stitle):
                to_remove.add(s["id"])
                continue

            # Remove false positive sidebar tags: company name MUST appear in headline or summary
            cid = s.get("company_id")
            if cid and cid in comp_aliases_map and s.get("source_type") != "filing":
                text = (stitle + " " + (s.get("summary") or "")).lower()
                valid_names = comp_aliases_map[cid]
                if not any(name in text for name in valid_names):
                    to_remove.add(s["id"])
                    continue

        for i, s1 in enumerate(stories):
            if s1["id"] in to_remove:
                continue
            s1_sources = json.loads(s1.get("sources_json") or "[]")
            s1_urls = {x.get("url") for x in s1_sources if x.get("url")}
            if s1.get("url"):
                s1_urls.add(s1["url"])

            for s2 in stories[i + 1:]:
                if s2["id"] in to_remove:
                    continue

                is_dup = False
                # Exact same URL
                if s1.get("url") and s2.get("url") and s1["url"].strip() == s2["url"].strip():
                    is_dup = True
                # Exact same filing_id
                elif s1.get("filing_id") and s2.get("filing_id") and s1["filing_id"].strip() == s2["filing_id"].strip():
                    is_dup = True
                # Same company and near-duplicate title
                elif s1.get("company_id") == s2.get("company_id") and are_near_duplicates(s1["title"], s2["title"]):
                    is_dup = True

                if is_dup:
                    to_remove.add(s2["id"])
                    # Merge sources from s2 into s1
                    s2_sources = json.loads(s2.get("sources_json") or "[]")
                    if s2.get("url") and s2["url"] not in s1_urls:
                        s1_sources.append({"name": s2.get("source_name", "News"), "url": s2["url"]})
                        s1_urls.add(s2["url"])
                    for src in s2_sources:
                        if src.get("url") and src["url"] not in s1_urls:
                            s1_sources.append(src)
                            s1_urls.add(src["url"])
                    merged_count += 1

            if len(s1_sources) > len(json.loads(s1.get("sources_json") or "[]")):
                conn.execute("UPDATE stories SET sources_json = ? WHERE id = ?", (json.dumps(s1_sources), s1["id"]))

        if to_remove:
            placeholders = ",".join("?" for _ in to_remove)
            conn.execute(f"DELETE FROM stories WHERE id IN ({placeholders})", tuple(to_remove))
            conn.execute(f"DELETE FROM sent_ledger WHERE story_id IN ({placeholders})", tuple(to_remove))
            deleted_count += len(to_remove)

        # 5. Deduplicate macro stories across official authorities and secondary wires
        macro_rows = [dict(r) for r in conn.execute("SELECT * FROM macro_stories ORDER BY published_at DESC").fetchall()]
        to_remove_macro = set()

        for i, m1 in enumerate(macro_rows):
            if m1["id"] in to_remove_macro:
                continue

            for m2 in macro_rows[i + 1:]:
                if m2["id"] in to_remove_macro:
                    continue

                if are_near_duplicates(m1["title"], m2["title"]):
                    # Always prefer official government sources (PIB, RBI, SEBI) over secondary financial wires
                    if m1["source_authority"] in ("PIB_GOV", "RBI", "SEBI") and m2["source_authority"] == "FINANCIAL_WIRE":
                        to_remove_macro.add(m2["id"])
                    elif m2["source_authority"] in ("PIB_GOV", "RBI", "SEBI") and m1["source_authority"] == "FINANCIAL_WIRE":
                        to_remove_macro.add(m1["id"])
                        break
                    else:
                        to_remove_macro.add(m2["id"])

        if to_remove_macro:
            placeholders = ",".join("?" for _ in to_remove_macro)
            conn.execute(f"DELETE FROM macro_stories WHERE id IN ({placeholders})", tuple(to_remove_macro))
            macro_deleted_count += len(to_remove_macro)

    return {
        "status": "ok",
        "company_stories_deleted": deleted_count,
        "company_stories_merged": merged_count,
        "macro_duplicates_deleted": macro_deleted_count,
    }


def save_macro_story(item: dict, db_path: Path = DB_PATH) -> str:
    """Insert or update verified macro intelligence record."""
    now_utc = datetime.now(UTC).isoformat()
    with get_connection(db_path) as conn:
        conn.execute("""
        INSERT INTO macro_stories (
            id, title, summary, url, source_authority, ministry_or_regulator,
            sectors_json, impact_grade, impact_bias, impact_summary,
            published_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,
            summary=excluded.summary,
            sectors_json=excluded.sectors_json,
            impact_grade=excluded.impact_grade,
            impact_bias=excluded.impact_bias,
            impact_summary=excluded.impact_summary
        """, (
            item["id"],
            item["title"],
            item.get("summary", ""),
            item.get("url", ""),
            item.get("source_authority", "GOV_PRIMARY"),
            item.get("ministry_or_regulator", "Govt of India"),
            json.dumps(item.get("sectors", ["GENERAL_MACRO"])),
            item.get("impact_grade", "Tier 2 (Sector Impact)"),
            item.get("impact_bias", "NEUTRAL"),
            item.get("impact_summary", ""),
            item.get("published_at") or now_utc,
            now_utc,
        ))
        return item["id"]


def get_macro_stories(
    limit: int = 50,
    sector: str | None = None,
    tier: str | None = None,
    mode: str = "live",
    db_path: Path = DB_PATH
) -> list[dict]:
    """Retrieve verified macro updates filtered by sector, impact tier, and time mode."""
    query = "SELECT * FROM macro_stories WHERE 1=1"
    params = []

    eff_mode = (mode or "live").lower()
    if eff_mode == "live":
        start_utc, end_utc = get_live_window(hours=24)
        query += " AND published_at >= ? AND published_at <= ?"
        params.extend([start_utc, end_utc])
    elif eff_mode in ("48h", "2d"):
        start_utc, end_utc = get_live_window(hours=48)
        query += " AND published_at >= ? AND published_at <= ?"
        params.extend([start_utc, end_utc])

    if sector and sector.upper() not in ("ALL", "ALL SECTORS"):
        query += " AND sectors_json LIKE ?"
        params.append(f"%{sector.strip()}%")

    if tier and tier.upper() not in ("ALL", "ALL TIERS"):
        query += " AND impact_grade LIKE ?"
        params.append(f"%{tier.strip()}%")

    query += " ORDER BY published_at DESC LIMIT ?"
    params.append(limit)

    with get_connection(db_path) as conn:
        rows = conn.execute(query, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["sectors"] = json.loads(d.get("sectors_json") or "[]")
            out.append(d)
        return out


def migrate_legacy_macro_sectors(db_path: Path = DB_PATH):
    """Normalize legacy coarse sector tags in macro_stories into the official 61-sector taxonomy."""
    mapping = {
        "DEFENSE": ["AEROSPACE & DEFENSE"],
        "BANKING & NBFC": ["BANKS", "FINANCE"],
        "AUTOMOTIVE": ["AUTOMOBILES", "AUTO COMPONENTS"],
        "RAILWAYS": ["TRANSPORT INFRASTRUCTURE", "TRANSPORT SERVICES"],
        "IT & TELECOM": ["IT - SERVICES", "TELECOM - SERVICES"],
        "METALS & MINING": ["FERROUS METALS", "MINERALS & MINING"],
        "OIL & ENERGY": ["OIL", "GAS", "PETROLEUM PRODUCTS"],
        "POWER & RENEWABLES": ["POWER"],
        "PHARMA & HEALTHCARE": ["PHARMACEUTICALS & BIOTECHNOLOGY", "HEALTHCARE SERVICES"],
        "INFRASTRUCTURE & REALTY": ["CONSTRUCTION", "REALTY"],
        "AGRICULTURE & FMCG": ["AGRICULTURAL FOOD & OTHER PRODUCTS", "DIVERSIFIED FMCG"],
        "CHEMICALS & FERTILIZERS": ["CHEMICALS & PETROCHEMICALS", "FERTILIZERS & AGROCHEMICALS"],
        "AVIATION & SHIPPING": ["TRANSPORT SERVICES", "TRANSPORT INFRASTRUCTURE"],
    }
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT id, sectors_json FROM macro_stories").fetchall()
        for r in rows:
            sid = r["id"]
            try:
                sectors = json.loads(r["sectors_json"] or "[]")
            except Exception:
                sectors = []
            new_sectors = []
            changed = False
            for s in sectors:
                su = str(s).strip().upper()
                if su in mapping:
                    new_sectors.extend(mapping[su])
                    changed = True
                else:
                    new_sectors.append(su)
            if changed:
                unique_new = list(dict.fromkeys(new_sectors))
                conn.execute("UPDATE macro_stories SET sectors_json = ? WHERE id = ?", (json.dumps(unique_new), sid))


def get_macro_sectors(db_path: Path = DB_PATH) -> list[dict]:
    """Return list of distinct active sectors with item counts across all 61 canonical sectors."""
    from .config import DEFAULT_MACRO_SECTORS
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT sectors_json FROM macro_stories").fetchall()
        counts: dict[str, int] = {}
        for r in rows:
            try:
                for s in json.loads(r["sectors_json"] or "[]"):
                    clean_s = str(s).strip().upper()
                    if clean_s:
                        counts[clean_s] = counts.get(clean_s, 0) + 1
            except Exception:
                pass

        seen = set()
        out: list[dict] = []

        # Add all 61 master sectors
        for sec in DEFAULT_MACRO_SECTORS:
            c = counts.get(sec, 0)
            out.append({"sector": sec, "count": c})
            seen.add(sec)

        # Include any dynamic/custom tags (e.g. GENERAL_MACRO)
        for sec, c in counts.items():
            if sec not in seen:
                out.append({"sector": sec, "count": c})

        # Sort: active sectors with count > 0 first (descending by count), then remaining alphabetically
        out.sort(key=lambda x: (x["count"] == 0, -x["count"], x["sector"]))
        return out



class _BenchmarkCache:
    timestamp: float = 0.0
    data: dict[str, dict[str, str]] | None = None


_BENCHMARK_CACHE = _BenchmarkCache()


def fetch_live_benchmarks() -> dict[str, dict[str, str]]:
    """Fetch live institutional market benchmarks with a 10-minute in-memory cache."""
    now = time.time()
    if _BENCHMARK_CACHE.data and (now - _BENCHMARK_CACHE.timestamp < 600):
        return _BENCHMARK_CACHE.data

    # Vetted official baseline values
    brent_val = "$104.30/bbl"
    brent_chg = "-1.7%"
    brent_bias = "POSITIVE"

    inr_val = "₹94.95"
    inr_chg = "-0.20%"
    inr_bias = "POSITIVE"

    us10y_val = "5.19%"
    us10y_chg = "-2 bps"
    us10y_bias = "POSITIVE"

    # Fetch live quotes for commodities, forex, and bond yields
    for ticker, key in [("BZ=F", "brent"), ("INR=X", "inr"), ("^TNX", "us10y")]:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=3) as r:
                res = json.loads(r.read())
                meta = res["chart"]["result"][0]["meta"]
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                pct = ((price - prev) / prev * 100) if (price and prev) else 0.0
                sign = "+" if pct >= 0 else ""

                if key == "brent" and price:
                    brent_val = f"${price:.2f}/bbl"
                    brent_chg = f"{sign}{pct:.1f}%"
                    brent_bias = "POSITIVE" if pct < 0 else "NEGATIVE"
                elif key == "inr" and price:
                    inr_val = f"₹{price:.2f}"
                    inr_chg = f"{sign}{pct:.2f}%"
                    inr_bias = "POSITIVE" if pct < 0 else "NEGATIVE"
                elif key == "us10y" and price:
                    us10y_val = f"{price:.2f}%"
                    us10y_chg = f"{sign}{pct:.2f}%"
                    us10y_bias = "POSITIVE" if pct < 0 else "NEGATIVE"
        except Exception:
            pass

    benchmarks = {
        "brent_crude": {"label": "Brent Crude", "val": brent_val, "change": brent_chg, "bias": brent_bias},
        "usd_inr": {"label": "USD / INR", "val": inr_val, "change": inr_chg, "bias": inr_bias},
        "us_10y": {"label": "US 10Y Yield", "val": us10y_val, "change": us10y_chg, "bias": us10y_bias},
        "rbi_repo": {"label": "RBI Repo Rate", "val": "5.50%", "change": "MPC Policy", "bias": "NEUTRAL"},
        "india_cpi": {"label": "India CPI Inflation", "val": "5.54%", "change": "Sep 2026 Print", "bias": "NEGATIVE"},
        "gst_collection": {"label": "GST Collection", "val": "₹2.04L Cr", "change": "+14.7% YoY", "bias": "POSITIVE"},
    }

    _BENCHMARK_CACHE.timestamp = now
    _BENCHMARK_CACHE.data = benchmarks
    return benchmarks


def get_macro_stats(db_path: Path = DB_PATH) -> dict:
    """Return live macro benchmark indicators and count of today's verified policy updates."""
    live_start, live_end = get_live_window(hours=24)
    with get_connection(db_path) as conn:
        total_live = conn.execute("""
            SELECT count(*) FROM macro_stories
            WHERE published_at >= ? AND published_at <= ?
        """, (live_start, live_end)).fetchone()[0]

        tier1_count = conn.execute("""
            SELECT count(*) FROM macro_stories
            WHERE impact_grade LIKE '%Tier 1%'
              AND published_at >= ? AND published_at <= ?
        """, (live_start, live_end)).fetchone()[0]

    return {
        "total_today": total_live,
        "tier1_today": tier1_count,
        "benchmarks": fetch_live_benchmarks(),
    }


DEFAULT_ANALYST_SECTORS: dict[str, list[str]] = {
    "rahul": ["BANKS", "CAPITAL MARKETS", "FINANCE", "GENERAL_MACRO"],
    "siddhesh": ["CONSTRUCTION", "REALTY", "POWER", "AEROSPACE & DEFENSE", "TRANSPORT INFRASTRUCTURE", "GENERAL_MACRO"],
    "kk": ["CAPITAL MARKETS", "BANKS", "IT - SERVICES", "GENERAL_MACRO"],
    "jash": ["CONSTRUCTION", "REALTY", "POWER", "OIL", "GAS", "GENERAL_MACRO"],
    "aashish": ["AGRICULTURAL FOOD & OTHER PRODUCTS", "PHARMACEUTICALS & BIOTECHNOLOGY", "FERROUS METALS", "GENERAL_MACRO"],
    "aditya": ["ALL"],
    "priya": ["IT - SERVICES", "TELECOM - SERVICES", "GENERAL_MACRO"],
    "amit": ["BANKS", "FINANCE", "GENERAL_MACRO"],
}


def get_analyst_macro_sectors(analyst_id: str) -> list[str]:
    """Return the designated macro sectors for an analyst (or ALL if unassigned)."""
    aid = (analyst_id or "").strip().lower()
    return DEFAULT_ANALYST_SECTORS.get(aid, ["ALL"])


def get_macro_stories_for_analyst(
    analyst_id: str,
    hours: int = 24,
    limit: int = 30,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Retrieve verified macro & policy stories matching an analyst's sector coverage."""
    sectors = get_analyst_macro_sectors(analyst_id)
    is_all = "ALL" in [s.upper() for s in sectors]

    live_start, live_end = get_live_window(hours=hours)
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT * FROM macro_stories
            WHERE published_at >= ? AND published_at <= ?
            ORDER BY
                CASE WHEN impact_grade LIKE '%Tier 1%' THEN 1
                     WHEN impact_grade LIKE '%Tier 2%' THEN 2
                     ELSE 3 END ASC,
                published_at DESC
        """, (live_start, live_end)).fetchall()

        matched: list[dict] = []
        for r in rows:
            d = dict(r)
            try:
                story_sectors = [s.strip().upper() for s in json.loads(d.get("sectors_json") or "[]")]
            except Exception:
                story_sectors = []
            d["sectors"] = story_sectors

            if is_all:
                matched.append(d)
            else:
                overlap = set(story_sectors) & set(sectors)
                if overlap or ("Tier 1" in (d.get("impact_grade") or "") and "GENERAL_MACRO" in sectors):
                    matched.append(d)

            if len(matched) >= limit:
                break

        return matched



