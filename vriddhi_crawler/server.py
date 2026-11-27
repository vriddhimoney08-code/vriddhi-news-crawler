"""FastAPI Application for Vriddhi News Crawler Web Dashboard on port 3009."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import (
    DIGESTS_DIR,
    GROUP_LOGOS_DIR,
    PORT,
    DASHBOARD_USERNAME,
    DASHBOARD_PASSWORD,
    SESSION_SECRET,
)
from .controlpanel import Analyst, Company, ClientGroup
from .db import (
    add_folder,
    add_source,
    delete_analyst,
    delete_company,
    delete_folder,
    delete_source,
    get_analysts,
    get_companies,
    get_connection,
    get_dashboard_stats,
    get_folders,
    get_recent_stories,
    get_source,
    get_sources,
    get_unsent_stories_for_analyst,
    init_db,
    mark_sent,
    record_dispatch_run,
    get_dispatch_runs,
    clear_sent_ledger,
    save_analyst,
    save_company,
    toggle_source_status,
    update_source,
    log_audit_event,
    get_audit_logs,
    clear_audit_logs,
    get_client_groups,
    save_client_group,
    delete_client_group,
    get_client_group,
    get_custom_news_topics,
    add_custom_news_topics,
    set_custom_news_topic_selected,
    set_all_custom_news_topics_selected,
    delete_custom_news_topic,
    save_custom_news_articles,
    get_custom_news_state,
    get_custom_news_schedule,
    save_custom_news_schedule,
    should_fire_custom_news_now,
    get_custom_news_digest_for_analyst,
)
from .http import Fetcher
from .pdf import generate_analyst_digest, get_clean_digest_filename, render_digest_html
from .pipeline import Pipeline
from .whatsapp import send_whatsapp_digest

log = logging.getLogger("vriddhi_server")

app = FastAPI(title="Vriddhi Research Desk Terminal", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database schema on startup
init_db(seed_defaults=True)


# =========================================================================
# Authentication & Session Security
# =========================================================================
def create_session_token(username: str) -> str:
    """Create a tamper-proof HMAC signed session token valid for 30 days."""
    ts = str(int(time.time()))
    data = f"{username}:{ts}".encode("utf-8")
    sig = hmac.new(SESSION_SECRET.encode("utf-8"), data, hashlib.sha256).hexdigest()
    return f"{username}.{ts}.{sig}"


def verify_session_token(token: str | None) -> str | None:
    """Validate token cryptographic signature and expiration."""
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        username, ts_str, sig = parts
        # 30 days expiration window (30 * 86400 = 2,592,000 seconds)
        ts = int(ts_str)
        if time.time() - ts > 2592000:
            return None
        data = f"{username}:{ts_str}".encode("utf-8")
        expected_sig = hmac.new(SESSION_SECRET.encode("utf-8"), data, hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected_sig):
            return username
    except Exception:
        return None
    return None


def get_current_user(request: Request) -> str | None:
    """Extract authenticated user from cookie or Authorization header."""
    token = request.cookies.get("vriddhi_session")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1].strip()
    return verify_session_token(token)


class LoginPayload(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
def api_login(payload: LoginPayload, response: Response):
    """Authenticate user with username and password, issuing a signed session cookie."""
    u = payload.username.strip()
    p = payload.password.strip()
    if u.lower() != DASHBOARD_USERNAME.lower() or p != DASHBOARD_PASSWORD:
        log_audit_event("AUTH_FAILED", u, f"Failed login attempt for username '{u}'")
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session_token(DASHBOARD_USERNAME)
    response.set_cookie(
        key="vriddhi_session",
        value=token,
        max_age=2592000,
        httponly=True,
        samesite="lax",
        path="/"
    )
    log_audit_event("AUTH_LOGIN", DASHBOARD_USERNAME, f"User '{DASHBOARD_USERNAME}' logged in to control panel")
    return {"status": "ok", "token": token, "username": DASHBOARD_USERNAME}


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    """Log out user and invalidate browser session."""
    user = get_current_user(request) or DASHBOARD_USERNAME
    log_audit_event("AUTH_LOGOUT", user, f"User '{user}' logged out")
    response.delete_cookie(key="vriddhi_session", path="/")
    return {"status": "ok", "message": "Logged out successfully"}


@app.get("/api/auth/check")
def api_auth_check(request: Request):
    """Check current authentication state."""
    user = get_current_user(request)
    if user:
        return {"authenticated": True, "username": user}
    return {"authenticated": False}


@app.get("/api/audit-logs")
def api_list_audit_logs(limit: int = 5):
    """Retrieve system audit and change history log (strictly latest 5 entries)."""
    return {"status": "ok", "logs": get_audit_logs(limit)}


@app.post("/api/audit-logs/clear")
def api_clear_audit_logs():
    """Vanish all system audit and change history logs."""
    count = clear_audit_logs()
    return {"status": "ok", "cleared_count": count, "message": "All change logs vanished successfully"}


@app.get("/api/scheduler/history")
def api_list_dispatch_history(limit: int = 50):
    """Retrieve full trigger and broadcast execution history."""
    return {"status": "ok", "runs": get_dispatch_runs(limit)}


# Mount static frontend directory
STATIC_DIR = Path(__file__).resolve().parent / "ui"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    """Serve the single-page application dashboard with no-cache headers."""
    index_file = STATIC_DIR / "index.html"
    return HTMLResponse(
        content=index_file.read_text(encoding="utf-8"),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/api/stats")
def get_stats():
    return get_dashboard_stats()


@app.get("/api/stories")
def list_stories(
    limit: int = 100,
    company_id: str | None = None,
    source_type: str | None = None,
    mode: str = "live",
    window_only: bool | None = None,
):
    return get_recent_stories(
        limit=limit,
        company_id=company_id,
        source_type=source_type,
        mode=mode,
        window_only=window_only,
    )


@app.post("/api/stories/cleanup")
def cleanup_stories():
    """Run deduplication audit and prune duplicate records from SQLite database."""
    from .db import cleanup_database_duplicates
    return cleanup_database_duplicates()


# =========================================================================
# Verified Macro & Sector Intelligence Endpoints
# =========================================================================

@app.get("/api/macro")
def list_macro_stories(
    limit: int = 50,
    sector: str | None = None,
    tier: str | None = None,
    mode: str = "live",
):
    from .db import get_macro_stories
    return get_macro_stories(limit=limit, sector=sector, tier=tier, mode=mode)


@app.get("/api/macro/stats")
def get_macro_statistics():
    from .db import get_macro_stats
    return get_macro_stats()


@app.get("/api/macro/sectors")
def list_macro_sectors(mode: str = "live"):
    from .db import get_macro_sectors
    return {"sectors": get_macro_sectors(mode=mode)}


@app.post("/api/macro/crawl")
def trigger_macro_crawl(hours: int = 24):
    """Trigger verified macro crawl across PIB, RBI, SEBI, and official wires."""
    from .sources.macro import MacroPipeline
    return MacroPipeline().run_macro_crawl(hours=hours)


@app.post("/api/macro/reclassify")
def reclassify_macro():
    """Reclassify existing macro database using the 61-sector taxonomy and purge noise."""
    from .db import reclassify_and_clean_macro_stories
    return reclassify_and_clean_macro_stories()


# =========================================================================
# Evening Macro & Policy Digest Endpoints
# =========================================================================

@app.get("/api/macro/digest/meta/{analyst_id}")
def get_macro_digest_meta(analyst_id: str):
    """Provide real-time intelligence summary metrics for the selected analyst's evening macro brief."""
    from .db import get_analyst_macro_sectors, get_macro_stories_for_analyst
    from .pdf import get_clean_macro_digest_filename

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=100)
    tier1_count = sum(1 for s in stories if "Tier 1" in (s.get("impact_grade") or ""))
    sectors = get_analyst_macro_sectors(analyst_id)
    pdf_filename = get_clean_macro_digest_filename(analyst.name, ext=".pdf")

    return {
        "analyst_id": analyst.id,
        "name": analyst.name,
        "phone": analyst.phone,
        "email": analyst.email,
        "assigned_sectors": sectors,
        "total_stories": len(stories),
        "tier1_count": tier1_count,
        "pdf_name": pdf_filename,
    }


@app.get("/api/macro/digest/preview/{analyst_id}", response_class=HTMLResponse)
def preview_macro_digest(analyst_id: str):
    """Render the Post-Market Macro & Policy Briefing HTML for the requested analyst."""
    from .db import get_macro_stories_for_analyst
    from .pdf import render_macro_digest_html

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=100)
    html_output = render_macro_digest_html(analyst.name, analyst.id, stories)

    return HTMLResponse(
        content=html_output,
        status_code=200,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/macro/digest/download/{analyst_id}")
def download_macro_digest_pdf(analyst_id: str):
    """Generate and download the Evening Macro & Policy Briefing PDF."""
    from .db import get_macro_stories_for_analyst
    from .pdf import generate_macro_digest

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=100)
    file_path, _ = generate_macro_digest(analyst.id, analyst.name, stories)

    media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "text/html"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@app.post("/api/macro/digest/send/{analyst_id}")
def dispatch_macro_digest(analyst_id: str):
    """Dispatch Post-Market Evening Macro & Policy Briefing to analyst via Interakt WhatsApp."""
    from .db import get_macro_stories_for_analyst
    from .pdf import generate_macro_digest
    from .whatsapp import send_whatsapp_macro_digest

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=100)
    if not stories:
        return {"status": "no_op", "message": f"No policy updates for {analyst.name} today.", "count": 0}

    file_path, _ = generate_macro_digest(analyst.id, analyst.name, stories)

    public_base = os.getenv("BASE_URL") or get_ngrok_public_url()
    cb = int(datetime.now().timestamp())
    public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}" if public_base else None

    wa_result = send_whatsapp_macro_digest(
        analyst_name=analyst.name,
        analyst_phone=analyst.phone,
        stories=stories,
        pdf_path=file_path,
        public_pdf_url=public_pdf_url,
    )

    dispatch_msg = wa_result.get("message", f"Dispatched {len(stories)} policy directives to {analyst.name}")
    return {
        "status": wa_result.get("status", "sent"),
        "mode": wa_result.get("mode", "simulated"),
        "message": dispatch_msg,
        "recipient": wa_result.get("recipient"),
        "file": file_path.name,
        "count": len(stories),
    }


