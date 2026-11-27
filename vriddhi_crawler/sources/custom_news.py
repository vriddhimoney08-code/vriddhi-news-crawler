"""Dedicated multi-engine open-web news fetcher strictly for the custom 'News' tab.

Aggregates unique, deduplicated articles across 5 free sources:
  1. Google News RSS
  2. Bing News RSS (unwraps direct publisher URLs)
  3. Yahoo News RSS
  4. GDELT Global News Index
  5. Configured active RSS feeds from Data Sources (strictly read-only keyword match)

Kept completely separate from the main portfolio watchlist crawler and WhatsApp dispatch pipeline.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import feedparser
import requests

from ..http import DEFAULT_HEADERS, Fetcher
from ..normalize import (
    canonical_url,
    clean_text,
    is_paywalled_url,
    is_reputable_publisher,
    is_sponsored_or_pr,
    strip_publisher_suffix,
)
from .base import parse_date

log = logging.getLogger(__name__)

VALID_HOURS = (24, 48, 720, 4320, 8760)

WINDOW_TO_WHEN = {
    24: "1d",
    48: "2d",
    720: "30d",
    4320: "180d",
    8760: "365d",
}

WINDOW_TO_GDELT = {
    24: "1d",
    48: "2d",
    720: "1m",
    4320: "3m",
    8760: "3m",
}

GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"

KNOWN_DOMAIN_NAMES = {
    "economictimes.indiatimes.com": "The Economic Times",
    "timesofindia.indiatimes.com": "Times of India",
    "livemint.com": "Livemint",
    "moneycontrol.com": "Moneycontrol",
    "business-standard.com": "Business Standard",
    "financialexpress.com": "Financial Express",
    "cnbctv18.com": "CNBC-TV18",
    "ndtvprofit.com": "NDTV Profit",
    "ndtv.com": "NDTV",
    "businesstoday.in": "Business Today",
    "thehindubusinessline.com": "The Hindu BusinessLine",
    "thehindu.com": "The Hindu",
    "indianexpress.com": "The Indian Express",
    "hindustantimes.com": "Hindustan Times",
    "reuters.com": "Reuters",
    "bloomberg.com": "Bloomberg",
    "bbc.com": "BBC News",
    "bbc.co.uk": "BBC News",
    "techcrunch.com": "TechCrunch",
    "cnbc.com": "CNBC",
    "inc42.com": "Inc42",
    "entrackr.com": "Entrackr",
    "yourstory.com": "YourStory",
    "zeebiz.com": "Zee Business",
}


def _http_get(url: str, params: dict | None = None, timeout: int = 12) -> requests.Response:
    """Thread-safe stateless HTTP GET with browser headers."""
    resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp


def _unwrap_bing_url(url: str) -> str:
    """Extract the direct publisher URL from a Bing News apiclick redirect link."""
    if not url or "bing.com/news/apiclick" not in url.lower():
        return url
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        target = qs.get("url", [None])[0]
        if target:
            decoded = unquote(target).strip()
            if decoded.startswith(("http://", "https://")):
                return decoded
    except Exception:
        pass
    return url


def _publisher_from_url(url: str, fallback: str = "Web News") -> str:
    """Derive a clean readable publisher label from a direct article URL."""
    try:
        host = urlparse(url).netloc.lower()
        for prefix in ("www.", "m.", "amp.", "news."):
            if host.startswith(prefix):
                host = host[len(prefix):]
        if host in KNOWN_DOMAIN_NAMES:
            return KNOWN_DOMAIN_NAMES[host]
        for dom, label in KNOWN_DOMAIN_NAMES.items():
            if host.endswith("." + dom):
                return label
        if host:
            core = host.split(".")[0]
            if core and len(core) >= 2:
                return core.upper() if len(core) <= 3 else core.capitalize()
    except Exception:
        pass
    return fallback


def _is_direct_url(url: str | None) -> bool:
    u = (url or "").lower()
    return bool(u) and ("news.google.com/" not in u) and ("bing.com/news/apiclick" not in u)


# Domains that are hard-paywalled / subscription-only / login-walled
PAID_NEWS_DOMAINS = {
    "bloomberg.com",
    "reuters.com",
    "ft.com",
    "wsj.com",
    "economist.com",
    "barrons.com",
    "nytimes.com",
    "washingtonpost.com",
    "the-ken.com",
    "themorningcontext.com",
    "thearcweb.com",
    "vccircle.com",
    "asia.nikkei.com",
    "nikkei.com",
    "seekingalpha.com",
    "theinformation.com",
    "businessinsider.com",
    "fortune.com",
    "telegraph.co.uk",
    "thetimes.co.uk",
    "thetimes.com",
    "hbr.org",
    "scmp.com",
    "etprime.com",
    "capitalmind.in",
    "thecapitalmind.in",
    "caravanmagazine.in",
    "epw.in",
}

# Publisher names for hard-paywalled sites or paid tiers (important for Google News redirect URLs)
PAID_PUBLISHER_EXACT = {
    "the times",
    "the ken",
    "the arc",
    "the telegraph",
    "fortune",
    "barron's",
    "barrons",
    "wsj",
    "ft",
    "et prime",
    "etprime",
    "mint premium",
    "moneycontrol pro",
    "mc pro",
    "bs premium",
    "toi+",
    "toi plus",
    "inc42+",
    "inc42 plus",
    "entrackr plus",
    "forbes india pro",
}

PAID_PUBLISHER_PATTERNS = [
    r"\bbloomberg\b",
    r"\breuters\b",
    r"\bfinancial\s+times\b",
    r"\bwall\s+street\s+journal\b",
    r"\bthe\s+economist\b",
    r"\bbarron'?s\b",
    r"\bnew\s+york\s+times\b",
    r"\bnytimes\b",
    r"\bwashington\s+post\b",
    r"\bthe\s+ken\b",
    r"\bthe\s+morning\s+context\b",
    r"\bthe\s+arc\b",
    r"\bvccircle\b",
    r"\bnikkei\s+asia\b",
    r"\bthe\s+information\b",
    r"\bseeking\s+alpha\b",
    r"\bbusiness\s+insider\b",
    r"\bet\s*prime\b",
    r"\bmint\s*premium\b",
    r"\bmoneycontrol\s*pro\b",
    r"\bmc\s*pro\b",
    r"\bbs\s*premium\b",
    r"\bbusiness\s+standard\s+premium\b",
    r"\btoi\s*plus\b",
    r"\btoi\+",
    r"\binc42\s*plus\b",
    r"\binc42\+",
    r"\bentrackr\s*plus\b",
    r"\bforbes\s+india\s+pro\b",
    r"\bsubscribers?\s+only\b",
]

# URL path patterns for paid tiers on otherwise free/hybrid publications
PAID_URL_PATH_PATTERNS = [
    r"/prime(/|$|\?)",
    r"-prime(/|$|\?)",
    r"/mint-premium(/|$|\?)",
    r"/premium(/|$|\?)",
    r"-premium(/|$|\?)",
    r"/bs-premium",
    r"/premium-story",
    r"/toi-plus(/|$|\?)",
    r"/toiplus(/|$|\?)",
    r"/mc-pro(/|$|\?)",
    r"/mcpro(/|$|\?)",
    r"moneycontrol\.com/.*/pro(/|$|\?)",
    r"inc42\.com/plus(/|$|\?)",
    r"entrackr\.com/plus(/|$|\?)",
    r"forbesindia\.com/pro(/|$|\?)",
    r"thehindubusinessline\.com/portfolio(/|$|\?)",
    r"/subscribers?-only(/|$|\?)",
    r"/paywall(/|$|\?)",
    r"/epaper(/|$|\?)",
]

PAID_TEXT_MARKERS = re.compile(
    r"\b(et\s*prime|mint\s*premium|moneycontrol\s*pro|mc\s*pro|bs\s*premium|"
    r"toi\s*plus|inc42\s*plus|subscribers?\s+only|for\s+subscribers|"
    r"exclusive\s+for\s+subscribers|premium\s+story)\b|\[premium\]|\btoi\+",
    re.IGNORECASE,
)


def is_paid_or_paywalled_news(
    title: str = "",
    publisher: str = "",
    url: str | None = None,
    summary: str = "",
) -> bool:
    """Return True if an article is from a paywalled publisher, paid tier, or sponsored PR wire."""
    if is_paywalled_url(url) or is_sponsored_or_pr(title, url):
        return True

    if url:
        u_low = url.lower().strip()
        try:
            host = urlparse(u_low).netloc.lower()
            for prefix in ("www.", "m.", "amp."):
                if host.startswith(prefix):
                    host = host[len(prefix):]
            if host in PAID_NEWS_DOMAINS or any(host.endswith("." + d) for d in PAID_NEWS_DOMAINS):
                return True
        except Exception:
            pass
        if any(re.search(pat, u_low) for pat in PAID_URL_PATH_PATTERNS):
            return True

    pub_low = re.sub(r"\s+", " ", (publisher or "").strip().lower())
    if pub_low:
        if pub_low in PAID_PUBLISHER_EXACT:
            return True
        if any(re.search(pat, pub_low) for pat in PAID_PUBLISHER_PATTERNS):
            return True

    if PAID_TEXT_MARKERS.search(f"{title} {summary}"):
        return True

    return False


# Generic corporate / fund / geographic words that must not trigger relevance on their own
_GENERIC_TOPIC_WORDS = {
    "a", "aif", "amc", "an", "and", "as", "at", "broking", "by", "co", "company",
    "corp", "corporation", "credit", "debt", "enterprises", "equity", "etf",
    "finance", "financial", "for", "fund", "funds", "global", "group", "hedge",
    "holding", "holdings", "in", "inc", "india", "indian", "industries",
    "international", "investment", "investments", "invit", "limited", "llc",
    "llp", "ltd", "management", "mutual", "of", "on", "partners", "plc", "pms",
    "portfolio", "private", "pvt", "reit", "scheme", "securities", "services",
    "solutions", "technologies", "the", "to", "trust", "venture", "ventures",
    "wealth", "advisors", "advisory", "asset", "assets", "bank", "capital",
}

# Trailing vehicle/entity suffixes that publishers frequently omit or substitute (e.g. "Capital" vs "Fund")
_VEHICLE_SUFFIX_WORDS = {
    "fund", "funds", "pms", "aif", "amc", "etf", "reit", "invit",
    "scheme", "trust", "ltd", "limited", "pvt", "private", "inc",
    "llc", "llp", "plc", "corp", "corporation", "co", "company",
}


def _build_search_query(topic_name: str, *, allow_or: bool = True) -> str:
    """Build a high-recall search query without over-restrictive exact quotes.

    - Preserves user-supplied search operators (quotes, OR, AND, site:).
    - Strips trailing corporate/fund vehicle suffixes when 2+ words remain
      (e.g. 'Catalio Capital Fund' -> 'Catalio Capital', 'Greysky Capital PMS' -> 'Greysky Capital').
    - When stripping a fund/PMS suffix leaves a single word (e.g. 'Morphosis Fund'),
      expands to 'Morphosis (Fund OR Capital)' (when allow_or=True) so publishers
      writing either 'Morphosis Fund' or 'Morphosis Capital' are captured.
    - Relevance is strictly enforced afterwards by is_relevant_to_topic().
    """
    query = re.sub(r"\s+", " ", (topic_name or "").strip())
    if not query:
        return ""
    if '"' in query or re.search(r"\b(OR|AND)\b|site:", query):
        return query

    words = query.split(" ")
    if len(words) == 1:
        return query

    stripped = list(words)
    removed_suffixes: list[str] = []
    while len(stripped) > 1 and stripped[-1].lower().strip(".,") in _VEHICLE_SUFFIX_WORDS:
        removed_suffixes.append(stripped.pop().lower().strip(".,"))

    if not removed_suffixes:
        return query

    if len(stripped) >= 2:
        return " ".join(stripped)

    core = stripped[0]
    if allow_or and any(s in {"fund", "funds", "pms", "aif", "amc"} for s in removed_suffixes):
        return f"{core} (Fund OR Capital)"
    return query


def is_relevant_to_topic(
    topic_name: str,
    title: str = "",
    summary: str = "",
    url: str | None = None,
) -> bool:
    """Verify an article actually mentions the topic's distinctive name (not just generic words like 'Capital' or 'Fund')."""
    clean_topic = re.sub(r"\s+", " ", (topic_name or "").strip()).strip('"').strip("'")
    if len(clean_topic) < 2:
        return True

    blob = f"{title} {summary} {url or ''}".lower()

    # Exact full-phrase match always passes
    exact_pat = re.compile(r"\b" + re.escape(clean_topic.lower()).replace(r"\ ", r"[\s\-_/]+") + r"\b", re.IGNORECASE)
    if exact_pat.search(blob):
        return True

    # Extract distinctive non-generic tokens (e.g. "Catalio Capital Fund" -> ["catalio"])
    all_words = re.findall(r"\b[a-z0-9]{2,}\b", clean_topic.lower())
    distinctive = [w for w in all_words if w not in _GENERIC_TOPIC_WORDS]

    if not distinctive:
        # Topic consists only of generic words (e.g. "Global Capital Fund") -> require exact phrase match
        return False

    matched_distinctive = [
        w for w in distinctive
        if re.search(rf"\b{re.escape(w)}\b", blob, re.IGNORECASE)
    ]

    if len(distinctive) == 1:
        # e.g. "Catalio Capital Fund" -> "catalio" MUST appear
        return len(matched_distinctive) == 1
    if len(distinctive) == 2:
        # e.g. "Tata Motors" -> both "tata" and "motors" must appear (avoids matching "Tata Steel")
        return len(matched_distinctive) == 2
    # 3+ distinctive tokens (e.g. "RBI Repo Rate") -> anchor token + at least 1 other distinctive token
    return (distinctive[0] in matched_distinctive) and len(matched_distinctive) >= 2


