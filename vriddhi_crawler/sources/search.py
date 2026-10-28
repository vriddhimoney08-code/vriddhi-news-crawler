"""Search-based sources that find the long tail: Google News (per company, several query variants and
language editions) and the GDELT news index (batches of companies per query)."""
from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote_plus

import feedparser

from ..controlpanel import Company
from ..http import Fetcher
from ..normalize import (
    clean_text,
    is_paywalled_url,
    is_reputable_publisher,
    is_sponsored_or_pr,
    resolve_news_url,
    strip_publisher_suffix,
)
from .base import RawItem, parse_date

log = logging.getLogger(__name__)


def default_queries(c: Company) -> list[str]:
    """Up to three query variants when the Watchlist gives none: names, then brands."""
    if c.search_queries:
        return c.search_queries
    names = [a for a in c.aliases if len(a) > 3][:4]
    qs = [" OR ".join(f'"{n}"' for n in names[:2])]
    if len(names) > 2:
        qs.append(" OR ".join(f'"{n}"' for n in names[2:4]))
    if c.nse_symbol and len(c.nse_symbol) >= 5:
        qs.append(f'"{c.nse_symbol}" share')
    return [q for q in qs if q]


def google_news(fetcher: Fetcher, company: Company, editions: list[str], since: datetime,
                failures: list[str]) -> list[RawItem]:
    out = []
    for q in default_queries(company):
        for ed in editions:
            lang = ed.split("-")[0]
            url = (f"https://news.google.com/rss/search?q={quote_plus(q + ' when:2d')}"
                   f"&hl={ed}&gl=IN&ceid=IN:{lang}")
            try:
                r = fetcher.get(url, check_robots=False, delay=1.5)
            except Exception as e:
                failures.append(f"{company.name} [{ed}]: {e}")
                continue
            for e in feedparser.parse(r.content).entries:
                pub = parse_date(str(e.get("published", "")))
                if not pub or pub < since:
                    continue
                src = e.get("source")
                publisher = "Google News"
                if isinstance(src, dict) and src.get("title"):
                    publisher = str(src.get("title"))
                elif hasattr(src, "title") and getattr(src, "title"):
                    publisher = str(getattr(src, "title"))
                raw_title = str(e.get("title") or "")
                title = strip_publisher_suffix(clean_text(raw_title), publisher)
                summary = clean_text(str(e.get("summary") or e.get("description") or ""))
                raw_link = e.get("link")
                link_str: str | None = str(raw_link) if raw_link is not None else None
                # Decode Google News redirect URL to obtain actual destination
                real_url = resolve_news_url(link_str) if link_str else ""
                final_url = real_url or link_str

                # Drop paywalled subscription links right at ingestion (ET Prime, Mint Premium, BS Premium, etc.)
                if is_paywalled_url(final_url):
                    continue

                # Drop paid PR wires, advertorials, and sponsored marketing
                if is_sponsored_or_pr(title, final_url):
                    continue

                if not is_reputable_publisher(publisher, final_url, "news"):
                    continue

                out.append(RawItem(source_name=publisher, source_type="news", title=title, summary=summary, url=final_url,
                                   published_at=pub, lang=lang))
    return out


GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def gdelt(fetcher: Fetcher, companies: list[Company], since: datetime, failures: list[str],
          batch: int = 5) -> list[RawItem]:
    """One query per batch of companies; the matcher later decides which company each article is about."""
    out = []
    for i in range(0, len(companies), batch):
        group = companies[i:i + batch]
        names = [f'"{c.name}"' for c in group if len(c.name) > 3]
        if not names:
            continue
        query = "(" + " OR ".join(names) + ")" if len(names) > 1 else names[0]
        params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": 250,
                  "timespan": "1d", "sort": "datedesc"}
        try:
            # GDELT asks clients to keep to about one request every five seconds
            r = fetcher.get(GDELT_API, params=params, check_robots=False, delay=5.5)
            data = r.json() if r.text.strip().startswith("{") else {}
        except Exception as e:
            failures.append(f"GDELT batch {i // batch + 1}: {e}")
            continue
        for a in data.get("articles", []):
            pub = parse_date(a.get("seendate"))
            if not pub or pub < since:
                continue
            src_domain = a.get("domain") or "GDELT"
            raw_url = a.get("url")
            if not is_reputable_publisher(src_domain, raw_url, "news"):
                continue
            out.append(RawItem(source_name=src_domain, source_type="news",
                               title=clean_text(a.get("title")), url=raw_url, published_at=pub,
                               lang=(a.get("language") or "en")[:2].lower()))
    return out
