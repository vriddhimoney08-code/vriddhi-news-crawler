"""Database operations, SQLite schema, deduplication fingerprints, and sent ledger."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from .config import DB_PATH
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

        CREATE INDEX IF NOT EXISTS idx_stories_company ON stories(company_id);
        CREATE INDEX IF NOT EXISTS idx_stories_published ON stories(published_at);
        CREATE INDEX IF NOT EXISTS idx_ledger_lookup ON sent_ledger(analyst_id, status);
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
                ])
        except Exception:
            pass

        # Always sync seed companies so code edits in db.py reflect in SQLite
        if seed_defaults:
            _seed_data(conn)


def _seed_data(conn: sqlite3.Connection):
    sample_analysts = [
        ("rahul", "Rahul", "9820000001", "rahul@vriddhicapital.com", json.dumps(["tatamotors", "polycab"])),
        ("priya", "Priya", "9820000002", "priya@vriddhicapital.com", json.dumps(["reliance", "infosys"])),
        ("amit", "Amit", "9820000003", "amit@vriddhicapital.com", json.dumps(["hdfcbank"])),
    ]
    try:
        conn.executemany("INSERT OR IGNORE INTO analysts VALUES (?, ?, ?, ?, ?, '[]')", [
            (a[0], a[1], a[2], a[3], a[4]) for a in sample_analysts
        ])
    except Exception:
        pass

    sample_companies = [
        ("tatamotors", "Tata Motors Ltd", "TATAMOTORS", "500570",
         json.dumps(["Tata Motors", "JLR", "Jaguar Land Rover", "TaMo"]),
         json.dumps(['"Tata Motors"', '"JLR"']),
         json.dumps(["Rahul"]), "GAME", 1),
        ("polycab", "Polycab India Ltd", "POLYCAB", "542652",
         json.dumps(["Polycab", "Polycab Wires", "Polycab India"]),
         json.dumps(['"Polycab"']),
         json.dumps(["Rahul"]), "GAME", 1),
        ("reliance", "Reliance Industries Ltd", "RELIANCE", "500325",
         json.dumps(["Reliance", "RIL", "Jio", "Reliance Retail"]),
         json.dumps(['"Reliance Industries"', '"RIL"']),
         json.dumps(["Priya"]), "SET", 1),
        ("infosys", "Infosys Ltd", "INFY", "500209",
         json.dumps(["Infosys", "Infy", "Salil Parekh"]),
         json.dumps(['"Infosys"', '"Infy"']),
         json.dumps(["Priya"]), "SET", 1),
        ("hdfcbank", "HDFC Bank Ltd", "HDFCBANK", "500180",
         json.dumps(["HDFC Bank", "HDFC", "Sashidhar Jagdishan"]),
         json.dumps(['"HDFC Bank"']),
         json.dumps(["Amit"]), "MATCH", 1),
    ]
    conn.executemany("""
    INSERT INTO companies (id, name, nse_symbol, bse_code, aliases, search_queries, analyst_names, folder, is_active)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        folder=excluded.folder,
        aliases=excluded.aliases,
        search_queries=excluded.search_queries
    """, sample_companies)

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
        default_folders = ["GAME", "SET", "MATCH"]
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
    if clean_name not in ("GAME", "SET", "MATCH"):
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
        return int(cur.lastrowid or 0)


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


def get_morning_digest_window(now: datetime | None = None) -> tuple[str, str]:
    """
    Returns (start_iso_utc, end_iso_utc) for the strict 24-hour reporting cycle:
    Yesterday 8:00 AM IST to Today 8:00 AM IST.
    Any stories arriving after 8:00 AM today roll into tomorrow's briefing cycle.
    """
    if now is None:
        now = datetime.now(UTC)
    
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = now.astimezone(ist_tz)
    
    cutoff_today_ist = now_ist.replace(hour=8, minute=0, second=0, microsecond=0)
    if now_ist >= cutoff_today_ist:
        end_ist = cutoff_today_ist
        start_ist = end_ist - timedelta(days=1)
    else:
        end_ist = cutoff_today_ist - timedelta(days=1)
        start_ist = end_ist - timedelta(days=1)
        
    start_utc = start_ist.astimezone(UTC).isoformat()
    end_utc = end_ist.astimezone(UTC).isoformat()
    return start_utc, end_utc


def get_recent_stories(limit: int = 100, company_id: str | None = None, source_type: str | None = None, window_only: bool = True, db_path: Path = DB_PATH) -> list[dict]:
    query = "SELECT s.*, c.name as company_name FROM stories s LEFT JOIN companies c ON s.company_id = c.id WHERE 1=1"
    params = []
    if window_only:
        start_utc, end_utc = get_morning_digest_window()
        query += " AND s.published_at IS NOT NULL AND s.published_at != '' AND s.published_at >= ? AND s.published_at < ?"
        params.extend([start_utc, end_utc])

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
    """Find all stories matching analyst's assigned companies and assigned folders within the 8:00 AM - 8:00 AM window."""
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
        placeholders = ",".join("?" for _ in assigned)
        query = f"""
        SELECT s.*, c.name as company_name
        FROM stories s
        JOIN companies c ON s.company_id = c.id
        WHERE s.company_id IN ({placeholders})
          AND s.published_at IS NOT NULL
          AND s.published_at != ''
          AND s.published_at >= ?
          AND s.published_at < ?
          AND s.id NOT IN (
              SELECT story_id FROM sent_ledger WHERE analyst_id = ? AND status = 'sent'
          )
        ORDER BY
            CASE s.grade WHEN 'Grade A' THEN 1 WHEN 'Grade B' THEN 2 ELSE 3 END,
            s.published_at DESC
        """
        rows = conn.execute(query, (*assigned, start_utc, end_utc, analyst_id)).fetchall()
        return [dict(r) for r in rows]


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
    start_utc, end_utc = get_morning_digest_window()
    with get_connection(db_path) as conn:
        total_stories = conn.execute("""
            SELECT count(*) FROM stories
            WHERE published_at IS NOT NULL AND published_at != ''
              AND published_at >= ?
              AND published_at < ?
        """, (start_utc, end_utc)).fetchone()[0]

        total_filings = conn.execute("""
            SELECT count(*) FROM stories
            WHERE source_type = 'filing'
              AND published_at IS NOT NULL AND published_at != ''
              AND published_at >= ?
              AND published_at < ?
        """, (start_utc, end_utc)).fetchone()[0]

        total_companies = conn.execute("SELECT count(*) FROM companies WHERE is_active = 1").fetchone()[0]
        total_analysts = conn.execute("SELECT count(*) FROM analysts").fetchone()[0]
        recent_run = conn.execute("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 1").fetchone()

        return {
            "total_stories": total_stories,
            "total_filings": total_filings,
            "total_companies": total_companies,
            "total_analysts": total_analysts,
            "last_crawl": dict(recent_run) if recent_run else None,
            "status": "HEALTHY",
            "cycle_start": start_utc,
            "cycle_end": end_utc
        }
