"""Verified Government, Central Bank, and Regulatory Macro Source Connectors."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc
from typing import Any
from urllib.parse import quote_plus

import feedparser  # type: ignore[import-untyped]

from ..db import get_live_window, save_macro_story
from ..http import Fetcher
from ..macro_ai import classify_macro_with_ai
from ..normalize import clean_text, strip_publisher_suffix
from .base import parse_date

log = logging.getLogger(__name__)


def extract_ministry_from_title(title: str, text: str = "") -> str:
    """Detect official Indian Ministry or Regulator from announcement text."""
    combined = f"{title} {text}".lower()
    ministry_map = [
        ("Cabinet / PMO", [r"\bcabinet\b", r"\bpmo\b", r"\bprime minister\b", r"\bunion cabinet\b"]),
        ("Ministry of Finance", [r"\bministry of finance\b", r"\bfinmin\b", r"\bgst\b", r"\bincome tax\b", r"\brevenue\b", r"\bexpenditure\b"]),
        ("Ministry of Commerce & Industry", [r"\bcommerce\b", r"\bindustry\b", r"\btrade\b", r"\bexport\b", r"\bimport\b", r"\banti-dumping\b", r"\bpli\b"]),
        ("Ministry of Defense", [r"\bdefense\b", r"\bdefence\b", r"\bdac\b", r"\barmy\b", r"\bnavy\b", r"\bair force\b", r"\bdrdo\b"]),
        ("Ministry of Railways", [r"\brailway\b", r"\brailways\b", r"\bvande bharat\b", r"\btracks\b", r"\blocos\b"]),
        ("Ministry of Power & MNRE", [r"\bpower\b", r"\belectricity\b", r"\brenewable\b", r"\bsolar\b", r"\bgreen hydrogen\b"]),
        ("Ministry of Petroleum & Natural Gas", [r"\bpetroleum\b", r"\bnatural gas\b", r"\bcrude\b", r"\boil\b", r"\brefining\b"]),
        ("Ministry of Road Transport (MoRTH)", [r"\bmorth\b", r"\bhighway\b", r"\bnhai\b", r"\broad transport\b", r"\bexpressway\b"]),
        ("Ministry of Chemicals & Fertilizers", [r"\bchemical\b", r"\bchemicals\b", r"\bfertilizer\b", r"\bfertilizers\b", r"\burea\b"]),
        ("Ministry of Agriculture", [r"\bagriculture\b", r"\bfarmer\b", r"\bmsp\b", r"\bkisan\b"]),
        ("Ministry of Heavy Industries", [r"\bheavy industries\b", r"\bautomotive\b", r"\bfame\b", r"\be-bus\b"]),
        ("Reserve Bank of India (RBI)", [r"\brbi\b", r"\breserve bank\b", r"\bmonetary policy\b", r"\brepo\b"]),
        ("Securities & Exchange Board (SEBI)", [r"\bsebi\b", r"\bsecurities and exchange\b", r"\bf&o\b", r"\bmutual fund\b"]),
        ("MoSPI (National Statistics)", [r"\bmospi\b", r"\bcpi\b", r"\bwholesale price\b", r"\biip\b", r"\bgdp\b"]),
    ]
    import re
    for name, pats in ministry_map:
        if any(re.search(p, combined) for p in pats):
            return name
    return "Government of India"


class MacroPipeline:
    """Orchestrates verified macro news crawling, AI impact classification, and persistence."""

    def __init__(self, fetcher: Fetcher | None = None):
        self.fetcher = fetcher or Fetcher()

    def run_macro_crawl(self, hours: int = 48) -> dict[str, Any]:
        """Ingest official government releases and regulatory circulars across all sectors."""
        now_utc = datetime.now(UTC)
        since = now_utc - timedelta(hours=hours)

        raw_items: list[dict[str, Any]] = []
        errors: list[str] = []

        # 1. PIB Government Releases
        try:
            pib_items = self._fetch_pib(since)
            raw_items.extend(pib_items)
        except Exception as e:
            errors.append(f"PIB crawl error: {e}")

        # 2. RBI Official Releases
        try:
            rbi_items = self._fetch_rbi(since)
            raw_items.extend(rbi_items)
        except Exception as e:
            errors.append(f"RBI crawl error: {e}")

        # 3. SEBI Official Releases
        try:
            sebi_items = self._fetch_sebi(since)
            raw_items.extend(sebi_items)
        except Exception as e:
            errors.append(f"SEBI crawl error: {e}")

        # 4. Verified Economy & Commodity Wires
        try:
            wire_items = self._fetch_economy_wires(since)
            raw_items.extend(wire_items)
        except Exception as e:
            errors.append(f"Economy wires error: {e}")

        # Sort raw items so official authorities (PIB_GOV, RBI, SEBI) are processed first
        def _auth_rank(src: str) -> int:
            return 1 if src in ("PIB_GOV", "RBI", "SEBI") else 2

        raw_items.sort(key=lambda x: _auth_rank(x.get("source_authority", "")))

        # Process and store items with cross-source deduplication
        from ..db import get_macro_stories
        from ..normalize import are_near_duplicates

        saved_count = 0
        existing_stories = get_macro_stories(limit=1500, mode="all")
        seen_fingerprints = {s["id"] for s in existing_stories}

        for item in raw_items:
            clean_title = clean_text(strip_publisher_suffix(item["title"]))
            if not clean_title or len(clean_title) < 15:
                continue

            # 1. Check for cross-source semantic near-duplicates
            matched_existing = None
            for ex in existing_stories:
                if are_near_duplicates(clean_title, ex.get("title", "")):
                    matched_existing = ex
                    break

            if matched_existing:
                # If current item is a secondary wire and existing is already official PIB/RBI/SEBI, drop the wire reprint!
                if item["source_authority"] == "FINANCIAL_WIRE" and matched_existing.get("source_authority") in ("PIB_GOV", "RBI", "SEBI"):
                    continue

                # If current item is official Government/PIB and existing was secondary wire, promote to official gazette!
                if item["source_authority"] in ("PIB_GOV", "RBI", "SEBI") and matched_existing.get("source_authority") == "FINANCIAL_WIRE":
                    matched_existing["title"] = clean_title
                    matched_existing["url"] = item.get("url", matched_existing.get("url", ""))
                    matched_existing["source_authority"] = item["source_authority"]
                    matched_existing["ministry_or_regulator"] = item["ministry_or_regulator"]
                    save_macro_story(matched_existing)
                continue

            # Deterministic ID based on clean title
            fp = hashlib.sha256(f"macro:{clean_title.lower()}".encode()).hexdigest()[:16]
            if fp in seen_fingerprints:
                continue
            seen_fingerprints.add(fp)

            # Classify sector and equity impact with AI
            classified = classify_macro_with_ai(
                title=clean_title,
                snippet=item.get("summary", ""),
                authority=item["ministry_or_regulator"]
            )

            story_record = {
                "id": fp,
                "title": clean_title,
                "summary": item.get("summary", clean_title),
                "url": item.get("url", ""),
                "source_authority": item["source_authority"],
                "ministry_or_regulator": item["ministry_or_regulator"],
                "sectors": classified.get("sectors", ["GENERAL_MACRO"]),
                "impact_grade": classified.get("impact_grade", "Tier 2 (Sector Impact)"),
                "impact_bias": classified.get("impact_bias", "NEUTRAL"),
                "impact_summary": classified.get("impact_summary", clean_title),
                "published_at": item.get("published_at") or now_utc.isoformat(),
            }

            save_macro_story(story_record)
            existing_stories.append(story_record)
            saved_count += 1

        return {
            "status": "success",
            "items_found": len(raw_items),
            "stories_saved": saved_count,
            "errors": errors
        }

    def _fetch_pib(self, since: datetime) -> list[dict[str, Any]]:
        """Fetch verified press releases from Government of India (pib.gov.in)."""
        items: list[dict[str, Any]] = []
        url = "https://news.google.com/rss/search?q=site:pib.gov.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            r = self.fetcher.get(url, check_robots=False, delay=1.0)
            fp = feedparser.parse(r.content)
            for e in fp.entries:
                pub = parse_date(str(e.get("published", "")))
                if pub and pub < since:
                    continue
                title = clean_text(str(e.get("title", "")))
                title = strip_publisher_suffix(title, "pib.gov.in")
                title = strip_publisher_suffix(title, "PIB")
                summary = clean_text(str(e.get("summary", "")))
                link = str(e.get("link", ""))
                ministry = extract_ministry_from_title(title, summary)
                items.append({
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source_authority": "PIB_GOV",
                    "ministry_or_regulator": ministry,
                    "published_at": pub.isoformat() if pub else None
                })
        except Exception as e:
            log.warning("PIB fetch error: %s", e)
        return items

    def _fetch_rbi(self, since: datetime) -> list[dict[str, Any]]:
        """Fetch official Reserve Bank of India press releases and notifications."""
        items: list[dict[str, Any]] = []
        # Direct RBI RSS
        direct_url = "https://rbi.org.in/pressreleases_rss.xml"
        try:
            r = self.fetcher.get(direct_url, check_robots=False, delay=1.0)
            fp = feedparser.parse(r.content)
            for e in fp.entries:
                pub = parse_date(str(e.get("published", "")))
                if pub and pub < since:
                    continue
                title = clean_text(str(e.get("title", "")))
                summary = clean_text(str(e.get("summary", "")))
                link = str(e.get("link", ""))
                items.append({
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source_authority": "RBI",
                    "ministry_or_regulator": "Reserve Bank of India (RBI)",
                    "published_at": pub.isoformat() if pub else None
                })
        except Exception:
            pass

        # Fallback Google query for RBI
        search_url = "https://news.google.com/rss/search?q=site:rbi.org.in+when:2d&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            r = self.fetcher.get(search_url, check_robots=False, delay=1.0)
            fp = feedparser.parse(r.content)
            for e in fp.entries:
                pub = parse_date(str(e.get("published", "")))
                if pub and pub < since:
                    continue
                title = strip_publisher_suffix(clean_text(str(e.get("title", ""))))
                if "tenders" in title.lower():
                    continue
                items.append({
                    "title": title,
                    "summary": clean_text(str(e.get("summary", ""))),
                    "url": str(e.get("link", "")),
                    "source_authority": "RBI",
                    "ministry_or_regulator": "Reserve Bank of India (RBI)",
                    "published_at": pub.isoformat() if pub else None
                })
        except Exception:
            pass

        return items

    def _fetch_sebi(self, since: datetime) -> list[dict[str, Any]]:
        """Fetch official SEBI circulars and board decisions."""
        items: list[dict[str, Any]] = []
        direct_url = "https://www.sebi.gov.in/sebirss.xml"
        try:
            r = self.fetcher.get(direct_url, check_robots=False, delay=1.0)
            fp = feedparser.parse(r.content)
            for e in fp.entries:
                pub = parse_date(str(e.get("published", "")))
                if pub and pub < since:
                    continue
                title = clean_text(str(e.get("title", "")))
                items.append({
                    "title": title,
                    "summary": clean_text(str(e.get("summary", ""))),
                    "url": str(e.get("link", "")),
                    "source_authority": "SEBI",
                    "ministry_or_regulator": "Securities & Exchange Board (SEBI)",
                    "published_at": pub.isoformat() if pub else None
                })
        except Exception:
            pass
        return items

    def _fetch_economy_wires(self, since: datetime) -> list[dict[str, Any]]:
        """Fetch verified Tier-1 financial macro/policy wire items."""
        items: list[dict[str, Any]] = []
        wire_urls = [
            ("Mint Economy", "https://www.livemint.com/rss/economy"),
            ("ET Economy", "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms")
        ]
        for source_name, url in wire_urls:
            try:
                r = self.fetcher.get(url, check_robots=False, delay=1.0)
                fp = feedparser.parse(r.content)
                for e in fp.entries:
                    pub = parse_date(str(e.get("published", "")))
                    if pub and pub < since:
                        continue
                    raw_title = clean_text(str(e.get("title", "")))
                    title = strip_publisher_suffix(raw_title, source_name)
                    # Filter out opinion columns and clickbait
                    if any(w in title.lower() for w in ["opinion:", "view:", "editorial", "why is", "here's why", "podcast"]):
                        continue
                    summary = clean_text(str(e.get("summary", "")))
                    items.append({
                        "title": title,
                        "summary": summary,
                        "url": str(e.get("link", "")),
                        "source_authority": "FINANCIAL_WIRE",
                        "ministry_or_regulator": extract_ministry_from_title(title, summary),
                        "published_at": pub.isoformat() if pub else None
                    })
            except Exception:
                pass
        return items