def _extract_rss_snippet(raw_description: str, clean_title: str, publisher: str) -> str:
    """Clean RSS snippet and drop redundant headline-only boilerplate."""
    if not raw_description:
        return ""
    cleaned = clean_text(raw_description)
    if not cleaned:
        return ""

    # Strip trailing publisher name if repeated (Google News often includes it twice)
    if publisher:
        pub_pat = re.escape(publisher.strip())
        for _ in range(2):
            cleaned = re.sub(rf"\s*[-|–—:]?\s*{pub_pat}\s*$", "", cleaned, flags=re.IGNORECASE).strip()

    # If the cleaned snippet is essentially identical to the headline, omit duplicate text.
    norm_title = re.sub(r"[^a-z0-9]+", "", clean_title.lower())
    norm_snip = re.sub(r"[^a-z0-9]+", "", cleaned.lower())
    if not norm_snip or norm_snip == norm_title:
        return ""
    if norm_title and norm_snip.startswith(norm_title):
        remainder = cleaned[len(clean_title):].strip(" -|–—:·•\u00a0")
        if publisher:
            pub_pat = re.escape(publisher.strip())
            remainder = re.sub(rf"^\s*{pub_pat}\s*", "", remainder, flags=re.IGNORECASE).strip(" -|–—:·•\u00a0")
            remainder = re.sub(rf"\s*[-|–—:]?\s*{pub_pat}\s*$", "", remainder, flags=re.IGNORECASE).strip(" -|–—:·•\u00a0")
        norm_rem = re.sub(r"[^a-z0-9]+", "", remainder.lower())
        if len(norm_rem) < 20:
            return ""
        cleaned = remainder

    if len(cleaned) > 320:
        cleaned = cleaned[:317].rsplit(" ", 1)[0] + "..."
    return cleaned


