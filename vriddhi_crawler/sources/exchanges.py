"""BSE and NSE corporate announcements for the whole market, kept for watchlist companies only.

Both read the data feeds behind the exchanges' own announcement pages. These are not licensed APIs:
if an exchange changes its format, this module logs the error and the rest of the crawler carries on.
"""
from __future__ import annotations

import logging
from datetime import datetime

try:
    from curl_cffi import requests as cffi_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

import requests

from ..config import IST
from ..http import Fetcher
from ..matching import Matcher
from ..normalize import clean_text
from .base import RawItem, parse_date

log = logging.getLogger(__name__)

BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_HEADERS = {
    "Referer": "https://www.bseindia.com/",
    "Origin": "https://www.bseindia.com",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
BSE_PDF = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"


def bse_announcements(fetcher: Fetcher, matcher: Matcher, since: datetime, max_pages: int) -> list[RawItem]:
    """Page through today's (and, early in the day, yesterday's) announcements, newest first,
    until a page holds nothing newer than `since`."""
    out: list[RawItem] = []
    today = datetime.now(IST).date()
    days = sorted({since.astimezone(IST).date(), today})
    for day in days:
        ymd = day.strftime("%Y%m%d")
        for page in range(1, max_pages + 1):
            params = {
                "pageno": page,
                "strCat": "-1",
                "strPrevDate": ymd,
                "strScrip": "",
                "strSearch": "P",
                "strToDate": ymd,
                "strType": "C",
                "subcategory": "-1",
            }
            rows = []
            try:
                if HAS_CURL_CFFI:
                    r = cffi_requests.get(
                        BSE_API,
                        params=params,
                        headers=BSE_HEADERS,
                        impersonate="chrome120",
                        timeout=8,
                    )
                else:
                    r = fetcher.get(BSE_API, params=params, headers=BSE_HEADERS, check_robots=False, delay=1.5)
                if getattr(r, "status_code", 0) == 200:
                    rows = (r.json() or {}).get("Table") or []
            except Exception as e:
                log.warning("BSE query error for %s: %s", ymd, e)
                break
            if not rows:
                break
            newest_on_page = None
            for a in rows:
                pub = parse_date(str(a.get("NEWS_DT") or a.get("DT_TM") or "")[:19], assume_ist=True)
                if pub and (newest_on_page is None or pub > newest_on_page):
                    newest_on_page = pub
                company = matcher.by_bse.get(str(a.get("SCRIP_CD") or "").strip())
                if not company:
                    continue
                if pub and pub < since:
                    continue
                attach = a.get("ATTACHMENTNAME")
                cat = clean_text(a.get("CATEGORYNAME") or "")
                out.append(RawItem(
                    source_name="BSE" + (f" · {cat}" if cat else ""),
                    source_type="filing",
                    title=clean_text(a.get("HEADLINE") or a.get("NEWSSUB") or "Exchange filing"),
                    url=(BSE_PDF + attach) if attach else "https://www.bseindia.com/corporates/ann.html",
                    published_at=pub,
                    filing_id=f"bse:{a.get('NEWSID')}" if a.get("NEWSID") else None,
                    company_ids=[company.id],
                ))
            if newest_on_page and newest_on_page < since:
                break
    return out


NSE_HOME = "https://www.nseindia.com"
NSE_API = "https://www.nseindia.com/api/corporate-announcements"
NSE_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}


def nse_announcements(fetcher: Fetcher, matcher: Matcher, since: datetime) -> list[RawItem]:
    frm = since.astimezone(IST).strftime("%d-%m-%Y")
    to = datetime.now(IST).strftime("%d-%m-%Y")
    api_headers = {
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    }
    if HAS_CURL_CFFI:
        s = cffi_requests.Session(impersonate="chrome120")
        s.headers.update(NSE_BROWSER_HEADERS)
        s.get(NSE_HOME, timeout=20)
        s.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", timeout=20)
        r = s.get(
            NSE_API,
            params={"index": "equities", "from_date": frm, "to_date": to},
            headers=api_headers,
            timeout=20,
        )
    else:
        s = requests.Session()
        s.headers.update(NSE_BROWSER_HEADERS)
        fetcher.get(NSE_HOME, session=s, check_robots=False, delay=1.5)
        fetcher.get("https://www.nseindia.com/companies-listing/corporate-filings-announcements", session=s, check_robots=False, delay=1.5)
        r = fetcher.get(
            NSE_API,
            params={"index": "equities", "from_date": frm, "to_date": to},
            headers=api_headers,
            session=s,
            check_robots=False,
            delay=1.5,
        )

    try:
        data = r.json() if getattr(r, "status_code", 0) == 200 else {}
    except Exception:
        data = {}
    rows = data if isinstance(data, list) else data.get("data", [])
    out: list[RawItem] = []
    for a in rows:
        company = matcher.by_nse.get(str(a.get("symbol") or "").strip().upper())
        if not company:
            continue
        pub = parse_date(a.get("sort_date") or a.get("an_dt"), assume_ist=True)
        if pub and pub < since:
            continue
        subject = clean_text(a.get("desc") or "")
        detail = clean_text(a.get("attchmntText") or "")
        title = f"{subject}: {detail}" if detail and detail.lower() != subject.lower() else (subject or detail)
        title = title[:300] or "Exchange filing"
        fid = a.get("seq_id") or a.get("attchmntFile")
        out.append(RawItem(
            source_name="NSE" + (f" · {subject}" if subject else ""),
            source_type="filing",
            title=title,
            url=a.get("attchmntFile") or "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
            published_at=pub,
            filing_id=f"nse:{fid}" if fid else None,
            company_ids=[company.id],
        ))
    return out
