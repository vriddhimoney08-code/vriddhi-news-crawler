"""URL and text normalization, publisher suffix stripping, and duplicate detection."""
from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Common tracking / campaign query parameters to drop
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "ref", "source", "cmpid", "ocid", "ved", "usqp",
}


def clean_text(text: str | None) -> str:
    """Unescape HTML, collapse whitespace, and strip zero-width characters."""
    if not text:
        return ""
    # Unescape HTML entities
    cleaned = html.unescape(text)
    # Remove HTML tags if present
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Remove zero-width spaces and weird unicode whitespace
    cleaned = re.sub(r"[\u200b-\u200f\ufeff]", "", cleaned)
    # Collapse multiple whitespaces/newlines into single space
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def canonical_url(url: str | None) -> str:
    """Normalize URL by removing tracking query parameters, fragments, and standardizing host."""
    if not url:
        return ""
    try:
        parsed = urlparse(url.strip())
        # Drop tracking parameters
        query_pairs = [
            (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in TRACKING_PARAMS
        ]
        # Sort query params for consistent hashing
        query_pairs.sort()
        clean_query = urlencode(query_pairs)

        # Standardize host (lowercase, remove 'www.' or 'm.' or 'amp.')
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        elif netloc.startswith("m."):
            netloc = netloc[2:]
        elif netloc.startswith("amp."):
            netloc = netloc[4:]

        # Clean path (strip trailing slashes, remove /amp suffix)
        path = re.sub(r"/amp/?$", "", parsed.path.rstrip("/"))

        return urlunparse((
            parsed.scheme.lower() or "https",
            netloc,
            path,
            "",
            clean_query,
            ""  # drop fragment #anchor
        ))
    except Exception:
        return (url or "").strip()


def strip_publisher_suffix(title: str, publisher: str = "") -> str:
    """Strip trailing publisher branding (e.g. 'Tata Motors Q2 - The Economic Times' -> 'Tata Motors Q2')."""
    if not title:
        return ""
    cleaned = clean_text(title)

    # If publisher name provided, try stripping it specifically
    if publisher:
        pub_escaped = re.escape(publisher.strip())
        cleaned = re.sub(rf"[-|–—:]\s*{pub_escaped}\s*$", "", cleaned, flags=re.IGNORECASE)

    # General pattern for trailing outlet names (e.g., " - Livemint", " | Moneycontrol", " - ET Energy")
    cleaned = re.sub(r"\s*[-|–—]\s*([A-Za-z0-9\s]{2,30})$", "", cleaned)
    return cleaned.strip()


def headline_fingerprint(headline: str) -> str:
    """Generate a simplified token string for headline similarity matching."""
    cleaned = clean_text(headline).lower()
    # Keep only alphanumeric and spaces
    words = re.findall(r"\b[a-z0-9]{3,}\b", cleaned)
    # Filter common financial stopwords
    stopwords = {"and", "the", "for", "with", "from", "after", "says", "said", "over", "into"}
    tokens = [w for w in words if w not in stopwords]
    return " ".join(sorted(tokens))


NOISE_PATTERNS = [
    # 1. Broad market wraps, benchmark index chatter
    r"\b(sensex|nifty|closing bell|opening bell|market wrap|d-street|dalal street|bse benchmark)\b",
    # 2. Retail stock tips, recommendations, gossip
    r"\b(stocks to buy|stocks to watch|stock tips|stock picks|top picks|hot stocks|buzzing stocks|top gainers|top losers|bets on)\b",
    r"\b(\d+\s+stocks?\s+(in focus|to watch|to buy|for today))\b",
    r"\b(share price today|share price target|target price|buy or sell|buy sell hold|brokerage (call|view|rating))\b",
    r"\b(top \d+ stocks|multibagger|penny stock|gold price|silver price|petrol price)\b",
    # 3. Weekly recaps, previews, sector wraps (not primary corporate news)
    r"\b(weekly recap|monthly wrap|weekly wrap|week ahead|month ahead|market outlook)\b",
    r"\b(why is (the )?(stock market|sensex|nifty|market) (down|falling|crashing|up))\b",
    r"\b(it sector (q[1-4] )?results preview|sector preview|sector rally|spark(s)? (it )?rally)\b",
    # 4. Celebrity, startup drama, lifestyle, clickbait
    r"\b(shark tank|anupam mittal|ashneer|aman gupta|viral|net worth|bollywood|horoscope|astrology|rashifal)\b",
    # 5. Automated ticker pages & algorithmic noise
    r"\b(share price,\s*(nse|bse)|share price live updates|stock price live)\b",
    # 6. Retail clickbait questions & speculative fluff
    r"\b(who really owns|can .* aid the bounce back|experts['\s]+views?|what investors should know|what should you do|here['’]s why)\b",
    r"\b(top \d+ factors|reasons behind|reasons why)\b",
]


def is_generic_market_noise(title: str) -> bool:
    """Identify retail clickbait, index wraps, and non-research gossip."""
    if not title:
        return True
    t_lower = title.lower()
    return any(re.search(pat, t_lower) for pat in NOISE_PATTERNS)


def extract_event_signature(title: str, summary: str = "") -> str | None:
    """Detect corporate and macro event clusters to match stories reported across different publishers."""
    text = f"{title} {summary}".lower()

    # 1. Quarterly Results & Earnings (e.g., Q1, Q2, Q3, Q4, Net Profit, PAT)
    q_match = re.search(r"\b(q[1-4]|quarter\s*[1-4])\b", text)
    quarter = q_match.group(1).replace(" ", "") if q_match else None
    has_results = bool(re.search(r"\b(results?|earnings?|net\s*profit|pat|loss|nii|ebitda|quarterly)\b", text))
    if quarter and has_results:
        return f"{quarter}_results"
    if has_results and any(w in text for w in ("annual", "full year", "fy2")):
        return "annual_results"

    # 2. Deals, Contracts, Orders & Tenders
    if re.search(r"\b(bags?|won|wins?|secures?|contract|order\s*win|epc\s*contract|tender|mou)\b", text):
        amt_match = re.search(r"rs\s*([0-9,.]+)\s*(cr|crore)?", text)
        amt_str = amt_match.group(1).replace(",", "") if amt_match else ""
        return f"order_win_{amt_str}" if amt_str else "order_win"

    # 3. Commercial Offers, Pricing & Festive Schemes
    if re.search(r"\b(festiv(e|al)\s*(offer|saving|discount|season|benefit)|festival\s*offer)\b", text):
        return "festive_offer"

    if re.search(r"\b(price\s*hike|hike.*prices?|tariff.*hike)\b", text):
        return "price_hike"

    # 4. Regulatory, Investigation & Scams (SEBI, RBI, CBI, ED)
    if re.search(r"\b(cbi|ed\s*raid|sebi\s*order|fraud|lawsuit|investigation|penalty|proclamation)\b", text):
        return "regulatory_legal"

    # 5. Government Directives & Sovereign Bonuses (e.g. 78-day bonus)
    if re.search(r"\b(cabinet\s*approves?\b.*\b(bonus|railway)|productivity\s*linked\s*bonus|plb)\b", text):
        return "cabinet_railway_bonus"

    return None


def are_near_duplicates(headline_a: str, headline_b: str, threshold: float = 0.50) -> bool:
    """Check if two headlines represent the exact same story/event across different publishers."""
    fp_a = headline_fingerprint(headline_a)
    fp_b = headline_fingerprint(headline_b)
    if not fp_a or not fp_b:
        return False
    if fp_a == fp_b:
        return True

    tokens_a = set(fp_a.split())
    tokens_b = set(fp_b.split())
    if not tokens_a or not tokens_b:
        return False

    # 0. Guard against distinct legal case/order/appeal numbers (e.g. Appeal 7109 vs Appeal 7108)
    years = {"2022", "2023", "2024", "2025", "2026", "2027"}
    nums_a = set(re.findall(r"\b\d{3,6}\b", headline_a)) - years
    nums_b = set(re.findall(r"\b\d{3,6}\b", headline_b)) - years
    if nums_a and nums_b and not (nums_a & nums_b):
        return False

    # 1. Match identical event signatures (e.g., Q2 Results, Festive Offer, Railway Bonus)
    sig_a = extract_event_signature(headline_a)
    sig_b = extract_event_signature(headline_b)
    if sig_a and sig_b and sig_a == sig_b:
        common_tokens = tokens_a & tokens_b
        meaningful = [t for t in common_tokens if t not in ("shares", "stock", "stocks", "ltd", "limited")]
        if len(meaningful) >= 2 or len(common_tokens) >= 3:
            return True

    # 2. Guard against stock directional conflict ('shares jump' vs 'shares crash')
    has_stock_pos_a = bool(re.search(r"\b(shares?|stock)\s+(jump|gain|rise|surge|rally|soar)\b", headline_a.lower()))
    has_stock_neg_a = bool(re.search(r"\b(shares?|stock)\s+(fall|drop|slump|plunge|down|crash|tumble)\b", headline_a.lower()))
    has_stock_pos_b = bool(re.search(r"\b(shares?|stock)\s+(jump|gain|rise|surge|rally|soar)\b", headline_b.lower()))
    has_stock_neg_b = bool(re.search(r"\b(shares?|stock)\s+(fall|drop|slump|plunge|down|crash|tumble)\b", headline_b.lower()))
    if (has_stock_pos_a and has_stock_neg_b) or (has_stock_neg_a and has_stock_pos_b):
        return False

    # 3. Guard against different quarters or reporting periods (e.g. Q1 vs Q2)
    quarter_words = {"q1", "q2", "q3", "q4"}
    q_a = tokens_a & quarter_words
    q_b = tokens_b & quarter_words
    if q_a and q_b and q_a != q_b:
        return False

    # 4. Standard Jaccard similarity on tokens
    union_len = len(tokens_a | tokens_b)
    jaccard = (len(tokens_a & tokens_b) / union_len) if union_len > 0 else 0.0
    if jaccard >= 0.45:
        return True

    # 5. SequenceMatcher ratio on sorted token fingerprints
    return SequenceMatcher(None, fp_a, fp_b).ratio() >= threshold



REPUTED_DOMAINS = {
    # Tier 1 Indian Financial Press
    "livemint.com",
    "moneycontrol.com",
    "economictimes.indiatimes.com",
    "timesofindia.indiatimes.com",
    "business-standard.com",
    "financialexpress.com",
    "cnbctv18.com",
    "ndtvprofit.com",
    "ndtv.com",
    "businesstoday.in",
    "thehindubusinessline.com",
    "thehindu.com",
    "indianexpress.com",
    "hindustantimes.com",
    "zeebiz.com",
    # Global Financial Wires
    "reuters.com",
    "bloomberg.com",
    "bloombergquint.com",
    # Verified Financial & Corporate Tech Portals
    "tradebrains.in",
    "marketsmithindia.com",
    "investmentguruindia.com",
    "indiainfoline.com",
    "iifl.com",
    "inc42.com",
    "entrackr.com",
    "yourstory.com",
    "businessworld.in",
    "bwdisrupt.com",
    "capitalmind.in",
    "thecapitalmind.in",
    "bizzbuzz.news",
    "cxotoday.com",
    "bqprime.com",
    "equitymaster.com",
    "moneyworks4me.com",
    # Official Stock Exchanges
    "bseindia.com",
    "nseindia.com",
}

REPUTED_PUBLISHER_KEYWORDS = [
    # Top Tier Financial Publications
    "livemint",
    "mint",
    "moneycontrol",
    "economic times",
    "times of india",
    "toi",
    "business standard",
    "financial express",
    "cnbc tv18",
    "cnbc-tv18",
    "cnbc",
    "ndtv profit",
    "ndtv",
    "business today",
    "businessline",
    "the hindu",
    "indian express",
    "hindustan times",
    "zee business",
    "reuters",
    "bloomberg",
    # Verified Corporate & Small-Cap Financial Portals
    "trade brains",
    "marketsmith",
    "investment guru",
    "india infoline",
    "iifl",
    "inc42",
    "entrackr",
    "yourstory",
    "businessworld",
    "capitalmind",
    "bizzbuzz",
    "cxotoday",
    "equitymaster",
    # Official Exchanges
    "bse",
    "nse",
]

BLACKLIST_KEYWORDS = [
    "scanx",
    "scannx",
    "odisha diary",
    "univest",
    "ad-hoc-news",
    "kalkine",
    "goodreturns",
    "instagram",
    "dailyhunt",
    "openpr",
    "simply wall street",
    "marketbeat",
    "apnnews",
]


def is_reputable_publisher(source_name: str, url: str | None = None, source_type: str = "news") -> bool:
    """Ensure news stories strictly originate from tier-1 reputed institutions (Mint, Moneycontrol, ET, TOI, etc.)."""
    # 1. Official exchange regulatory announcements are always trusted
    if source_type == "filing":
        return True

    s_lower = (source_name or "").lower().strip()
    u_lower = (url or "").lower().strip()

    # 2. Strict blacklist check: immediately reject scrapers, aggregators, and spam blogs
    if any(b in s_lower or b in u_lower for b in BLACKLIST_KEYWORDS):
        return False

    # 3. Whitelist check by URL domain
    if any(d in u_lower for d in REPUTED_DOMAINS):
        return True

    # 4. Whitelist check by publisher brand name
    if any(p in s_lower for p in REPUTED_PUBLISHER_KEYWORDS):
        return True

    # Reject obscure blogs, unknown aggregators, and non-whitelisted sources
    return False