# =========================================================================
# Direct External Cron Webhook Endpoints (cron-job.org / Webhook triggers)
# =========================================================================
@app.api_route("/api/cron/evening-broadcast", methods=["GET", "POST"])
def trigger_cron_evening_broadcast(run_crawl: bool = True):
    """Triggered by cron-job.org or manual admin dispatch for Evening Macro Briefing."""
    from .db import get_analysts, get_macro_stories_for_analyst, record_dispatch_run
    from .pdf import generate_macro_digest
    from .sources.macro import MacroPipeline
    from .whatsapp import send_whatsapp_macro_digest

    is_active_setting = os.getenv("EVENING_DISPATCH_ACTIVE", "yes").strip().lower() in ("yes", "true", "1")
    if not is_active_setting:
        log.warning("[CRON] Evening Policy & Macro Broadcast is PAUSED in scheduler settings. Skipping dispatch.")
        record_dispatch_run("evening_macro", recipients_count=0, stories_count=0, status="PAUSED", details=[{"status": "paused", "msg": "Delivery paused in scheduler"}])
        return {
            "status": "paused",
            "message": "Evening Macro & Policy Briefing broadcast is currently PAUSED in scheduler settings.",
            "dispatched_count": 0
        }

    log.info("[CRON] Starting Evening Policy & Macro Broadcast to active clients...")
    if run_crawl:
        try:
            MacroPipeline().run_macro_crawl(hours=48)
        except Exception as e:
            log.warning("[CRON] Macro crawl warning: %s", e)

    all_analysts = get_analysts()
    active_analysts = [a for a in all_analysts if getattr(a, "is_active", True)]
    results = []
    public_base = os.getenv("BASE_URL") or "https://35.244.60.224.sslip.io"

    for a in active_analysts:
        stories = get_macro_stories_for_analyst(a.id, hours=24, limit=100)
        if not stories:
            results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": 0, "status": "no_updates"})
            continue

        try:
            file_path, _ = generate_macro_digest(a.id, a.name, stories)
            cb = int(datetime.now().timestamp())
            public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}"

            wa_result = send_whatsapp_macro_digest(
                analyst_name=a.name,
                analyst_phone=a.phone,
                stories=stories,
                pdf_path=file_path,
                public_pdf_url=public_pdf_url,
            )
            results.append({
                "id": a.id,
                "name": a.name,
                "phone": a.phone,
                "count": len(stories),
                "status": wa_result.get("status", "sent"),
                "message": wa_result.get("message")
            })
        except Exception as err:
            log.error("[CRON] Failed to send evening macro brief to %s: %s", a.name, err)
            results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": len(stories), "status": "error", "error": str(err)})

    sent_count = len([r for r in results if r["status"] == "sent"])
    total_stories = sum(r["count"] for r in results)
    run_status = "COMPLETED" if sent_count > 0 else ("CLEAN" if all(r["status"] == "no_updates" for r in results) else "PARTIAL")

    record_dispatch_run("evening_macro", recipients_count=sent_count, stories_count=total_stories, status=run_status, details=results)
    log.info("[CRON] Evening Broadcast complete. Sent to %d / %d active clients.", sent_count, len(active_analysts))

    return {
        "status": "success",
        "broadcast": "evening_macro_briefing",
        "total_clients": len(active_analysts),
        "dispatched_count": sent_count,
        "results": results
    }


@app.api_route("/api/cron/morning-broadcast", methods=["GET", "POST"])
def trigger_cron_morning_broadcast(run_crawl: bool = False):
    """Triggered by cron-job.org or manual admin dispatch for Morning Company News."""
    from .db import get_analysts, get_unsent_stories_for_analyst, mark_sent, record_dispatch_run
    from .pdf import generate_analyst_digest
    from .pipeline import Pipeline
    from .whatsapp import send_whatsapp_digest

    is_active_setting = os.getenv("MORNING_DISPATCH_ACTIVE", "yes").strip().lower() in ("yes", "true", "1")
    if not is_active_setting:
        log.warning("[CRON] Morning Companies News Broadcast is PAUSED in scheduler settings. Skipping dispatch.")
        record_dispatch_run("morning_digest", recipients_count=0, stories_count=0, status="PAUSED", details=[{"status": "paused", "msg": "Delivery paused in scheduler"}])
        return {
            "status": "paused",
            "message": "Morning Equity News broadcast is currently PAUSED in scheduler settings.",
            "dispatched_count": 0
        }

    log.info("[CRON] Starting Morning Companies News Broadcast to active clients...")
    if run_crawl:
        try:
            # Fast crawl for pre-broadcast: exchanges and active publishers (background crontab handles heavy search loops)
            Pipeline().run_crawl(groups=["exchanges", "publishers"])
        except Exception as e:
            log.warning("[CRON] Morning crawl warning: %s", e)

    all_analysts = get_analysts()
    active_analysts = [a for a in all_analysts if getattr(a, "is_active", True)]
    results = []
    public_base = os.getenv("BASE_URL") or "https://35.244.60.224.sslip.io"

    for a in active_analysts:
        stories = get_unsent_stories_for_analyst(a.id)
        if not stories:
            results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": 0, "status": "ledger_clean"})
            continue

        try:
            file_path, _ = generate_analyst_digest(a.id, a.name, stories)
            cb = int(datetime.now().timestamp())
            public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}"

            wa_result = send_whatsapp_digest(
                analyst_name=a.name,
                analyst_phone=a.phone,
                stories=stories,
                pdf_path=file_path,
                public_pdf_url=public_pdf_url,
            )
            if wa_result.get("status") in ("sent", "simulated"):
                mark_sent([s["id"] for s in stories], a.id)
            results.append({
                "id": a.id,
                "name": a.name,
                "phone": a.phone,
                "count": len(stories),
                "status": wa_result.get("status", "sent"),
                "message": wa_result.get("message")
            })
        except Exception as err:
            log.error("[CRON] Failed to send morning digest to %s: %s", a.name, err)
            results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": len(stories), "status": "error", "error": str(err)})

    sent_count = len([r for r in results if r["status"] == "sent"])
    total_stories = sum(r["count"] for r in results)
    run_status = "COMPLETED" if sent_count > 0 else ("CLEAN" if all(r["status"] == "ledger_clean" for r in results) else "PARTIAL")

    record_dispatch_run("morning_digest", recipients_count=sent_count, stories_count=total_stories, status=run_status, details=results)
    log.info("[CRON] Morning Broadcast complete. Sent to %d / %d active clients.", sent_count, len(active_analysts))

    return {
        "status": "success",
        "broadcast": "morning_companies_briefing",
        "total_clients": len(active_analysts),
        "dispatched_count": sent_count,
        "results": results
    }


@app.get("/api/watchlist")
def list_watchlist():
    companies = get_companies()
    return [asdict(c) for c in companies]




@app.get("/api/folders")
def list_folders():
    return {"folders": get_folders()}


@app.post("/api/folders")
def create_folder(payload: dict):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required")
    folders = add_folder(name)
    return {"status": "ok", "folders": folders}


@app.delete("/api/folders/{name}")
def delete_custom_folder(name: str):
    delete_folder(name)
    return {"status": "deleted", "folders": get_folders()}


class CompanyCreate(BaseModel):
    id: str
    name: str
    nse_symbol: str = ""
    bse_code: str = ""
    aliases: list[str] = []
    search_queries: list[str] = []
    analyst_names: list[str] = []
    folder: str = ""
    folders: list[str] = []
    assigned_analyst_ids: list[str] | None = None
    is_active: bool = True


class CompanyFolderUpdate(BaseModel):
    folder: str = ""
    folders: list[str] | None = None


class FolderActionRequest(BaseModel):
    folder: str


@app.post("/api/watchlist")
def add_watchlist_company(item: CompanyCreate):
    flds = [f.strip().upper() for f in item.folders if f.strip()]
    if not flds and item.folder:
        flds = [f.strip().upper() for f in item.folder.split(",") if f.strip()]

    comp = Company(
        id=item.id,
        name=item.name,
        nse_symbol=item.nse_symbol,
        bse_code=item.bse_code,
        aliases=item.aliases,
        search_queries=item.search_queries,
        analyst_names=item.analyst_names,
        folder=", ".join(flds),
        folders=flds,
        is_active=item.is_active
    )
    save_company(comp)

    # Sync manual analyst assignment (if provided)
    if item.assigned_analyst_ids is not None:
        all_analysts = get_analysts()
        target_aids = set(item.assigned_analyst_ids)
        for an in all_analysts:
            changed = False
            if an.id in target_aids:
                if comp.id not in an.assigned_companies:
                    an.assigned_companies.append(comp.id)
                    changed = True
            else:
                if comp.id in an.assigned_companies:
                    an.assigned_companies.remove(comp.id)
                    changed = True
            if changed:
                save_analyst(an)

    return {"status": "ok", "company": asdict(comp)}


@app.patch("/api/watchlist/{company_id}/folder")
@app.patch("/api/watchlist/{company_id}/folders")
def update_company_folder(company_id: str, item: CompanyFolderUpdate):
    if item.folders is not None:
        flds = [f.strip().upper() for f in item.folders if f.strip()]
    elif item.folder:
        flds = [f.strip().upper() for f in item.folder.split(",") if f.strip()]
    else:
        flds = []
    stored_val = json.dumps(flds)
    with get_connection() as conn:
        conn.execute("UPDATE companies SET folder = ? WHERE id = ?", (stored_val, company_id))
        conn.commit()
    return {"status": "ok", "company_id": company_id, "folders": flds, "folder": ", ".join(flds)}


