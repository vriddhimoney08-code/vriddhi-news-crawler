"""Crawl pipeline: source execution -> matching -> deduplication -> database storage."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc
from typing import Any

from .ai import evaluate_and_summarize, is_gemini_active
from .config import GOOGLE_NEWS_EDITIONS, MAX_ITEM_AGE_HOURS
from .controlpanel import Company, Source
from .db import (
    add_fingerprint,
    get_companies,
    get_connection,
    get_recent_stories,
    get_sources,
    has_fingerprint,
    save_story,
)
from .http import Fetcher
from .matching import Matcher
from .normalize import (
    are_near_duplicates,
    canonical_url,
    headline_fingerprint,
    is_generic_market_noise,
    is_reputable_publisher,
    strip_publisher_suffix,
)
from .sources import exchanges, publishers, search
from .sources.base import RawItem

log = logging.getLogger(__name__)


class Pipeline:
    """Orchestrates crawls, company matching, deduplication, and persistence."""

    def __init__(self, fetcher: Fetcher | None = None):
        self.fetcher = fetcher or Fetcher()

    def run_crawl(self, groups: list[str] | None = None, force: bool = False) -> dict[str, Any]:
        """Execute crawl across specified groups: exchanges, publishers, search."""
        if groups is None:
            groups = ["exchanges", "publishers", "search"]

        started_at = datetime.now(UTC)
        since = started_at - timedelta(hours=MAX_ITEM_AGE_HOURS)

        companies = get_companies()
        matcher = Matcher(companies)
        source_records = get_sources()

        raw_items: list[RawItem] = []
        errors: list[str] = []
        sources_checked = 0

        # Group 1: Exchanges (BSE & NSE)
        if "exchanges" in groups:
            # BSE
            sources_checked += 1
            try:
                bse_items = exchanges.bse_announcements(self.fetcher, matcher, since=since, max_pages=3)
                raw_items.extend(bse_items)
            except Exception as e:
                msg = f"BSE announcements failed: {e}"
                log.warning(msg)
                errors.append(msg)

            # NSE
            sources_checked += 1
            try:
                nse_items = exchanges.nse_announcements(self.fetcher, matcher, since=since)
                raw_items.extend(nse_items)
            except Exception as e:
                msg = f"NSE announcements failed: {e}"
                log.warning(msg)
                errors.append(msg)

        # Group 2: Publishers (RSS, Sitemaps, Pages)
        if "publishers" in groups:
            for s_row in source_records:
                if not s_row.get("is_active"):
                    continue
                stype = s_row.get("type", "").lower()
                if stype in ("filing",):
                    continue  # already covered by exchanges
                sources_checked += 1
                src = Source(
                    name=s_row["name"],
                    url=s_row["url"],
                    type=stype,
                    keep_pattern=s_row.get("keep_pattern"),
                    language=s_row.get("language", "en"),
                    body_check=bool(s_row.get("body_check")),
                    is_active=bool(s_row.get("is_active")),
                )
                try:
                    if stype == "sitemap":
                        items = publishers.read_sitemap(self.fetcher, src, since=since)
                        raw_items.extend(items)
                    elif stype == "rss":
                        items = publishers.read_rss(self.fetcher, src, since=since)
                        raw_items.extend(items)
                except Exception as e:
                    msg = f"Source {src.name} failed: {e}"
                    log.warning(msg)
                    errors.append(msg)

        # Group 3: Search (Google News & GDELT)
        if "search" in groups:
            for comp in companies:
                sources_checked += 1
                try:
                    g_items = search.google_news(self.fetcher, comp, GOOGLE_NEWS_EDITIONS, since, errors)
                    for item in g_items:
                        # Strictly verify that the headline explicitly mentions this company or alias
                        headline_matches = matcher.match_text(item.title)
                        if any(m.id == comp.id for m in headline_matches):
                            item.company_ids = [comp.id]
                            raw_items.append(item)
                except Exception as e:
                    errors.append(f"Google News for {comp.name}: {e}")

        # Process and store raw items
        saved_count = self._process_items(raw_items, matcher, companies)

        completed_at = datetime.now(UTC)
        result = {
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "sources_checked": sources_checked,
            "items_found": len(raw_items),
            "stories_saved": saved_count,
            "errors": "; ".join(errors) if errors else ""
        }

        # Log crawl run to DB
        with get_connection() as conn:
            conn.execute("""
            INSERT INTO crawl_runs (started_at, completed_at, sources_checked, items_found, stories_saved, errors)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (result["started_at"], result["completed_at"], sources_checked, len(raw_items), saved_count, result["errors"]))

        return result

    def _process_items(self, items: list[RawItem], matcher: Matcher, companies: list[Company]) -> int:
        saved_count = 0
        body_fetches = 0
        company_lookup = {c.id: c for c in companies}
        # Retrieve all recent stories (no 8 AM cutoff) so deduplication works across all runs
        recent_stories = get_recent_stories(limit=2000, mode="all")

        now_utc = datetime.now(UTC)

        for item in items:
            # 0a. Strict Tier-1 Institutional Publisher Filter: drop ScanX and unverified scrapers
            if not is_reputable_publisher(item.source_name, item.url, item.source_type):
                continue

            # 0b. Drop generic market wrap noise immediately
            if item.source_type != "filing" and is_generic_market_noise(item.title):
                continue

            # 0b. Strict 24-hour freshness filter: drop older news or news without a publication date
            if item.published_at:
                if (now_utc - item.published_at) > timedelta(hours=MAX_ITEM_AGE_HOURS):
                    continue
                if (item.published_at - now_utc) > timedelta(hours=2):
                    continue
            elif item.source_type != "filing":
                # Drop undated news so old archived articles never get stamped with today's date
                continue

            # 1. Deduplicate by filing ID if present
            if item.filing_id:
                filing_fp = hashlib.sha256(f"filing:{item.filing_id}".encode()).hexdigest()
                if has_fingerprint(filing_fp):
                    continue
                add_fingerprint(filing_fp, "filing")

            # 2. Canonical URL check
            norm_url = canonical_url(item.url)
            if norm_url:
                url_fp = hashlib.sha256(f"url:{norm_url}".encode()).hexdigest()
                if has_fingerprint(url_fp):
                    continue
                add_fingerprint(url_fp, "url")

            # 3. Resolve target companies strictly
            matched_companies: list[Company] = []
            if item.company_ids:
                matched_companies = [company_lookup[cid] for cid in item.company_ids if cid in company_lookup]
            else:
                matched_companies = matcher.match_text(item.title)
                if not matched_companies and item.summary:
                    matched_companies = matcher.match_text(item.summary)
                # If body check enabled and no headline/summary match, safely inspect main content
                if not matched_companies and item.body_check and item.url and body_fetches < 10:
                    try:
                        r = self.fetcher.get(item.url, check_robots=False, delay=0.5, timeout=8)
                        body = matcher.extract_body_text(r.content)
                        if body:
                            body_matches = matcher.match_text(body[:3000])
                            # Only accept if exactly 1 company matches and name appears at least twice
                            if len(body_matches) == 1:
                                cand = body_matches[0]
                                if body.lower().count(cand.name.lower()) >= 2:
                                    matched_companies = [cand]
                        body_fetches += 1
                    except Exception:
                        pass

            # Prioritize companies explicitly named in headline if multiple were found
            if len(matched_companies) > 1 and item.source_type != "filing":
                headline_only = matcher.match_text(item.title)
                if headline_only:
                    matched_companies = headline_only

            # Discard generic multi-company sector wraps and listicles (3+ companies)
            if len(matched_companies) >= 3 and item.source_type != "filing":
                continue

            cleaned_title = strip_publisher_suffix(item.title, item.source_name)
            if not cleaned_title:
                continue

            grade = matcher.grade_story(cleaned_title, item.summary, item.source_type)
            final_summary = item.summary or ""

            # Drop non-material Grade C news if not an official filing or rating
            if item.source_type != "filing" and grade == "Grade C" and not is_gemini_active():
                continue

            for comp in matched_companies:
                # 3b. Evaluate materiality with Gemini AI if active
                if is_gemini_active() and item.source_type != "filing":
                    eval_res = evaluate_and_summarize(comp.name, cleaned_title, item.summary)
                    if not eval_res.get("is_material", True):
                        continue  # AI discarded as non-material noise!
                    grade = eval_res.get("grade", grade)
                    final_summary = eval_res.get("executive_summary", final_summary)

                # 4. Check for near-duplicates in recent stories for this company
                merged = False
                for existing in recent_stories:
                    if existing["company_id"] == comp.id:
                        if are_near_duplicates(cleaned_title, existing["title"]) or (item.url and item.url == existing.get("url")):
                            # Merge source into existing story
                            sources_list = existing.get("sources", [])
                            if item.url and not any(s.get("url") == item.url for s in sources_list):
                                sources_list.append({"name": item.source_name, "url": item.url})
                                existing["sources"] = sources_list
                                save_story(existing)
                            merged = True
                            break

                if merged:
                    continue

                # 5. Generate story record with deterministic primary key ID
                fp_key = headline_fingerprint(cleaned_title) or cleaned_title.lower()
                story_id = hashlib.sha256(f"{comp.id}:{fp_key}".encode()).hexdigest()[:16]
                story_dict = {
                    "id": story_id,
                    "title": cleaned_title,
                    "summary": final_summary,
                    "url": item.url or "",
                    "source_name": item.source_name,
                    "source_type": item.source_type,
                    "published_at": (item.published_at or now_utc).isoformat(),
                    "company_id": comp.id,
                    "grade": grade,
                    "filing_id": item.filing_id,
                    "sources": [{"name": item.source_name, "url": item.url}] if item.url else [],
                }
                save_story(story_dict)
                recent_stories.append(story_dict)
                saved_count += 1

        return saved_count
