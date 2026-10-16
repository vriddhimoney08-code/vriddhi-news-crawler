"""FastAPI Application for Vriddhi News Crawler Web Dashboard on port 3009."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import DIGESTS_DIR, PORT
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
    get_sources,
    get_unsent_stories_for_analyst,
    init_db,
    mark_sent,
    save_analyst,
    save_company,
    toggle_source_status,
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
def list_macro_sectors():
    from .db import get_macro_sectors
    return {"sectors": get_macro_sectors()}


@app.post("/api/macro/crawl")
def trigger_macro_crawl(hours: int = 48):
    """Trigger verified macro crawl across PIB, RBI, SEBI, and official wires."""
    from .sources.macro import MacroPipeline
    return MacroPipeline().run_macro_crawl(hours=hours)


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

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=30)
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

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=30)
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

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=30)
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

    stories = get_macro_stories_for_analyst(analyst_id, hours=24, limit=30)
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
        is_active=True
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


class AnalystCreate(BaseModel):
    id: str = ""
    name: str
    phone: str
    email: str = ""
    assigned_companies: list[str] = []
    assigned_folders: list[str] = []


@app.get("/api/analysts")
def list_analysts():
    return [asdict(a) for a in get_analysts()]


@app.post("/api/analysts")
def create_or_update_analyst(item: AnalystCreate):
    aid = item.id.strip().lower() or item.name.strip().lower().replace(" ", "_")
    analyst = Analyst(
        id=aid,
        name=item.name.strip(),
        phone=item.phone.strip(),
        email=item.email.strip(),
        assigned_companies=item.assigned_companies,
        assigned_folders=item.assigned_folders
    )
    save_analyst(analyst)
    return {"status": "ok", "analyst": asdict(analyst)}


@app.delete("/api/analysts/{analyst_id}")
def remove_analyst(analyst_id: str):
    delete_analyst(analyst_id)
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
