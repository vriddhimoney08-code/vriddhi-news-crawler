"""FastAPI Application for Vriddhi News Crawler Web Dashboard on port 3009."""
from __future__ import annotations

import json
import logging
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
    delete_analyst,
    delete_company,
    delete_folder,
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
)
from .pdf import generate_analyst_digest, render_digest_html
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
def list_stories(limit: int = 100, company_id: str | None = None, source_type: str | None = None, window_only: bool = True):
    return get_recent_stories(limit=limit, company_id=company_id, source_type=source_type, window_only=window_only)


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
    html_output = render_digest_html(analyst.name, stories)
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
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


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

    # Detect live public tunnel URL for direct WhatsApp PDF attachment with cache-buster
    public_base = get_ngrok_public_url()
    cb = int(datetime.now().timestamp())
    public_pdf_url = f"{public_base}/api/digest/file/{file_path.name}?t={cb}" if public_base else None

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


def start():
    """Run uvicorn server on configured port."""
    import uvicorn
    uvicorn.run("vriddhi_crawler.server:app", host="0.0.0.0", port=PORT, reload=False)


if __name__ == "__main__":
    start()