@app.post("/api/watchlist/{company_id}/add-folder")
def add_folder_to_company(company_id: str, item: FolderActionRequest):
    target = item.folder.strip().upper()
    if not target:
        raise HTTPException(status_code=400, detail="Folder required")
    with get_connection() as conn:
        row = conn.execute("SELECT folder FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
        raw = row["folder"] or ""
        current = []
        if raw.startswith("["):
            try:
                current = [str(x).upper() for x in json.loads(raw)]
            except Exception:
                current = [raw.upper()]
        elif "," in raw:
            current = [x.strip().upper() for x in raw.split(",") if x.strip()]
        elif raw.strip():
            current = [raw.strip().upper()]
        if target not in current:
            current.append(target)
        conn.execute("UPDATE companies SET folder = ? WHERE id = ?", (json.dumps(current), company_id))
        conn.commit()
    return {"status": "ok", "company_id": company_id, "folders": current}


@app.post("/api/watchlist/{company_id}/remove-folder")
def remove_folder_from_company(company_id: str, item: FolderActionRequest):
    target = item.folder.strip().upper()
    with get_connection() as conn:
        row = conn.execute("SELECT folder FROM companies WHERE id = ?", (company_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
        raw = row["folder"] or ""
        current = []
        if raw.startswith("["):
            try:
                current = [str(x).upper() for x in json.loads(raw)]
            except Exception:
                current = [raw.upper()]
        elif "," in raw:
            current = [x.strip().upper() for x in raw.split(",") if x.strip()]
        elif raw.strip():
            current = [raw.strip().upper()]
        if target in current:
            current.remove(target)
        conn.execute("UPDATE companies SET folder = ? WHERE id = ?", (json.dumps(current), company_id))
        conn.commit()
    return {"status": "ok", "company_id": company_id, "folders": current}


@app.delete("/api/watchlist/{company_id}")
def remove_watchlist_company(company_id: str):
    delete_company(company_id)
    return {"status": "deleted"}


@app.get("/api/watchlist/export")
def export_watchlist_csv():
    """Export complete watchlist as a clean CSV file."""
    import csv
    import io
    companies = get_companies(include_inactive=True)
    all_analysts = get_analysts()

    comp_analysts: dict[str, list[str]] = {}
    for a in all_analysts:
        for cid in a.assigned_companies:
            comp_analysts.setdefault(cid, []).append(a.name)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Company Name", "NSE Symbol", "BSE Code",
        "Baskets", "Aliases", "Search Queries", "Assigned Clients", "Status"
    ])
    for c in companies:
        c_flds = getattr(c, "folders", []) or ([c.folder] if c.folder else [])
        assigned_names = comp_analysts.get(c.id, [])
        writer.writerow([
            c.id,
            c.name,
            c.nse_symbol,
            c.bse_code,
            ", ".join(c_flds),
            ", ".join(c.aliases),
            ", ".join(c.search_queries),
            ", ".join(assigned_names),
            "Active" if c.is_active else "Paused"
        ])

    today_str = datetime.now().strftime("%Y%m%d")
    filename = f"vriddhi_watchlist_{today_str}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@app.get("/api/watchlist/{company_id}")
def get_watchlist_company(company_id: str):
    """Retrieve complete metadata for a single company."""
    comps = {c.id: c for c in get_companies(include_inactive=True)}
    comp = comps.get(company_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Company not found")
    all_analysts = get_analysts()
    assigned_aids = [a.id for a in all_analysts if comp.id in a.assigned_companies]
    res = asdict(comp)
    res["assigned_analyst_ids"] = assigned_aids
    return res


class BatchWatchlistAction(BaseModel):
    action: str  # "assign_folder", "remove_folder", "assign_analyst", "delete", "toggle_active"
    company_ids: list[str]
    value: str | None = None


@app.post("/api/watchlist/batch")
def batch_watchlist_action(req: BatchWatchlistAction):
    """Execute bulk operations across selected companies."""
    cids = set(req.company_ids)
    if not cids:
        return {"status": "no_op", "count": 0}

    all_comps = {c.id: c for c in get_companies(include_inactive=True)}
    all_analysts = get_analysts()

    if req.action == "delete":
        for cid in cids:
            delete_company(cid)
            for a in all_analysts:
                if cid in a.assigned_companies:
                    a.assigned_companies.remove(cid)
                    save_analyst(a)
        return {"status": "ok", "message": f"Deleted {len(cids)} companies", "count": len(cids)}

    elif req.action == "assign_folder":
        folder = (req.value or "").strip().upper()
        if not folder:
            raise HTTPException(status_code=400, detail="Folder value required")
        for cid in cids:
            comp = all_comps.get(cid)
            if comp:
                cur_flds = [f.upper() for f in (getattr(comp, "folders", []) or ([comp.folder] if comp.folder else []))]
                if folder not in cur_flds:
                    cur_flds.append(folder)
                comp.folders = cur_flds
                comp.folder = ", ".join(cur_flds)
                save_company(comp)
        return {"status": "ok", "message": f"Added basket '{folder}' to {len(cids)} companies", "count": len(cids)}

    elif req.action == "remove_folder":
        folder = (req.value or "").strip().upper()
        if not folder:
            raise HTTPException(status_code=400, detail="Folder value required")
        for cid in cids:
            comp = all_comps.get(cid)
            if comp:
                cur_flds = [f.upper() for f in (getattr(comp, "folders", []) or ([comp.folder] if comp.folder else []))]
                if folder in cur_flds:
                    cur_flds.remove(folder)
                comp.folders = cur_flds
                comp.folder = ", ".join(cur_flds)
                save_company(comp)
        return {"status": "ok", "message": f"Removed basket '{folder}' from {len(cids)} companies", "count": len(cids)}

    elif req.action == "assign_analyst":
        aid = (req.value or "").strip()
        analyst = next((a for a in all_analysts if a.id == aid), None)
        if not analyst:
            raise HTTPException(status_code=404, detail="Client not found")
        updated = False
        for cid in cids:
            if cid not in analyst.assigned_companies:
                analyst.assigned_companies.append(cid)
                updated = True
        if updated:
            save_analyst(analyst)
        return {"status": "ok", "message": f"Assigned {len(cids)} stocks to {analyst.name}", "count": len(cids)}

    elif req.action == "toggle_active":
        target_state = str(req.value).lower() in ("1", "true", "active", "yes")
        with get_connection() as conn:
            for cid in cids:
                conn.execute("UPDATE companies SET is_active = ? WHERE id = ?", (1 if target_state else 0, cid))
            conn.commit()
        state_label = "Activated" if target_state else "Paused"
        return {"status": "ok", "message": f"{state_label} {len(cids)} companies", "count": len(cids)}

    raise HTTPException(status_code=400, detail="Unknown batch action")


class BulkImportCompany(BaseModel):
    name: str
    nse_symbol: str = ""
    bse_code: str = ""
    folder: str = ""
    folders: list[str] = []
    aliases: list[str] = []


class BulkImportRequest(BaseModel):
    items: list[BulkImportCompany]


@app.post("/api/watchlist/import")
def import_watchlist_bulk(req: BulkImportRequest):
    """Import batch of companies."""
    import re
    added = 0
    for it in req.items:
        name = it.name.strip()
        if not name:
            continue
        cid = re.sub(r"[^a-z0-9]", "", name.lower())
        flds = [f.strip().upper() for f in it.folders if f.strip()]
        if not flds and it.folder:
            flds = [f.strip().upper() for f in it.folder.split(",") if f.strip()]
        if not flds:
            flds = ["GAME"]

        aliases = [a.strip() for a in it.aliases if a.strip()]
        if name not in aliases:
            aliases.insert(0, name)
        if it.nse_symbol and it.nse_symbol not in aliases:
            aliases.append(it.nse_symbol.strip().upper())

        comp = Company(
            id=cid,
            name=name,
            nse_symbol=(it.nse_symbol or "").strip().upper(),
            bse_code=(it.bse_code or "").strip(),
            aliases=aliases,
            search_queries=[f'"{name}"'],
            analyst_names=[],
            folder=", ".join(flds),
            folders=flds,
            is_active=True
        )
        save_company(comp)
        added += 1
    return {"status": "ok", "imported": added}


from .client_importer import generate_clients_workbook, generate_clients_csv, parse_client_sheet, import_clients_records

class AnalystCreate(BaseModel):
    id: str = ""
    name: str
    phone: str
    email: str = ""
    assigned_companies: list[str] = []
    assigned_folders: list[str] = []
    macro_sectors: list[str] = ["ALL"]
    assigned_news_topics: list[str] = []
    is_active: bool = True
    group_id: str = ""
    logo_path: str = ""
    logo_data: str = ""


class ClientGroupCreate(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    morning_active: bool = True
    evening_active: bool = True
    client_ids: list[str] = []
    logo_path: str = ""
    logo_data: str = ""


class GroupDispatchAction(BaseModel):
    type: str = "morning"  # "morning" or "evening"


# =========================================================================
# Client Groups Management Endpoints
# =========================================================================

@app.get("/api/groups")
def list_client_groups():
    groups = get_client_groups()
    analysts_map = {a.id: a for a in get_analysts()}
    out = []
    for g in groups:
        d: dict[str, Any] = asdict(g)
        members = []
        for cid in (g.client_ids or []):
            if cid in analysts_map:
                a = analysts_map[cid]
                members.append({
                    "id": a.id,
                    "name": a.name,
                    "phone": a.phone,
                    "is_active": getattr(a, "is_active", True)
                })
        d["member_count"] = len(members)
        d["members"] = members
        out.append(d)
    return out


@app.post("/api/groups")
def create_or_update_client_group(item: ClientGroupCreate):
    import re
    clean_name = item.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Group name is required")
    gid = item.id.strip().lower() or re.sub(r"[^a-z0-9_]+", "_", clean_name.lower()).strip("_")
    
    # If group exists, preserve existing logo if not explicitly passed
    existing_g = get_client_group(gid)
    l_path = item.logo_path or ""
    l_data = getattr(item, "logo_data", "") or ""
    if not l_path and existing_g:
        l_path = existing_g.logo_path or ""
        l_data = getattr(existing_g, "logo_data", "") or ""

    group = ClientGroup(
        id=gid,
        name=clean_name,
        description=item.description.strip(),
        morning_active=item.morning_active,
        evening_active=item.evening_active,
        client_ids=item.client_ids or [],
        logo_path=l_path,
        logo_data=l_data
    )
    save_client_group(group)
    log_audit_event("GROUP_UPDATE", group.name, f"Saved client group '{group.name}' with {len(group.client_ids)} members (Morning: {group.morning_active}, Evening: {group.evening_active}, Logo: {'Yes' if l_path or l_data else 'No'})")
    return {"status": "ok", "group": asdict(group)}


@app.delete("/api/groups/{group_id}")
def remove_client_group(group_id: str):
    g = get_client_group(group_id)
    name = g.name if g else group_id
    deleted = delete_client_group(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")
    log_audit_event("GROUP_DELETE", name, f"Deleted client group '{name}' (ID: {group_id})")
    return {"status": "ok", "message": f"Deleted group {name}"}


@app.post("/api/groups/{group_id}/logo")
async def upload_group_logo(group_id: str, file: UploadFile = File(...)):
    """Upload custom corporate white-label logo for a client group (PNG, JPG, SVG, WEBP). Saves to SQLite DB and disk."""
    g = get_client_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected")

    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".svg"]:
        raise HTTPException(status_code=400, detail="Only PNG, JPG, JPEG, WEBP, or SVG images are supported.")

    import re
    safe_name = re.sub(r"[^a-zA-Z0-9_\.-]", "_", file.filename)
    filename = f"{group_id}_{safe_name}"
    target_path = GROUP_LOGOS_DIR / filename

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    # 1. Write to disk
    try:
        target_path.write_bytes(content)
    except Exception as e:
        log.warning("Could not write logo to disk %s: %s", target_path, e)

    # 2. Encode to Base64 Data URI for direct DB storage
    mime = "image/png"
    if ext in (".jpg", ".jpeg"): mime = "image/jpeg"
    elif ext == ".svg": mime = "image/svg+xml"
    elif ext == ".webp": mime = "image/webp"
    raw_b64 = base64.b64encode(content).decode("ascii")
    data_uri = f"data:{mime};base64,{raw_b64}"

    # 3. Save to corporate_logos dedicated SQLite table
    from .db import save_corporate_logo
    save_corporate_logo("group", group_id, filename, mime, data_uri)

    # 4. Save to client_groups table
    g.logo_path = filename
    g.logo_data = data_uri
    save_client_group(g)

    log_audit_event("GROUP_LOGO_UPDATE", g.name, f"Uploaded custom corporate logo '{filename}' for group '{g.name}' (saved to SQLite DB and disk)")
    return {"status": "ok", "logo_path": filename, "logo_data": data_uri}


@app.delete("/api/groups/{group_id}/logo")
def delete_group_logo(group_id: str):
    """Remove custom corporate white-label logo from a client group."""
    g = get_client_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")
    old_file = g.logo_path
    g.logo_path = ""
    g.logo_data = ""
    from .db import delete_corporate_logo, get_connection
    delete_corporate_logo("group", group_id)
    with get_connection() as conn:
        conn.execute("UPDATE client_groups SET logo_path = '', logo_data = '' WHERE id = ?", (g.id,))
    if old_file:
        file_path = GROUP_LOGOS_DIR / old_file
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass
    log_audit_event("GROUP_LOGO_DELETE", g.name, f"Removed custom corporate logo from group '{g.name}'")
    return {"status": "ok", "message": "Group logo removed"}


@app.get("/api/groups/logo/{filename}")
def get_group_logo(filename: str):
    """Serve uploaded group logo image from disk or directly from SQLite DB."""
    import re
    safe_name = re.sub(r"[^a-zA-Z0-9_\.-]", "", filename)
    file_path = GROUP_LOGOS_DIR / safe_name
    if file_path.exists() and file_path.is_file():
        ext = file_path.suffix.lower()
        media_type = "image/png"
        if ext in [".jpg", ".jpeg"]: media_type = "image/jpeg"
        elif ext == ".svg": media_type = "image/svg+xml"
        elif ext == ".webp": media_type = "image/webp"
        return FileResponse(path=str(file_path), media_type=media_type)

    # Fallback to SQLite DB
    from .db import get_connection
    with get_connection() as conn:
        row = conn.execute("SELECT logo_data FROM corporate_logos WHERE filename = ? OR id LIKE ?", (safe_name, f"%{safe_name}%")).fetchone()
        if not row:
            row = conn.execute("SELECT logo_data FROM client_groups WHERE logo_path = ?", (safe_name,)).fetchone()
        if row and row["logo_data"]:
            m = re.match(r"^data:(.*?);base64,(.*)$", row["logo_data"])
            if m:
                m_type = m.group(1)
                b_bytes = base64.b64decode(m.group(2))
                return Response(content=b_bytes, media_type=m_type)

    raise HTTPException(status_code=404, detail="Logo not found")


@app.post("/api/groups/{group_id}/dispatch")
def dispatch_group_briefing(group_id: str, action: GroupDispatchAction):
    g = get_client_group(group_id)
    if not g:
        raise HTTPException(status_code=404, detail="Group not found")

    from .db import get_macro_stories_for_analyst
    from .whatsapp import send_whatsapp_digest, send_whatsapp_macro_digest
    from .pdf import generate_macro_digest

    analysts_map = {a.id: a for a in get_analysts()}
    target_analysts = [analysts_map[cid] for cid in (g.client_ids or []) if cid in analysts_map and getattr(analysts_map[cid], "is_active", True)]

    if not target_analysts:
        return {"status": "no_op", "message": f"No active clients found in group '{g.name}'", "results": []}

    public_base = os.getenv("BASE_URL") or "https://35.244.60.224.sslip.io"
    results = []

    if action.type == "morning":
        for a in target_analysts:
            stories = get_unsent_stories_for_analyst(a.id)
            if not stories:
                results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": 0, "status": "ledger_clean", "message": "No unsent stories currently queued"})
                continue

            file_path, _ = generate_analyst_digest(a.id, a.name, stories)
            cb = int(datetime.now().timestamp())
            public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}"
            res = send_whatsapp_digest(
                analyst_name=a.name,
                analyst_phone=a.phone,
                stories=stories,
                pdf_path=file_path,
                public_pdf_url=public_pdf_url
            )
            st = res.get("status", "sent")
            if st in ("sent", "simulated"):
                mark_sent([s["id"] for s in stories], a.id)
            results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": len(stories), "status": st, "message": res.get("message")})

        sent_count = len([r for r in results if r["status"] == "sent"])
        record_dispatch_run(f"group_morning_{g.id}", recipients_count=sent_count, stories_count=sum(r["count"] for r in results), status="COMPLETED" if sent_count > 0 else "CLEAN", details=results)

    elif action.type == "evening":
        for a in target_analysts:
            stories = get_macro_stories_for_analyst(a.id, hours=24, limit=100)
            if not stories:
                results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": 0, "status": "no_updates", "message": "No macro policy updates today"})
                continue

            file_path, _ = generate_macro_digest(a.id, a.name, stories)
            cb = int(datetime.now().timestamp())
            public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}"
            res = send_whatsapp_macro_digest(
                analyst_name=a.name,
                analyst_phone=a.phone,
                stories=stories,
                pdf_path=file_path,
                public_pdf_url=public_pdf_url
            )
            st = res.get("status", "sent")
            results.append({"id": a.id, "name": a.name, "phone": a.phone, "count": len(stories), "status": st, "message": res.get("message")})

        sent_count = len([r for r in results if r["status"] == "sent"])
        record_dispatch_run(f"group_evening_{g.id}", recipients_count=sent_count, stories_count=sum(r["count"] for r in results), status="COMPLETED" if sent_count > 0 else "CLEAN", details=results)

    else:
        raise HTTPException(status_code=400, detail="Action type must be 'morning' or 'evening'")

    log_audit_event("GROUP_DISPATCH", g.name, f"Dispatched {action.type} brief to group '{g.name}' ({len(target_analysts)} recipients)")
    return {"status": "ok", "group": g.name, "type": action.type, "total_recipients": len(target_analysts), "results": results}


@app.get("/api/analysts/export")
def export_clients_data(format: str = "xlsx", template: bool = False):
    """Export all registered clients or a sample template as Excel or CSV."""
    from datetime import datetime
    today_str = datetime.now().strftime("%Y%m%d")
    is_template = str(template).lower() in ["1", "true", "yes"]

    if format.lower() == "csv":
        csv_data = generate_clients_csv(include_template=is_template)
        filename = "vriddhi_clients_template.csv" if is_template else f"vriddhi_clients_{today_str}.csv"
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    else:
        xlsx_bytes = generate_clients_workbook(include_template=is_template)
        filename = "vriddhi_clients_template.xlsx" if is_template else f"vriddhi_clients_{today_str}.xlsx"
        return Response(
            content=xlsx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )


@app.post("/api/analysts/import")
async def import_clients_file(
    file: UploadFile = File(...),
    auto_create_groups: bool = True
):
    """Bulk import clients and distribution group assignments from Excel (.xlsx) or CSV."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    filename_lower = file.filename.lower()
    if not (filename_lower.endswith(".xlsx") or filename_lower.endswith(".xls") or filename_lower.endswith(".csv")):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload an Excel (.xlsx/.xls) or CSV (.csv) file.")

    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {str(e)}")

    parsed = parse_client_sheet(content, file.filename)
    if "error" in parsed:
        return JSONResponse(status_code=400, content={"status": "error", "message": parsed["error"]})

    records = parsed.get("records", [])
    if not records:
        return JSONResponse(status_code=400, content={"status": "error", "message": "No valid client rows found in spreadsheet."})

    result = import_clients_records(records, auto_create_groups=auto_create_groups)
    log_audit_event(
        "CLIENT_BULK_IMPORT",
        "System",
        f"Bulk imported from {file.filename}: {result['imported_count']} new, {result['updated_count']} updated, {result['groups_created_count']} groups created"
    )
    return result


@app.get("/api/analysts")
def list_analysts():
    analysts = get_analysts()
    groups = get_client_groups()
    aid_to_grp = {}
    for g in groups:
        for cid in (g.client_ids or []):
            aid_to_grp[cid] = {"group_id": g.id, "group_name": g.name, "group_logo_path": g.logo_path}

    out = []
    for a in analysts:
        d = asdict(a)
        grp_info = aid_to_grp.get(a.id) or {}
        d["group_id"] = getattr(a, "group_id", "") or grp_info.get("group_id", "")
        d["group_name"] = grp_info.get("group_name", "")
        d["group_logo_path"] = getattr(a, "logo_path", "") or grp_info.get("group_logo_path", "")
        out.append(d)
    return out


@app.get("/api/macro-sectors")
def list_macro_sectors():
    try:
        from .macro_ai import SECTOR_KEYWORDS
        keys = sorted(list(SECTOR_KEYWORDS.keys()))
        return ["ALL"] + keys
    except Exception:
        return [
            "ALL", "BANKS", "FINANCE", "FINANCIAL TECHNOLOGY (FINTECH)", "CAPITAL MARKETS",
            "INSURANCE", "AUTOMOBILES", "AUTO COMPONENTS", "AEROSPACE & DEFENSE",
            "POWER", "OIL", "GAS", "PETROLEUM PRODUCTS", "PHARMACEUTICALS & BIOTECHNOLOGY",
            "HEALTHCARE SERVICES", "IT - SERVICES", "IT - SOFTWARE", "IT - HARDWARE",
            "TELECOM - SERVICES", "REALTY", "CONSTRUCTION", "CEMENT & CEMENT PRODUCTS",
            "FERROUS METALS", "CHEMICALS & PETROCHEMICALS", "DIVERSIFIED FMCG", "GENERAL_MACRO"
        ]


@app.post("/api/analysts")
def create_or_update_analyst(item: AnalystCreate):
    aid = item.id.strip().lower() or item.name.strip().lower().replace(" ", "_")
    target_group_id = (item.group_id or "").strip().lower()
    analyst = Analyst(
        id=aid,
        name=item.name.strip(),
        phone=item.phone.strip(),
        email=item.email.strip(),
        assigned_companies=item.assigned_companies,
        assigned_folders=item.assigned_folders,
        macro_sectors=item.macro_sectors or ["ALL"],
        assigned_news_topics=item.assigned_news_topics or [],
        is_active=item.is_active,
        group_id=target_group_id,
        logo_path=getattr(item, "logo_path", "") or "",
        logo_data=getattr(item, "logo_data", "") or ""
    )
    save_analyst(analyst)

    # Sync group membership automatically
    try:
        groups = get_client_groups()
        for g in groups:
            cur_members = list(g.client_ids or [])
            if g.id == target_group_id:
                if aid not in cur_members:
                    cur_members.append(aid)
                    g.client_ids = cur_members
                    save_client_group(g)
            else:
                if aid in cur_members:
                    cur_members = [x for x in cur_members if x != aid]
                    g.client_ids = cur_members
                    save_client_group(g)
    except Exception as e:
        log.warning("Failed syncing group membership for analyst %s: %s", aid, e)

    log_audit_event("CLIENT_UPDATE", analyst.name, f"Saved client {analyst.name} (Phone: {analyst.phone}, Active: {analyst.is_active}, Group: {target_group_id or 'None'})")
    return {"status": "ok", "analyst": asdict(analyst)}


@app.post("/api/analysts/{analyst_id}/toggle-status")
def toggle_analyst_status(analyst_id: str):
    """Toggle client broadcast delivery status (Active vs Paused)."""
    analysts = {a.id: a for a in get_analysts()}
    a = analysts.get(analyst_id)
    if not a:
        raise HTTPException(status_code=404, detail="Client not found")
    a.is_active = not getattr(a, "is_active", True)
    save_analyst(a)
    st = "ACTIVE" if a.is_active else "PAUSED"
    log_audit_event("CLIENT_TOGGLE", a.name, f"Toggled delivery status of client {a.name} to {st}")
    return {"status": "ok", "id": analyst_id, "is_active": a.is_active}


@app.post("/api/analysts/{analyst_id}/test-ping")
def test_ping_analyst(analyst_id: str):
    """Send an immediate test WhatsApp verification message to a single client."""
    analysts = {a.id: a for a in get_analysts()}
    a = analysts.get(analyst_id)
    if not a:
        raise HTTPException(status_code=404, detail="Client not found")
    from .whatsapp import send_whatsapp_digest
    sample_story = [{
        "company_name": "Vriddhi Intelligence Desk",
        "title": "Gateway Connectivity Test: Automated Briefings Active",
        "grade": "Grade A"
    }]
    res = send_whatsapp_digest(
        analyst_name=a.name,
        analyst_phone=a.phone,
        stories=sample_story,
        pdf_path=None
    )
    log_audit_event("TEST_PING", a.name, f"Sent test WhatsApp ping to {a.name} ({a.phone})")
    return res


@app.delete("/api/analysts/{analyst_id}")
def remove_analyst(analyst_id: str):
    analysts = {a.id: a for a in get_analysts()}
    client = analysts.get(analyst_id)
    name = client.name if client is not None else analyst_id
    delete_analyst(analyst_id)
    log_audit_event("CLIENT_DELETE", name, f"Deleted client '{name}' (ID: {analyst_id})")
    return {"status": "deleted"}


@app.get("/api/sources")
def list_sources():
    return get_sources()


@app.post("/api/sources")
def create_source(source_data: dict):
    if not source_data.get("name") or not source_data.get("url"):
        raise HTTPException(status_code=400, detail="Source name and URL are required")
    new_id = add_source(source_data)
    return {"status": "created", "id": new_id}


@app.post("/api/sources/{source_id}/toggle")
def toggle_source(source_id: int, req: dict):
    is_active = bool(req.get("is_active", True))
    toggle_source_status(source_id, is_active)
    return {"status": "updated", "id": source_id, "is_active": is_active}


@app.delete("/api/sources/{source_id}")
def remove_source(source_id: int):
    delete_source(source_id)
    return {"status": "deleted", "id": source_id}


@app.get("/api/sources/{source_id}")
def get_single_source(source_id: int):
    s = get_source(source_id)
    if not s:
        raise HTTPException(status_code=404, detail="Source feed not found")
    return s


@app.put("/api/sources/{source_id}")
def update_existing_source(source_id: int, source_data: dict):
    s = get_source(source_id)
    if not s:
        raise HTTPException(status_code=404, detail="Source feed not found")
    if not source_data.get("name") or not source_data.get("url"):
        raise HTTPException(status_code=400, detail="Source name and URL are required")
    update_source(source_id, source_data)
    return {"status": "updated", "id": source_id}


# =========================================================================
# Automated Scheduler & Broadcast Controls
# =========================================================================
@app.get("/api/scheduler/status")
def get_scheduler_status():
    """Return scheduler configuration, next execution countdowns, active clients, and recent dispatch runs."""
    import os
    from datetime import datetime, time
    from zoneinfo import ZoneInfo
    from dotenv import load_dotenv
    from .config import PROJECT_ROOT

    load_dotenv(PROJECT_ROOT / ".env", override=True)
    ist = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(ist)

    morning_time = os.getenv("MORNING_DISPATCH_TIME", "08:30").strip()
    morning_active = os.getenv("MORNING_DISPATCH_ACTIVE", "yes").strip().lower() in ("yes", "true", "1")
    evening_time = os.getenv("EVENING_DISPATCH_TIME", "17:15").strip()
    evening_active = os.getenv("EVENING_DISPATCH_ACTIVE", "yes").strip().lower() in ("yes", "true", "1")
    crawl_interval = int(os.getenv("CRAWL_INTERVAL_MINUTES", "30"))

    def compute_next_run(time_str: str) -> str:
        try:
            parts = [int(p) for p in time_str.split(":")]
            target_time = time(parts[0], parts[1])
            target_dt = now_ist.replace(hour=target_time.hour, minute=target_time.minute, second=0, microsecond=0)
            if target_dt <= now_ist:
                from datetime import timedelta
                target_dt += timedelta(days=1)
                prefix = "Tomorrow"
            else:
                prefix = "Today"
            return f"{prefix}, {target_dt.strftime('%I:%M %p IST')}"
        except Exception:
            return f"Scheduled daily at {time_str} IST"

    all_analysts = get_analysts()
    active_analysts = [a for a in all_analysts if getattr(a, "is_active", True)]
    recent_runs = get_dispatch_runs(15)
    news_sched = get_custom_news_schedule()

    return {
        "morning_time": morning_time,
        "morning_active": morning_active,
        "evening_time": evening_time,
        "evening_active": evening_active,
        "news_time": news_sched["dispatch_time"],
        "news_time_12h": news_sched["dispatch_time_12h"],
        "news_active": news_sched["dispatch_active"],
        "news_window_hours": news_sched["window_hours"],
        "news_window_label": news_sched["window_label"],
        "next_news_run": news_sched["next_run_ist"],
        "crawl_interval_minutes": crawl_interval,
        "next_morning_run": compute_next_run(morning_time) if morning_active else "Delivery Paused",
        "next_evening_run": compute_next_run(evening_time) if evening_active else "Delivery Paused",
        "active_clients_count": len(active_analysts),
        "total_clients_count": len(all_analysts),
        "recent_runs": recent_runs
    }


@app.post("/api/scheduler/save")
def save_scheduler_settings(payload: dict):
    """Save broadcast dispatch times and active states to .env."""
    import re
    from .config import PROJECT_ROOT
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        raise HTTPException(status_code=500, detail=".env file missing")

    content = env_path.read_text(encoding="utf-8")

    def update_var(txt: str, key: str, val: str) -> str:
        pattern = rf"^{key}\s*=.*$"
        if re.search(pattern, txt, flags=re.MULTILINE):
            return re.sub(pattern, f"{key}={val}", txt, flags=re.MULTILINE)
        else:
            return txt + f"\n{key}={val}"

    if "morning_time" in payload and payload["morning_time"]:
        content = update_var(content, "MORNING_DISPATCH_TIME", str(payload["morning_time"]).strip())

    if "morning_active" in payload:
        val = "yes" if payload["morning_active"] else "no"
        content = update_var(content, "MORNING_DISPATCH_ACTIVE", val)

    if "evening_time" in payload and payload["evening_time"]:
        content = update_var(content, "EVENING_DISPATCH_TIME", str(payload["evening_time"]).strip())

    if "evening_active" in payload:
        val = "yes" if payload["evening_active"] else "no"
        content = update_var(content, "EVENING_DISPATCH_ACTIVE", val)

    if "crawl_interval_minutes" in payload:
        content = update_var(content, "CRAWL_INTERVAL_MINUTES", str(int(payload["crawl_interval_minutes"])))

    env_path.write_text(content, encoding="utf-8")
    log_audit_event(
        "SETTINGS_UPDATE",
        "Scheduler",
        f"Updated dispatch schedule: Morning={payload.get('morning_time', '08:30')} (Active: {payload.get('morning_active', True)}), Evening={payload.get('evening_time', '17:15')} (Active: {payload.get('evening_active', True)})"
    )
    return {"status": "ok", "message": "Scheduler settings updated and persisted"}


@app.post("/api/scheduler/trigger-morning")
def manual_trigger_morning(crawl: bool = False):
    """Manual on-demand trigger of the 8:30 AM Equity Digest broadcast."""
    log_audit_event("MANUAL_TRIGGER", "Morning Equity Digest", "Initiated manual morning digest dispatch from web terminal")
    return trigger_cron_morning_broadcast(run_crawl=crawl)


@app.post("/api/scheduler/trigger-evening")
def manual_trigger_evening(crawl: bool = False):
    """Manual on-demand trigger of the 5:15 PM Macro Briefing broadcast."""
    log_audit_event("MANUAL_TRIGGER", "Evening Macro Briefing", "Initiated manual evening macro dispatch from web terminal")
    return trigger_cron_evening_broadcast(run_crawl=crawl)


@app.post("/api/scheduler/clear-ledger")
def manual_clear_sent_ledger():
    """Clear sent stories ledger so test dispatches can be executed."""
    count = clear_sent_ledger()
    log_audit_event("LEDGER_CLEAR", "Sent Ledger", f"Manually cleared {count} records from sent stories ledger")
    return {"status": "ok", "cleared_records": count, "message": f"Cleared {count} ledger records"}


@app.post("/api/sources/ping")
def ping_source(req: dict):
    url = req.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required for ping")
    import time
    t0 = time.time()
    try:
        fetcher = Fetcher()
        resp = fetcher.session.get(url, timeout=6.0, headers=fetcher.session.headers)
        latency_ms = int((time.time() - t0) * 1000)
        content_len = len(resp.content)
        return {
            "status": "online" if resp.status_code < 400 else "warning",
            "http_code": resp.status_code,
            "latency_ms": latency_ms,
            "bytes": content_len,
            "msg": f"HTTP {resp.status_code} ({latency_ms}ms, {content_len} bytes)"
        }
    except Exception as e:
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "status": "error",
            "http_code": 0,
            "latency_ms": latency_ms,
            "bytes": 0,
            "msg": str(e)[:120]
        }


# =========================================================================
# Phase 3: Story Editorial & Manual Overrides
# =========================================================================
@app.get("/api/stories/{story_id}")
def get_story_details(story_id: str):
    from .db import get_story
    story = get_story(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return story


@app.put("/api/stories/{story_id}")
def edit_story(story_id: str, payload: dict):
    from .db import get_story, update_story
    story = get_story(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="Story title is required")
    update_story(story_id, payload)
    return {"status": "ok", "id": story_id, "message": "Story updated successfully"}


@app.delete("/api/stories/{story_id}")
def remove_story(story_id: str):
    from .db import get_story, delete_story
    story = get_story(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    delete_story(story_id)
    return {"status": "ok", "id": story_id, "message": "Story deleted"}


@app.post("/api/stories/manual")
def add_manual_story(payload: dict):
    from .db import create_manual_story
    if not payload.get("title") or not payload.get("company_id"):
        raise HTTPException(status_code=400, detail="Company and title are required")
    sid = create_manual_story(payload)
    return {"status": "ok", "id": sid, "message": "Breaking story published to intelligence desk"}


@app.get("/api/macro/{story_id}")
def get_macro_story_details(story_id: str):
    from .db import get_macro_story
    story = get_macro_story(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Macro story not found")
    return story


@app.put("/api/macro/{story_id}")
def edit_macro_story(story_id: str, payload: dict):
    from .db import get_macro_story, update_macro_story
    story = get_macro_story(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Macro story not found")
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="Directive title is required")
    update_macro_story(story_id, payload)
    return {"status": "ok", "id": story_id, "message": "Macro directive updated successfully"}


@app.delete("/api/macro/{story_id}")
def remove_macro_story(story_id: str):
    from .db import get_macro_story, delete_macro_story
    story = get_macro_story(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Macro story not found")
    delete_macro_story(story_id)
    return {"status": "ok", "id": story_id, "message": "Macro directive deleted"}


@app.post("/api/macro/manual")
def add_manual_macro_story(payload: dict):
    from .db import create_manual_macro_story
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="Title is required")
    sid = create_manual_macro_story(payload)
    return {"status": "ok", "id": sid, "message": "Manual macro policy directive published"}


# =========================================================================
# Phase 3: AI Prompt Engineering & Studio
# =========================================================================
@app.get("/api/ai/prompts")
def list_ai_prompts():
    from .db import get_ai_prompts
    return get_ai_prompts()


@app.get("/api/ai/prompts/{prompt_id}")
def get_single_ai_prompt(prompt_id: str):
    from .db import get_ai_prompt
    p = get_ai_prompt(prompt_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prompt template not found")
    return p


@app.post("/api/ai/prompts/{prompt_id}")
def update_ai_prompt(prompt_id: str, payload: dict):
    from .db import save_ai_prompt
    prompt_text = payload.get("prompt_text", "").strip()
    if not prompt_text:
        raise HTTPException(status_code=400, detail="Prompt template cannot be empty")
    model = payload.get("model", "gemini-1.5-flash")
    temperature = float(payload.get("temperature", 0.2))
    max_tokens = int(payload.get("max_tokens", 400))
    save_ai_prompt(prompt_id, prompt_text, model=model, temperature=temperature, max_tokens=max_tokens)
    return {"status": "ok", "id": prompt_id, "message": "Prompt template saved & active"}


@app.post("/api/ai/prompts/{prompt_id}/reset")
def reset_single_ai_prompt(prompt_id: str):
    from .db import reset_ai_prompt
    res = reset_ai_prompt(prompt_id)
    return {"status": "ok", "prompt": res, "message": "Prompt template reset to factory default"}


@app.post("/api/ai/test-prompt")
def test_ai_prompt(payload: dict):
    from .ai import get_gemini_key
    key = get_gemini_key()
    if not key:
        raise HTTPException(status_code=400, detail="Gemini API Key is missing in Settings / .env")

    prompt_text = payload.get("prompt_text", "")
    model = payload.get("model", "gemini-1.5-flash")
    temperature = float(payload.get("temperature", 0.2))
    max_tokens = int(payload.get("max_tokens", 400))

    company = payload.get("sample_company", "Reliance Industries")
    headline = payload.get("sample_headline", "Reliance Jio achieves record 500M subscriber milestone with nationwide 5G rollout")
    summary = payload.get("sample_snippet", "Jio Platforms added 12 million subscribers in the latest quarter with ARPU climbing to 182 rupees.")
    authority = payload.get("sample_authority", "Reserve Bank of India")

    # Safe variable replacement without breaking on JSON schema curly braces
    formatted_prompt = prompt_text
    for tag, val in [
        ("{company_name}", company),
        ("{headline}", headline),
        ("{summary}", summary),
        ("{authority}", authority),
        ("{title}", headline),
        ("{snippet}", summary),
    ]:
        formatted_prompt = formatted_prompt.replace(tag, str(val))

    import time
    import requests
    t0 = time.time()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    req_body = {
        "contents": [{"parts": [{"text": formatted_prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens, "responseMimeType": "application/json"}
    }

    try:
        res = requests.post(url, json=req_body, timeout=12)
        latency_ms = int((time.time() - t0) * 1000)
        if res.status_code == 200:
            data = res.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            parsed = None
            try:
                parsed = json.loads(raw)
            except Exception:
                pass
            return {
                "status": "ok",
                "latency_ms": latency_ms,
                "model": model,
                "raw_text": raw,
                "parsed": parsed
            }
        else:
            return {
                "status": "error",
                "latency_ms": latency_ms,
                "http_code": res.status_code,
                "message": res.text[:300]
            }
    except Exception as err:
        return {
            "status": "error",
            "latency_ms": int((time.time() - t0) * 1000),
            "message": str(err)
        }


@app.post("/api/crawl/run")
def trigger_crawl():
    """Trigger an immediate crawl across exchanges, publishers, and search feeds."""
    pipeline = Pipeline()
    res = pipeline.run_crawl(groups=["exchanges", "publishers", "search"])
    return res


@app.get("/api/logs")
def list_logs():
    with get_connection() as conn:
        runs = conn.execute("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 10").fetchall()
        logs = []
        for r in runs:
            st = str(r["started_at"] or "")[:19].replace("T", " ")
            logs.append({
                "time": st,
                "msg": f"Crawl cycle #{r['id']}: Checked {r['sources_checked']} sources -> Found {r['items_found']} items -> Stored {r['stories_saved']} stories",
                "type": "success" if not r["errors"] else "warn"
            })
            if r["errors"]:
                logs.append({
                    "time": st,
                    "msg": f"Notice: {r['errors']}",
                    "type": "warn"
                })
        return logs


@app.get("/api/digest/preview/{analyst_id}", response_class=HTMLResponse)
def preview_digest(analyst_id: str):
    """Render the daily digest HTML for the requested analyst."""
    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_unsent_stories_for_analyst(analyst_id)
    if not stories:
        from .db import get_sent_stories_for_analyst_today
        stories = get_sent_stories_for_analyst_today(analyst_id)

    html_output = render_digest_html(
        analyst.name,
        stories,
        analyst_id=analyst.id,
        assigned_folders=getattr(analyst, "assigned_folders", []),
        assigned_companies=getattr(analyst, "assigned_companies", []),
    )
    return HTMLResponse(
        content=html_output,
        status_code=200,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def get_ngrok_public_url() -> str | None:
    """Detect if ngrok tunnel is active to supply a live public URL for WhatsApp media delivery."""
    import requests
    try:
        r = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=1.5)
        if r.status_code == 200:
            for t in r.json().get("tunnels", []):
                if t.get("proto") == "https":
                    return t.get("public_url")
    except Exception:
        pass
    return None


@app.get("/api/digest/file/{filename}")
def serve_digest_file(filename: str):
    """Directly serve generated scorecard PDF for WhatsApp attachment and download."""
    target = DIGESTS_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="Digest file not found")
    media_type = "application/pdf" if target.suffix.lower() == ".pdf" else "text/html"
    return FileResponse(
        path=str(target),
        media_type=media_type,
        filename=filename,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/digest/download/{analyst_id}")
def download_digest_pdf(analyst_id: str):
    """Generate on demand and return high-definition PDF download for requested analyst named [Client_Name]_[Date].pdf."""
    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_unsent_stories_for_analyst(analyst_id)
    if not stories:
        from .db import get_sent_stories_for_analyst_today
        stories = get_sent_stories_for_analyst_today(analyst_id)

    file_path, _ = generate_analyst_digest(analyst.id, analyst.name, stories)

    media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "text/html"
    download_filename = file_path.name

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=download_filename,
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
    )


@app.get("/api/digest/meta/{analyst_id}")
def get_digest_meta(analyst_id: str):
    """Provide real-time intelligence summary metrics for the selected client's daily briefing."""
    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_unsent_stories_for_analyst(analyst_id)
    if not stories:
        from .db import get_sent_stories_for_analyst_today
        stories = get_sent_stories_for_analyst_today(analyst_id)

    filings = sum(1 for s in stories if s.get("filing_id") or (s.get("source_type") or "").lower() == "filing")
    grade_a = sum(1 for s in stories if (s.get("grade") or "").upper().startswith("GRADE A"))
    pdf_filename = get_clean_digest_filename(analyst.name, ext=".pdf")

    return {
        "analyst_id": analyst.id,
        "name": analyst.name,
        "phone": analyst.phone,
        "email": analyst.email,
        "assigned_folders": getattr(analyst, "assigned_folders", []),
        "assigned_companies": getattr(analyst, "assigned_companies", []),
        "total_stories": len(stories),
        "total_filings": filings,
        "grade_a_count": grade_a,
        "pdf_name": pdf_filename,
    }


@app.post("/api/digest/simulate-send/{analyst_id}")
def simulate_send_digest(analyst_id: str):
    """Dispatch 8:00 AM morning digest: generate PDF/HTML, send via Interakt WhatsApp, update sent ledger."""
    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    stories = get_unsent_stories_for_analyst(analyst_id)
    if not stories:
        return {"status": "no_op", "message": f"No unsent stories for {analyst.name}. Ledger is clean!", "count": 0}

    # Generate the physical digest file (PDF or HTML)
    file_path, _ = generate_analyst_digest(analyst.id, analyst.name, stories)

    # Detect live public URL (BASE_URL on GCP / ngrok tunnel) for direct WhatsApp PDF attachment with cache-buster
    public_base = os.getenv("BASE_URL") or get_ngrok_public_url()
    cb = int(datetime.now().timestamp())
    public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}" if public_base else None

    # Dispatch via Interakt WhatsApp (or safe simulation if not configured/TEST_MODE)
    wa_result = send_whatsapp_digest(
        analyst_name=analyst.name,
        analyst_phone=analyst.phone,
        stories=stories,
        pdf_path=file_path,
        public_pdf_url=public_pdf_url,
    )

    # Only mark as sent if dispatch succeeded or was simulated successfully
    if wa_result.get("status") in ("sent", "simulated"):
        story_ids = [s["id"] for s in stories]
        mark_sent(story_ids, analyst.id)

    dispatch_msg = wa_result.get("message", f"Dispatched {len(stories)} stories to {analyst.name}")
    return {
        "status": wa_result.get("status", "sent"),
        "mode": wa_result.get("mode", "simulated"),
        "message": dispatch_msg,
        "recipient": wa_result.get("recipient"),
        "file": file_path.name,
        "count": len(stories),
    }


