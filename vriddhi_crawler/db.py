from __future__ import annotations
"""Database operations, SQLite schema, deduplication fingerprints, and sent ledger."""
import base64
import logging
import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timedelta, timezone
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
from pathlib import Path
from typing import Any

from .config import DB_PATH, DEFAULT_FOLDERS, GROUP_LOGOS_DIR
from .controlpanel import Analyst, Company, ClientGroup

log = logging.getLogger(__name__)


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
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

        CREATE TABLE IF NOT EXISTS dispatch_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT NOT NULL,
            dispatched_at TEXT NOT NULL,
            recipients_count INTEGER DEFAULT 0,
            stories_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'COMPLETED',
            details_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_dispatch_time ON dispatch_runs(dispatched_at);

        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT 'Admin',
            action_type TEXT NOT NULL,
            target_name TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS client_groups (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            morning_active INTEGER DEFAULT 1,
            evening_active INTEGER DEFAULT 1,
            client_ids TEXT DEFAULT '[]',
            created_at TEXT,
            logo_path TEXT DEFAULT '',
            logo_data TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS corporate_logos (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            mime_type TEXT NOT NULL,
            logo_data TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_corp_logos_entity ON corporate_logos(entity_type, entity_id);

        CREATE TABLE IF NOT EXISTS custom_news_topics (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            is_selected INTEGER DEFAULT 1,
            last_fetched_at TEXT,
            last_fetched_hours INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS custom_news_articles (
            id TEXT PRIMARY KEY,
            topic_id TEXT NOT NULL,
            topic_name TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            publisher TEXT DEFAULT 'Google News',
            source_engine TEXT DEFAULT 'Google News',
            url TEXT NOT NULL,
            published_at TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            FOREIGN KEY (topic_id) REFERENCES custom_news_topics(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_custom_news_topic ON custom_news_articles(topic_id);
        CREATE INDEX IF NOT EXISTS idx_custom_news_published ON custom_news_articles(published_at);

        CREATE TABLE IF NOT EXISTS custom_news_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            dispatch_time TEXT NOT NULL DEFAULT '11:00',
            dispatch_active INTEGER NOT NULL DEFAULT 1,
            window_hours INTEGER NOT NULL DEFAULT 24,
            interakt_template TEXT DEFAULT '',
            updated_at TEXT
        );
        """)

        # Safe migration for source_engine on custom_news_articles
        try:
            conn.execute("ALTER TABLE custom_news_articles ADD COLUMN source_engine TEXT DEFAULT 'Google News'")
        except Exception:
            pass

        # Safe migration for assigned_news_topics on analysts (defaults to [] so no client gets news until assigned)
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN assigned_news_topics TEXT DEFAULT '[]'")
        except Exception:
            pass

        # Seed single-row default schedule settings for News tab WhatsApp delivery
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO custom_news_settings (id, dispatch_time, dispatch_active, window_hours, interakt_template, updated_at)
                VALUES (1, '11:00', 1, 24, '', ?)
                """,
                (datetime.now(UTC).isoformat(),),
            )
        except Exception:
            pass

        # Safe migrations for frequency, day_of_week, day_of_month on custom_news_settings
        try:
            conn.execute("ALTER TABLE custom_news_settings ADD COLUMN frequency TEXT NOT NULL DEFAULT 'daily'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE custom_news_settings ADD COLUMN day_of_week INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE custom_news_settings ADD COLUMN day_of_month INTEGER NOT NULL DEFAULT 1")
        except Exception:
            pass

        # Safe migration for logo_path and logo_data on client_groups
        try:
            conn.execute("ALTER TABLE client_groups ADD COLUMN logo_path TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE client_groups ADD COLUMN logo_data TEXT DEFAULT ''")
        except Exception:
            pass

        # Safe migration for folder column
        try:
            conn.execute("ALTER TABLE companies ADD COLUMN folder TEXT DEFAULT ''")
        except Exception:
            pass

        # Safe migration for assigned_folders, macro_sectors, is_active, group_id, logo_path, logo_data on analysts
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN assigned_folders TEXT DEFAULT '[]'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN macro_sectors TEXT DEFAULT '[\"ALL\"]'")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN is_active INTEGER DEFAULT 1")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN group_id TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN logo_path TEXT DEFAULT ''")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE analysts ADD COLUMN logo_data TEXT DEFAULT ''")
        except Exception:
            pass

        # Auto-migrate any existing disk logos into corporate_logos table & client_groups.logo_data
        try:
            c_groups = conn.execute("SELECT id, logo_path, logo_data FROM client_groups WHERE logo_path != ''").fetchall()
            for cg in c_groups:
                cg_keys = cg.keys()
                l_data = cg["logo_data"] if "logo_data" in cg_keys and cg["logo_data"] else ""
                l_path = cg["logo_path"] if "logo_path" in cg_keys and cg["logo_path"] else ""
                if not l_data and l_path:
                    disk_p = GROUP_LOGOS_DIR / l_path
                    if disk_p.exists() and disk_p.is_file():
                        ext = disk_p.suffix.lower()
                        mime = "image/png"
                        if ext in (".jpg", ".jpeg"): mime = "image/jpeg"
                        elif ext == ".svg": mime = "image/svg+xml"
                        elif ext == ".webp": mime = "image/webp"
                        b64_str = base64.b64encode(disk_p.read_bytes()).decode("ascii")
                        uri = f"data:{mime};base64,{b64_str}"
                        conn.execute("UPDATE client_groups SET logo_data = ? WHERE id = ?", (uri, cg["id"]))
                        conn.execute("""
                            INSERT INTO corporate_logos (id, entity_type, entity_id, filename, mime_type, logo_data, created_at, updated_at)
                            VALUES (?, 'group', ?, ?, ?, ?, datetime('now'), datetime('now'))
                            ON CONFLICT(id) DO UPDATE SET logo_data=excluded.logo_data, updated_at=excluded.updated_at
                        """, (f"group_{cg['id']}", cg["id"], l_path, mime, uri))
        except Exception as e:
            log.warning("Disk-to-DB logo migration notice: %s", e)

        # Safe migration for is_excluded on stories and macro_stories
        try:
            conn.execute("ALTER TABLE stories ADD COLUMN is_excluded INTEGER DEFAULT 0")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE macro_stories ADD COLUMN is_excluded INTEGER DEFAULT 0")
        except Exception:
            pass

        # Table for custom AI system prompts
        conn.execute("""
        CREATE TABLE IF NOT EXISTS ai_prompts (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt_text TEXT NOT NULL,
            model TEXT DEFAULT 'gemini-1.5-flash',
            temperature REAL DEFAULT 0.2,
            max_tokens INTEGER DEFAULT 400,
            updated_at TEXT
        );
        """)

        # Seed default AI prompts if empty
        try:
            pc = conn.execute("SELECT count(*) FROM ai_prompts").fetchone()[0]
            if pc == 0:
                conn.execute("""
                    INSERT INTO ai_prompts (id, name, prompt_text, model, temperature, max_tokens, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    "equity_summary",
                    "Institutional Equity Research Summarizer",
                    DEFAULT_EQUITY_PROMPT,
                    "gemini-flash-lite-latest",
                    0.2,
                    400,
                    "Factory Default"
                ))
                conn.execute("""
                    INSERT INTO ai_prompts (id, name, prompt_text, model, temperature, max_tokens, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    "macro_directive",
                    "Macro Policy & Sovereign Directive Classifier",
                    DEFAULT_MACRO_PROMPT,
                    "gemini-flash-lite-latest",
                    0.1,
                    400,
                    "Factory Default"
                ))
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

    try:
        migrate_legacy_macro_sectors(db_path)
    except Exception as e:
        log.warning("migrate_legacy_macro_sectors skipped: %s", e)

    try:
        purge_macro_archive_stories(db_path)
    except Exception as e:
        log.warning("purge_macro_archive_stories skipped: %s", e)

    try:
        cleanup_misattributed_stories(db_path)
    except Exception as e:
        log.warning("cleanup_misattributed_stories skipped: %s", e)


def _seed_data(conn: sqlite3.Connection):
    # Seed default analysts ONLY if analysts table is completely empty (never overwrite/re-insert deleted)
    try:
        ac = conn.execute("SELECT count(*) FROM analysts").fetchone()[0]
        if ac == 0:
            from .seed_data import DEFAULT_ANALYSTS
            for a in DEFAULT_ANALYSTS:
                conn.execute("""
                INSERT OR IGNORE INTO analysts (id, name, phone, email, assigned_companies, assigned_folders)
                VALUES (?, ?, ?, ?, ?, ?)
                """, a)
    except Exception as e:
        log.warning("Seeding default analysts failed: %s", e)

    # Seed default companies ONLY if companies table is completely empty (never resurrect deleted companies)
    try:
        cc = conn.execute("SELECT count(*) FROM companies").fetchone()[0]
        if cc == 0:
            from .seed_data import DEFAULT_COMPANIES
            for c in DEFAULT_COMPANIES:
                conn.execute("""
                INSERT INTO companies (id, name, nse_symbol, bse_code, aliases, search_queries, analyst_names, folder, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    nse_symbol=excluded.nse_symbol,
                    bse_code=excluded.bse_code,
                    aliases=excluded.aliases,
                    search_queries=excluded.search_queries,
                    folder=excluded.folder
                """, c)
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


def get_companies(db_path: Path = DB_PATH, include_inactive: bool = True) -> list[Company]:
    with get_connection(db_path) as conn:
        q = "SELECT * FROM companies ORDER BY name ASC" if include_inactive else "SELECT * FROM companies WHERE is_active = 1 ORDER BY name ASC"
        rows = conn.execute(q).fetchall()
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
        conn.execute("DELETE FROM stories WHERE company_id = ?", (cid,))
        # Unlink deleted company from all analyst coverage assignments
        rows = conn.execute("SELECT id, assigned_companies FROM analysts").fetchall()
        for r in rows:
            try:
                assigned = json.loads(r["assigned_companies"] or "[]")
                if cid in assigned:
                    new_assigned = [x for x in assigned if x != cid]
                    conn.execute("UPDATE analysts SET assigned_companies = ? WHERE id = ?", (json.dumps(new_assigned), r["id"]))
            except Exception:
                pass


def get_analysts(db_path: Path = DB_PATH) -> list[Analyst]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM analysts ORDER BY name ASC").fetchall()
        out = []
        for r in rows:
            keys = r.keys()
            flds = json.loads(r["assigned_folders"] or "[]") if "assigned_folders" in keys and r["assigned_folders"] else []
            sectors = json.loads(r["macro_sectors"] or '["ALL"]') if "macro_sectors" in keys and r["macro_sectors"] else ["ALL"]
            news_topics = json.loads(r["assigned_news_topics"] or "[]") if "assigned_news_topics" in keys and r["assigned_news_topics"] else []
            is_act = bool(r["is_active"]) if "is_active" in keys and r["is_active"] is not None else True
            g_id = r["group_id"] if "group_id" in keys and r["group_id"] else ""
            l_path = r["logo_path"] if "logo_path" in keys and r["logo_path"] else ""
            l_data = r["logo_data"] if "logo_data" in keys and r["logo_data"] else ""
            out.append(Analyst(
                id=r["id"],
                name=r["name"],
                phone=r["phone"],
                email=r["email"] or "",
                assigned_companies=json.loads(r["assigned_companies"] or "[]"),
                assigned_folders=flds,
                macro_sectors=sectors,
                assigned_news_topics=news_topics,
                is_active=is_act,
                group_id=g_id,
                logo_path=l_path,
                logo_data=l_data,
            ))
        return out


def save_analyst(a: Analyst, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        folders_json = json.dumps(getattr(a, "assigned_folders", []))
        sectors_json = json.dumps(getattr(a, "macro_sectors", ["ALL"]))
        news_topics_json = json.dumps(getattr(a, "assigned_news_topics", []) or [])
        is_act = 1 if getattr(a, "is_active", True) else 0
        g_id = getattr(a, "group_id", "") or ""
        l_path = getattr(a, "logo_path", "") or ""
        l_data = getattr(a, "logo_data", "") or ""
        conn.execute("""
        INSERT INTO analysts (id, name, phone, email, assigned_companies, assigned_folders, macro_sectors, assigned_news_topics, is_active, group_id, logo_path, logo_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            phone=excluded.phone,
            email=excluded.email,
            assigned_companies=excluded.assigned_companies,
            assigned_folders=excluded.assigned_folders,
            macro_sectors=excluded.macro_sectors,
            assigned_news_topics=excluded.assigned_news_topics,
            is_active=excluded.is_active,
            group_id=excluded.group_id,
            logo_path=CASE WHEN excluded.logo_path != '' THEN excluded.logo_path ELSE analysts.logo_path END,
            logo_data=CASE WHEN excluded.logo_data != '' THEN excluded.logo_data ELSE analysts.logo_data END
        """, (a.id, a.name, a.phone, a.email, json.dumps(a.assigned_companies), folders_json, sectors_json, news_topics_json, is_act, g_id, l_path, l_data))


def delete_analyst(aid: str, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM analysts WHERE id = ?", (aid,))
        conn.execute("DELETE FROM sent_ledger WHERE analyst_id = ?", (aid,))


def save_corporate_logo(
    entity_type: str,
    entity_id: str,
    filename: str,
    mime_type: str,
    logo_data: str,
    db_path: Path = DB_PATH
) -> None:
    """Save or update corporate white-label logo binary/data URI in dedicated SQLite corporate_logos table."""
    logo_id = f"{entity_type}_{entity_id}"
    now_ts = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute("""
        INSERT INTO corporate_logos (id, entity_type, entity_id, filename, mime_type, logo_data, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            filename=excluded.filename,
            mime_type=excluded.mime_type,
            logo_data=excluded.logo_data,
            updated_at=excluded.updated_at
        """, (logo_id, entity_type, entity_id, filename, mime_type, logo_data, now_ts, now_ts))


def get_corporate_logo(entity_type: str, entity_id: str, db_path: Path = DB_PATH) -> dict | None:
    """Retrieve corporate white-label logo from dedicated SQLite corporate_logos table."""
    logo_id = f"{entity_type}_{entity_id}"
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM corporate_logos WHERE id = ?", (logo_id,)).fetchone()
        if row:
            return dict(row)
        row = conn.execute("SELECT * FROM corporate_logos WHERE entity_id = ? AND entity_type = ?", (entity_id, entity_type)).fetchone()
        return dict(row) if row else None


def delete_corporate_logo(entity_type: str, entity_id: str, db_path: Path = DB_PATH) -> bool:
    """Delete corporate white-label logo from dedicated SQLite corporate_logos table."""
    logo_id = f"{entity_type}_{entity_id}"
    with get_connection(db_path) as conn:
        res = conn.execute("DELETE FROM corporate_logos WHERE id = ? OR (entity_id = ? AND entity_type = ?)", (logo_id, entity_id, entity_type))
        return res.rowcount > 0


def get_client_groups(db_path: Path = DB_PATH) -> list[ClientGroup]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM client_groups ORDER BY name ASC").fetchall()
        out = []
        for r in rows:
            keys = r.keys()
            cids = json.loads(r["client_ids"] or "[]") if "client_ids" in keys and r["client_ids"] else []
            m_act = bool(r["morning_active"]) if "morning_active" in keys and r["morning_active"] is not None else True
            e_act = bool(r["evening_active"]) if "evening_active" in keys and r["evening_active"] is not None else True
            desc = r["description"] if "description" in keys and r["description"] else ""
            c_at = r["created_at"] if "created_at" in keys and r["created_at"] else ""
            l_path = r["logo_path"] if "logo_path" in keys and r["logo_path"] else ""
            l_data = r["logo_data"] if "logo_data" in keys and r["logo_data"] else ""
            out.append(ClientGroup(
                id=r["id"],
                name=r["name"],
                description=desc,
                morning_active=m_act,
                evening_active=e_act,
                client_ids=cids,
                created_at=c_at,
                logo_path=l_path,
                logo_data=l_data,
            ))
        return out


def save_client_group(g: ClientGroup, db_path: Path = DB_PATH) -> ClientGroup:
    from datetime import datetime, timezone
    with get_connection(db_path) as conn:
        now_ts = datetime.now(timezone.utc).isoformat()
        created = g.created_at or now_ts
        conn.execute("""
        INSERT INTO client_groups (id, name, description, morning_active, evening_active, client_ids, created_at, logo_path, logo_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            morning_active=excluded.morning_active,
            evening_active=excluded.evening_active,
            client_ids=excluded.client_ids,
            logo_path=CASE WHEN excluded.logo_path != '' THEN excluded.logo_path ELSE client_groups.logo_path END,
            logo_data=CASE WHEN excluded.logo_data != '' THEN excluded.logo_data ELSE client_groups.logo_data END
        """, (
            g.id,
            g.name,
            g.description,
            1 if g.morning_active else 0,
            1 if g.evening_active else 0,
            json.dumps(g.client_ids or []),
            created,
            g.logo_path or "",
            getattr(g, "logo_data", "") or "",
        ))
    return g


def delete_client_group(gid: str, db_path: Path = DB_PATH) -> bool:
    with get_connection(db_path) as conn:
        res = conn.execute("DELETE FROM client_groups WHERE id = ?", (gid,))
        return res.rowcount > 0


def get_client_group(gid: str, db_path: Path = DB_PATH) -> ClientGroup | None:
    groups = get_client_groups(db_path)
    for g in groups:
        if g.id == gid:
            return g
    return None



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


def get_source(source_id: int, db_path: Path = DB_PATH) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        return dict(row) if row else None


def update_source(source_id: int, data: dict, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE sources SET
               name = ?,
               url = ?,
               type = ?,
               keep_pattern = ?,
               language = ?,
               body_check = ?,
               is_active = ?
               WHERE id = ?""",
            (
                data["name"].strip(),
                data["url"].strip(),
                data.get("type", "rss").strip().lower(),
                data.get("keep_pattern"),
                data.get("language", "en"),
                1 if data.get("body_check") else 0,
                1 if data.get("is_active", True) else 0,
                source_id
            )
        )


def record_dispatch_run(
    run_type: str,
    recipients_count: int,
    stories_count: int,
    status: str = "COMPLETED",
    details: list | dict | None = None,
    db_path: Path = DB_PATH
) -> int:
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    details_str = json.dumps(details or [])
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO dispatch_runs (run_type, dispatched_at, recipients_count, stories_count, status, details_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_type, now_ist, recipients_count, stories_count, status, details_str)
        )
        return cur.lastrowid or 0


def get_dispatch_runs(limit: int = 20, db_path: Path = DB_PATH) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM dispatch_runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["details"] = json.loads(d.get("details_json") or "[]")
            except Exception:
                d["details"] = []
            result.append(d)
        return result


def log_audit_event(
    action_type: str,
    target_name: str,
    details: str,
    actor: str = "Admin",
    db_path: Path = DB_PATH
) -> int:
    """Record an administrative change or system event in the audit trail (strictly capped at 5 latest entries)."""
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %I:%M:%S %p IST")
    now_utc = datetime.now(UTC).isoformat()
    try:
        with get_connection(db_path) as conn:
            cur = conn.execute(
                """INSERT INTO audit_logs (timestamp, actor, action_type, target_name, details, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (now_ist, actor, action_type, target_name, details, now_utc)
            )
            # Auto-limit: Keep only latest 5 entries, vanish anything older
            conn.execute(
                """DELETE FROM audit_logs
                   WHERE id NOT IN (
                       SELECT id FROM audit_logs ORDER BY id DESC LIMIT 5
                   )"""
            )
            return cur.lastrowid or 0
    except Exception as exc:
        log.warning("Failed to record audit event: %s", exc)
        return 0


def get_audit_logs(limit: int = 5, db_path: Path = DB_PATH) -> list[dict]:
    """Retrieve recent audit logs in descending chronological order (strictly max 5)."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (min(limit, 5),)
        ).fetchall()
        return [dict(r) for r in rows]


def clear_audit_logs(db_path: Path = DB_PATH) -> int:
    """Vanish all audit logs and activity history."""
    with get_connection(db_path) as conn:
        cur = conn.execute("DELETE FROM audit_logs")
        return cur.rowcount




def clear_sent_ledger(analyst_id: str | None = None, db_path: Path = DB_PATH) -> int:
    with get_connection(db_path) as conn:
        if analyst_id:
            cur = conn.execute("DELETE FROM sent_ledger WHERE analyst_id = ?", (analyst_id,))
        else:
            cur = conn.execute("DELETE FROM sent_ledger")
        return cur.rowcount


# =========================================================================
# Phase 3: AI Prompts Management
# =========================================================================
DEFAULT_EQUITY_PROMPT = """You are a senior institutional equity research analyst covering Indian stock markets.
Evaluate this news article for: {company_name}

Headline: {headline}
Content snippet: {summary}

Determine:
1. Is this a material event for equity research (earnings, regulatory/SEBI action, corporate disclosure, M&A, large order win, debt default, credit rating change, senior management change, capex)?
2. Or is it noise (generic market wrap like 'Sensex rises', clickbait broker tip, retail stock gossip, algorithm price update, paid PR wire, sponsored advertorial, or promotional marketing)?

If the story is a promotional PR wire, sponsored content, or marketing advertorial, strictly mark "is_material": false, "grade": "Grade C", and "score": 1.

Respond strictly in JSON format:
{
  "is_material": true or false,
  "score": integer between 1 and 10 (1=spam/noise, 10=major earnings/regulatory action),
  "grade": "Grade A" (if score >= 8), "Grade B" (if score 6-7), or "Grade C" (if score < 6),
  "executive_summary": "Crisp 1-2 sentence institutional summary focusing on the financial/operational impact for {company_name}."
}"""

DEFAULT_MACRO_PROMPT = """You are a senior macroeconomic equity strategist for Indian stock markets.
Analyze this official government or regulatory announcement:

Authority: {authority}
Title: {title}
Snippet: {snippet}

Evaluate for institutional capital markets:
1. Impacted Sectors (select 1 to 3 most relevant from the official taxonomy: AEROSPACE & DEFENSE, AGRICULTURAL, COMMERCIAL & CONSTRUCTION VEHICLES, AGRICULTURAL FOOD & OTHER PRODUCTS, AUTO COMPONENTS, AUTOMOBILES, BANKS, BEVERAGES, CAPITAL MARKETS, CEMENT & CEMENT PRODUCTS, CHEMICALS & PETROCHEMICALS, CIGARETTES & TOBACCO PRODUCTS, COMMERCIAL SERVICES & SUPPLIES, CONSTRUCTION, CONSUMABLE FUELS, CONSUMER DURABLES, DIVERSIFIED, DIVERSIFIED FMCG, DIVERSIFIED METALS, ELECTRICAL EQUIPMENT, ENGINEERING SERVICES, ENTERTAINMENT, ETFS, FERROUS METALS, FERTILIZERS & AGROCHEMICALS, FINANCE, FINANCIAL TECHNOLOGY (FINTECH), FOOD PRODUCTS, GAS, HEALTHCARE EQUIPMENT & SUPPLIES, HEALTHCARE SERVICES, HOUSEHOLD PRODUCTS, INDUSTRIAL MANUFACTURING, INDUSTRIAL PRODUCTS, INSURANCE, IT - HARDWARE, IT - SERVICES, IT - SOFTWARE, LEISURE SERVICES, MEDIA, METALS & MINERALS TRADING, MINERALS & MINING, NON - FERROUS METALS, OIL, OTHER, OTHER CONSTRUCTION MATERIALS, OTHER CONSUMER SERVICES, OTHER SUB-SECTORS, OTHER UTILITIES, PAPER, FOREST & JUTE PRODUCTS, PERSONAL PRODUCTS, PETROLEUM PRODUCTS, PHARMACEUTICALS & BIOTECHNOLOGY, POWER, PRINTING & PUBLICATION, REALTY, RETAILING, TELECOM - EQUIPMENT & ACCESSORIES, TELECOM - SERVICES, TEXTILES & APPARELS, TRANSPORT INFRASTRUCTURE, TRANSPORT SERVICES, GENERAL_MACRO).
2. Materiality Tier:
   - "Tier 1 (Market Mover)" if it shifts repo rate, GDP/CPI, broad taxation, crude policy, or multi-billion dollar cabinet sanction.
   - "Tier 2 (Sector Impact)" if it catalysts a specific industry (e.g. anti-dumping duty, defense DAC clearance, PLI sanction).
   - "Tier 3 (Routine)" if procedural or administrative.
3. Market Bias: "POSITIVE", "NEGATIVE", or "NEUTRAL".
4. Implication: 1 crisp sentence explaining which listed equities/sectors benefit or face headwinds.

Respond strictly in valid JSON format:
{
  "sectors": ["AEROSPACE & DEFENSE", "CONSTRUCTION"],
  "impact_grade": "Tier 2 (Sector Impact)",
  "impact_bias": "POSITIVE",
  "impact_summary": "Beneficial for defense equipment manufacturers due to fresh indigenous procurement clearance."
}"""


def get_ai_prompts(db_path: Path = DB_PATH) -> list[dict]:
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT * FROM ai_prompts ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def get_ai_prompt(prompt_id: str, db_path: Path = DB_PATH) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM ai_prompts WHERE id = ?", (prompt_id,)).fetchone()
        return dict(row) if row else None


def save_ai_prompt(
    prompt_id: str,
    prompt_text: str,
    model: str = "gemini-flash-lite-latest",
    temperature: float = 0.2,
    max_tokens: int = 400,
    db_path: Path = DB_PATH
):
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    name = "Institutional Equity Research Summarizer" if prompt_id == "equity_summary" else "Macro Policy Classifier"
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO ai_prompts (id, name, prompt_text, model, temperature, max_tokens, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               prompt_text = excluded.prompt_text,
               model = excluded.model,
               temperature = excluded.temperature,
               max_tokens = excluded.max_tokens,
               updated_at = excluded.updated_at""",
            (
                prompt_id,
                name,
                prompt_text.strip(),
                model.strip(),
                temperature,
                max_tokens,
                now_ist
            )
        )


def reset_ai_prompt(prompt_id: str, db_path: Path = DB_PATH) -> dict:
    if prompt_id == "equity_summary":
        save_ai_prompt("equity_summary", DEFAULT_EQUITY_PROMPT, model="gemini-flash-lite-latest", temperature=0.2, max_tokens=400, db_path=db_path)
    elif prompt_id == "macro_directive":
        save_ai_prompt("macro_directive", DEFAULT_MACRO_PROMPT, model="gemini-flash-lite-latest", temperature=0.1, max_tokens=400, db_path=db_path)
    return get_ai_prompt(prompt_id, db_path=db_path) or {}


# =========================================================================
# Phase 3: Story Editorial & Manual Overrides
# =========================================================================
def get_story(story_id: str, db_path: Path = DB_PATH) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """SELECT s.*, c.name as company_name 
               FROM stories s 
               LEFT JOIN companies c ON s.company_id = c.id 
               WHERE s.id = ?""",
            (story_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["sources"] = json.loads(d.get("sources_json") or "[]")
        except Exception:
            d["sources"] = []
        return d


def update_story(story_id: str, data: dict, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE stories SET
               title = ?,
               summary = ?,
               grade = ?,
               company_id = ?,
               is_excluded = ?
               WHERE id = ?""",
            (
                data["title"].strip(),
                data.get("summary", "").strip(),
                data.get("grade", "Grade B").strip(),
                data.get("company_id", "").strip(),
                1 if data.get("is_excluded") else 0,
                story_id
            )
        )


def delete_story(story_id: str, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
        conn.execute("DELETE FROM sent_ledger WHERE story_id = ?", (story_id,))


def create_manual_story(data: dict, db_path: Path = DB_PATH) -> str:
    import uuid
    sid = f"manual-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    now_utc = datetime.now(timezone.utc).isoformat()
    sources_json = json.dumps([{"name": data.get("source_name", "Editorial Desk").strip() or "Editorial Desk", "url": data.get("url", "").strip()}])
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO stories (id, title, summary, url, source_name, source_type, published_at, company_id, grade, sources_json, created_at, is_excluded)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid,
                data["title"].strip(),
                data.get("summary", "").strip(),
                data.get("url", "").strip() or "#",
                data.get("source_name", "Manual Editorial Desk").strip() or "Manual Editorial Desk",
                "manual",
                now_ist,
                data.get("company_id", "").strip(),
                data.get("grade", "Grade A").strip(),
                sources_json,
                now_utc,
                0
            )
        )
    return sid


def get_macro_story(story_id: str, db_path: Path = DB_PATH) -> dict | None:
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM macro_stories WHERE id = ?", (story_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["sectors"] = json.loads(d.get("sectors_json") or "[]")
        except Exception:
            d["sectors"] = []
        return d


def update_macro_story(story_id: str, data: dict, db_path: Path = DB_PATH):
    sectors = data.get("sectors", ["GENERAL_MACRO"])
    if isinstance(sectors, str):
        sectors = [s.strip() for s in sectors.split(",") if s.strip()]
    sectors_json = json.dumps(sectors)
    with get_connection(db_path) as conn:
        conn.execute(
            """UPDATE macro_stories SET
               title = ?,
               summary = ?,
               source_authority = ?,
               sectors_json = ?,
               impact_grade = ?,
               impact_bias = ?,
               impact_summary = ?,
               is_excluded = ?
               WHERE id = ?""",
            (
                data["title"].strip(),
                data.get("summary", "").strip(),
                data.get("source_authority", "Editorial Desk").strip(),
                sectors_json,
                data.get("impact_grade", "Tier 2 (Sector Impact)").strip(),
                data.get("impact_bias", "NEUTRAL").strip(),
                data.get("impact_summary", "").strip() or data.get("summary", "").strip(),
                1 if data.get("is_excluded") else 0,
                story_id
            )
        )


def delete_macro_story(story_id: str, db_path: Path = DB_PATH):
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM macro_stories WHERE id = ?", (story_id,))


def create_manual_macro_story(data: dict, db_path: Path = DB_PATH) -> str:
    import uuid
    sid = f"macro-manual-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    now_utc = datetime.now(timezone.utc).isoformat()
    sectors = data.get("sectors", ["GENERAL_MACRO"])
    if isinstance(sectors, str):
        sectors = [s.strip() for s in sectors.split(",") if s.strip()]
    sectors_json = json.dumps(sectors)
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO macro_stories (id, title, summary, url, source_authority, ministry_or_regulator, sectors_json, impact_grade, impact_bias, impact_summary, published_at, created_at, is_excluded)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sid,
                data["title"].strip(),
                data.get("summary", "").strip(),
                data.get("url", "").strip() or "#",
                data.get("source_authority", "Editorial Desk").strip(),
                data.get("source_authority", "Editorial Desk").strip(),
                sectors_json,
                data.get("impact_grade", "Tier 1 (Market Mover)").strip(),
                data.get("impact_bias", "POSITIVE").strip(),
                data.get("impact_summary", "").strip() or data.get("summary", "").strip(),
                now_ist,
                now_utc,
                0
            )
        )
    return sid


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
    Anchored to 8:00 AM IST:
    - Yesterday 8:00 AM IST to Today (now + buffer) when checked in the morning/day.
    """
    if now is None:
        now = datetime.now(UTC)

    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = now.astimezone(ist_tz)

    cutoff_today_ist = now_ist.replace(hour=8, minute=0, second=0, microsecond=0)
    # The morning briefing covers the past 24 hours: yesterday 8:00 AM IST up through current morning
    start_ist = cutoff_today_ist - timedelta(days=1)
    end_ist = max(now_ist, cutoff_today_ist) + timedelta(hours=2)

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
    query = "SELECT s.*, c.name as company_name FROM stories s LEFT JOIN companies c ON s.company_id = c.id WHERE (s.is_excluded IS NULL OR s.is_excluded = 0)"
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
          AND (s.is_excluded IS NULL OR s.is_excluded = 0)
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
    query = "SELECT * FROM macro_stories WHERE (is_excluded IS NULL OR is_excluded = 0)"
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


def purge_macro_archive_stories(db_path: Path = DB_PATH) -> int:
    """Identify and mark is_excluded=1 for legacy factsheets, blogs, and historical PIB stories."""
    import re
    with get_connection(db_path) as conn:
        stale_titles = [
            "pm chairs ccs meeting%",
            "factsheet details%",
            "blogdescription%",
            "pib backgrounder%",
            "upi: transforming india's payment%",
            "financial inclusion in india:%",
            "%gdp performance%",
            "india's first hydrogen-powered train%",
            "paimana: strengthening%",
            "the prevention of insults to national honour%",
            "fcra: foreign contribution%",
            "semiconductor and ai revolution%",
            "ncw women helpline%",
            "%strategy for environmental economic%",
            "smp kolkata organises road show for balagarh%",
            "pm interacts with team india representatives at 48th worldsk%",
            "raksha rajya mantri chairs special joint state representative%",
            "quarterly release of performance monitoring dashboard%",
            "uidai unveils five new initiatives at aadhaar samvaad%",
            "ins trishul participates in 24th edition%",
            "historic first for jammu & kashmir (ut): mining development%",
            "cabinet approves scheme for support to ncrpb%",
            "ministry of corporate affairs hosts the pmis industry awards%",
            "indian railways announces five new reforms%",
            "provision of rs 13000 cr for biopharma shakti%",
            "%lease%out%",
            "%sq%ft%",
            "%sara ali khan%",
            "%hall of fame%",
            "%recruitment results%",
            "%subhashitam%",
            "%plot subdivision%",
        ]
        excluded_count = 0
        for pattern in stale_titles:
            cur = conn.execute(
                "UPDATE macro_stories SET is_excluded = 1 WHERE LOWER(title) LIKE ? AND (is_excluded IS NULL OR is_excluded = 0)",
                (pattern,)
            )
            excluded_count += cur.rowcount

        url_patterns = [
            "%FactsheetDetails.aspx%",
            "%blogsdescr.aspx%",
            "%BackgrounderDetail.aspx%",
        ]
        for upat in url_patterns:
            cur = conn.execute(
                "UPDATE macro_stories SET is_excluded = 1 WHERE url LIKE ? AND (is_excluded IS NULL OR is_excluded = 0)",
                (upat,)
            )
            excluded_count += cur.rowcount

        # Check any story whose URL already contains a PRID older than 2324000
        cur = conn.execute("SELECT id, url FROM macro_stories WHERE url LIKE '%PRID=%' AND (is_excluded IS NULL OR is_excluded = 0)")
        for row in cur.fetchall():
            m = re.search(r'PRID=(\d+)', row["url"], re.I)
            if m:
                try:
                    if int(m.group(1)) < 2324000:
                        conn.execute("UPDATE macro_stories SET is_excluded = 1 WHERE id = ?", (row["id"],))
                        excluded_count += 1
                except Exception:
                    pass

        return excluded_count


def cleanup_misattributed_stories(db_path: Path = DB_PATH) -> int:
    """Clean up Acutaas Chemicals aliases/queries and delete any misattributed cross-company stories."""
    deleted_count = 0
    with get_connection(db_path) as conn:
        try:
            row = conn.execute("SELECT aliases, search_queries FROM companies WHERE id = 'acutaaschemical'").fetchone()
            if row:
                aliases_raw, queries_raw = str(row["aliases"] or ""), str(row["search_queries"] or "")
                if "Ami Organics" in aliases_raw or "Ami Organics" in queries_raw:
                    conn.execute("""
                        UPDATE companies
                        SET aliases = '["Acutaas Chemicals", "Acutaas"]',
                            search_queries = '["\\"Acutaas Chemicals\\"", "\\"ACUTAAS\\" share"]'
                        WHERE id = 'acutaaschemical'
                    """)
                    log.info("Cleaned up Acutaas Chemicals aliases and search queries in SQLite DB")
        except Exception as e:
            log.warning("Acutaas company migration failed: %s", e)

        # Remove any misattributed stories where title mentions PVR or INOX but is tagged as Acutaas Chemicals
        try:
            cur = conn.execute("""
                DELETE FROM stories
                WHERE company_id = 'acutaaschemical'
                  AND (title LIKE '%PVR%' OR title LIKE '%INOX%')
            """)
            deleted_count = cur.rowcount
            if deleted_count > 0:
                log.info("Removed %d misattributed PVR/INOX stories from Acutaas Chemicals", deleted_count)
        except Exception as e:
            log.warning("PVR story cleanup failed: %s", e)

    return deleted_count


def get_macro_sectors(mode: str = "live", db_path: Path = DB_PATH) -> list[dict]:
    """Return list of distinct active sectors with item counts across all 61 canonical sectors."""
    from .config import DEFAULT_MACRO_SECTORS
    with get_connection(db_path) as conn:
        query = "SELECT sectors_json FROM macro_stories WHERE (is_excluded IS NULL OR is_excluded = 0)"
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

        rows = conn.execute(query, params).fetchall()
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


def reclassify_and_clean_macro_stories(db_path: Path = DB_PATH) -> dict[str, int]:
    """Reclassify existing macro stories using the updated 61-sector taxonomy and purge noise."""
    from .macro_ai import classify_macro_heuristically
    total = 0
    excluded = 0
    reclassified = 0
    with get_connection(db_path) as conn:
        rows = conn.execute("SELECT id, title, summary, ministry_or_regulator FROM macro_stories").fetchall()
        for r in rows:
            total += 1
            sid = r["id"]
            title = r["title"] or ""
            summary = r["summary"] or ""
            authority = r["ministry_or_regulator"] or ""

            res = classify_macro_heuristically(title, summary, authority)
            if not res.get("is_material", True):
                conn.execute("UPDATE macro_stories SET is_excluded = 1 WHERE id = ?", (sid,))
                excluded += 1
            else:
                conn.execute("""
                    UPDATE macro_stories
                    SET sectors_json = ?,
                        impact_grade = ?,
                        impact_bias = ?,
                        impact_summary = ?,
                        is_excluded = 0
                    WHERE id = ?
                """, (
                    json.dumps(res.get("sectors", ["GENERAL_MACRO"])),
                    res.get("impact_grade", "Tier 2 (Sector Impact)"),
                    res.get("impact_bias", "NEUTRAL"),
                    res.get("impact_summary", ""),
                    sid
                ))
                reclassified += 1
    return {
        "total": total,
        "excluded": excluded,
        "active": reclassified
    }



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
            WHERE (is_excluded IS NULL OR is_excluded = 0)
              AND published_at >= ? AND published_at <= ?
        """, (live_start, live_end)).fetchone()[0]

        tier1_count = conn.execute("""
            SELECT count(*) FROM macro_stories
            WHERE (is_excluded IS NULL OR is_excluded = 0)
              AND impact_grade LIKE '%Tier 1%'
              AND published_at >= ? AND published_at <= ?
        """, (live_start, live_end)).fetchone()[0]

    return {
        "total_today": total_live,
        "tier1_today": tier1_count,
        "benchmarks": fetch_live_benchmarks(),
    }


DEFAULT_ANALYST_SECTORS: dict[str, list[str]] = {
    "siddhesh": ["ALL"],
    "kk": ["ALL"],
    "jash": ["ALL"],
    "aashish": ["ALL"],
    "aditya": ["ALL"],
}


def get_analyst_macro_sectors(analyst_id: str, db_path: Path = DB_PATH) -> list[str]:
    """Return the designated macro sectors for an analyst from database (or ALL if unassigned)."""
    try:
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT macro_sectors FROM analysts WHERE id = ?", (analyst_id,)).fetchone()
            if row and row["macro_sectors"]:
                res = json.loads(row["macro_sectors"])
                if isinstance(res, list) and res:
                    return [s.strip().upper() for s in res if s.strip()]
    except Exception:
        pass
    aid = (analyst_id or "").strip().lower()
    return DEFAULT_ANALYST_SECTORS.get(aid, ["ALL"])


def get_macro_stories_for_analyst(
    analyst_id: str,
    hours: int = 24,
    limit: int = 100,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Retrieve verified macro & policy stories matching an analyst's sector coverage."""
    sectors = get_analyst_macro_sectors(analyst_id)
    is_all = "ALL" in [s.upper() for s in sectors]

    live_start, live_end = get_live_window(hours=hours)
    with get_connection(db_path) as conn:
        rows = conn.execute("""
            SELECT * FROM macro_stories
            WHERE (is_excluded IS NULL OR is_excluded = 0)
              AND published_at >= ? AND published_at <= ?
              AND NOT (
                impact_grade LIKE '%Tier 3%' AND (
                    sectors_json LIKE '%GENERAL_MACRO%' OR
                    sectors_json LIKE '%OTHER%'
                )
              )
            ORDER BY
                CASE WHEN impact_grade LIKE '%Tier 1%' THEN 1
                     WHEN impact_grade LIKE '%Tier 2%' THEN 2
                     ELSE 3 END ASC,
                published_at DESC
        """, (live_start, live_end)).fetchall()

        matched: list[dict] = []
        for r in rows:
            d = dict(r)
            title_l = (d.get("title") or "").lower()
            if any(w in title_l for w in [
                "lease out", "leases out", "leased out", "sq ft", "sqft", "square feet",
                "hall of fame", "recruitment results", "exam results", "admit card",
                "subhashitam", "sanskrit", "plot subdivision"
            ]):
                continue

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


# =========================================================================
# Isolated Custom Web News Tracker (News Tab Only)
# =========================================================================

def _slugify_topic_id(name: str) -> str:
    """Create a deterministic normalized ID for a custom news topic name."""
    import hashlib
    import re
    clean = re.sub(r"\s+", " ", (name or "").strip())
    slug = re.sub(r"[^a-z0-9]+", "-", clean.lower()).strip("-")
    if not slug:
        slug = "topic-" + hashlib.sha1(clean.lower().encode("utf-8")).hexdigest()[:10]
    return slug


def _format_ist_timestamp(iso_str: str | None) -> str:
    """Format a UTC ISO timestamp into a readable IST string."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST")
    except Exception:
        return iso_str


def get_custom_news_topics(db_path: Path = DB_PATH) -> list[dict]:
    """Return all saved custom news topics in insertion order."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM custom_news_topics ORDER BY ROWID ASC"
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["is_selected"] = bool(d.get("is_selected", 1))
        d["last_fetched_hours"] = int(d.get("last_fetched_hours") or 0)
        d["last_fetched_ist"] = _format_ist_timestamp(d.get("last_fetched_at"))
        out.append(d)
    return out


def add_custom_news_topics(names: list[str], db_path: Path = DB_PATH) -> dict:
    """Persist one or more custom topic/company names (case-insensitive deduplication)."""
    import re
    now_utc = datetime.now(UTC).isoformat()
    added: list[dict] = []
    skipped: list[str] = []

    conn = get_connection(db_path)
    try:
        with conn:
            existing_rows = conn.execute("SELECT id, name FROM custom_news_topics").fetchall()
            existing_ids = {r["id"] for r in existing_rows}
            existing_lower = {r["name"].strip().lower() for r in existing_rows}

            for raw_name in names:
                clean_name = re.sub(r"\s+", " ", (raw_name or "").strip())
                if not clean_name:
                    continue
                low = clean_name.lower()
                tid = _slugify_topic_id(clean_name)
                if low in existing_lower or tid in existing_ids:
                    skipped.append(clean_name)
                    continue
                conn.execute(
                    """
                    INSERT INTO custom_news_topics (id, name, is_selected, last_fetched_at, last_fetched_hours, created_at)
                    VALUES (?, ?, 1, NULL, 0, ?)
                    """,
                    (tid, clean_name, now_utc),
                )
                existing_ids.add(tid)
                existing_lower.add(low)
                added.append({
                    "id": tid,
                    "name": clean_name,
                    "is_selected": True,
                    "last_fetched_at": None,
                    "last_fetched_hours": 0,
                    "last_fetched_ist": "",
                    "created_at": now_utc,
                })
    finally:
        conn.close()

    return {
        "added": added,
        "skipped": skipped,
        "topics": get_custom_news_topics(db_path),
    }


def set_custom_news_topic_selected(topic_id: str, is_selected: bool, db_path: Path = DB_PATH) -> bool:
    """Persist selection state for a single saved custom news topic."""
    conn = get_connection(db_path)
    try:
        with conn:
            res = conn.execute(
                "UPDATE custom_news_topics SET is_selected = ? WHERE id = ?",
                (1 if is_selected else 0, topic_id),
            )
            return res.rowcount > 0
    finally:
        conn.close()


def set_all_custom_news_topics_selected(is_selected: bool, db_path: Path = DB_PATH) -> int:
    """Select or deselect all saved custom news topics."""
    conn = get_connection(db_path)
    try:
        with conn:
            res = conn.execute(
                "UPDATE custom_news_topics SET is_selected = ?",
                (1 if is_selected else 0,),
            )
            return res.rowcount
    finally:
        conn.close()


def delete_custom_news_topic(topic_id: str, db_path: Path = DB_PATH) -> bool:
    """Permanently delete a saved custom news topic, its cached articles, and unlink it from clients."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute("DELETE FROM custom_news_articles WHERE topic_id = ?", (topic_id,))
            res = conn.execute("DELETE FROM custom_news_topics WHERE id = ?", (topic_id,))
            # Unlink removed topic from any client's assigned_news_topics
            try:
                rows = conn.execute("SELECT id, assigned_news_topics FROM analysts").fetchall()
                for r in rows:
                    assigned = json.loads(r["assigned_news_topics"] or "[]")
                    if topic_id in assigned:
                        updated = [x for x in assigned if x != topic_id]
                        conn.execute(
                            "UPDATE analysts SET assigned_news_topics = ? WHERE id = ?",
                            (json.dumps(updated), r["id"]),
                        )
            except Exception:
                pass
            return res.rowcount > 0
    finally:
        conn.close()


def _parse_utc_iso(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    except Exception:
        return None


def _is_redirect_news_url(url: str | None) -> bool:
    u = (url or "").lower()
    return ("news.google.com/" in u) or ("bing.com/news/apiclick" in u)


def save_custom_news_articles(
    topic_id: str,
    topic_name: str,
    articles: list[dict],
    fetched_hours: int = 24,
    db_path: Path = DB_PATH,
) -> int:
    """Upsert fetched custom news articles with cross-source deduplication and 95-day retention."""
    import re
    from .normalize import canonical_url, clean_text
    from .sources.custom_news import are_same_topic_duplicates, is_paid_or_paywalled_news, is_relevant_to_topic

    now_utc = datetime.now(UTC)
    now_iso = now_utc.isoformat()
    prune_cutoff = (now_utc - timedelta(days=370)).isoformat()
    saved = 0

    conn = get_connection(db_path)
    try:
        with conn:
            # Load existing cached rows for this topic so repeat / multi-engine fetches never create duplicates
            existing_rows = conn.execute(
                """
                SELECT id, title, summary, publisher, source_engine, url, published_at
                FROM custom_news_articles
                WHERE topic_id = ? AND published_at >= ?
                """,
                (topic_id, prune_cutoff),
            ).fetchall()

            existing_items: list[dict] = []
            for r in existing_rows:
                keys = r.keys()
                ex_title = r["title"] or ""
                existing_items.append({
                    "id": r["id"],
                    "title": ex_title,
                    "summary": r["summary"] or "",
                    "publisher": r["publisher"] or "Google News",
                    "source_engine": (r["source_engine"] if "source_engine" in keys and r["source_engine"] else "Google News"),
                    "url": r["url"] or "",
                    "canon": canonical_url(r["url"]),
                    "exact": re.sub(r"[^a-z0-9]+", " ", clean_text(ex_title).lower()).strip(),
                    "dt": _parse_utc_iso(r["published_at"]),
                })

            for art in articles:
                new_title = art["title"]
                new_url = art["url"]
                new_summary = art.get("summary") or ""
                new_publisher = art.get("publisher") or "Google News"
                new_engine = art.get("source_engine") or "Google News"
                if is_paid_or_paywalled_news(new_title, new_publisher, new_url, new_summary):
                    continue
                if not is_relevant_to_topic(topic_name, new_title, new_summary, new_url):
                    continue
                new_canon = canonical_url(new_url)
                new_exact = re.sub(r"[^a-z0-9]+", " ", clean_text(new_title).lower()).strip()
                new_dt = _parse_utc_iso(art.get("published_at"))

                matched_existing = None
                for ex in existing_items:
                    if ex["id"] == art["id"]:
                        matched_existing = ex
                        break
                    if new_canon and ex["canon"] and new_canon == ex["canon"]:
                        matched_existing = ex
                        break
                    if new_exact and ex["exact"] and new_exact == ex["exact"]:
                        matched_existing = ex
                        break
                    # Topic-aware near-duplicate headline check within 72h (never falsely merges distinct stories)
                    if new_dt and ex["dt"] and abs((new_dt - ex["dt"]).total_seconds()) <= 72 * 3600:
                        if are_same_topic_duplicates(ex["title"], new_title, topic_name):
                            matched_existing = ex
                            break

                if matched_existing is not None:
                    # Upgrade existing row in-place if the incoming copy has a direct link or richer summary
                    best_url = matched_existing["url"]
                    best_engine = matched_existing["source_engine"]
                    if _is_redirect_news_url(best_url) and not _is_redirect_news_url(new_url):
                        best_url = new_url
                        best_engine = new_engine
                    best_summary = matched_existing["summary"]
                    if len(new_summary) > len(best_summary) + 15:
                        best_summary = new_summary
                    best_pub = matched_existing["publisher"]
                    if best_pub in ("Google News", "Bing News", "Yahoo News", "GDELT", "") and new_publisher not in ("Google News", ""):
                        best_pub = new_publisher

                    if (
                        best_url != matched_existing["url"]
                        or best_summary != matched_existing["summary"]
                        or best_pub != matched_existing["publisher"]
                        or best_engine != matched_existing["source_engine"]
                    ):
                        conn.execute(
                            """
                            UPDATE custom_news_articles
                            SET url = ?, summary = ?, publisher = ?, source_engine = ?, fetched_at = ?
                            WHERE id = ?
                            """,
                            (best_url, best_summary, best_pub, best_engine, now_iso, matched_existing["id"]),
                        )
                        matched_existing["url"] = best_url
                        matched_existing["canon"] = canonical_url(best_url)
                        matched_existing["summary"] = best_summary
                        matched_existing["publisher"] = best_pub
                        matched_existing["source_engine"] = best_engine
                    continue

                conn.execute(
                    """
                    INSERT INTO custom_news_articles (
                        id, topic_id, topic_name, title, summary, publisher, source_engine, url, published_at, fetched_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        topic_name = excluded.topic_name,
                        title = excluded.title,
                        summary = excluded.summary,
                        publisher = excluded.publisher,
                        source_engine = excluded.source_engine,
                        url = excluded.url,
                        published_at = excluded.published_at,
                        fetched_at = excluded.fetched_at
                    """,
                    (
                        art["id"],
                        topic_id,
                        topic_name,
                        new_title,
                        new_summary,
                        new_publisher,
                        new_engine,
                        new_url,
                        art["published_at"],
                        now_iso,
                    ),
                )
                existing_items.append({
                    "id": art["id"],
                    "title": new_title,
                    "summary": new_summary,
                    "publisher": new_publisher,
                    "source_engine": new_engine,
                    "url": new_url,
                    "canon": new_canon,
                    "exact": new_exact,
                    "dt": new_dt,
                })
                saved += 1

            # Prune articles older than 370 days (just over 1 Year) for this topic so cache stays lean
            conn.execute(
                "DELETE FROM custom_news_articles WHERE topic_id = ? AND published_at < ?",
                (topic_id, prune_cutoff),
            )

            # Keep track of the widest window recently fetched (reset if last fetch > 6h ago)
            row = conn.execute(
                "SELECT last_fetched_at, last_fetched_hours FROM custom_news_topics WHERE id = ?",
                (topic_id,),
            ).fetchone()
            effective_hours = fetched_hours
            if row and row["last_fetched_at"]:
                try:
                    prev_dt = datetime.fromisoformat(str(row["last_fetched_at"]).replace("Z", "+00:00"))
                    if prev_dt.tzinfo is None:
                        prev_dt = prev_dt.replace(tzinfo=UTC)
                    if (now_utc - prev_dt) < timedelta(hours=6):
                        effective_hours = max(effective_hours, int(row["last_fetched_hours"] or 0))
                except Exception:
                    pass

            conn.execute(
                """
                UPDATE custom_news_topics
                SET last_fetched_at = ?, last_fetched_hours = ?
                WHERE id = ?
                """,
                (now_iso, effective_hours, topic_id),
            )
    finally:
        conn.close()

    return saved


def get_custom_news_state(
    hours: int = 24,
    topic_ids: list[str] | None = None,
    search: str | None = None,
    scope: str = "all",
    db_path: Path = DB_PATH,
) -> dict:
    """Return saved custom news topics and cached articles grouped by topic for the requested time window."""
    from .normalize import is_reputable_publisher
    from .sources.custom_news import is_paid_or_paywalled_news, is_relevant_to_topic

    hours_val = hours if hours in (24, 48, 720, 4320, 8760) else 24
    start_utc, end_utc = get_live_window(hours=hours_val)
    topics = get_custom_news_topics(db_path)

    selected_filter = set(topic_ids) if topic_ids else None
    search_q = (search or "").strip().lower()
    financial_only = (scope or "all").strip().lower() == "financial"

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """
            SELECT * FROM custom_news_articles
            WHERE published_at >= ? AND published_at <= ?
            ORDER BY published_at DESC
            """,
            (start_utc, end_utc),
        ).fetchall()
    finally:
        conn.close()

    articles_by_topic: dict[str, list[dict]] = {}
    paid_ids_to_prune: list[str] = []
    for r in rows:
        d = dict(r)
        if not d.get("source_engine"):
            d["source_engine"] = "Google News"
        if is_paid_or_paywalled_news(
            d.get("title") or "",
            d.get("publisher") or "",
            d.get("url"),
            d.get("summary") or "",
        ) or not is_relevant_to_topic(
            d.get("topic_name") or "",
            d.get("title") or "",
            d.get("summary") or "",
            d.get("url"),
        ):
            paid_ids_to_prune.append(d["id"])
            continue
        if financial_only and not is_reputable_publisher(d.get("publisher") or "", d.get("url"), "news"):
            continue
        if search_q:
            haystack = f"{d.get('title', '')} {d.get('summary', '')} {d.get('publisher', '')} {d.get('topic_name', '')}".lower()
            if search_q not in haystack:
                continue
        d["published_ist"] = _format_ist_timestamp(d.get("published_at"))
        articles_by_topic.setdefault(d["topic_id"], []).append(d)

    # Cleanly remove any previously cached paywalled rows from SQLite
    if paid_ids_to_prune:
        pconn = get_connection(db_path)
        try:
            with pconn:
                pconn.executemany(
                    "DELETE FROM custom_news_articles WHERE id = ?",
                    [(pid,) for pid in paid_ids_to_prune],
                )
        finally:
            pconn.close()

    # Annotate every saved topic with article count in this window
    latest_fetched_at: str | None = None
    for t in topics:
        t_articles = articles_by_topic.get(t["id"], [])
        t["article_count"] = len(t_articles)
        if t.get("last_fetched_at"):
            if not latest_fetched_at or str(t["last_fetched_at"]) > latest_fetched_at:
                latest_fetched_at = str(t["last_fetched_at"])

    # Build grouped view for either explicitly passed topic_ids, or all selected topics (falling back to all if none selected)
    any_selected = any(t["is_selected"] for t in topics)
    groups: list[dict] = []
    total_articles = 0
    needs_wider_fetch = False

    for t in topics:
        if selected_filter is not None:
            if t["id"] not in selected_filter:
                continue
        elif any_selected and not t["is_selected"]:
            continue

        t_articles = articles_by_topic.get(t["id"], [])
        total_articles += len(t_articles)
        if t.get("last_fetched_at") and int(t.get("last_fetched_hours") or 0) < hours_val:
            needs_wider_fetch = True

        groups.append({
            "topic_id": t["id"],
            "topic_name": t["name"],
            "is_selected": t["is_selected"],
            "last_fetched_at": t.get("last_fetched_at"),
            "last_fetched_ist": t.get("last_fetched_ist", ""),
            "last_fetched_hours": int(t.get("last_fetched_hours") or 0),
            "article_count": len(t_articles),
            "articles": t_articles,
        })

    return {
        "status": "ok",
        "hours": hours_val,
        "scope": "financial" if financial_only else "all",
        "topics": topics,
        "groups": groups,
        "total_articles": total_articles,
        "last_fetched_at": latest_fetched_at,
        "last_fetched_ist": _format_ist_timestamp(latest_fetched_at),
        "needs_wider_fetch": needs_wider_fetch,
    }


CUSTOM_NEWS_WINDOW_LABELS: dict[int, str] = {
    24: "Last 24 hrs",
    48: "Last 48 hrs",
    720: "Last 1M",
    4320: "Last 6M",
    8760: "Last 1 Year",
}

CUSTOM_NEWS_FREQUENCIES: dict[str, str] = {
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
    "quarterly": "Quarterly",
}

CUSTOM_NEWS_WEEKDAYS: list[str] = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CUSTOM_NEWS_QUARTER_MONTHS: tuple[int, ...] = (1, 4, 7, 10)  # Jan, Apr, Jul, Oct


def _ordinal_day(day: int) -> str:
    if 11 <= (day % 100) <= 13:
        return f"{day}th"
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{day}{suffix}"


def _format_frequency_summary(frequency: str, day_of_week: int, day_of_month: int) -> str:
    if frequency == "weekly":
        wd = CUSTOM_NEWS_WEEKDAYS[day_of_week] if 0 <= day_of_week <= 6 else "Mon"
        return f"Weekly ({wd})"
    if frequency == "monthly":
        return f"Monthly ({_ordinal_day(day_of_month)})"
    if frequency == "quarterly":
        return f"Quarterly ({_ordinal_day(day_of_month)} of Jan/Apr/Jul/Oct)"
    return "Daily"


def _format_time_12h(hhmm: str) -> str:
    """Convert 24-hour 'HH:MM' into 'hh:mm AM/PM'."""
    try:
        parts = [int(p) for p in hhmm.strip().split(":")]
        dt = datetime(2026, 1, 1, parts[0], parts[1])
        return dt.strftime("%I:%M %p")
    except Exception:
        return hhmm or "11:00 AM"


def should_fire_custom_news_now(sched: dict[str, Any], now_ist: datetime | None = None) -> bool:
    """Return True if the saved News WhatsApp schedule matches the current IST date and minute."""
    if not sched.get("dispatch_active"):
        return False
    cur = now_ist if now_ist is not None else datetime.now(IST)
    if cur.strftime("%H:%M") != str(sched.get("dispatch_time") or "").strip():
        return False

    freq = str(sched.get("frequency") or "daily").strip().lower()
    if freq == "weekly":
        return cur.weekday() == int(sched.get("day_of_week", 0))
    if freq == "monthly":
        return cur.day == int(sched.get("day_of_month", 1))
    if freq == "quarterly":
        return (cur.month in CUSTOM_NEWS_QUARTER_MONTHS) and (cur.day == int(sched.get("day_of_month", 1)))
    return True


def _compute_next_ist_run(
    hhmm: str,
    frequency: str = "daily",
    day_of_week: int = 0,
    day_of_month: int = 1,
    now_ist: datetime | None = None,
) -> str:
    """Return human-readable next scheduled IST run for Daily, Weekly, Monthly, or Quarterly."""
    try:
        parts = [int(p) for p in hhmm.strip().split(":")]
        hour, minute = parts[0], parts[1]
        cur = now_ist if now_ist is not None else datetime.now(IST)
        freq = frequency if frequency in CUSTOM_NEWS_FREQUENCIES else "daily"
        dow = day_of_week if 0 <= day_of_week <= 6 else 0
        dom = day_of_month if 1 <= day_of_month <= 28 else 1

        target: datetime | None = None
        if freq == "daily":
            cand = cur.replace(hour=hour, minute=minute, second=0, microsecond=0)
            target = cand if cand > cur else cand + timedelta(days=1)
        elif freq == "weekly":
            days_ahead = (dow - cur.weekday()) % 7
            cand = (cur + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
            if cand <= cur:
                cand += timedelta(days=7)
            target = cand
        elif freq == "monthly":
            y, m = cur.year, cur.month
            cand = datetime(y, m, dom, hour, minute, tzinfo=IST)
            if cand <= cur:
                if m == 12:
                    y, m = y + 1, 1
                else:
                    m += 1
                cand = datetime(y, m, dom, hour, minute, tzinfo=IST)
            target = cand
        else:  # quarterly (Jan, Apr, Jul, Oct)
            for year in (cur.year, cur.year + 1):
                for month in CUSTOM_NEWS_QUARTER_MONTHS:
                    cand = datetime(year, month, dom, hour, minute, tzinfo=IST)
                    if cand > cur:
                        target = cand
                        break
                if target is not None:
                    break

        if target is None:
            return f"Scheduled at {hhmm} IST"

        time_str = target.strftime("%I:%M %p IST")
        if target.date() == cur.date():
            return f"Today, {time_str}"
        if target.date() == (cur + timedelta(days=1)).date():
            return f"Tomorrow, {time_str}"
        if freq == "weekly":
            return f"{target.strftime('%a, %d %b')} • {time_str}"
        return f"{target.strftime('%d %b %Y')} • {time_str}" if target.year != cur.year else f"{target.strftime('%d %b')} • {time_str}"
    except Exception:
        return f"Scheduled at {hhmm} IST"


def get_custom_news_schedule(db_path: Path = DB_PATH) -> dict[str, Any]:
    """Return editable WhatsApp delivery schedule, frequency & saved time window for the News tab."""
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM custom_news_settings WHERE id = 1").fetchone()
    finally:
        conn.close()

    keys = row.keys() if row else []
    dispatch_time = (row["dispatch_time"] if row and row["dispatch_time"] else "11:00").strip()
    dispatch_active = bool(row["dispatch_active"]) if row and row["dispatch_active"] is not None else True
    raw_hours = int(row["window_hours"]) if row and row["window_hours"] else 24
    if raw_hours == 168:
        window_hours = 720
    elif raw_hours == 2160:
        window_hours = 4320
    else:
        window_hours = raw_hours if raw_hours in CUSTOM_NEWS_WINDOW_LABELS else 24
    interakt_template = (row["interakt_template"] if row and row["interakt_template"] else "").strip()
    updated_at = (row["updated_at"] if row and row["updated_at"] else "")

    raw_freq = str(row["frequency"]).strip().lower() if (row and "frequency" in keys and row["frequency"]) else "daily"
    frequency = raw_freq if raw_freq in CUSTOM_NEWS_FREQUENCIES else "daily"
    raw_dow = int(row["day_of_week"]) if (row and "day_of_week" in keys and row["day_of_week"] is not None) else 0
    day_of_week = raw_dow if 0 <= raw_dow <= 6 else 0
    raw_dom = int(row["day_of_month"]) if (row and "day_of_month" in keys and row["day_of_month"] is not None) else 1
    day_of_month = raw_dom if 1 <= raw_dom <= 28 else 1

    assigned_clients = [
        a for a in get_analysts(db_path)
        if getattr(a, "is_active", True) and len(getattr(a, "assigned_news_topics", []) or []) > 0
    ]

    return {
        "dispatch_time": dispatch_time,
        "dispatch_time_12h": _format_time_12h(dispatch_time),
        "dispatch_active": dispatch_active,
        "window_hours": window_hours,
        "window_label": CUSTOM_NEWS_WINDOW_LABELS.get(window_hours, "Last 24 hrs"),
        "frequency": frequency,
        "frequency_label": CUSTOM_NEWS_FREQUENCIES.get(frequency, "Daily"),
        "frequency_summary": _format_frequency_summary(frequency, day_of_week, day_of_month),
        "day_of_week": day_of_week,
        "day_of_month": day_of_month,
        "interakt_template": interakt_template,
        "updated_at": updated_at,
        "next_run_ist": (
            _compute_next_ist_run(dispatch_time, frequency, day_of_week, day_of_month)
            if dispatch_active
            else "Delivery Paused"
        ),
        "assigned_clients_count": len(assigned_clients),
    }


def save_custom_news_schedule(
    dispatch_time: str | None = None,
    dispatch_active: bool | None = None,
    window_hours: int | None = None,
    interakt_template: str | None = None,
    frequency: str | None = None,
    day_of_week: int | None = None,
    day_of_month: int | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Persist editable WhatsApp send time, frequency, day, active flag, and digest window for the News tab."""
    import re
    current = get_custom_news_schedule(db_path)

    new_time = current["dispatch_time"]
    if dispatch_time is not None:
        cleaned_t = dispatch_time.strip()
        if re.match(r"^([01]\d|2[0-3]):[0-5]\d$", cleaned_t):
            new_time = cleaned_t

    new_active = current["dispatch_active"] if dispatch_active is None else bool(dispatch_active)

    new_hours = current["window_hours"]
    if window_hours is not None and window_hours in CUSTOM_NEWS_WINDOW_LABELS:
        new_hours = window_hours

    new_freq = current["frequency"]
    if frequency is not None:
        cleaned_f = frequency.strip().lower()
        if cleaned_f in CUSTOM_NEWS_FREQUENCIES:
            new_freq = cleaned_f

    new_dow = current["day_of_week"]
    if day_of_week is not None and 0 <= day_of_week <= 6:
        new_dow = day_of_week

    new_dom = current["day_of_month"]
    if day_of_month is not None and 1 <= day_of_month <= 28:
        new_dom = day_of_month

    new_tpl = current["interakt_template"] if interakt_template is None else interakt_template.strip()
    now_iso = datetime.now(UTC).isoformat()

    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO custom_news_settings (
                    id, dispatch_time, dispatch_active, window_hours, interakt_template,
                    frequency, day_of_week, day_of_month, updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    dispatch_time = excluded.dispatch_time,
                    dispatch_active = excluded.dispatch_active,
                    window_hours = excluded.window_hours,
                    interakt_template = excluded.interakt_template,
                    frequency = excluded.frequency,
                    day_of_week = excluded.day_of_week,
                    day_of_month = excluded.day_of_month,
                    updated_at = excluded.updated_at
                """,
                (new_time, 1 if new_active else 0, new_hours, new_tpl, new_freq, new_dow, new_dom, now_iso),
            )
    finally:
        conn.close()

    return get_custom_news_schedule(db_path)


def get_custom_news_digest_for_analyst(
    analyst_id: str,
    hours: int | None = None,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Compile a client's personalized News PDF dataset across their assigned News tab topics.

    Always returns every assigned topic (even with 0 articles -> 'No news from this topic')
    and always includes all unique free articles within the saved window (no cross-day sent-ledger suppression).
    """
    sched = get_custom_news_schedule(db_path)
    hours_val = hours if (hours is not None and hours in CUSTOM_NEWS_WINDOW_LABELS) else sched["window_hours"]
    window_label = CUSTOM_NEWS_WINDOW_LABELS.get(hours_val, "Last 24 hrs")

    analysts = {a.id: a for a in get_analysts(db_path)}
    analyst = analysts.get(analyst_id)
    assigned_ids = list(getattr(analyst, "assigned_news_topics", []) or []) if analyst else []

    all_topics = {t["id"]: t for t in get_custom_news_topics(db_path)}
    valid_assigned_ids = [tid for tid in assigned_ids if tid in all_topics]

    if not valid_assigned_ids:
        return {
            "analyst_id": analyst_id,
            "analyst_name": analyst.name if analyst else analyst_id,
            "hours": hours_val,
            "window_label": window_label,
            "assigned_topic_ids": [],
            "assigned_topic_names": [],
            "topic_groups": [],
            "total_articles": 0,
            "topics_with_news": 0,
            "topics_without_news": 0,
        }

    state = get_custom_news_state(hours=hours_val, topic_ids=valid_assigned_ids, scope="all", db_path=db_path)
    group_map = {g["topic_id"]: g for g in state.get("groups", [])}

    topic_groups: list[dict[str, Any]] = []
    total_articles = 0
    topics_with_news = 0
    topics_without_news = 0

    for tid in valid_assigned_ids:
        t_info = all_topics[tid]
        g = group_map.get(tid)
        arts = list(g.get("articles", [])) if g else []
        cnt = len(arts)
        total_articles += cnt
        if cnt > 0:
            topics_with_news += 1
        else:
            topics_without_news += 1
        topic_groups.append({
            "topic_id": tid,
            "topic_name": t_info["name"],
            "count": cnt,
            "articles": arts,
            "last_fetched_ist": t_info.get("last_fetched_ist", ""),
        })

    return {
        "analyst_id": analyst_id,
        "analyst_name": analyst.name if analyst else analyst_id,
        "hours": hours_val,
        "window_label": window_label,
        "assigned_topic_ids": valid_assigned_ids,
        "assigned_topic_names": [all_topics[tid]["name"] for tid in valid_assigned_ids],
        "topic_groups": topic_groups,
        "total_articles": total_articles,
        "topics_with_news": topics_with_news,
        "topics_without_news": topics_without_news,
    }