def _make_article_id(topic_id: str, url: str, title: str) -> str:
    """Deterministic article ID scoped to a topic for idempotent SQLite upserts."""
    canon = canonical_url(url) or title.lower().strip()
    raw = f"{topic_id}::{canon}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _parse_iso_dt(iso_str: str | None) -> datetime | None:
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except Exception:
        return None


def _article_quality_score(art: dict) -> tuple[int, int, str]:
    """Rank duplicate candidates so direct publisher links + richer snippets always win."""
    direct = 1 if _is_direct_url(art.get("url")) else 0
    has_summary = 1 if len((art.get("summary") or "").strip()) >= 25 else 0
    pub = art.get("publisher") or ""
    good_pub = 1 if pub and pub not in ("Google News", "Bing News", "Yahoo News", "GDELT", "Web News") else 0
    score = direct * 4 + has_summary * 2 + good_pub
    return (score, len(art.get("summary") or ""), art.get("published_at") or "")


_DEDUP_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "of", "on", "or", "over", "rs", "said", "says",
    "that", "the", "this", "to", "up", "via", "was", "were", "will", "with", "after",
}


def _topic_aware_tokens(text: str) -> set[str]:
    """Extract normalized 2+ char keywords (preserving EV, AI, Q2, 5G, numbers) minus stopwords."""
    cleaned = clean_text(text).lower()
    words = re.findall(r"\b[a-z0-9]{2,}\b", cleaned)
    return {w for w in words if w not in _DEDUP_STOPWORDS}