class BatchSendRequest(BaseModel):
    analyst_ids: list[str]


@app.post("/api/digest/send-multiple")
def send_multiple_digests(req: BatchSendRequest):
    """Dispatch digests to multiple selected analysts."""
    results = []
    for aid in req.analyst_ids:
        try:
            res = simulate_send_digest(aid)
            results.append({"analyst_id": aid, "status": res.get("status"), "message": res.get("message")})
        except Exception as e:
            results.append({"analyst_id": aid, "status": "error", "message": str(e)})
    return {"results": results, "total": len(results)}


@app.get("/api/settings/delivery-mode")
def get_delivery_mode():
    """Check whether system is in TEST_MODE (safety redirect) or LIVE PRODUCTION."""
    import os
    from dotenv import load_dotenv
    from .config import PROJECT_ROOT
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    is_test = os.getenv("TEST_MODE", "yes").strip().lower() in ("yes", "true", "1")
    test_phone = os.getenv("TEST_WHATSAPP", "7900084773").strip()
    return {"test_mode": is_test, "test_phone": test_phone}


@app.post("/api/settings/delivery-mode")
def set_delivery_mode(payload: dict):
    """Toggle between TEST_MODE (safety redirect) and LIVE PRODUCTION (direct to analyst phone)."""
    import os
    import re
    from .config import PROJECT_ROOT
    new_mode = "yes" if payload.get("test_mode") else "no"
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        content = re.sub(r"^TEST_MODE\s*=.*$", f"TEST_MODE={new_mode}", content, flags=re.MULTILINE)
        env_path.write_text(content, encoding="utf-8")
    return {"test_mode": new_mode == "yes"}


