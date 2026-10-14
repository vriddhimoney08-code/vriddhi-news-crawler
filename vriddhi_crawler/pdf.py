"""Executive PDF and HTML Digest Generator for Vriddhi Research Desk."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from .config import DIGESTS_DIR, IST
from .db import get_analysts, get_companies

log = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
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

  /* 1. Modern Header Masthead */
  .masthead {
    background: linear-gradient(135deg, #090d16 0%, #111827 60%, #06241a 100%);
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 16px;
    color: #ffffff;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.08);
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
    gap: 12px;
  }

  .brand-logo-badge {
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, #10b981 0%, #06b6d4 100%);
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14pt;
    font-weight: 800;
    color: #ffffff;
    box-shadow: 0 2px 10px rgba(16, 185, 129, 0.35);
  }

  .brand-title {
    font-size: 16pt;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0;
    line-height: 1.1;
  }

  .brand-title .brand-accent {
    color: #10b981;
    text-shadow: 0 0 12px rgba(16, 185, 129, 0.4);
  }

  .brand-sub {
    font-size: 8pt;
    color: #94a3b8;
    font-weight: 500;
    letter-spacing: 0.3px;
    margin-top: 2px;
  }

  .meta-pills {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 8pt;
    color: #cbd5e1;
  }

  .meta-pills strong { color: #ffffff; }

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
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
    page-break-inside: avoid;
  }

  .portfolio-banner {
    padding: 12px 18px;
    color: #ffffff;
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
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 7.5pt;
    color: #64748b;
    margin-top: 4px;
  }

  .publisher-pill {
    background: #f1f5f9;
    padding: 2px 6px;
    border-radius: 3px;
    color: #475569;
    font-weight: 500;
  }

  .source-link-action {
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
</style>
</head>
<body>

<!-- Masthead -->
<div class="masthead">
  <div class="brand-row">
    <div class="brand-group">
      <div class="brand-logo-badge">&#9670;</div>
      <div>
        <h1 class="brand-title">VRIDDHI <span class="brand-accent">MONEY</span></h1>
        <div class="brand-sub">Equity Research Executive Intelligence Desk</div>
      </div>
    </div>
    <div class="meta-pills">
      <span><strong>Client:</strong> {{ analyst_name }}</span>
      <span>&bull;</span>
      <span><strong>Portfolios:</strong> {{ assigned_folders_str }}</span>
      <span>&bull;</span>
      <span>{{ date_str }}</span>
      <span>&bull;</span>
      <span style="color:#10b981;font-weight:700;">{{ total_items }} Stories ({{ total_filings }} Filings)</span>
    </div>
  </div>
</div>

<!-- 1. Executive Scorecard Table -->
{% if scorecard %}
<div class="section-heading">&#128200; Equity Research Morning Scorecard</div>
<div class="company-card" style="padding: 0; overflow: hidden; margin-bottom: 20px;">
  <table style="width: 100%; border-collapse: collapse; font-size: 8.5pt;">
    <thead>
      <tr style="background: #0f172a; color: #f8fafc; text-align: left; font-size: 7.5pt; text-transform: uppercase; letter-spacing: 0.5px;">
        <th style="padding: 10px 12px; width: 22%;">Company</th>
        <th style="padding: 10px 10px; width: 14%;">Portfolio</th>
        <th style="padding: 10px 12px; width: 38%;">Key Catalyst / Corporate Event</th>
        <th style="padding: 10px 10px; width: 16%;">Materiality</th>
        <th style="padding: 10px 12px; width: 10%; text-align: right;">Action</th>
      </tr>
    </thead>
    <tbody>
      {% for row in scorecard %}
      <tr style="border-bottom: 1px solid #f1f5f9; background: {{ '#ffffff' if loop.index % 2 == 1 else '#f8fafc' }};">
        <td style="padding: 10px 12px; font-weight: 800; color: #0f172a;">
          {{ row.company }}
        </td>
        <td style="padding: 10px 10px;">
          <span class="basket-pill-badge basket-pill-{{ row.theme }}">{{ row.portfolio }}</span>
        </td>
        <td style="padding: 10px 12px; color: #334155; line-height: 1.4;">
          <a href="{{ row.url }}" target="_blank" style="color: #0f172a; text-decoration: none; font-weight: 600;">{{ row.catalyst }}</a>
        </td>
        <td style="padding: 10px 10px;">
          {% if row.grade == 'Grade A' %}
          <span class="badge badge-grade-a">&#128293; Grade A &bull; Material</span>
          {% else %}
          <span class="badge badge-grade-b">Grade B &bull; Research</span>
          {% endif %}
        </td>
        <td style="padding: 10px 12px; text-align: right;">
          <a class="source-link-action" href="{{ row.url }}" target="_blank">Track &rarr;</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<!-- 2. Portfolio Baskets News & Filings -->
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

    template = Template(HTML_TEMPLATE)
    return template.render(
        analyst_name=analyst_name,
        assigned_folders_str=assigned_folders_str,
        date_str=date_str,
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


def get_clean_digest_filename(analyst_name: str, ext: str = ".pdf") -> str:
    """Format PDF filename as [Client_Name]_[Date].pdf."""
    now = datetime.now(IST)
    date_str = now.strftime("%Y-%m-%d")
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
        return pdf_file, html_content

    # 2. Attempt WeasyPrint if available
    try:
        import weasyprint  # type: ignore[import-untyped]
        weasyprint.HTML(string=html_content).write_pdf(str(pdf_file))
        return pdf_file, html_content
    except Exception as e:  # noqa: BLE001
        log.info("WeasyPrint direct compilation not active (%s); using HTML digest fallback", e)
        return html_file, html_content