def are_same_topic_duplicates(title_a: str, title_b: str, topic_name: str = "") -> bool:
    """Detect whether two headlines for the same topic describe the exact same news story,
    without falsely merging distinct stories just because they both mention the topic name."""
    norm_exact_a = re.sub(r"[^a-z0-9]+", " ", clean_text(title_a).lower()).strip()
    norm_exact_b = re.sub(r"[^a-z0-9]+", " ", clean_text(title_b).lower()).strip()
    if not norm_exact_a or not norm_exact_b:
        return False
    if norm_exact_a == norm_exact_b:
        return True

    topic_tokens = _topic_aware_tokens(topic_name) if topic_name else set()
    tokens_a = _topic_aware_tokens(title_a) - topic_tokens
    tokens_b = _topic_aware_tokens(title_b) - topic_tokens
    if not tokens_a or not tokens_b:
        return False

    # Guard against different quarters (Q1 vs Q2)
    quarters = {"q1", "q2", "q3", "q4"}
    qa, qb = tokens_a & quarters, tokens_b & quarters
    if qa and qb and qa != qb:
        return False

    common = tokens_a & tokens_b
    if len(common) < 2:
        return False

    union = tokens_a | tokens_b
    jaccard = len(common) / len(union)
    if jaccard >= 0.45:
        return True

    min_len = min(len(tokens_a), len(tokens_b))
    if min_len >= 3 and (len(common) / min_len) >= 0.65:
        return True

    norm_a = " ".join(sorted(tokens_a))
    norm_b = " ".join(sorted(tokens_b))
    return SequenceMatcher(None, norm_a, norm_b).ratio() >= 0.72


def deduplicate_custom_articles(articles: list[dict], topic_name: str = "") -> tuple[list[dict], int]:
    """Deduplicate articles across multiple engines while keeping the best copy of each unique story.

    Returns (unique_articles_sorted_newest_first, duplicates_removed_count).
    """
    if not articles:
        return [], 0

    # Process highest-quality candidates first (direct URL + snippet wins over redirect stub)
    ranked = sorted(articles, key=_article_quality_score, reverse=True)
    kept: list[dict] = []
    kept_meta: list[dict] = []
    duplicates_removed = 0

    for cand in ranked:
        c_url = cand.get("url") or ""
        c_title = cand.get("title") or ""
        c_topic = topic_name or cand.get("topic_name") or ""
        c_canon = canonical_url(c_url)
        c_exact = re.sub(r"[^a-z0-9]+", " ", clean_text(c_title).lower()).strip()
        c_dt = _parse_iso_dt(cand.get("published_at"))

        dup_idx = None
        for idx, meta in enumerate(kept_meta):
            if c_canon and meta["canon"] and c_canon == meta["canon"]:
                dup_idx = idx
                break
            if c_exact and meta["exact"] and c_exact == meta["exact"]:
                dup_idx = idx
                break
            # Topic-aware near-duplicate headline check within 72h (avoids merging stories months apart)
            if c_dt and meta["dt"] and abs((c_dt - meta["dt"]).total_seconds()) <= 72 * 3600:
                if are_same_topic_duplicates(meta["title"], c_title, c_topic):
                    dup_idx = idx
                    break

        if dup_idx is not None:
            duplicates_removed += 1
            winner = kept[dup_idx]
            # Borrow a cleaner snippet or direct URL if the winner lacked one
            if len(cand.get("summary") or "") > len(winner.get("summary") or "") + 15:
                winner["summary"] = cand["summary"]
            if not _is_direct_url(winner.get("url")) and _is_direct_url(c_url):
                winner["url"] = c_url
                kept_meta[dup_idx]["canon"] = c_canon
            if winner.get("publisher") in ("Google News", "Bing News", "Yahoo News", "GDELT", "Web News", "") and cand.get("publisher"):
                winner["publisher"] = cand["publisher"]
            continue

        kept.append(dict(cand))
        kept_meta.append({
            "canon": c_canon,
            "exact": c_exact,
            "title": c_title,
            "dt": c_dt,
        })

    kept.sort(key=lambda a: a.get("published_at") or "", reverse=True)
    return kept, duplicates_removed


