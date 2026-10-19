"""Interakt WhatsApp Business API Client for Vriddhi News Crawler."""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import (
    INTERAKT_API_KEY,
    INTERAKT_DOCUMENT_HEADER,
    INTERAKT_LANGUAGE,
    INTERAKT_TEMPLATE,
    IST,
    TEST_MODE,
    TEST_WHATSAPP,
)

log = logging.getLogger("vriddhi_whatsapp")


def format_phone_number(raw_phone: str) -> tuple[str, str]:
    """Extract country code and 10-digit phone number.
    Returns: (country_code, 10_digit_number)
    """
    digits = "".join(ch for ch in raw_phone if ch.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        return "+91", digits[2:]
    if len(digits) >= 10:
        return "+91", digits[-10:]
    return "+91", digits


import re


def sanitize_variable(val: Any) -> str:
    """Ensure WhatsApp template variable contains no tabs, newlines, or >1 consecutive spaces."""
    s = str(val or "")
    s = re.sub(r"[\r\n\t]+", " ", s)
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s or "—"


def build_highlights_text(stories: list[dict[str, Any]]) -> str:
    """Build concise single-line highlight for WhatsApp body variable (Meta prohibits newlines in variables)."""
    if not stories:
        return "Market intelligence updates recorded"
    top = stories[0]
    cname = top.get("company_name") or "Watchlist"
    title = top.get("title") or "Corporate update"
    text = f"{cname}: {title}"
    clean = sanitize_variable(text)
    if len(clean) > 80:
        clean = clean[:77] + "..."
    return clean


_PDF_CDN_CACHE: dict[str, str] = {}


def upload_pdf_to_cdn(pdf_path: Path | None) -> str | None:
    """Upload research scorecard PDF to a fast public CDN returning a direct application/pdf binary stream."""
    if not pdf_path or not Path(pdf_path).exists() or Path(pdf_path).suffix.lower() != ".pdf":
        return None

    pdf_p = Path(pdf_path)
    cache_key = f"{pdf_p.resolve()}_{pdf_p.stat().st_mtime}"
    if cache_key in _PDF_CDN_CACHE:
        return _PDF_CDN_CACHE[cache_key]

    fname = pdf_p.name

    # 1. Primary: Direct application/pdf binary stream upload via Catbox CDN
    try:
        import requests
        with open(pdf_p, "rb") as f:
            res = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": (fname, f, "application/pdf")},
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                timeout=25,
            )
        if res.status_code == 200 and res.text.strip().startswith("http"):
            cdn_url = res.text.strip()
            log.info("Uploaded direct binary PDF to Catbox CDN: %s", cdn_url)
            _PDF_CDN_CACHE[cache_key] = cdn_url
            return cdn_url
    except Exception as e:
        log.warning("Catbox CDN upload failed (%s), trying secondary providers...", e)

    # 2. Secondary: GitHub Release Asset if running inside GitHub Actions
    gh_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    gh_repo = os.getenv("GITHUB_REPOSITORY", "vriddhimoney08-code/vriddhi-news-crawler")
    if gh_token and gh_repo:
        try:
            import requests
            gh_headers = {
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "VriddhiCrawler",
            }
            # Look up release ID for latest-digests tag
            r_rel = requests.get(f"https://api.github.com/repos/{gh_repo}/releases/tags/latest-digests", headers=gh_headers, timeout=10)
            if r_rel.status_code == 200:
                rel_id = r_rel.json().get("id")
                # Upload asset
                with open(pdf_p, "rb") as f:
                    up_res = requests.post(
                        f"https://uploads.github.com/repos/{gh_repo}/releases/{rel_id}/assets?name={fname}",
                        headers={
                            "Authorization": f"Bearer {gh_token}",
                            "Content-Type": "application/pdf",
                            "Accept": "application/vnd.github.v3+json",
                            "User-Agent": "VriddhiCrawler",
                        },
                        data=f.read(),
                        timeout=30,
                    )
                if up_res.status_code in (200, 201):
                    gh_asset_url = up_res.json().get("browser_download_url")
                    log.info("Uploaded PDF to GitHub Release asset: %s", gh_asset_url)
                    _PDF_CDN_CACHE[cache_key] = gh_asset_url
                    return gh_asset_url
        except Exception as gh_err:
            log.warning("GitHub Release asset upload failed: %s", gh_err)

    return None