@app.get("/api/settings/full")
def get_full_settings():
    """Return complete system configuration, gateway states, and database diagnostics."""
    import os
    from dotenv import load_dotenv
    from .config import DB_PATH, PROJECT_ROOT
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    is_test = os.getenv("TEST_MODE", "yes").strip().lower() in ("yes", "true", "1")
    test_phone = os.getenv("TEST_WHATSAPP", "7900084773").strip()

    interakt_key = os.getenv("INTERAKT_API_KEY", "").strip()
    interakt_masked = (interakt_key[:6] + "••••••••" + interakt_key[-4:]) if len(interakt_key) > 12 else "Not configured"

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_masked = (gemini_key[:4] + "••••••••" + gemini_key[-4:]) if len(gemini_key) > 10 else "Not configured"

    template = os.getenv("INTERAKT_TEMPLATE", "vriddhi_daily_digest_49").strip()
    max_age = int(os.getenv("MAX_ITEM_AGE_HOURS", "24"))
    delay_sec = float(os.getenv("PER_HOST_DELAY_SEC", "1.5"))
    body_limit = int(os.getenv("BODY_FETCH_LIMIT", "20"))

    db_size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

    with get_connection() as conn:
        stories_cnt = conn.execute("SELECT count(*) FROM stories").fetchone()[0]
        companies_cnt = conn.execute("SELECT count(*) FROM companies").fetchone()[0]
        sources_cnt = conn.execute("SELECT count(*) FROM sources").fetchone()[0]
        analysts_cnt = conn.execute("SELECT count(*) FROM analysts").fetchone()[0]
        fingerprints_cnt = conn.execute("SELECT count(*) FROM fingerprints").fetchone()[0]

    return {
        "test_mode": is_test,
        "test_phone": test_phone,
        "interakt_key_masked": interakt_masked,
        "interakt_has_key": bool(interakt_key),
        "interakt_template": template,
        "gemini_key_masked": gemini_masked,
        "gemini_has_key": bool(gemini_key),
        "max_item_age_hours": max_age,
        "per_host_delay_sec": delay_sec,
        "body_fetch_limit": body_limit,
        "db_size_bytes": db_size,
        "db_size_formatted": f"{db_size / (1024*1024):.2f} MB" if db_size > 1024*1024 else f"{db_size / 1024:.1f} KB",
        "counts": {
            "stories": stories_cnt,
            "companies": companies_cnt,
            "sources": sources_cnt,
            "analysts": analysts_cnt,
            "fingerprints": fingerprints_cnt,
        }
    }