# =========================================================================
# Engine 1: Google News RSS
# =========================================================================

def fetch_google_news_for_topic(
    topic_id: str,
    topic_name: str,
    hours: int = 24,
    scope: str = "all",
    max_items: int = 30,
    fetcher: Fetcher | None = None,
) -> tuple[list[dict], str | None]:
    """Fetch open-web Google News RSS articles for a single topic within the exact IST/UTC window."""
    hours_val = hours if hours in WINDOW_TO_WHEN else 24
    financial_only = (scope or "all").strip().lower() == "financial"

    query = _build_search_query(topic_name)
    if not query:
        return [], "Empty topic name"

    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(hours=hours_val)
    future_cap = now_utc + timedelta(hours=2)

    if hours_val <= 48:
        when_token = WINDOW_TO_WHEN[hours_val]
        query_slices = [f"{query} when:{when_token}"]
    elif hours_val <= 720:
        after_date = cutoff_utc.strftime("%Y-%m-%d")
        query_slices = [f"{query} after:{after_date}"]
    else:
        # For 6M (180d) and 1 Year (365d), run the full-window query PLUS an explicit older-half slice
        # so Google News doesn't crowd out 3M–12M older articles with recent headlines.
        after_date = cutoff_utc.strftime("%Y-%m-%d")
        mid_date = (now_utc - timedelta(hours=hours_val // 2)).strftime("%Y-%m-%d")
        query_slices = [
            f"{query} after:{after_date}",
            f"{query} after:{after_date} before:{mid_date}",
        ]

    articles: list[dict] = []
    slice_errors: list[str] = []
    slices_succeeded = 0

    for idx, q_with_range in enumerate(query_slices):
        if idx > 0 and fetcher is None:
            time.sleep(0.35)
        rss_url = (
            f"https://news.google.com/rss/search?q={quote_plus(q_with_range)}"
            "&hl=en-IN&gl=IN&ceid=IN:en"
        )
        try:
            if fetcher is not None:
                resp = fetcher.get(rss_url, check_robots=False, delay=0.35, timeout=16)
            else:
                resp = _http_get(rss_url, timeout=14)
        except Exception as exc:
            log.warning("Google News RSS fetch failed for '%s' (%s): %s", topic_name, q_with_range, exc)
            slice_errors.append(f"Google News: {exc}")
            continue

        slices_succeeded += 1
        parsed_feed = feedparser.parse(resp.content)

        for entry in parsed_feed.entries:
            pub_dt = parse_date(str(entry.get("published") or entry.get("updated") or ""))
            if not pub_dt or pub_dt < cutoff_utc or pub_dt > future_cap:
                continue

            src = entry.get("source")
            publisher = "Google News"
            if isinstance(src, dict) and src.get("title"):
                publisher = str(src.get("title")).strip()
            elif hasattr(src, "title") and getattr(src, "title"):
                publisher = str(getattr(src, "title")).strip()

            raw_title = str(entry.get("title") or "").strip()
            if not raw_title:
                continue

            cleaned_raw = clean_text(raw_title)
            if publisher == "Google News" and " - " in cleaned_raw:
                parts = cleaned_raw.rsplit(" - ", 1)
                if len(parts[1]) <= 45:
                    publisher = parts[1].strip()

            title = strip_publisher_suffix(cleaned_raw, publisher) or cleaned_raw
            raw_link = str(entry.get("link") or "").strip()
            if not raw_link:
                continue

            if financial_only and not is_reputable_publisher(publisher, raw_link, "news"):
                continue

            raw_desc = str(entry.get("summary") or entry.get("description") or "")
            summary = _extract_rss_snippet(raw_desc, title, publisher)

            if is_paid_or_paywalled_news(title, publisher, raw_link, summary):
                continue
            if not is_relevant_to_topic(topic_name, title, summary, raw_link):
                continue

            articles.append({
                "id": _make_article_id(topic_id, raw_link, title),
                "topic_id": topic_id,
                "topic_name": topic_name,
                "title": title,
                "summary": summary,
                "publisher": publisher,
                "source_engine": "Google News",
                "url": raw_link,
                "published_at": pub_dt.astimezone(timezone.utc).isoformat(),
            })

    if slices_succeeded == 0 and slice_errors:
        return [], slice_errors[0]

    deduped, _ = deduplicate_custom_articles(articles, topic_name=topic_name)
    return deduped[:max_items], None


# =========================================================================
# Engine 2: Bing News RSS
# =========================================================================

def fetch_bing_news_for_topic(
    topic_id: str,
    topic_name: str,
    hours: int = 24,
    max_items: int = 25,
    http_get=_http_get,
) -> tuple[list[dict], str | None]:
    """Fetch open-web Bing News RSS articles and unwrap direct publisher URLs."""
    hours_val = hours if hours in WINDOW_TO_WHEN else 24
    query = _build_search_query(topic_name)
    if not query:
        return [], None

    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(hours=hours_val)
    future_cap = now_utc + timedelta(hours=2)

    params: dict[str, str] = {
        "q": query,
        "format": "rss",
        "mkt": "en-IN",
    }
    if hours_val <= 24:
        params["qft"] = 'interval="7"'
    elif hours_val <= 48:
        params["qft"] = 'interval="8"'
    elif hours_val <= 720:
        params["qft"] = 'interval="9"'

    try:
        resp = http_get("https://www.bing.com/news/search", params=params, timeout=12)
    except Exception as exc:
        log.warning("Bing News RSS fetch failed for '%s': %s", topic_name, exc)
        return [], f"Bing News: {exc}"

    parsed_feed = feedparser.parse(resp.content)
    articles: list[dict] = []

    for entry in parsed_feed.entries:
        pub_dt = parse_date(str(entry.get("published") or entry.get("updated") or ""))
        if not pub_dt or pub_dt < cutoff_utc or pub_dt > future_cap:
            continue

        raw_link = str(entry.get("link") or "").strip()
        if not raw_link:
            continue
        direct_url = _unwrap_bing_url(raw_link)

        publisher = ""
        news_src = entry.get("news_source") or entry.get("source")
        if isinstance(news_src, dict):
            publisher = str(news_src.get("title") or "").strip()
        elif isinstance(news_src, str):
            publisher = news_src.strip()
        elif hasattr(news_src, "title") and getattr(news_src, "title"):
            publisher = str(getattr(news_src, "title")).strip()
        if not publisher:
            publisher = _publisher_from_url(direct_url, fallback="Bing News")

        raw_title = clean_text(str(entry.get("title") or ""))
        if not raw_title:
            continue
        title = strip_publisher_suffix(raw_title, publisher) or raw_title

        raw_desc = str(entry.get("summary") or entry.get("description") or "")
        summary = _extract_rss_snippet(raw_desc, title, publisher)

        if is_paid_or_paywalled_news(title, publisher, direct_url, summary):
            continue
        if not is_relevant_to_topic(topic_name, title, summary, direct_url):
            continue

        articles.append({
            "id": _make_article_id(topic_id, direct_url, title),
            "topic_id": topic_id,
            "topic_name": topic_name,
            "title": title,
            "summary": summary,
            "publisher": publisher,
            "source_engine": "Bing News",
            "url": direct_url,
            "published_at": pub_dt.astimezone(timezone.utc).isoformat(),
        })

    articles.sort(key=lambda a: a["published_at"], reverse=True)
    return articles[:max_items], None


# =========================================================================
# Engine 3: Yahoo News RSS
# =========================================================================

def fetch_yahoo_news_for_topic(
    topic_id: str,
    topic_name: str,
    hours: int = 24,
    max_items: int = 25,
    http_get=_http_get,
) -> tuple[list[dict], str | None]:
    """Fetch open-web Yahoo News RSS search results."""
    hours_val = hours if hours in WINDOW_TO_WHEN else 24
    query = _build_search_query(topic_name, allow_or=False)
    if not query:
        return [], None

    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(hours=hours_val)
    future_cap = now_utc + timedelta(hours=2)

    try:
        resp = http_get(
            "https://news.search.yahoo.com/rss",
            params={"p": query},
            timeout=6,
        )
    except Exception as exc:
        log.warning("Yahoo News RSS fetch failed for '%s': %s", topic_name, exc)
        return [], f"Yahoo News: {exc}"

    parsed_feed = feedparser.parse(resp.content)
    articles: list[dict] = []

    for entry in parsed_feed.entries:
        pub_dt = parse_date(str(entry.get("published") or entry.get("updated") or ""))
        if not pub_dt or pub_dt < cutoff_utc or pub_dt > future_cap:
            continue

        raw_link = str(entry.get("link") or "").strip()
        if not raw_link:
            continue

        src = entry.get("source")
        publisher = ""
        if isinstance(src, dict) and src.get("title"):
            publisher = str(src.get("title")).strip()
        elif hasattr(src, "title") and getattr(src, "title"):
            publisher = str(getattr(src, "title")).strip()
        if not publisher:
            publisher = _publisher_from_url(raw_link, fallback="Yahoo News")

        raw_title = clean_text(str(entry.get("title") or ""))
        if not raw_title:
            continue
        title = strip_publisher_suffix(raw_title, publisher) or raw_title

        raw_desc = str(entry.get("summary") or entry.get("description") or "")
        summary = _extract_rss_snippet(raw_desc, title, publisher)

        if is_paid_or_paywalled_news(title, publisher, raw_link, summary):
            continue
        if not is_relevant_to_topic(topic_name, title, summary, raw_link):
            continue

        articles.append({
            "id": _make_article_id(topic_id, raw_link, title),
            "topic_id": topic_id,
            "topic_name": topic_name,
            "title": title,
            "summary": summary,
            "publisher": publisher,
            "source_engine": "Yahoo News",
            "url": raw_link,
            "published_at": pub_dt.astimezone(timezone.utc).isoformat(),
        })

    articles.sort(key=lambda a: a["published_at"], reverse=True)
    return articles[:max_items], None


# =========================================================================
# Engine 4: GDELT Global News Index
# =========================================================================

def fetch_gdelt_news_for_topic(
    topic_id: str,
    topic_name: str,
    hours: int = 24,
    max_items: int = 25,
    http_get=_http_get,
) -> tuple[list[dict], str | None]:
    """Fetch worldwide/Indian news articles from the free GDELT v2 Doc API (supports up to 3M)."""
    hours_val = hours if hours in WINDOW_TO_GDELT else 24
    query = _build_search_query(topic_name, allow_or=False)
    if len(query) < 3:
        return [], None

    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(hours=hours_val)
    future_cap = now_utc + timedelta(hours=2)

    # GDELT requires quotes around multi-word phrases
    gdelt_query = query if ('"' in query or " " not in query) else f'"{query}"'
    params = {
        "query": f"{gdelt_query} sourcelang:english",
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_items),
        "timespan": WINDOW_TO_GDELT[hours_val],
        "sort": "datedesc",
    }

    try:
        resp = http_get(GDELT_API, params=params, timeout=5)
        text = (resp.text or "").strip()
        if not text.startswith("{"):
            return [], None
        data = resp.json()
    except Exception as exc:
        log.warning("GDELT fetch failed for '%s': %s", topic_name, exc)
        return [], f"GDELT: {exc}"

    articles: list[dict] = []
    for item in data.get("articles", []) or []:
        pub_dt = parse_date(str(item.get("seendate") or ""))
        if not pub_dt or pub_dt < cutoff_utc or pub_dt > future_cap:
            continue

        raw_link = str(item.get("url") or "").strip()
        raw_title = clean_text(str(item.get("title") or ""))
        if not raw_link or not raw_title:
            continue

        domain = str(item.get("domain") or "").strip()
        publisher = _publisher_from_url(raw_link, fallback=domain or "GDELT")
        title = strip_publisher_suffix(raw_title, publisher) or raw_title

        if is_paid_or_paywalled_news(title, publisher, raw_link):
            continue
        if not is_relevant_to_topic(topic_name, title, "", raw_link):
            continue

        articles.append({
            "id": _make_article_id(topic_id, raw_link, title),
            "topic_id": topic_id,
            "topic_name": topic_name,
            "title": title,
            "summary": "",
            "publisher": publisher,
            "source_engine": "GDELT",
            "url": raw_link,
            "published_at": pub_dt.astimezone(timezone.utc).isoformat(),
        })

    articles.sort(key=lambda a: a["published_at"], reverse=True)
    return articles[:max_items], None


# =========================================================================
# Engine 5: Configured Data Sources RSS Feeds (Read-Only Keyword Match)
# =========================================================================

def preload_data_sources_rss(
    rss_sources: list[dict],
    hours: int = 24,
    http_get=_http_get,
) -> list[dict]:
    """Fetch active RSS feeds from Data Sources ONCE in parallel (strictly read-only)."""
    if not rss_sources:
        return []

    hours_val = hours if hours in WINDOW_TO_WHEN else 24
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(hours=hours_val)
    future_cap = now_utc + timedelta(hours=2)

    active_feeds = [
        s for s in rss_sources
        if s.get("is_active", 1) and str(s.get("type") or "").strip().lower() == "rss" and s.get("url")
    ]
    if not active_feeds:
        return []

    def _read_single_feed(src: dict) -> list[dict]:
        feed_url = str(src["url"]).strip()
        feed_name = str(src.get("name") or "").strip() or _publisher_from_url(feed_url, "Data Sources")
        # Clean common " RSS" / " Top News RSS" suffix for publisher pill readability
        publisher = re.sub(r"\s+(top\s+news|markets|business|news)?\s*rss\s*$", "", feed_name, flags=re.IGNORECASE).strip() or feed_name
        try:
            resp = http_get(feed_url, timeout=10)
            parsed = feedparser.parse(resp.content)
        except Exception as exc:
            log.debug("Data Sources RSS skip (%s): %s", feed_name, exc)
            return []

        items: list[dict] = []
        for entry in parsed.entries:
            pub_dt = parse_date(str(entry.get("published") or entry.get("updated") or ""))
            if not pub_dt or pub_dt < cutoff_utc or pub_dt > future_cap:
                continue
            link = str(entry.get("link") or "").strip()
            raw_title = clean_text(str(entry.get("title") or ""))
            if not link or not raw_title:
                continue
            title = strip_publisher_suffix(raw_title, publisher) or raw_title
            raw_desc = str(entry.get("summary") or entry.get("description") or "")
            summary = _extract_rss_snippet(raw_desc, title, publisher)
            if is_paid_or_paywalled_news(title, publisher, link, summary):
                continue
            items.append({
                "title": title,
                "summary": summary,
                "publisher": publisher,
                "url": link,
                "published_at": pub_dt.astimezone(timezone.utc).isoformat(),
                "search_blob": f"{title} {summary}".lower(),
            })
        return items

    all_entries: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(6, len(active_feeds))) as pool:
        futures = [pool.submit(_read_single_feed, src) for src in active_feeds]
        for fut in as_completed(futures):
            try:
                all_entries.extend(fut.result())
            except Exception:
                pass
    return all_entries


