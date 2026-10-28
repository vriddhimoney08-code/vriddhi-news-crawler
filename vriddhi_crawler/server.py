"""FastAPI Application for Vriddhi News Crawler Web Dashboard on port 3009."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import (
    DIGESTS_DIR,
    PORT,
    DASHBOARD_USERNAME,
    DASHBOARD_PASSWORD,
    SESSION_SECRET,
)
from .controlpanel import Analyst, Company
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


@app.get("/", response_class=FileResponse)
def serve_dashboard():
    """Serve the single-page application dashboard."""
    index_file = STATIC_DIR / "index.html"
    return FileResponse(str(index_file))


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


class AnalystCreate(BaseModel):
    id: str = ""
    name: str
    phone: str
    email: str = ""
    assigned_companies: list[str] = []
    assigned_folders: list[str] = []
    macro_sectors: list[str] = ["ALL"]
    is_active: bool = True


@app.get("/api/analysts")
def list_analysts():
    return [asdict(a) for a in get_analysts()]


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
    analyst = Analyst(
        id=aid,
        name=item.name.strip(),
        phone=item.phone.strip(),
        email=item.email.strip(),
        assigned_companies=item.assigned_companies,
        assigned_folders=item.assigned_folders,
        macro_sectors=item.macro_sectors or ["ALL"],
        is_active=item.is_active
    )
    save_analyst(analyst)
    log_audit_event("CLIENT_UPDATE", analyst.name, f"Saved client {analyst.name} (Phone: {analyst.phone}, Active: {analyst.is_active}, Sectors: {len(analyst.macro_sectors)})")
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

    return {
        "morning_time": morning_time,
        "morning_active": morning_active,
        "evening_time": evening_time,
        "evening_active": evening_active,
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


def start():
    """Run uvicorn server on configured port."""
    import uvicorn
    uvicorn.run("vriddhi_crawler.server:app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    start()