@app.post("/api/settings/save")
def save_settings(payload: dict):
    """Update settings parameters in .env file with immediate reload."""
    import os
    import re
    from .config import PROJECT_ROOT
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        raise HTTPException(status_code=500, detail=".env file missing")

    content = env_path.read_text(encoding="utf-8")

    def update_var(txt: str, key: str, val: str) -> str:
        pattern = rf"^{key}\s*=.*$"
        if re.search(pattern, txt, flags=re.MULTILINE):
            return re.sub(pattern, f"{key}={val}", txt, flags=re.MULTILINE)
        else:
            return txt + f"\n{key}={val}"

    if "test_mode" in payload:
        val = "yes" if payload["test_mode"] else "no"
        content = update_var(content, "TEST_MODE", val)

    if "test_phone" in payload and payload["test_phone"]:
        clean_p = re.sub(r"[^\d]", "", str(payload["test_phone"]))[-10:]
        content = update_var(content, "TEST_WHATSAPP", clean_p)

    if "interakt_template" in payload and payload["interakt_template"]:
        content = update_var(content, "INTERAKT_TEMPLATE", str(payload["interakt_template"]).strip())

    if "gemini_key" in payload and payload["gemini_key"] and not payload["gemini_key"].startswith("••"):
        content = update_var(content, "GEMINI_API_KEY", str(payload["gemini_key"]).strip())

    if "interakt_key" in payload and payload["interakt_key"] and not payload["interakt_key"].startswith("••"):
        content = update_var(content, "INTERAKT_API_KEY", str(payload["interakt_key"]).strip())

    env_path.write_text(content, encoding="utf-8")
    return {"status": "saved"}