def match_data_sources_for_topic(
    topic_id: str,
    topic_name: str,
    preloaded_entries: list[dict],
) -> list[dict]:
    """Match a plain topic name against preloaded Data Sources RSS entries using whole-word phrase matching."""
    if not preloaded_entries:
        return []
    clean_name = re.sub(r"\s+", " ", (topic_name or "").strip()).strip('"').strip("'")
    if len(clean_name) < 2:
        return []

    # Whole-word flexible-whitespace phrase match (e.g. "Tata Motors" matches "Tata Motors", not "orbital" for "RBI")
    pattern = re.compile(r"\b" + re.escape(clean_name.lower()).replace(r"\ ", r"\s+") + r"\b", re.IGNORECASE)
    matched: list[dict] = []

    for entry in preloaded_entries:
        if pattern.search(entry.get("search_blob") or ""):
            matched.append({
                "id": _make_article_id(topic_id, entry["url"], entry["title"]),
                "topic_id": topic_id,
                "topic_name": topic_name,
                "title": entry["title"],
                "summary": entry["summary"],
                "publisher": entry["publisher"],
                "source_engine": "Data Sources",
                "url": entry["url"],
                "published_at": entry["published_at"],
            })

    matched.sort(key=lambda a: a["published_at"], reverse=True)
    return matched