def send_whatsapp_digest(
    analyst_name: str,
    analyst_phone: str,
    stories: list[dict[str, Any]],
    pdf_path: Path | None = None,
    public_pdf_url: str | None = None,
) -> dict[str, Any]:
    """Send or simulate sending a WhatsApp digest via Interakt.

    If INTERAKT_API_KEY is not set or TEST_MODE is on, handles dispatch safely.
    """
    import os
    from dotenv import load_dotenv
    from .config import PROJECT_ROOT

    # Dynamically read latest .env values in case user just updated keys
    load_dotenv(PROJECT_ROOT / ".env", override=True)

    api_key = os.getenv("INTERAKT_API_KEY", "").strip()
    template_name = os.getenv("INTERAKT_TEMPLATE", "vriddhi_daily_digest_49").strip()
    lang = os.getenv("INTERAKT_LANGUAGE", "en").strip()
    doc_header = os.getenv("INTERAKT_DOCUMENT_HEADER", "yes").strip().lower() in ("yes", "true", "1")
    is_test_mode = os.getenv("TEST_MODE", "no").strip().lower() in ("yes", "true", "1")
    test_phone = os.getenv("TEST_WHATSAPP", "").strip()

    today_str = datetime.now(IST).strftime("%d-%b-%Y")
    first_name = analyst_name.split()[0] if analyst_name else "Analyst"

    # Determine recipient number: use analyst phone if test_phone is left as dummy placeholder
    if is_test_mode and test_phone and test_phone not in ("9820000000", "9800000000", ""):
        target_raw_phone = test_phone
    else:
        target_raw_phone = analyst_phone or test_phone

    if target_raw_phone in ("9820000000", "9820000001", "9820000002", "9820000003", ""):
        log.info("Skipping dummy placeholder phone number %s for %s", target_raw_phone, analyst_name)
        return {
            "status": "skipped",
            "mode": "dummy_phone",
            "recipient": target_raw_phone,
            "message": f"Skipped dispatch for {analyst_name} (dummy placeholder number {target_raw_phone})",
        }

    country_code, clean_phone = format_phone_number(target_raw_phone)

    # Compute digest metrics
    unique_companies = {s.get("company_id") for s in stories if s.get("company_id")}
    filings_count = sum(1 for s in stories if s.get("source_type") == "filing")
    top_bullets = build_highlights_text(stories)

    raw_body_values = [
        first_name,
        today_str,
        str(len(stories)),
        str(len(unique_companies)),
        str(filings_count),
        top_bullets,
    ]
    body_values = [sanitize_variable(v) for v in raw_body_values]

    # Check if API key is configured
    if not api_key:
        log.info(
            "INTERAKT_API_KEY is not set in .env. Running in PREVIEW/SIMULATION mode for %s (%s%s).",
            analyst_name,
            country_code,
            clean_phone,
        )
        return {
            "status": "simulated",
            "mode": "preview",
            "recipient": f"{country_code} {clean_phone}",
            "template": template_name,
            "variables": body_values,
            "message": f"Preview simulated for {analyst_name} ({country_code} {clean_phone}). Set INTERAKT_API_KEY in .env for live dispatch.",
        }

    # Prepare Interakt API request (handle both raw key and pre-encoded Base64 string)
    try:
        decoded = base64.b64decode(api_key).decode("utf-8")
        if ":" in decoded or len(decoded) > 20:
            auth_b64 = api_key
        else:
            auth_bytes = f"{api_key}:".encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("ascii")
    except Exception:
        auth_bytes = f"{api_key}:".encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")



    pdf_filename = Path(pdf_path).name if pdf_path else f"{first_name}_{today_str}.pdf"

    header_values = []
    if doc_header:
        cdn_link = upload_pdf_to_cdn(pdf_path) if pdf_path else None
        base_url = (os.getenv("BASE_URL") or "").rstrip("/")
        fallback_server_url = f"{base_url}/api/digest/file/{pdf_filename}" if (base_url and pdf_filename) else None
        doc_link = (
            public_pdf_url
            or cdn_link
            or fallback_server_url
            or "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
        )
        header_values.append(doc_link)

    candidates = [template_name]
    for alt in ["vriddhi_daily_digest_49", "vriddhi_daily_digest_48", "vriddhi_daily_digest"]:
        if alt not in candidates:
            candidates.append(alt)

    last_error_code = 400
    last_error_body = ""

    for candidate in candidates:
        template_obj: dict[str, Any] = {
            "name": candidate,
            "languageCode": lang,
            "headerValues": header_values,
            "bodyValues": body_values,
        }
        if doc_header and pdf_filename:
            template_obj["fileName"] = pdf_filename

        payload = {
            "countryCode": country_code,
            "phoneNumber": clean_phone,
            "type": "Template",
            "template": template_obj,
        }

        req = urllib.request.Request(
            url="https://api.interakt.ai/v1/public/message/",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth_b64}",
                "User-Agent": "VriddhiCrawler/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                log.info("Interakt WhatsApp dispatch succeeded with template '%s': %s", candidate, resp_data)
                return {
                    "status": "sent",
                    "mode": "live",
                    "recipient": f"{country_code} {clean_phone}",
                    "template": candidate,
                    "data": resp_data,
                    "message": f"Live WhatsApp message dispatched to {country_code} {clean_phone} via Interakt!",
                }
        except urllib.error.HTTPError as e:
            last_error_code = e.code
            last_error_body = e.read().decode("utf-8", errors="replace")
            log.warning("Interakt candidate '%s' HTTP %s: %s", candidate, e.code, last_error_body)

            # If rejected because of fileName property, retry candidate without fileName
            if "fileName" in last_error_body and "fileName" in template_obj:
                try:
                    template_obj.pop("fileName", None)
                    payload["template"] = template_obj
                    req_retry = urllib.request.Request(
                        url="https://api.interakt.ai/v1/public/message/",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Basic {auth_b64}",
                            "User-Agent": "VriddhiCrawler/1.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req_retry, timeout=15) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        log.info("Interakt WhatsApp dispatch succeeded without fileName '%s': %s", candidate, resp_data)
                        return {
                            "status": "sent",
                            "mode": "live",
                            "recipient": f"{country_code} {clean_phone}",
                            "template": candidate,
                            "data": resp_data,
                            "message": f"Live WhatsApp message dispatched to {country_code} {clean_phone} via Interakt!",
                        }
                except Exception as retry_err:
                    log.warning("Retry without fileName also failed: %s", retry_err)

            # If error is not a template mismatch, don't try other candidates
            if "No approved template found" not in last_error_body:
                break
        except Exception as e:
            log.error("Failed to reach Interakt API: %s", e)
            return {
                "status": "error",
                "recipient": f"{country_code} {clean_phone}",
                "error": str(e),
                "message": f"Failed to connect to Interakt: {e}",
            }

    # If reached here, dispatch failed
    if "re-sync on Interakt dashboard" in last_error_body:
        helpful_msg = (
            "Interakt Sync Required: Meta has approved your template, but Interakt's dispatch engine "
            "requires a manual sync. In your Interakt dashboard (app.interakt.ai/templates), "
            "click the green [Sync] button on the top right next to 'Last synced on', wait 10 seconds, then try again."
        )
    else:
        helpful_msg = f"Interakt API Error ({last_error_code}): {last_error_body}"

    return {
        "status": "error",
        "http_code": last_error_code,
        "recipient": f"{country_code} {clean_phone}",
        "error": last_error_body,
        "message": helpful_msg,
    }


def send_whatsapp_macro_digest(
    analyst_name: str,
    analyst_phone: str,
    stories: list[dict[str, Any]],
    pdf_path: Path | None = None,
    public_pdf_url: str | None = None,
) -> dict[str, Any]:
    """Send or simulate sending an Evening Macro & Policy WhatsApp digest via Interakt.
    Reuses the existing approved Interakt template.
    """
    import os
    from dotenv import load_dotenv
    from .config import PROJECT_ROOT

    load_dotenv(PROJECT_ROOT / ".env", override=True)

    api_key = os.getenv("INTERAKT_API_KEY", "").strip()
    template_name = os.getenv("INTERAKT_MACRO_TEMPLATE", os.getenv("INTERAKT_TEMPLATE", "vriddhi_daily_digest_49")).strip()
    lang = os.getenv("INTERAKT_LANGUAGE", "en").strip()
    doc_header = os.getenv("INTERAKT_DOCUMENT_HEADER", "yes").strip().lower() in ("yes", "true", "1")
    is_test_mode = os.getenv("TEST_MODE", "no").strip().lower() in ("yes", "true", "1")
    test_phone = os.getenv("TEST_WHATSAPP", "").strip()

    today_str = datetime.now(IST).strftime("%d-%b-%Y (Evening)")
    first_name = analyst_name.split()[0] if analyst_name else "Analyst"

    if is_test_mode and test_phone and test_phone not in ("9820000000", "9800000000", ""):
        target_raw_phone = test_phone
    else:
        target_raw_phone = analyst_phone or test_phone

    if target_raw_phone in ("9820000000", "9820000001", "9820000002", "9820000003", ""):
        log.info("Skipping dummy placeholder phone number %s for %s", target_raw_phone, analyst_name)
        return {
            "status": "skipped",
            "mode": "dummy_phone",
            "recipient": target_raw_phone,
            "message": f"Skipped dispatch for {analyst_name} (dummy placeholder number {target_raw_phone})",
        }

    country_code, clean_phone = format_phone_number(target_raw_phone)

    unique_sectors = set()
    for s in stories:
        for sec in s.get("sectors", []):
            unique_sectors.add(sec)
    tier1_count = sum(1 for s in stories if "Tier 1" in (s.get("impact_grade") or ""))

    # Top highlight line
    top_title = stories[0].get("title", "") if stories else "Market policy directives recorded"
    auth = stories[0].get("source_authority", "Govt") if stories else "Gazette"
    highlight = f"Brent $104.30 | INR 94.94 | [{auth}] {top_title}"
    clean_highlight = sanitize_variable(highlight)
    if len(clean_highlight) > 80:
        clean_highlight = clean_highlight[:77] + "..."

    raw_body_values = [
        first_name,
        today_str,
        str(len(stories)),
        f"{len(unique_sectors)} Sectors" if unique_sectors else "All Sectors",
        str(tier1_count),
        clean_highlight,
    ]
    body_values = [sanitize_variable(v) for v in raw_body_values]

    if not api_key:
        log.info(
            "INTERAKT_API_KEY is not set in .env. Running in PREVIEW/SIMULATION mode for %s (%s%s).",
            analyst_name,
            country_code,
            clean_phone,
        )
        return {
            "status": "simulated",
            "mode": "preview",
            "recipient": f"{country_code} {clean_phone}",
            "template": template_name,
            "variables": body_values,
            "message": f"Preview simulated for {analyst_name} ({country_code} {clean_phone}). Set INTERAKT_API_KEY in .env for live dispatch.",
        }

    try:
        decoded = base64.b64decode(api_key).decode("utf-8")
        if ":" in decoded or len(decoded) > 20:
            auth_b64 = api_key
        else:
            auth_bytes = f"{api_key}:".encode("utf-8")
            auth_b64 = base64.b64encode(auth_bytes).decode("ascii")
    except Exception:
        auth_bytes = f"{api_key}:".encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("ascii")

    pdf_filename = Path(pdf_path).name if pdf_path else f"{first_name}_Macro_{today_str}.pdf"

    header_values = []
    if doc_header:
        cdn_link = upload_pdf_to_cdn(pdf_path) if pdf_path else None
        base_url = (os.getenv("BASE_URL") or "").rstrip("/")
        fallback_server_url = f"{base_url}/api/digest/file/{pdf_filename}" if (base_url and pdf_filename) else None
        doc_link = (
            public_pdf_url
            or cdn_link
            or fallback_server_url
            or "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
        )
        header_values.append(doc_link)

    candidates = [template_name]
    for alt in ["vriddhi_evening_macro_01", "vriddhi_daily_digest_49", "vriddhi_daily_digest"]:
        if alt not in candidates:
            candidates.append(alt)

    last_error_code = 400
    last_error_body = ""

    for candidate in candidates:
        template_obj: dict[str, Any] = {
            "name": candidate,
            "languageCode": lang,
            "headerValues": header_values,
            "bodyValues": body_values,
        }
        if doc_header and pdf_filename:
            template_obj["fileName"] = pdf_filename

        payload = {
            "countryCode": country_code,
            "phoneNumber": clean_phone,
            "type": "Template",
            "template": template_obj,
        }

        req = urllib.request.Request(
            url="https://api.interakt.ai/v1/public/message/",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Basic {auth_b64}",
                "User-Agent": "VriddhiCrawler/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                log.info("Interakt WhatsApp macro dispatch succeeded with template '%s': %s", candidate, resp_data)
                return {
                    "status": "sent",
                    "mode": "live",
                    "recipient": f"{country_code} {clean_phone}",
                    "template": candidate,
                    "data": resp_data,
                    "message": f"Live WhatsApp Macro briefing dispatched to {country_code} {clean_phone} via Interakt!",
                }
        except urllib.error.HTTPError as e:
            last_error_code = e.code
            last_error_body = e.read().decode("utf-8", errors="replace")
            log.warning("Interakt candidate '%s' HTTP %s: %s", candidate, e.code, last_error_body)

            if "fileName" in last_error_body and "fileName" in template_obj:
                try:
                    template_obj.pop("fileName", None)
                    payload["template"] = template_obj
                    req_retry = urllib.request.Request(
                        url="https://api.interakt.ai/v1/public/message/",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": f"Basic {auth_b64}",
                            "User-Agent": "VriddhiCrawler/1.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req_retry, timeout=15) as resp:
                        resp_data = json.loads(resp.read().decode("utf-8"))
                        log.info("Interakt WhatsApp macro dispatch succeeded without fileName '%s': %s", candidate, resp_data)
                        return {
                            "status": "sent",
                            "mode": "live",
                            "recipient": f"{country_code} {clean_phone}",
                            "template": candidate,
                            "data": resp_data,
                            "message": f"Live WhatsApp Macro briefing dispatched to {country_code} {clean_phone} via Interakt!",
                        }
                except Exception as retry_err:
                    log.warning("Retry without fileName failed: %s", retry_err)

            if "No approved template found" not in last_error_body:
                break

        except urllib.error.URLError as e:
            log.error("Failed to reach Interakt API: %s", e)
            return {
                "status": "error",
                "recipient": f"{country_code} {clean_phone}",
                "error": str(e),
                "message": f"Failed to connect to Interakt: {e}",
            }

    if "re-sync on Interakt dashboard" in last_error_body:
        helpful_msg = (
            "Interakt Sync Required: Meta has approved your template, but Interakt's dispatch engine "
            "requires a manual sync. In your Interakt dashboard (app.interakt.ai/templates), "
            "click the green [Sync] button on the top right next to 'Last synced on', wait 10 seconds, then try again."
        )
    else:
        helpful_msg = f"Interakt API Error ({last_error_code}): {last_error_body}"

    return {
        "status": "error",
        "http_code": last_error_code,
        "recipient": f"{country_code} {clean_phone}",
        "error": last_error_body,
        "message": helpful_msg,
    }

