"""Executive PDF and HTML Digest Generator for Vriddhi Research Desk."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from .config import DIGESTS_DIR, IST

log = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;600&display=swap');

  @page {
    size: A4;
    margin: 14mm 14mm 14mm 14mm;
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
    gap: 8px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 6px 12px;
    border-radius: 20px;
    font-size: 8pt;
    color: #cbd5e1;
  }

  .meta-pills strong { color: #ffffff; }

  /* 2. Executive Highlights Box */
  .highlights-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #10b981;
    border-radius: 10px;
    padding: 14px 18px;
    margin-bottom: 18px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
  }

  .highlights-title {
    font-size: 9.5pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    color: #0f172a;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 8px;
  }

  .highlights-list {
    margin: 0;
    padding-left: 18px;
    font-size: 8.8pt;
    color: #334155;
    line-height: 1.55;
  }

  .highlights-list li {
    margin-bottom: 4px;
  }

  /* 3. Section Titles */
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

  /* 4. Company & Story Cards */
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

  /* 5. Modern Story Items */
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
    transition: color 0.15s;
  }

  .story-headline a:hover {
    color: #10b981;
    text-decoration: underline;
  }

  /* Materiality & Filing Badges */
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

  /* 6. Footer */
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
      <span><strong>Analyst:</strong> {{ analyst_name }}</span>
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
        <th style="padding: 10px 14px; width: 22%;">Company</th>
        <th style="padding: 10px 14px; width: 45%;">Key Catalyst / Corporate Event</th>
        <th style="padding: 10px 14px; width: 18%;">Materiality</th>
        <th style="padding: 10px 14px; width: 15%; text-align: right;">Action</th>
      </tr>
    </thead>
    <tbody>
      {% for row in scorecard %}
      <tr style="border-bottom: 1px solid #f1f5f9; background: {{ '#ffffff' if loop.index % 2 == 1 else '#f8fafc' }};">
        <td style="padding: 10px 14px; font-weight: 800; color: #0f172a;">
          {{ row.company }}
        </td>
        <td style="padding: 10px 14px; color: #334155; line-height: 1.4;">
          <a href="{{ row.url }}" target="_blank" style="color: #0f172a; text-decoration: none; font-weight: 600;">{{ row.catalyst }}</a>
        </td>
        <td style="padding: 10px 14px;">
          {% if row.grade == 'Grade A' %}
          <span class="badge badge-grade-a">&#128293; Grade A &bull; Material</span>
          {% else %}
          <span class="badge badge-grade-b">Grade B &bull; Research</span>
          {% endif %}
        </td>
        <td style="padding: 10px 14px; text-align: right;">
          <a class="source-link-action" href="{{ row.url }}" target="_blank">Track &rarr;</a>
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<!-- 2. Official Exchange Filings -->
{% if filings %}
<div class="section-heading">&#127963; Exchange Filings & Regulatory Disclosures</div>
<div class="company-card" style="border-left: 3px solid #7c3aed;">
  {% for item in filings %}
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

<!-- 2. Watchlist News By Company -->
<div class="section-heading">&#128202; Watchlist Corporate & Market Intelligence</div>
{% if not news_by_company %}
<div class="company-card" style="text-align: center; color: #64748b; font-style: italic; padding: 24px;">
  No new unsent news items for today. Sent ledger is clean!
</div>
{% endif %}

{% for company_name, items in news_by_company.items() %}
<div class="company-card">
  <div class="company-header">
    <div class="company-name">
      <span>{{ company_name }}</span>
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

<div class="doc-footer">
  CONFIDENTIAL &bull; VRIDDHI MONEY INSTITUTIONAL RESEARCH DESK &bull; PROPRIETARY NEVER-RESEND LEDGER PROTECTED
</div>

</body>
</html>
"""


def render_digest_html(analyst_name: str, stories: list[dict], date_str: str | None = None) -> str:
    """Render the HTML digest for the given analyst and stories."""
    from jinja2 import Template  # type: ignore

    if not date_str:
        date_str = datetime.now(IST).strftime("%d %b %Y")

    filings = []
    news_by_company: dict[str, list[dict]] = {}

    for s in stories:
        item = dict(s)
        # Format time
        try:
            raw_pub = str(item.get("published_at") or "")
            dt = datetime.fromisoformat(raw_pub).astimezone(IST)
            item["published_formatted"] = dt.strftime("%I:%M %p")
        except (ValueError, TypeError):
            item["published_formatted"] = ""

        if item.get("source_type") == "filing":
            filings.append(item)
        else:
            cname = item.get("company_name", "General")
            news_by_company.setdefault(cname, []).append(item)

    # Build Executive Scorecard list for the morning matrix table
    scorecard = []
    for f in filings:
        scorecard.append({
            "company": f.get("company_name", "Company"),
            "catalyst": f.get("title", ""),
            "grade": "Grade A",
            "url": f.get("url", "#"),
        })

    for cname, items in news_by_company.items():
        if items:
            top = items[0]
            scorecard.append({
                "company": cname,
                "catalyst": top.get("title", ""),
                "grade": top.get("grade", "Grade B"),
                "url": top.get("url", "#"),
            })

    template = Template(HTML_TEMPLATE)
    return template.render(
        analyst_name=analyst_name,
        date_str=date_str,
        total_items=len(stories),
        total_filings=len(filings),
        filings=filings,
        scorecard=scorecard,
        news_by_company=news_by_company,
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


def generate_analyst_digest(analyst_id: str, analyst_name: str, stories: list[dict]) -> tuple[Path, str]:
    """Generate both an HTML digest and a high-definition PDF rendering with unique timestamps."""
    import shutil
    now = datetime.now(IST)
    today_str = now.strftime("%Y%m%d")
    ts = now.strftime("%H%M%S")
    html_content = render_digest_html(analyst_name, stories)

    # Unique timestamped filename prevents Meta/WhatsApp media server from caching old documents
    html_file = DIGESTS_DIR / f"{analyst_id}_{today_str}_{ts}.html"
    html_file.write_text(html_content, encoding="utf-8")

    # Also keep standard un-timestamped file updated
    latest_html = DIGESTS_DIR / f"{analyst_id}_{today_str}.html"
    latest_html.write_text(html_content, encoding="utf-8")

    pdf_file = DIGESTS_DIR / f"{analyst_id}_{today_str}_{ts}.pdf"

    # 1. Try native browser headless print-to-pdf (produces clean vector PDF)
    if generate_pdf_via_browser(html_file, pdf_file):
        log.info("Compiled fresh PDF via native browser: %s (size: %s bytes)", pdf_file, pdf_file.stat().st_size)
        latest_pdf = DIGESTS_DIR / f"{analyst_id}_{today_str}.pdf"
        try:
            shutil.copyfile(pdf_file, latest_pdf)
        except Exception:
            pass
        return pdf_file, html_content

    # 2. Attempt WeasyPrint if available
    try:
        import weasyprint  # type: ignore[import-untyped]
        weasyprint.HTML(string=html_content).write_pdf(str(pdf_file))
        latest_pdf = DIGESTS_DIR / f"{analyst_id}_{today_str}.pdf"
        try:
            shutil.copyfile(pdf_file, latest_pdf)
        except Exception:
            pass
        return pdf_file, html_content
    except Exception as e:  # noqa: BLE001
        log.info("WeasyPrint direct compilation not active (%s); using HTML digest fallback", e)
        return html_file, html_content