# =========================================================================
# Unified Multi-Engine Orchestrator
# =========================================================================

def fetch_multi_engine_news_for_topic(
    topic_id: str,
    topic_name: str,
    hours: int = 24,
    max_items: int = 50,
    preloaded_rss_entries: list[dict] | None = None,
) -> dict:
    """Query Google News, Bing News, Yahoo News, GDELT, and Data Sources concurrently & deduplicate."""
    raw_articles: list[dict] = []
    engine_errors: list[str] = []
    succeeded_engines = 0

    gn_limit = max(35, min(max_items, 100))
    other_limit = max(25, min(max_items, 50))

    tasks = {
        "Google News": lambda: fetch_google_news_for_topic(topic_id, topic_name, hours=hours, scope="all", max_items=gn_limit),
        "Bing News": lambda: fetch_bing_news_for_topic(topic_id, topic_name, hours=hours, max_items=other_limit),
        "Yahoo News": lambda: fetch_yahoo_news_for_topic(topic_id, topic_name, hours=hours, max_items=other_limit),
        "GDELT": lambda: fetch_gdelt_news_for_topic(topic_id, topic_name, hours=hours, max_items=other_limit),
    }

    with ThreadPoolExecutor(max_workers=4) as pool:
        future_map = {pool.submit(fn): eng for eng, fn in tasks.items()}
        for fut in as_completed(future_map):
            eng = future_map[fut]
            try:
                items, err = fut.result()
                if err:
                    engine_errors.append(err)
                else:
                    succeeded_engines += 1
                raw_articles.extend(items)
            except Exception as exc:
                engine_errors.append(f"{eng}: {exc}")

    # Match against preloaded Data Sources RSS feeds in memory
    if preloaded_rss_entries is not None:
        ds_items = match_data_sources_for_topic(topic_id, topic_name, preloaded_rss_entries)
        raw_articles.extend(ds_items)
        if preloaded_rss_entries:
            succeeded_engines += 1

    unique_articles, duplicates_removed = deduplicate_custom_articles(raw_articles, topic_name=topic_name)
    capped = unique_articles[:max_items]

    engine_counts: dict[str, int] = {}
    for a in capped:
        eng = a.get("source_engine") or "Google News"
        engine_counts[eng] = engine_counts.get(eng, 0) + 1

    return {
        "articles": capped,
        "duplicates_removed": duplicates_removed,
        "engine_counts": engine_counts,
        "errors": engine_errors,
        "all_failed": (succeeded_engines == 0 and len(engine_errors) > 0),
    }