@app.post("/api/settings/test-whatsapp")
def test_whatsapp_gateway():
    """Verify live connectivity and authentication against the Interakt WhatsApp Business API."""
    import os
    import requests
    from dotenv import load_dotenv
    from .config import PROJECT_ROOT
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    api_key = os.getenv("INTERAKT_API_KEY", "").strip()
    if not api_key:
        return {"status": "error", "message": "INTERAKT_API_KEY is not configured in .env"}

    headers = {"Authorization": f"Basic {api_key}"}
    try:
        r = requests.get("https://api.interakt.ai/v1/public/track/users/", headers=headers, timeout=5.0)
        if r.status_code in (200, 201, 400, 404, 405):
            return {"status": "online", "code": r.status_code, "message": "Interakt WhatsApp Gateway authenticated & operational!"}
        elif r.status_code == 401:
            return {"status": "error", "code": 401, "message": "Unauthorized: Invalid Interakt API key"}
        else:
            return {"status": "warning", "code": r.status_code, "message": f"Gateway responded HTTP {r.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"Connection error: {str(e)[:80]}"}


@app.post("/api/settings/test-ai")
def test_ai_connection():
    """Test Google Gemini AI summarization engine status."""
    from .ai import is_gemini_active
    active = is_gemini_active()
    if active:
        return {"status": "online", "message": "Google Gemini 1.5 Flash AI Engine is online and ready for executive summaries."}
    else:
        return {"status": "warning", "message": "Gemini API key quota limit reached; heuristic zero-delay engine is currently handling summarization."}


@app.get("/api/settings/backup")
def download_database_backup():
    """Stream live snapshot backup of crawler.db directly to analyst computer."""
    from .config import DB_PATH
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="Database file not found")
    today = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(
        path=str(DB_PATH),
        filename=f"vriddhi_crawler_backup_{today}.db",
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="vriddhi_crawler_backup_{today}.db"'}
    )


@app.post("/api/settings/clean-db")
def clean_database():
    """Vacuum SQLite database and prune legacy crawl run logs to optimize performance."""
    import sqlite3
    from .config import DB_PATH
    with get_connection() as conn:
        conn.execute("DELETE FROM crawl_runs WHERE id NOT IN (SELECT id FROM crawl_runs ORDER BY id DESC LIMIT 50)")
    raw_conn = sqlite3.connect(DB_PATH, isolation_level=None)
    raw_conn.execute("VACUUM")
    raw_conn.close()
    return {"status": "cleaned", "message": "SQLite database vacuumed and optimized. Historical logs pruned."}


# =========================================================================
# Isolated Custom Web News Tracker Endpoints ("News" Tab Only)
# =========================================================================

class CustomNewsTopicsCreate(BaseModel):
    names: list[str] = []
    raw_input: str = ""


class CustomNewsTopicSelectUpdate(BaseModel):
    is_selected: bool


class CustomNewsFetchRequest(BaseModel):
    hours: int = 24
    topic_ids: list[str] | None = None
    scope: str = "all"


@app.get("/api/custom-news")
def api_get_custom_news(
    hours: int = 24,
    topic_ids: str | None = None,
    q: str | None = None,
    scope: str = "all",
):
    """Return saved custom news topics and SQLite-persisted articles grouped by topic."""
    parsed_ids = [x.strip() for x in topic_ids.split(",") if x.strip()] if topic_ids else None
    return get_custom_news_state(hours=hours, topic_ids=parsed_ids, search=q, scope=scope)


@app.post("/api/custom-news/topics")
def api_add_custom_news_topics(payload: CustomNewsTopicsCreate):
    """Save one or multiple custom topic/company names permanently for the News tab."""
    import re
    names: list[str] = list(payload.names or [])
    if payload.raw_input:
        parts = re.split(r"[,;\r\n]+", payload.raw_input)
        names.extend(parts)
    cleaned = [re.sub(r"\s+", " ", n.strip()) for n in names if n and n.strip()]
    if not cleaned:
        raise HTTPException(status_code=400, detail="Please enter at least one company or topic name.")
    res = add_custom_news_topics(cleaned)
    return {
        "status": "ok",
        "added": res["added"],
        "skipped": res["skipped"],
        "topics": res["topics"],
    }


@app.patch("/api/custom-news/topics/{topic_id}")
def api_toggle_custom_news_topic(topic_id: str, payload: CustomNewsTopicSelectUpdate):
    """Toggle selection state for a saved custom news topic."""
    updated = set_custom_news_topic_selected(topic_id, payload.is_selected)
    if not updated:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"status": "ok", "topic_id": topic_id, "is_selected": payload.is_selected}


@app.post("/api/custom-news/topics/select-all")
def api_select_all_custom_news_topics(payload: CustomNewsTopicSelectUpdate):
    """Select or clear selection for all saved custom news topics."""
    count = set_all_custom_news_topics_selected(payload.is_selected)
    return {"status": "ok", "updated": count, "is_selected": payload.is_selected}


