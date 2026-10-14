"""Gemini AI Materiality Filter and Institutional Research Summarizer."""
from __future__ import annotations

import json
import logging
import os

import requests

log = logging.getLogger(__name__)


def get_gemini_key() -> str:
    from dotenv import load_dotenv

    from .config import PROJECT_ROOT
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    return os.getenv("GEMINI_API_KEY", "").strip()


def is_gemini_active() -> bool:
    return bool(get_gemini_key())


PROMPT_TEMPLATE = """You are a senior institutional equity research analyst covering Indian stock markets.
Evaluate this news article for: {company_name}

Headline: {headline}
Content snippet: {summary}

Determine:
1. Is this a material event for equity research (earnings, regulatory/SEBI action, corporate disclosure, M&A, large order win, debt default, credit rating change, senior management change, capex)?
2. Or is it noise (generic market wrap like 'Sensex rises', clickbait broker tip, retail stock gossip, algorithm price update)?

Respond strictly in JSON format:
{{
  "is_material": true or false,
  "score": integer between 1 and 10 (1=spam/noise, 10=major earnings/regulatory action),
  "grade": "Grade A" (if score >= 8), "Grade B" (if score 6-7), or "Grade C" (if score < 6),
  "executive_summary": "Crisp 1-2 sentence institutional summary focusing on the financial/operational impact for {company_name}."
}}
"""


def evaluate_and_summarize(company_name: str, headline: str, summary: str = "") -> dict:
    """Evaluate article with Gemini AI. Falls back to heuristics if key is absent."""
    key = get_gemini_key()
    if not key:
        return {
            "is_material": True,
            "score": 6,
            "grade": "Grade B",
            "executive_summary": summary[:250] if summary else headline
        }

    prompt = PROMPT_TEMPLATE.format(
        company_name=company_name,
        headline=headline,
        summary=summary or "No additional snippet provided."
    )

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=8)
        if res.status_code == 200:
            data = res.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            return {
                "is_material": bool(parsed.get("is_material", True)),
                "score": int(parsed.get("score", 6)),
                "grade": parsed.get("grade", "Grade B"),
                "executive_summary": parsed.get("executive_summary", summary or headline)
            }
        else:
            log.warning("Gemini API returned status %s: %s", res.status_code, res.text[:200])
    except Exception as e:
        log.warning("Gemini evaluation error (%s); falling back to heuristic", e)

    return {
        "is_material": True,
        "score": 6,
        "grade": "Grade B",
        "executive_summary": summary[:250] if summary else headline
    }