def fetch_multi_engine_news_batch(
    topics: list[dict],
    hours: int = 24,
    rss_sources: list[dict] | None = None,
    max_per_topic: int = 50,
) -> dict:
    """Fetch deduplicated multi-engine news across all requested saved topics."""
    preloaded_rss = preload_data_sources_rss(rss_sources or [], hours=hours)

    results_by_topic: dict[str, list[dict]] = {}
    errors: list[dict] = []
    failed_topic_ids: set[str] = set()
    engine_counts: dict[str, int] = {}
    total_found = 0
    total_duplicates_removed = 0

    for t in topics:
        tid = t["id"]
        tname = t["name"]
        res = fetch_multi_engine_news_for_topic(
            topic_id=tid,
            topic_name=tname,
            hours=hours,
            max_items=max_per_topic,
            preloaded_rss_entries=preloaded_rss,
        )
        results_by_topic[tid] = res["articles"]
        total_found += len(res["articles"])
        total_duplicates_removed += res["duplicates_removed"]
        for eng, cnt in res["engine_counts"].items():
            engine_counts[eng] = engine_counts.get(eng, 0) + cnt
        if res["all_failed"]:
            failed_topic_ids.add(tid)
        for err_msg in res["errors"]:
            errors.append({"topic_id": tid, "topic_name": tname, "error": err_msg})

    return {
        "results_by_topic": results_by_topic,
        "total_found": total_found,
        "duplicates_removed": total_duplicates_removed,
        "engine_counts": engine_counts,
        "failed_topic_ids": failed_topic_ids,
        "errors": errors,
    }


def fetch_google_news_batch(
    topics: list[dict],
    hours: int = 24,
    scope: str = "all",
    max_per_topic: int = 40,
) -> dict:
    """Backwards-compatible wrapper delegating to multi-engine batch fetch."""
    return fetch_multi_engine_news_batch(
        topics=topics,
        hours=hours,
        rss_sources=None,
        max_per_topic=max_per_topic,
    )
