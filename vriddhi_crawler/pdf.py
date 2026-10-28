"""Executive PDF and HTML Digest Generator for Vriddhi Research Desk."""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from .config import DIGESTS_DIR, IST
from .db import get_analysts, get_companies

log = logging.getLogger(__name__)

_VRIDDHI_LOGO_CACHE: str | None = None


def get_vriddhi_logo_data_uri() -> str:
    """Load and cache the Vriddhi rectangular brand logo as a base64 Data URI for seamless PDF & HTML rendering."""
    global _VRIDDHI_LOGO_CACHE
    if _VRIDDHI_LOGO_CACHE:
        return _VRIDDHI_LOGO_CACHE
    logo_path = Path(__file__).resolve().parent / "ui" / "vriddhi_logo_transparent.png"
    if not logo_path.exists():
        logo_path = Path(__file__).resolve().parent / "ui" / "vriddhi_logo_rect_optimized.png"
    if not logo_path.exists():
        logo_path = Path(__file__).resolve().parent / "ui" / "vriddhi_logo_rect.png"
    if logo_path.exists():
        raw_b64 = base64.b64encode(logo_path.read_bytes()).decode("ascii")
        _VRIDDHI_LOGO_CACHE = f"data:image/png;base64,{raw_b64}"
        return _VRIDDHI_LOGO_CACHE
    return ""


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ analyst_name }}_{{ date_str_file }}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

  @page {
    size: A4;
    margin: 12mm 12mm 12mm 12mm;
    @bottom-right {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 8pt;
      color: #94a3b8;
      font-family: 'Plus Jakarta Sans', sans-serif;
    }
  }

  * { box-sizing: border-box; }

  body {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #0f172a;
    background-color: #f8fafc;
    line-height: 1.5;
    margin: 0;
    padding: 12px;
    font-size: 9.5pt;
  }

  /* 1. Modern Header Masthead - Executive Whitish Theme */
  .masthead {
    background: #ffffff;
    border-radius: 12px;
    padding: 16px 22px;
    margin-bottom: 16px;
    color: #0f172a;
    box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.04);
    border: 1px solid #e2e8f0;
    border-left: 5px solid #10b981;
  }

  .brand-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }

  .brand-group {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .masthead-rect-logo {
    height: 52px;
    width: auto;
    object-fit: contain;
    display: block;
  }

  .brand-v-divider {
    width: 1px;
    height: 38px;
    background: #e2e8f0;
  }

  .brand-desk-title {
    font-size: 11pt;
    font-weight: 800;
    letter-spacing: -0.2px;
    color: #0f172a;
    margin: 0;
    line-height: 1.2;
  }

  .brand-sub {
    font-size: 8pt;
    color: #64748b;
    font-weight: 500;
    letter-spacing: 0.2px;
    margin-top: 2px;
  }

  .meta-pills {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 7px 16px;
    border-radius: 30px;
    font-size: 8pt;
    color: #334155;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  }

  .meta-pills strong {
    color: #0f172a;
  }

  /* 2. Section Titles */
  .section-heading {
    font-size: 10.5pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #0f172a;
    margin: 20px 0 10px 0;
    display: flex;
    align-items: center;
    gap: 8px;
    page-break-after: avoid;
    break-after: avoid;
  }

  .section-heading::after {
    content: "";
    flex: 1;
    height: 1px;
    background: #e2e8f0;
    margin-left: 8px;
  }

  /* 3. Basket Pill Badges in Matrix Scorecard */
  .basket-pill-badge {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7pt;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 4px;
    text-transform: uppercase;
    display: inline-block;
    letter-spacing: 0.3px;
    white-space: nowrap;
  }

  .basket-pill-game {
    background: #ecfdf5;
    color: #047857;
    border: 1px solid #a7f3d0;
  }

  .basket-pill-set {
    background: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
  }

  .basket-pill-match {
    background: #faf5ff;
    color: #7e22ce;
    border: 1px solid #e9d5ff;
  }

  .basket-pill-junior {
    background: #fdf4ff;
    color: #a21caf;
    border: 1px solid #f0abfc;
  }

  .basket-pill-custom {
    background: #f0fdf4;
    color: #065f46;
    border: 1px solid #bbf7d0;
  }

  .basket-pill-watchlist {
    background: #f1f5f9;
    color: #475569;
    border: 1px solid #cbd5e1;
  }

  /* 4. Portfolio Basket Wrappers */
  .portfolio-basket-wrapper {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    margin-bottom: 22px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
    page-break-inside: auto;
    break-inside: auto;
  }

  .portfolio-banner {
    padding: 12px 18px;
    color: #ffffff;
    border-radius: 11px 11px 0 0;
    page-break-after: avoid;
    break-after: avoid;
  }

  .portfolio-banner-game {
    background: linear-gradient(135deg, #064e3b 0%, #065f46 50%, #047857 100%);
  }

  .portfolio-banner-set {
    background: linear-gradient(135deg, #1e3a8a 0%, #1e40af 50%, #2563eb 100%);
  }

  .portfolio-banner-match {
    background: linear-gradient(135deg, #581c87 0%, #6b21a8 50%, #7c3aed 100%);
  }

  .portfolio-banner-junior {
    background: linear-gradient(135deg, #701a75 0%, #86198f 50%, #a21caf 100%);
  }

  .portfolio-banner-custom {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%);
  }

  .portfolio-banner-watchlist {
    background: linear-gradient(135deg, #18181b 0%, #27272a 50%, #3f3f46 100%);
  }

  .portfolio-banner-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .portfolio-banner-title {
    font-size: 11pt;
    font-weight: 800;
    letter-spacing: 0.5px;
    display: flex;
    align-items: center;
    gap: 8px;
    text-transform: uppercase;
  }

  .portfolio-icon {
    font-size: 13pt;
  }

  .portfolio-banner-count {
    background: rgba(255, 255, 255, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.25);
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 7.5pt;
    font-weight: 700;
    letter-spacing: 0.3px;
  }

  .portfolio-companies-bar {
    background: rgba(0, 0, 0, 0.18);
    border-top: 1px solid rgba(255, 255, 255, 0.12);
    margin: 10px -18px -12px -18px;
    padding: 8px 18px;
    font-size: 8pt;
    color: #f1f5f9;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }

  .portfolio-bar-label {
    font-weight: 700;
    text-transform: uppercase;
    font-size: 7.5pt;
    letter-spacing: 0.4px;
    color: #e2e8f0;
  }

  .comp-pill {
    background: rgba(255, 255, 255, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.22);
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 7.5pt;
    font-weight: 600;
    color: #ffffff;
    white-space: nowrap;
  }

  .basket-body {
    padding: 16px 18px;
  }

  .basket-subheading {
    font-size: 8.8pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #334155;
    margin: 10px 0 8px 0;
    display: flex;
    align-items: center;
    gap: 6px;
    page-break-after: avoid;
    break-after: avoid;
  }

  .basket-empty {
    text-align: center;
    color: #64748b;
    font-size: 8.5pt;
    font-style: italic;
    padding: 16px 12px;
    background: #f8fafc;
    border-radius: 8px;
    border: 1px dashed #cbd5e1;
  }

  /* 5. Company & Story Cards */
  .company-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 14px;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
    page-break-inside: avoid;
  }

  .company-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }

  .company-name {
    font-size: 11pt;
    font-weight: 800;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .basket-mini-tag {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7pt;
    font-weight: 700;
    padding: 1px 6px;
    border-radius: 3px;
    text-transform: uppercase;
  }

  .basket-mini-game { background: #d1fae5; color: #065f46; }
  .basket-mini-set { background: #dbeafe; color: #1e40af; }
  .basket-mini-match { background: #ede9fe; color: #6b21a8; }
  .basket-mini-junior { background: #fae8ff; color: #86198f; }
  .basket-mini-custom { background: #e0f2fe; color: #0369a1; }
  .basket-mini-watchlist { background: #f1f5f9; color: #475569; }

  .ticker-pill {
    font-family: 'JetBrains Mono', monospace;
    font-size: 7.5pt;
    font-weight: 600;
    background: #f1f5f9;
    color: #475569;
    padding: 2px 7px;
    border-radius: 4px;
    letter-spacing: 0.2px;
  }

  /* 6. Story Items */
  .story-item {
    padding: 8px 0;
    border-bottom: 1px dashed #f1f5f9;
    page-break-inside: avoid;
    break-inside: avoid;
  }

  .story-item:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .story-top-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 4px;
  }

  .story-headline {
    font-size: 9.5pt;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.35;
    flex: 1;
  }

  .story-headline a {
    color: #0f172a;
    text-decoration: none;
  }

  .story-headline a:hover {
    color: #10b981;
    text-decoration: underline;
  }

  .badge {
    font-family: 'JetBrains Mono', monospace;
    display: inline-block;
    font-size: 7pt;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 4px;
    text-transform: uppercase;
    white-space: nowrap;
    letter-spacing: 0.3px;
  }

  .badge-filing {
    background: #ede9fe;
    color: #6d28d9;
    border: 1px solid #ddd6fe;
  }

  .badge-grade-a {
    background: #ecfdf5;
    color: #047857;
    border: 1px solid #a7f3d0;
  }

  .badge-grade-b {
    background: #f8fafc;
    color: #475569;
    border: 1px solid #e2e8f0;
  }

  .story-summary-box {
    background: #f8fafc;
    border-left: 3px solid #cbd5e1;
    padding: 6px 10px;
    margin: 6px 0;
    border-radius: 0 6px 6px 0;
    font-size: 8.5pt;
    color: #334155;
    line-height: 1.45;
  }

  .story-footer-row {
    display: block;
    line-height: 18px;
    overflow: hidden;
    font-size: 7.5pt;
    color: #64748b;
    margin-top: 4px;
  }

  .story-footer-row > div:first-child {
    display: inline-block;
    float: left;
    line-height: 18px;
  }

  .publisher-pill {
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 3px;
    color: #475569;
    font-weight: 500;
  }

  .source-link-action {
    display: inline-block;
    float: right;
    line-height: 18px;
    color: #2563eb;
    text-decoration: none;
    font-weight: 600;
  }

  .source-link-action:hover {
    text-decoration: underline;
  }

  /* 7. Footer */
  .doc-footer {
    margin-top: 24px;
    border-top: 1px solid #e2e8f0;
    padding-top: 10px;
    font-size: 7.5pt;
    color: #94a3b8;
    text-align: center;
    letter-spacing: 0.3px;
  }
  /* 8. 24-Hour Coverage Window Notice */
  .coverage-window-banner {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-left: 4px solid #0284c7;
    border-radius: 8px;
    padding: 8px 14px;
    margin-bottom: 16px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
  }
  .coverage-icon {
    font-size: 13pt;
    line-height: 1;
    margin-top: 1px;
  }
  .coverage-content {
    flex: 1;
  }
  .coverage-title {
    font-size: 8pt;
    font-weight: 800;
    color: #0369a1;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 2px;
  }
  .coverage-details {
    font-size: 8pt;
    color: #334155;
    line-height: 1.4;
  }
  .coverage-note {
    font-size: 7.2pt;
    color: #64748b;
    font-style: italic;
    margin-top: 2px;
  }
</style>
</head>
<body>

<!-- Masthead -->
<div class="masthead">
  <div class="brand-row">
    <div class="brand-group">
      {% if logo_data_uri %}
      <img src="{{ logo_data_uri }}" class="masthead-rect-logo" alt="Vriddhi - Building wealth with wisdom" />
      {% endif %}
      <div class="brand-v-divider"></div>
      <div>
        <div class="brand-desk-title">EQUITY RESEARCH DESK</div>
        <div class="brand-sub">Daily Executive Intelligence Digest</div>
      </div>
    </div>
    <div class="meta-pills">
      <span><strong>Client:</strong> {{ analyst_name }}</span>
      <span>&bull;</span>
      <span><strong>Portfolios:</strong> {{ assigned_folders_str }}</span>
      <span>&bull;</span>
      <span>{{ date_str }}</span>
      <span>&bull;</span>
      <span style="color:#059669;font-weight:700;">{{ total_items }} Stories ({{ total_filings }} Filings)</span>
    </div>
  </div>
</div>

<!-- 24-Hour Coverage Window Notice -->
<div class="coverage-window-banner">
  <div class="coverage-icon">&#128338;</div>
  <div class="coverage-content">
    <div class="coverage-title">Intelligence Coverage Window &bull; Last 24 Hours</div>
    <div class="coverage-details">
      <strong>Timeframe:</strong> {{ coverage_window_start }} &mdash; {{ coverage_window_end }} &bull; 
      <strong>Scope:</strong> BSE / NSE Corporate Announcements, Disclosures &amp; Verified Financial Press
    </div>
    <div class="coverage-note">
      * All updates in this scorecard were published within the last 24 hours. Tracked companies with no entries had zero material disclosures during this cycle.
    </div>
  </div>
</div>

<!-- Portfolio Baskets News & Filings -->
<div class="section-heading">&#128202; Portfolio Baskets & Corporate Intelligence</div>

{% if not baskets %}
<div class="company-card" style="text-align: center; color: #64748b; font-style: italic; padding: 24px;">
  No portfolio baskets assigned or no stories found for today. Sent ledger is clean!
</div>
{% endif %}

{% for basket in baskets %}
<div class="portfolio-basket-wrapper">
  <!-- Portfolio Basket Header Banner -->
  <div class="portfolio-banner portfolio-banner-{{ basket.theme }}">
    <div class="portfolio-banner-top">
      <div class="portfolio-banner-title">
        <span class="portfolio-icon">{{ basket.icon }}</span>
        <span>PORTFOLIO BASKET: <strong>{{ basket.name }}</strong></span>
      </div>
      <span class="portfolio-banner-count">{{ basket.companies_count }} Companies &bull; {{ basket.total_updates }} Updates</span>
    </div>
    <div class="portfolio-companies-bar">
      <span class="portfolio-bar-label">COMPANIES IN {{ basket.name }}:</span>
      {% if basket.all_companies %}
        {% for c in basket.all_companies %}
        <span class="comp-pill">{{ c }}</span>
        {% endfor %}
      {% else %}
        <span style="opacity:0.8; font-style:italic;">No companies mapped</span>
      {% endif %}
    </div>
  </div>

  <div class="basket-body">
    <!-- Filings for this basket -->
    {% if basket.filings %}
    <div class="basket-subheading">&#127963; Exchange Filings & Regulatory Disclosures</div>
    <div class="company-card" style="border-left: 3px solid #7c3aed; margin-bottom: 14px;">
      {% for item in basket.filings %}
      <div class="story-item">
        <div class="story-top-row">
          <span class="badge badge-filing">&#127963; SEBI / Exchange Filing</span>
          <div class="story-headline">
            <strong>{{ item.company_name }}</strong>: 
            <a href="{{ item.url }}" target="_blank">{{ item.title }}</a>
          </div>
        </div>
        {% if item.summary %}
        <div class="story-summary-box">{{ item.summary }}</div>
        {% endif %}
        <div class="story-footer-row">
          <div>
            <span class="publisher-pill">{{ item.source_name }}</span>
            {% if item.published_formatted %} &bull; {{ item.published_formatted }}{% endif %}
          </div>
          {% if item.url %}
          <a class="source-link-action" href="{{ item.url }}" target="_blank">&rarr; View Official Document</a>
          {% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
    {% endif %}

    <!-- News by Company for this basket -->
    {% if basket.news_by_company %}
    <div class="basket-subheading">&#128202; Corporate & Market Intelligence</div>
    {% for company_name, items in basket.news_by_company.items() %}
    <div class="company-card">
      <div class="company-header">
        <div class="company-name">
          <span>{{ company_name }}</span>
          <span class="basket-mini-tag basket-mini-{{ basket.theme }}">{{ basket.name }}</span>
        </div>
        <span class="ticker-pill">{{ items|length }} Updates</span>
      </div>
      {% for item in items %}
      <div class="story-item">
        <div class="story-top-row">
          {% if item.grade == 'Grade A' %}
          <span class="badge badge-grade-a">&#128293; Grade A &bull; Material</span>
          {% else %}
          <span class="badge badge-grade-b">Grade B &bull; Research</span>
          {% endif %}
          <div class="story-headline">
            <a href="{{ item.url }}" target="_blank">{{ item.title }}</a>
          </div>
        </div>
        {% if item.summary %}
        <div class="story-summary-box">{{ item.summary }}</div>
        {% endif %}
        <div class="story-footer-row">
          <div>
            <span class="publisher-pill">{{ item.source_name }}</span>
            {% if item.published_formatted %} &bull; {{ item.published_formatted }}{% endif %}
          </div>
          {% if item.sources %}
          <div>
            {% for src in item.sources %}
            <a class="source-link-action" href="{{ src.url }}" target="_blank" style="margin-left: 6px;">[{{ src.name }}]</a>
            {% endfor %}
          </div>
          {% elif item.url %}
          <a class="source-link-action" href="{{ item.url }}" target="_blank">&rarr; Read Article</a>
          {% endif %}
        </div>
      </div>
      {% endfor %}
    </div>
    {% endfor %}
    {% elif not basket.filings %}
    <div class="basket-empty">
      No new unsent news items or regulatory filings for {{ basket.name }} companies today. Sent ledger is clean!
    </div>
    {% endif %}
  </div>
</div>
{% endfor %}

<div class="doc-footer">
  CONFIDENTIAL &bull; VRIDDHI MONEY INSTITUTIONAL RESEARCH DESK &bull; PROPRIETARY NEVER-RESEND LEDGER PROTECTED
</div>

</body>
</html>
"""


def _get_basket_theme(name: str) -> tuple[str, str]:
    """Return (theme_key, icon) for a portfolio basket name."""
    clean = name.strip().upper()
    if clean == "GAME":
        return "game", "🏆"
    if clean == "SET":
        return "set", "💎"
    if clean == "MATCH":
        return "match", "⚡"
    if clean == "JUNIOR":
        return "junior", "🚀"
    if "WATCHLIST" in clean or "DIRECT" in clean:
        return "watchlist", "🎯"
    return "custom", "📁"


def render_digest_html(
    analyst_name: str,
    stories: list[dict],
    date_str: str | None = None,
    analyst_id: str | None = None,
    assigned_folders: list[str] | None = None,
    assigned_companies: list[str] | None = None,
) -> str:
    """Render the HTML digest with portfolio-specific groupings for the given analyst and stories."""
    from jinja2 import Template  # type: ignore

    if not date_str:
        date_str = datetime.now(IST).strftime("%d %b %Y")

    # 1. Fetch analyst if folders/companies not explicitly supplied
    if (assigned_folders is None or assigned_companies is None) and analyst_id:
        try:
            for a in get_analysts():
                if a.id == analyst_id:
                    if assigned_folders is None:
                        assigned_folders = a.assigned_folders
                    if assigned_companies is None:
                        assigned_companies = a.assigned_companies
                    break
        except Exception as e:
            log.warning("Could not load analyst details: %s", e)

    assigned_folders = [f.strip().upper() for f in (assigned_folders or []) if f.strip()]
    assigned_companies = [c.strip() for c in (assigned_companies or []) if c.strip()]

    # 2. Fetch all companies for portfolio mapping
    try:
        all_comps = get_companies()
    except Exception:
        all_comps = []

    comp_by_id = {c.id: c for c in all_comps}
    comp_by_name = {c.name.strip().lower(): c for c in all_comps}

    # 3. Format stories and resolve company meta
    processed_stories: list[dict] = []
    total_filings = 0

    for s in stories:
        item = dict(s)
        try:
            raw_pub = str(item.get("published_at") or "")
            dt = datetime.fromisoformat(raw_pub).astimezone(IST)
            item["published_formatted"] = dt.strftime("%I:%M %p")
        except (ValueError, TypeError):
            item["published_formatted"] = ""

        # Map company metadata
        cid = item.get("company_id")
        cname_raw = str(item.get("company_name", "")).strip()
        cobj = comp_by_id.get(cid) or comp_by_name.get(cname_raw.lower())

        if cobj:
            item["company_name"] = cobj.name
            item["company_folders"] = [f.upper() for f in (getattr(cobj, "folders", []) or ([cobj.folder] if cobj.folder else []))]
        else:
            item["company_folders"] = []

        is_filing = item.get("source_type") == "filing" or bool(item.get("filing_id"))
        if is_filing:
            total_filings += 1

        processed_stories.append(item)

    # 4. Build Portfolio Baskets
    baskets: list[dict] = []
    handled_story_ids: set[str] = set()

    for folder_name in assigned_folders:
        theme, icon = _get_basket_theme(folder_name)
        # Companies belonging to this basket
        basket_comps = [c for c in all_comps if folder_name in [f.upper() for f in (getattr(c, "folders", []) or ([c.folder] if c.folder else []))]]
        basket_comp_ids = {c.id for c in basket_comps}
        basket_comp_names = [c.name for c in basket_comps]

        # Stories matching this basket
        basket_stories = [
            s for s in processed_stories
            if s.get("company_id") in basket_comp_ids
            or folder_name in s.get("company_folders", [])
        ]

        # If there are no company updates/filings in this basket, neglect/hide it completely
        if not basket_stories:
            continue

        b_filings = [s for s in basket_stories if s.get("source_type") == "filing" or bool(s.get("filing_id"))]
        b_news_by_company: dict[str, list[dict]] = {}
        for s in basket_stories:
            handled_story_ids.add(s["id"])
            if s in b_filings:
                continue
            cname = s.get("company_name", "General")
            b_news_by_company.setdefault(cname, []).append(s)

        baskets.append({
            "name": folder_name,
            "icon": icon,
            "theme": theme,
            "companies_count": len(basket_comps),
            "all_companies": basket_comp_names,
            "total_updates": len(basket_stories),
            "filings": b_filings,
            "news_by_company": b_news_by_company,
        })

    # 5. Handle any remaining stories (direct company assignments or watchlist)
    remaining_stories = [s for s in processed_stories if s["id"] not in handled_story_ids]
    if remaining_stories or (not assigned_folders and processed_stories):
        basket_name = "DIRECT WATCHLIST" if assigned_companies else "PORTFOLIO WATCHLIST"
        theme, icon = _get_basket_theme(basket_name)

        r_filings = [s for s in remaining_stories if s.get("source_type") == "filing" or bool(s.get("filing_id"))]
        r_news_by_company: dict[str, list[dict]] = {}
        r_comp_names = set()

        for s in remaining_stories:
            cname = s.get("company_name", "General")
            r_comp_names.add(cname)
            if s in r_filings:
                continue
            r_news_by_company.setdefault(cname, []).append(s)

        direct_company_names = [comp_by_id[cid].name for cid in assigned_companies if cid in comp_by_id]
        all_display_comps = direct_company_names or sorted(list(r_comp_names))

        baskets.append({
            "name": basket_name,
            "icon": icon,
            "theme": theme,
            "companies_count": len(all_display_comps),
            "all_companies": all_display_comps,
            "total_updates": len(remaining_stories),
            "filings": r_filings,
            "news_by_company": r_news_by_company,
        })

    # 6. Build Morning Scorecard Matrix Table
    scorecard = []
    for b in baskets:
        # Scorecard entries from filings
        for f in b["filings"][:3]:
            scorecard.append({
                "company": f.get("company_name", "Company"),
                "portfolio": b["name"],
                "theme": b["theme"],
                "catalyst": f.get("title", ""),
                "grade": "Grade A",
                "url": f.get("url", "#"),
            })
        # Top catalyst from news per company
        for cname, items in b["news_by_company"].items():
            if items:
                top = items[0]
                scorecard.append({
                    "company": cname,
                    "portfolio": b["name"],
                    "theme": b["theme"],
                    "catalyst": top.get("title", ""),
                    "grade": top.get("grade", "Grade B"),
                    "url": top.get("url", "#"),
                })

    assigned_folders_str = ", ".join(assigned_folders) if assigned_folders else "Direct Watchlist"
    now_ist = datetime.now(IST)
    date_str_file = now_ist.strftime("%d-%m-%Y")
    
    # Anchored 24h market window for Morning Scorecard: Yesterday 08:00 AM IST to Today 08:00 AM IST
    today_8am = now_ist.replace(hour=8, minute=0, second=0, microsecond=0)
    yesterday_8am = today_8am - timedelta(days=1)
    coverage_window_start = yesterday_8am.strftime("%d-%b-%Y 08:00 AM IST")
    coverage_window_end = today_8am.strftime("%d-%b-%Y 08:00 AM IST")

    template = Template(HTML_TEMPLATE)
    return template.render(
        logo_data_uri=get_vriddhi_logo_data_uri(),
        analyst_name=analyst_name,
        assigned_folders_str=assigned_folders_str,
        date_str=date_str,
        date_str_file=date_str_file,
        coverage_window_start=coverage_window_start,
        coverage_window_end=coverage_window_end,
        total_items=len(stories),
        total_filings=total_filings,
        scorecard=scorecard,
        baskets=baskets,
    )


def generate_pdf_via_browser(html_path: Path, pdf_path: Path) -> bool:
    """Render HTML to PDF using native headless Chromium / Edge on Windows/Linux."""
    import shutil
    import subprocess
    browser_candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        shutil.which("chromium"),
    ]
    browser_exe = None
    for b in browser_candidates:
        if b and Path(b).exists():
            browser_exe = b
            break

    if not browser_exe:
        return False

    cmd = [
        browser_exe,
        "--headless",
        "--disable-gpu",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        html_path.resolve().as_uri(),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=30)
        return pdf_path.exists() and pdf_path.stat().st_size > 1000
    except Exception as e:
        log.warning("Browser headless PDF generation failed: %s", e)
        return False


def normalize_pdf_link_rects(pdf_path: Path) -> None:
    """Ensure all /Rect bounding boxes in PDF annotations satisfy x1 < x2 and y1 < y2.
    WeasyPrint inverted y-coordinates [x1, y_top, x2, y_bottom] cause hit-tests in mobile and
    desktop PDF viewers to fail due to negative height rectangles.
    """
    try:
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import ArrayObject, FloatObject, NameObject

        reader = PdfReader(str(pdf_path))
        writer = PdfWriter()
        writer.append(reader)
        modified = False

        for page in writer.pages:
            annots = page.get("/Annots")
            if not annots:
                continue
            for a in annots:
                obj = a.get_object()
                rect = obj.get("/Rect")
                if rect and len(rect) == 4:
                    x1, y1, x2, y2 = [float(v) for v in rect]
                    nx1 = min(x1, x2)
                    ny1 = min(y1, y2)
                    nx2 = max(x1, x2)
                    ny2 = max(y1, y2)
                    if (x1, y1, x2, y2) != (nx1, ny1, nx2, ny2):
                        obj[NameObject("/Rect")] = ArrayObject([
                            FloatObject(nx1),
                            FloatObject(ny1),
                            FloatObject(nx2),
                            FloatObject(ny2),
                        ])
                        modified = True

        if modified:
            with open(pdf_path, "wb") as f:
                writer.write(f)
            log.info("Normalized inverted link annotations in PDF: %s", pdf_path.name)
    except Exception as e:
        log.warning("PDF rect normalization skipped: %s", e)


def get_clean_digest_filename(analyst_name: str, ext: str = ".pdf") -> str:
    """Format PDF filename as [Client_Name]_[Date].pdf using DD-MM-YYYY format."""
    now = datetime.now(IST)
    date_str = now.strftime("%d-%m-%Y")
    words = [w for w in analyst_name.strip().split() if w]
    sanitized_words = ["".join(c for c in w if c.isalnum() or c == "_") for w in words]
    clean_name = "_".join(w for w in sanitized_words if w) or "Client"
    return f"{clean_name}_{date_str}{ext}"


def generate_analyst_digest(analyst_id: str, analyst_name: str, stories: list[dict]) -> tuple[Path, str]:
    """Generate both an HTML digest and a high-definition PDF rendering with [Client_Name]_[Date].pdf."""
    import shutil
    html_content = render_digest_html(analyst_name, stories, analyst_id=analyst_id)

    html_filename = get_clean_digest_filename(analyst_name, ext=".html")
    pdf_filename = get_clean_digest_filename(analyst_name, ext=".pdf")

    html_file = DIGESTS_DIR / html_filename
    html_file.write_text(html_content, encoding="utf-8")

    pdf_file = DIGESTS_DIR / pdf_filename

    # 1. Try native browser headless print-to-pdf (produces clean vector PDF)
    if generate_pdf_via_browser(html_file, pdf_file):
        log.info("Compiled fresh PDF via native browser: %s (size: %s bytes)", pdf_file, pdf_file.stat().st_size)
        normalize_pdf_link_rects(pdf_file)
        return pdf_file, html_content

    # 2. Attempt WeasyPrint if available
    try:
        import weasyprint  # type: ignore[import-untyped]
        weasyprint.HTML(string=html_content).write_pdf(str(pdf_file))
        normalize_pdf_link_rects(pdf_file)
        return pdf_file, html_content
    except Exception as e:  # noqa: BLE001
        log.info("WeasyPrint direct compilation not active (%s); using HTML digest fallback", e)
        return html_file, html_content


MACRO_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{{ analyst_name }}_Macro_Evening_{{ date_str_file }}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap');

  @page {
    size: A4;
    margin: 10mm 10mm 10mm 10mm;
    @bottom-right {
      content: "Page " counter(page) " of " counter(pages);
      font-size: 8pt;
      color: #94a3b8;
      font-family: 'Plus Jakarta Sans', sans-serif;
    }
  }

  * { box-sizing: border-box; }

  body {
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    color: #0f172a;
    background-color: #f8fafc;
    line-height: 1.5;
    margin: 0;
    padding: 8px;
    font-size: 9pt;
  }

  .masthead {
    background: #ffffff;
    border-radius: 12px;
    padding: 16px 22px;
    margin-bottom: 14px;
    color: #0f172a;
    box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.06), 0 1px 3px rgba(15, 23, 42, 0.04);
    border: 1px solid #e2e8f0;
    border-left: 5px solid #0284c7;
  }

  .brand-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #f1f5f9;
    padding-bottom: 12px;
    margin-bottom: 10px;
  }

  .brand-group {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .masthead-rect-logo {
    height: 52px;
    width: auto;
    object-fit: contain;
    display: block;
  }

  .brand-v-divider {
    width: 1px;
    height: 38px;
    background: #e2e8f0;
  }

  .brand-desk-title {
    font-size: 11pt;
    font-weight: 800;
    letter-spacing: -0.2px;
    color: #0f172a;
    margin: 0;
    line-height: 1.2;
  }

  .brand-sub {
    font-size: 7.8pt;
    color: #64748b;
    font-weight: 500;
    letter-spacing: 0.2px;
    margin-top: 2px;
  }

  .analyst-badge {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 8.5pt;
    font-weight: 600;
    color: #0f172a;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
  }

  .meta-sub-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 8pt;
    color: #64748b;
  }

  .meta-sub-row strong {
    color: #0f172a;
  }

  /* Benchmark Grid */
  .benchmark-grid {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 9px;
    margin-bottom: 20px;
  }

  .benchmark-box {
    background: #ffffff;
    border: 1.5px solid #94a3b8;
    border-top: 4px solid #0284c7;
    border-radius: 8px;
    padding: 8px 6px;
    text-align: center;
    box-shadow: 0 2px 5px rgba(15, 23, 42, 0.08);
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: center;
  }

  .bm-label {
    font-size: 7.2pt;
    text-transform: uppercase;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: 0.6px;
    background: #f1f5f9;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 2.5px 6px;
    display: inline-block;
    width: 90%;
    margin-bottom: 5px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .bm-val {
    font-size: 12.5pt;
    font-weight: 900;
    color: #090d16;
    font-family: 'JetBrains Mono', monospace;
    margin: 2px 0 6px 0;
    letter-spacing: -0.4px;
    line-height: 1.15;
  }

  .bm-chg {
    font-size: 7.2pt;
    font-weight: 800;
    padding: 3px 8px;
    border-radius: 4px;
    display: inline-block;
    letter-spacing: 0.3px;
  }

  .chg-pos { background: #dcfce7; color: #15803d; border: 1.5px solid #4ade80; }
  .chg-neg { background: #fee2e2; color: #b91c1c; border: 1.5px solid #f87171; }
  .chg-neu { background: #f1f5f9; color: #0f172a; border: 1.5px solid #94a3b8; }

  /* Section Headings */
  .section-heading {
    font-size: 10pt;
    font-weight: 800;
    color: #0f172a;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 16px 0 10px 0;
    display: flex;
    align-items: center;
    gap: 6px;
    border-bottom: 2px solid #cbd5e1;
    padding-bottom: 5px;
  }

  /* Story Cards */
  .macro-card {
    background: #ffffff;
    border: 1.5px solid #cbd5e1;
    border-radius: 8px;
    padding: 11px 14px;
    margin-bottom: 9px;
    page-break-inside: avoid;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  }

  .card-top {
    display: flex;
    justify-content: flex-start;
    align-items: center;
    margin-bottom: 5px;
  }

  .tier-tag {
    font-size: 6.8pt;
    font-weight: 700;
    padding: 2.5px 8px;
    border-radius: 4px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }

  .tier-1 {
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #fcd34d;
  }
  .tier-2 {
    background: #f1f5f9;
    color: #475569;
    border: 1px solid #e2e8f0;
  }

  .story-title {
    font-size: 9.5pt;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.4;
    margin: 4px 0 6px 0;
  }

  .story-title a {
    color: #0f172a;
    text-decoration: none;
    transition: color 0.15s ease;
  }

  .story-title a:hover {
    color: #0284c7;
    text-decoration: underline;
  }

  .impact-strip {
    background: #f8fafc;
    border-left: 3.5px solid #10b981;
    border-radius: 0 5px 5px 0;
    padding: 5px 10px;
    font-size: 8.2pt;
    line-height: 1.45;
    color: #1e293b;
    margin: 6px 0 8px 0;
    border-top: 1px solid #f1f5f9;
    border-right: 1px solid #f1f5f9;
    border-bottom: 1px solid #f1f5f9;
  }

  .impact-strip-neg {
    border-left-color: #ef4444;
    background: #fff5f5;
  }
  .impact-strip-neu {
    border-left-color: #64748b;
    background: #f8fafc;
  }

  .card-footer {
    display: block;
    font-size: 7.5pt;
    color: #64748b;
    margin-top: 6px;
    padding-top: 6px;
    border-top: 1px solid #f1f5f9;
    line-height: 20px;
    overflow: hidden;
  }

  .regulator-name {
    font-weight: 600;
    color: #475569;
    display: inline-block;
    float: left;
    line-height: 20px;
  }

  .action-link {
    color: #0284c7;
    font-weight: 800;
    font-size: 7.5pt;
    text-decoration: none;
    padding: 3px 10px;
    border-radius: 4px;
    background: #f0f9ff;
    border: 1.5px solid #0284c7;
    display: inline-block;
    float: right;
    line-height: 14px;
    transition: all 0.15s ease;
  }

  .action-link:hover {
    color: #ffffff;
    background: #0284c7;
    border-color: #0369a1;
  }

  .coverage-window-banner {
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-left: 4px solid #0284c7;
    border-radius: 8px;
    padding: 8px 14px;
    margin-bottom: 14px;
    display: flex;
    align-items: flex-start;
    gap: 10px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
  }
  .coverage-icon {
    font-size: 13pt;
    line-height: 1;
    margin-top: 1px;
  }
  .coverage-content {
    flex: 1;
  }
  .coverage-title {
    font-size: 8pt;
    font-weight: 800;
    color: #0369a1;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    margin-bottom: 2px;
  }
  .coverage-details {
    font-size: 8pt;
    color: #334155;
    line-height: 1.4;
  }
  .sector-nav-index {
    display: block;
    line-height: 28px;
    margin-bottom: 18px;
    padding: 12px 14px;
    background: #ffffff;
    border: 1.5px solid #cbd5e1;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
  }
  .sector-nav-chip {
    display: inline-block;
    vertical-align: middle;
    margin-right: 6px;
    margin-bottom: 6px;
    padding: 5px 10px;
    background: #f8fafc;
    border: 1.5px solid #cbd5e1;
    border-radius: 6px;
    text-decoration: none;
    font-size: 7.5pt;
    font-weight: 800;
    color: #1e293b;
    box-shadow: 0 1px 2px rgba(0,0,0,0.03);
  }
  .sector-nav-chip:hover {
    border-color: #0284c7;
    background: #f0f9ff;
    color: #0284c7;
  }
  .sector-nav-chip .chip-count {
    background: #0284c7;
    color: #ffffff;
    font-size: 6.8pt;
    padding: 1.5px 6px;
    border-radius: 10px;
    font-weight: 800;
  }
  .sector-group-block {
    margin-bottom: 22px;
    page-break-inside: auto;
    break-inside: auto;
  }
  .sector-group-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    background: linear-gradient(90deg, #e0f2fe 0%, #f0f9ff 45%, #ffffff 100%);
    border: 1.5px solid #0284c7;
    border-left: 7px solid #0369a1;
    border-radius: 6px;
    margin-bottom: 12px;
    box-shadow: 0 2px 6px rgba(2, 132, 199, 0.12);
    page-break-after: avoid;
    break-after: avoid;
  }
  .sector-group-title {
    font-size: 10.5pt;
    font-weight: 900;
    color: #0f172a;
    letter-spacing: 0.7px;
    text-transform: uppercase;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .sector-group-icon {
    font-size: 12pt;
    line-height: 1;
  }
  .sector-label-badge {
    font-size: 7pt;
    font-weight: 800;
    color: #ffffff;
    background: #0284c7;
    border: 1px solid #0369a1;
    padding: 2px 7px;
    border-radius: 4px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
  }
  .sector-name-text {
    font-weight: 900;
    color: #0f172a;
  }
  .sector-group-count {
    font-size: 7.8pt;
    font-weight: 800;
    color: #ffffff;
    background: #0f172a;
    border: 1.5px solid #0284c7;
    padding: 3.5px 12px;
    border-radius: 14px;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    box-shadow: 0 1px 4px rgba(15, 23, 42, 0.2);
  }
</style>
</head>
<body>

<!-- Masthead -->
<div class="masthead">
  <div class="brand-row">
    <div class="brand-group">
      {% if logo_data_uri %}
      <img src="{{ logo_data_uri }}" class="masthead-rect-logo" alt="Vriddhi - Building wealth with wisdom" />
      {% endif %}
      <div class="brand-v-divider"></div>
      <div>
        <div class="brand-desk-title">POST-MARKET MACRO DESK</div>
        <div class="brand-sub">Sovereign &amp; Regulatory Policy Briefing</div>
      </div>
    </div>
    <div class="analyst-badge">
      &#128100; {{ analyst_name }} &bull; {{ sectors_label }}
    </div>
  </div>
  <div class="meta-sub-row">
    <div>Date: <strong>{{ date_str }} (Evening Wrap)</strong></div>
    <div>{{ total_items }} Verified Policy Directives &bull; {{ tier1_count }} Sovereign/Tier-1</div>
  </div>
</div>

<!-- 24-Hour Policy Coverage Window Notice -->
<div class="coverage-window-banner">
  <div class="coverage-icon">&#128338;</div>
  <div class="coverage-content">
    <div class="coverage-title">Post-Market Policy Window &bull; Last 24 Hours</div>
    <div class="coverage-details">
      <strong>Timeframe:</strong> {{ coverage_window_start }} &mdash; {{ coverage_window_end }} &bull; 
      <strong>Scope:</strong> RBI, SEBI, PIB, Official Gazettes &amp; Sector Directives
    </div>
    <div class="coverage-note">
      * Real-time regulatory &amp; macroeconomic circulars verified over the last 24-hour cycle.
    </div>
  </div>
</div>

<!-- Benchmarks Strip -->
<div class="benchmark-grid">
  {% for k, bm in benchmarks.items() %}
  <div class="benchmark-box">
    <div class="bm-label">{{ bm.label }}</div>
    <div class="bm-val">{{ bm.val }}</div>
    <span class="bm-chg {% if bm.bias == 'POSITIVE' %}chg-pos{% elif bm.bias == 'NEGATIVE' %}chg-neg{% else %}chg-neu{% endif %}">
      {{ bm.change }}
    </span>
  </div>
  {% endfor %}
</div>

<!-- Section: Verified Directives Organized By Sector -->
<div class="section-heading">&#128220; Institutional &amp; Sector Directives</div>

{% if not stories %}
<div class="macro-card" style="text-align: center; color: #64748b; padding: 24px;">
  No new policy gazettes or directives for this sector window today.
</div>
{% endif %}

<!-- Sector Navigation Index -->
{% if sector_groups and sector_groups|length > 1 %}
<div class="sector-nav-index">
  {% for sg in sector_groups %}
  <a href="#sec-{{ loop.index }}" class="sector-nav-chip">
    <span>{{ sg.icon }} {{ sg.name }}</span>
    <span class="chip-count">{{ sg.count }}</span>
  </a>
  {% endfor %}
</div>
{% endif %}

{% for sg in sector_groups %}
<div class="sector-group-block" id="sec-{{ loop.index }}">
  <div class="sector-group-header">
    <div class="sector-group-title">
      <span class="sector-group-icon">{{ sg.icon }}</span>
      <span class="sector-label-badge">SECTOR</span>
      <span class="sector-name-text">{{ sg.name }}</span>
    </div>
    <span class="sector-group-count">{{ sg.count }} DIRECTIVE{% if sg.count > 1 %}S{% endif %}</span>
  </div>

  {% for s in sg.stories %}
  <div class="macro-card">
    <div class="card-top">
      <span class="tier-tag {% if 'Tier 1' in s.impact_grade %}tier-1{% else %}tier-2{% endif %}">
        {% if 'Tier 1' in s.impact_grade %}&#9889; {% endif %}{{ s.impact_grade }}
      </span>
    </div>

    <div class="story-title">
      <a href="{{ s.url or '#' }}" target="_blank" rel="noopener noreferrer">{{ s.title }}</a>
    </div>

    {% if s.impact_summary %}
    <div class="impact-strip {% if s.impact_bias == 'NEGATIVE' %}impact-strip-neg{% elif s.impact_bias == 'NEUTRAL' %}impact-strip-neu{% endif %}">
      <strong>Impact:</strong> {{ s.impact_summary }}
    </div>
    {% endif %}

    <div class="card-footer">
      <span class="regulator-name">&#127963; {{ s.ministry_or_regulator or s.source_authority or 'Government / Regulatory Authority' }}</span>
      <a href="{{ s.url or '#' }}" target="_blank" rel="noopener noreferrer" class="action-link">Go to website &rarr;</a>
      <div style="clear: both;"></div>
    </div>
  </div>
  {% endfor %}
</div>
{% endfor %}

</body>
</html>
"""


def get_clean_macro_digest_filename(analyst_name: str, ext: str = ".pdf") -> str:
    now = datetime.now(IST)
    date_str = now.strftime("%d-%m-%Y")
    words = [w for w in analyst_name.strip().split() if w]
    sanitized_words = ["".join(c for c in w if c.isalnum() or c == "_") for w in words]
    clean_name = "_".join(w for w in sanitized_words if w) or "Client"
    return f"{clean_name}_Macro_Evening_{date_str}{ext}"


def render_macro_digest_html(
    analyst_name: str,
    analyst_id: str,
    stories: list[dict],
    benchmarks: dict | None = None,
    date_str: str | None = None,
) -> str:
    """Render the HTML digest for the Post-Market Macro & Policy Briefing."""
    from jinja2 import Template
    from .db import fetch_live_benchmarks, get_analyst_macro_sectors

    if not date_str:
        date_str = datetime.now(IST).strftime("%d %b %Y")

    if not benchmarks:
        benchmarks = fetch_live_benchmarks()

    sectors = get_analyst_macro_sectors(analyst_id)
    sectors_label = "All Sectors" if "ALL" in [s.upper() for s in sectors] else ", ".join(sectors[:2])
    if len(sectors) > 2 and sectors_label != "All Sectors":
        sectors_label += f" +{len(sectors)-2}"

    now_ist = datetime.now(IST)
    date_str_file = now_ist.strftime("%d-%m-%Y")
    
    # Anchored 24h market window for Evening Macro Briefing: Yesterday 05:00 PM IST to Today 05:00 PM IST
    today_5pm = now_ist.replace(hour=17, minute=0, second=0, microsecond=0)
    yesterday_5pm = today_5pm - timedelta(days=1)
    coverage_window_start = yesterday_5pm.strftime("%d-%b-%Y 05:00 PM IST")
    coverage_window_end = today_5pm.strftime("%d-%b-%Y 05:00 PM IST")
    tier1_count = sum(1 for s in stories if "Tier 1" in (s.get("impact_grade") or ""))

    # Ensure each story has its parsed sectors list & formatted publish time
    import json
    for s in stories:
        if not s.get("sectors"):
            try:
                s["sectors"] = [sec.strip().upper() for sec in json.loads(s.get("sectors_json") or "[]")]
            except Exception:
                s["sectors"] = []
        raw_pub = str(s.get("published_at") or "")
        if raw_pub and not s.get("published_formatted"):
            try:
                dt = datetime.fromisoformat(raw_pub.replace("Z", "+00:00")).astimezone(IST)
                s["published_formatted"] = dt.strftime("%I:%M %p")
            except Exception:
                s["published_formatted"] = ""

    # Sector icons mapping for institutional aesthetics
    SECTOR_ICONS = {
        "AUTOMOBILES": "🚗",
        "AUTO COMPONENTS": "⚙️",
        "POWER": "⚡",
        "OIL": "🛢️",
        "GAS": "🔥",
        "PETROLEUM PRODUCTS": "⛽",
        "OTHER UTILITIES": "💧",
        "BANKS": "🏦",
        "FINANCE": "💳",
        "CAPITAL MARKETS": "📈",
        "CONSTRUCTION": "🏗️",
        "REALTY": "🏢",
        "TRANSPORT INFRASTRUCTURE": "🛣️",
        "TRANSPORT SERVICES": "🚆",
        "IT - SERVICES": "💻",
        "IT - HARDWARE": "🖥️",
        "IT - SOFTWARE": "💾",
        "TELECOM - SERVICES": "📡",
        "TELECOM - EQUIPMENT & ACCESSORIES": "📶",
        "CHEMICALS & PETROCHEMICALS": "🧪",
        "FERTILIZERS & AGROCHEMICALS": "🌱",
        "AGRICULTURAL FOOD & OTHER PRODUCTS": "🌾",
        "AGRICULTURAL, COMMERCIAL & CONSTRUCTION VEHICLES": "🚜",
        "PHARMACEUTICALS & BIOTECHNOLOGY": "💊",
        "HEALTHCARE SERVICES": "🏥",
        "AEROSPACE & DEFENSE": "🛡️",
        "FERROUS METALS": "🔩",
        "MINERALS & MINING": "⛏️",
        "INDUSTRIAL PRODUCTS": "🏭",
        "INDUSTRIAL MANUFACTURING": "🏭",
        "COMMERCIAL SERVICES & SUPPLIES": "📦",
        "CIGARETTES & TOBACCO PRODUCTS": "🍂",
        "DIVERSIFIED FMCG": "🛒",
        "GENERAL_MACRO": "🏛️",
        "OTHER": "📰",
    }

    # Group stories by primary sector
    grouped_dict: dict[str, list[dict]] = {}
    for s in stories:
        secs = s.get("sectors") or []
        primary_sec = secs[0].strip().upper() if secs else "GENERAL_MACRO"
        grouped_dict.setdefault(primary_sec, []).append(s)

    def _group_priority(item: tuple[str, list[dict]]) -> tuple[int, int]:
        sec_name, sec_stories = item
        has_tier1 = any("Tier 1" in (st.get("impact_grade") or "") for st in sec_stories)
        is_general = sec_name in ("GENERAL_MACRO", "OTHER")
        tier_score = 0 if has_tier1 else (2 if is_general else 1)
        return (tier_score, -len(sec_stories))

    sorted_groups_raw = sorted(grouped_dict.items(), key=_group_priority)
    
    sector_groups = []
    for sec_name, sec_stories in sorted_groups_raw:
        icon = SECTOR_ICONS.get(sec_name, "📊")
        # Sort stories inside each sector: Tier 1 first, then newest published_at
        sorted_sec_stories = list(sec_stories)
        def _story_sort_key(x: dict) -> tuple[int, float]:
            is_t1 = 0 if "Tier 1" in (x.get("impact_grade") or "") else 1
            ts = 0.0
            pub_raw = x.get("published_at")
            if pub_raw:
                try:
                    ts = -(datetime.fromisoformat(pub_raw.replace("Z", "+00:00")).timestamp())
                except Exception:
                    pass
            return (is_t1, ts)

        sorted_sec_stories.sort(key=_story_sort_key)
        sector_groups.append({
            "name": sec_name,
            "icon": icon,
            "stories": sorted_sec_stories,
            "count": len(sorted_sec_stories),
        })

    template = Template(MACRO_HTML_TEMPLATE)
    return template.render(
        logo_data_uri=get_vriddhi_logo_data_uri(),
        analyst_name=analyst_name,
        sectors_label=sectors_label,
        date_str=date_str,
        date_str_file=date_str_file,
        coverage_window_start=coverage_window_start,
        coverage_window_end=coverage_window_end,
        total_items=len(stories),
        tier1_count=tier1_count,
        benchmarks=benchmarks,
        stories=stories,
        sector_groups=sector_groups,
    )


def generate_macro_digest(analyst_id: str, analyst_name: str, stories: list[dict]) -> tuple[Path, str]:
    """Generate both an HTML digest and high-definition PDF for the Evening Macro Briefing."""
    html_content = render_macro_digest_html(analyst_name, analyst_id, stories)

    html_filename = get_clean_macro_digest_filename(analyst_name, ext=".html")
    pdf_filename = get_clean_macro_digest_filename(analyst_name, ext=".pdf")

    html_file = DIGESTS_DIR / html_filename
    html_file.write_text(html_content, encoding="utf-8")

    pdf_file = DIGESTS_DIR / pdf_filename

    # 1. Try native browser headless print-to-pdf
    if generate_pdf_via_browser(html_file, pdf_file):
        log.info("Compiled fresh Macro PDF via native browser: %s (size: %s bytes)", pdf_file, pdf_file.stat().st_size)
        normalize_pdf_link_rects(pdf_file)
        return pdf_file, html_content

    # 2. Attempt WeasyPrint if available
    try:
        import weasyprint  # type: ignore[import-untyped]
        weasyprint.HTML(string=html_content).write_pdf(str(pdf_file))
        normalize_pdf_link_rects(pdf_file)
        return pdf_file, html_content
    except Exception as e:
        log.info("WeasyPrint direct compilation fallback (%s)", e)
        return html_file, html_content