@app.delete("/api/custom-news/topics/{topic_id}")
def api_delete_custom_news_topic(topic_id: str):
    """Permanently delete a saved custom news topic and its cached articles."""
    deleted = delete_custom_news_topic(topic_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Topic not found")
    return {"status": "deleted", "topic_id": topic_id}


@app.post("/api/custom-news/fetch")
def api_fetch_custom_news(payload: CustomNewsFetchRequest):
    """Fetch live multi-engine web news (Google, Bing, Yahoo, GDELT + Data Sources RSS) and persist unique articles."""
    from .sources.custom_news import fetch_multi_engine_news_batch

    hours_val = payload.hours if payload.hours in (24, 48, 720, 4320, 8760) else 24
    scope_val = "financial" if (payload.scope or "all").strip().lower() == "financial" else "all"
    all_topics = get_custom_news_topics()
    if not all_topics:
        return {
            **get_custom_news_state(hours=hours_val, scope=scope_val),
            "fetch_summary": {
                "fetched_topics": 0,
                "total_found": 0,
                "duplicates_removed": 0,
                "engine_counts": {},
                "errors": [],
            },
        }

    if payload.topic_ids:
        requested = set(payload.topic_ids)
        target_topics = [t for t in all_topics if t["id"] in requested]
        # Ensure explicitly refreshed topics are selected so their results appear immediately
        for t in target_topics:
            if not t.get("is_selected"):
                set_custom_news_topic_selected(t["id"], True)
    else:
        selected = [t for t in all_topics if t.get("is_selected")]
        target_topics = selected if selected else all_topics

    if not target_topics:
        raise HTTPException(status_code=404, detail="No matching saved topics found to fetch.")

    # Read active Data Sources RSS feeds strictly read-only for keyword matching
    try:
        active_rss_sources = [
            s for s in get_sources()
            if s.get("is_active", 1) and str(s.get("type") or "").strip().lower() == "rss"
        ]
    except Exception:
        active_rss_sources = []

    max_per_topic = 100 if hours_val >= 4320 else (75 if hours_val >= 720 else 50)
    batch = fetch_multi_engine_news_batch(
        target_topics,
        hours=hours_val,
        rss_sources=active_rss_sources,
        max_per_topic=max_per_topic,
    )
    failed_ids = batch.get("failed_topic_ids") or set()

    for t in target_topics:
        tid = t["id"]
        if tid in failed_ids:
            continue
        items = batch["results_by_topic"].get(tid, [])
        save_custom_news_articles(tid, t["name"], items, fetched_hours=hours_val)

    state = get_custom_news_state(hours=hours_val, scope=scope_val)
    state["fetch_summary"] = {
        "fetched_topics": len(target_topics),
        "total_found": batch["total_found"],
        "duplicates_removed": batch.get("duplicates_removed", 0),
        "engine_counts": batch.get("engine_counts", {}),
        "errors": batch["errors"],
    }
    return state


# =========================================================================
# Custom News WhatsApp Schedule, PDF Digest Preview & Broadcast Endpoints
# =========================================================================

class CustomNewsScheduleUpdate(BaseModel):
    dispatch_time: str | None = None
    dispatch_active: bool | None = None
    window_hours: int | None = None
    interakt_template: str | None = None
    frequency: str | None = None
    day_of_week: int | None = None
    day_of_month: int | None = None


@app.get("/api/custom-news/schedule")
def api_get_custom_news_schedule():
    """Return editable WhatsApp delivery time, frequency, active status, and saved digest window for News tab."""
    return {"status": "ok", **get_custom_news_schedule()}


@app.post("/api/custom-news/schedule")
def api_save_custom_news_schedule(payload: CustomNewsScheduleUpdate):
    """Save editable WhatsApp delivery time, frequency, day, active status, and digest window for News tab."""
    updated = save_custom_news_schedule(
        dispatch_time=payload.dispatch_time,
        dispatch_active=payload.dispatch_active,
        window_hours=payload.window_hours,
        interakt_template=payload.interakt_template,
        frequency=payload.frequency,
        day_of_week=payload.day_of_week,
        day_of_month=payload.day_of_month,
    )
    log_audit_event(
        "NEWS_SCHEDULE_UPDATE",
        "News Digest",
        f"Updated News WhatsApp schedule: {updated['frequency_summary']} at {updated['dispatch_time']} IST, Window={updated['window_label']}, Active={updated['dispatch_active']}",
    )
    return {"status": "ok", **updated}


@app.get("/api/custom-news/digest/meta/{analyst_id}")
def get_custom_news_digest_meta(analyst_id: str):
    """Return metadata for a client's personalized News PDF digest."""
    from .pdf import get_clean_news_digest_filename

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    digest_data = get_custom_news_digest_for_analyst(analyst_id)
    sched = get_custom_news_schedule()
    pdf_filename = get_clean_news_digest_filename(analyst.name, ext=".pdf")

    return {
        "analyst_id": analyst.id,
        "name": analyst.name,
        "phone": analyst.phone,
        "email": analyst.email,
        "assigned_topics": digest_data["assigned_topic_names"],
        "assigned_topic_ids": digest_data["assigned_topic_ids"],
        "topics_count": len(digest_data["topic_groups"]),
        "total_stories": digest_data["total_articles"],
        "topics_with_news": digest_data["topics_with_news"],
        "topics_without_news": digest_data["topics_without_news"],
        "window_hours": digest_data["hours"],
        "window_label": digest_data["window_label"],
        "dispatch_time": sched["dispatch_time"],
        "dispatch_time_12h": sched["dispatch_time_12h"],
        "frequency": sched["frequency"],
        "frequency_label": sched["frequency_label"],
        "frequency_summary": sched["frequency_summary"],
        "pdf_name": pdf_filename,
    }


@app.get("/api/custom-news/digest/preview/{analyst_id}", response_class=HTMLResponse)
def preview_custom_news_digest(analyst_id: str):
    """Render the personalized News Briefing HTML preview for the requested client."""
    from .pdf import render_news_digest_html

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    digest_data = get_custom_news_digest_for_analyst(analyst_id)
    html_output = render_news_digest_html(analyst.name, analyst.id, digest_data)

    return HTMLResponse(
        content=html_output,
        status_code=200,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/custom-news/digest/download/{analyst_id}")
def download_custom_news_digest_pdf(analyst_id: str):
    """Generate and download the personalized News Briefing PDF."""
    from .pdf import generate_news_digest

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    digest_data = get_custom_news_digest_for_analyst(analyst_id)
    file_path, _ = generate_news_digest(analyst.id, analyst.name, digest_data)

    media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "text/html"
    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name,
        headers={
            "Content-Disposition": f'attachment; filename="{file_path.name}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@app.post("/api/custom-news/digest/send/{analyst_id}")
def dispatch_custom_news_digest(analyst_id: str):
    """Generate and dispatch a client's personalized News PDF via WhatsApp (sends 'No news from this topic' if 0 articles)."""
    from .pdf import generate_news_digest
    from .whatsapp import send_whatsapp_news_digest

    analysts = {a.id: a for a in get_analysts()}
    analyst = analysts.get(analyst_id)
    if not analyst:
        raise HTTPException(status_code=404, detail="Analyst not found")

    digest_data = get_custom_news_digest_for_analyst(analyst_id)
    if not digest_data["assigned_topic_ids"]:
        return {
            "status": "no_op",
            "message": f"No News tab topics are assigned to {analyst.name}. Edit client to assign topics first.",
            "count": 0,
        }

    file_path, _ = generate_news_digest(analyst.id, analyst.name, digest_data)
    public_base = os.getenv("BASE_URL") or get_ngrok_public_url()
    cb = int(datetime.now().timestamp())
    public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}" if public_base else None

    wa_result = send_whatsapp_news_digest(
        analyst_name=analyst.name,
        analyst_phone=analyst.phone,
        digest_data=digest_data,
        pdf_path=file_path,
        public_pdf_url=public_pdf_url,
    )

    dispatch_msg = wa_result.get(
        "message",
        f"Dispatched News PDF ({digest_data['total_articles']} articles across {len(digest_data['topic_groups'])} topics) to {analyst.name}",
    )
    return {
        "status": wa_result.get("status", "sent"),
        "mode": wa_result.get("mode", "simulated"),
        "message": dispatch_msg,
        "recipient": wa_result.get("recipient"),
        "file": file_path.name,
        "count": digest_data["total_articles"],
        "topics_count": len(digest_data["topic_groups"]),
    }


@app.api_route("/api/cron/news-broadcast", methods=["GET", "POST"])
def trigger_cron_news_broadcast(run_fetch: bool = True):
    """Automated or manual broadcast of personalized News Tab PDFs to all active clients with assigned News topics."""
    from .pdf import generate_news_digest
    from .sources.custom_news import fetch_multi_engine_news_batch
    from .whatsapp import send_whatsapp_news_digest

    sched = get_custom_news_schedule()
    if not sched["dispatch_active"]:
        log.warning("[CRON] News Tab WhatsApp Broadcast is PAUSED. Skipping dispatch.")
        record_dispatch_run(
            "custom_news",
            recipients_count=0,
            stories_count=0,
            status="PAUSED",
            details=[{"status": "paused", "msg": "News delivery paused in schedule"}],
        )
        return {
            "status": "paused",
            "message": "News Briefing WhatsApp broadcast is currently PAUSED.",
            "dispatched_count": 0,
        }

    all_analysts = get_analysts()
    assigned_clients = [
        a for a in all_analysts
        if getattr(a, "is_active", True) and len(getattr(a, "assigned_news_topics", []) or []) > 0
    ]
    if not assigned_clients:
        record_dispatch_run(
            "custom_news",
            recipients_count=0,
            stories_count=0,
            status="CLEAN",
            details=[{"status": "no_clients", "msg": "No active clients have assigned News topics"}],
        )
        return {
            "status": "no_op",
            "message": "No active clients have News tab topics assigned yet.",
            "total_clients": 0,
            "dispatched_count": 0,
            "results": [],
        }

    hours_val = sched["window_hours"]
    if run_fetch:
        try:
            needed_ids = {tid for a in assigned_clients for tid in (getattr(a, "assigned_news_topics", []) or [])}
            all_topics = get_custom_news_topics()
            target_topics = [t for t in all_topics if t["id"] in needed_ids]
            if target_topics:
                active_rss = [
                    s for s in get_sources()
                    if s.get("is_active", 1) and str(s.get("type") or "").strip().lower() == "rss"
                ]
                max_per_topic = 100 if hours_val >= 4320 else (75 if hours_val >= 720 else 50)
                batch = fetch_multi_engine_news_batch(
                    target_topics,
                    hours=hours_val,
                    rss_sources=active_rss,
                    max_per_topic=max_per_topic,
                )
                failed_ids = batch.get("failed_topic_ids") or set()
                for t in target_topics:
                    if t["id"] not in failed_ids:
                        save_custom_news_articles(t["id"], t["name"], batch["results_by_topic"].get(t["id"], []), fetched_hours=hours_val)
        except Exception as fetch_err:
            log.warning("[CRON] News pre-broadcast fetch warning: %s", fetch_err)

    public_base = os.getenv("BASE_URL") or get_ngrok_public_url() or "https://35.244.60.224.sslip.io"
    results = []

    for a in assigned_clients:
        digest_data = get_custom_news_digest_for_analyst(a.id, hours=hours_val)
        if not digest_data["assigned_topic_ids"]:
            continue
        try:
            file_path, _ = generate_news_digest(a.id, a.name, digest_data)
            cb = int(datetime.now().timestamp())
            public_pdf_url = f"{public_base.rstrip('/')}/api/digest/file/{file_path.name}?t={cb}"
            wa_result = send_whatsapp_news_digest(
                analyst_name=a.name,
                analyst_phone=a.phone,
                digest_data=digest_data,
                pdf_path=file_path,
                public_pdf_url=public_pdf_url,
            )
            results.append({
                "id": a.id,
                "name": a.name,
                "phone": a.phone,
                "count": digest_data["total_articles"],
                "topics": len(digest_data["topic_groups"]),
                "status": wa_result.get("status", "sent"),
                "message": wa_result.get("message"),
            })
        except Exception as err:
            log.error("[CRON] Failed to send News PDF to %s: %s", a.name, err)
            results.append({
                "id": a.id,
                "name": a.name,
                "phone": a.phone,
                "count": digest_data["total_articles"],
                "status": "error",
                "error": str(err),
            })

    sent_count = len([r for r in results if r["status"] in ("sent", "simulated")])
    total_articles = sum(r["count"] for r in results)
    run_status = "COMPLETED" if sent_count > 0 else "PARTIAL"
    record_dispatch_run("custom_news", recipients_count=sent_count, stories_count=total_articles, status=run_status, details=results)

    return {
        "status": "success",
        "broadcast": "custom_news_briefing",
        "window_label": sched["window_label"],
        "total_clients": len(assigned_clients),
        "dispatched_count": sent_count,
        "results": results,
    }


@app.post("/api/scheduler/trigger-news")
def manual_trigger_news(crawl: bool = True):
    """Manual on-demand trigger of the News Tab PDF WhatsApp broadcast."""
    log_audit_event("MANUAL_TRIGGER", "News Tab Digest", "Initiated manual News tab WhatsApp broadcast from web terminal")
    return trigger_cron_news_broadcast(run_fetch=crawl)


_NEWS_TIMER_STARTED = False


def _start_custom_news_timer_loop() -> None:
    """Background IST timer that fires the News WhatsApp broadcast at the editable dispatch_time."""
    global _NEWS_TIMER_STARTED
    if _NEWS_TIMER_STARTED:
        return
    _NEWS_TIMER_STARTED = True

    import threading
    from .config import IST

    def _loop() -> None:
        last_fired_key = ""
        while True:
            try:
                sched = get_custom_news_schedule()
                now_ist = datetime.now(IST)
                hhmm = now_ist.strftime("%H:%M")
                slot_key = f"{now_ist.strftime('%Y-%m-%d')} {hhmm}"
                if should_fire_custom_news_now(sched, now_ist) and slot_key != last_fired_key:
                    last_fired_key = slot_key
                    log.info(
                        "[TIMER] Triggering scheduled %s News WhatsApp broadcast at %s IST",
                        sched.get("frequency_summary", "Daily"),
                        hhmm,
                    )
                    trigger_cron_news_broadcast(run_fetch=True)
            except Exception as exc:
                log.warning("[TIMER] Custom news timer check error: %s", exc)
            time.sleep(25)

    t = threading.Thread(target=_loop, name="custom-news-whatsapp-timer", daemon=True)
    t.start()


@app.on_event("startup")
def _on_startup_timers():
    _start_custom_news_timer_loop()


def start():
    """Run uvicorn server on configured port."""
    import uvicorn
    uvicorn.run("vriddhi_crawler.server:app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    start()
