"""Company alias matching, full-text body inspection, and priority grading."""
from __future__ import annotations

import logging
import re
from collections.abc import Sequence

import trafilatura  # type: ignore[import-untyped]

from .controlpanel import Company
from .normalize import clean_text

log = logging.getLogger(__name__)

# Grade A: High-impact corporate/financial/regulatory events
GRADE_A_KEYWORDS = [
    r"\bearnings\b", r"\bresults\b", r"\bq[1-4]\b", r"\bprofit\b", r"\bloss\b",
    r"\brevenue\b", r"\bebitda\b", r"\bdividend\b", r"\bbonus\b", r"\bsplit\b",
    r"\bacquisition\b", r"\bmerger\b", r"\bbuyout\b", r"\bstake\b", r"\border win\b",
    r"\bcontract\b", r"\bpenalty\b", r"\bsebi\b", r"\bfraud\b", r"\braid\b",
    r"\bcbi\b", r"\bed\b", r"\bcfo\b", r"\bceo\b", r"\bresigns\b", r"\bdefault\b",
    r"\binsolvency\b", r"\bnclt\b", r"\bdisinvestment\b", r"\boffer for sale\b",
    r"\bipo\b", r"\blisting\b", r"\bboard meeting\b", r"\bfunding\b", r"\bvaluation\b",
]

# Grade B: Operational events, credit ratings, production, capex
GRADE_B_KEYWORDS = [
    r"\bexpansion\b", r"\bplant\b", r"\bfacility\b", r"\bcapex\b", r"\bvolumes\b",
    r"\bdeliveries\b", r"\blaunch\b", r"\bpartnership\b", r"\btie-?up\b", r"\brating\b",
    r"\bcrisil\b", r"\bicra\b", r"\bcareedge\b", r"\bindia ratings\b", r"\bupgrade\b",
    r"\bdowngrade\b", r"\btarget\b", r"\boutlook\b", r"\binvest\w*\b", r"\border\w*\b",
    r"\bcommissioning\b", r"\bmou\b", r"\bdeal\b", r"\bsolar\b", r"\binverter\b",
    r"\bserver\b", r"\bdatacenter\b", r"\bai\b", r"\bfleet\b", r"\bev\b", r"\bedtech\b",
    r"\blogistics\b", r"\bchemical\w*\b", r"\belectrolyte\b", r"\bshares?\b", r"\bstock\b",
]


class Matcher:
    """Matches raw news items against watchlist companies by scrip code, alias, or text."""

    def __init__(self, companies: Sequence[Company]):
        self.companies = list(companies)
        self.by_bse: dict[str, Company] = {}
        self.by_nse: dict[str, Company] = {}
        self._compiled_regexes: list[tuple[Company, list[re.Pattern]]] = []

        for c in self.companies:
            if c.bse_code:
                self.by_bse[c.bse_code.strip()] = c
            if c.nse_symbol:
                self.by_nse[c.nse_symbol.strip().upper()] = c

            patterns = []
            for name in c.all_names:
                escaped = re.escape(name.strip())
                # Require word boundaries for clean matching
                patterns.append(re.compile(rf"\b{escaped}\b", re.IGNORECASE))
            self._compiled_regexes.append((c, patterns))

    def match_text(self, text: str) -> list[Company]:
        """Match headline or body snippet against company names and aliases."""
        if not text:
            return []
        matched = []
        for company, patterns in self._compiled_regexes:
            if any(p.search(text) for p in patterns):
                matched.append(company)
        return matched

    def grade_story(self, title: str, summary: str = "", source_type: str = "news") -> str:
        """Assign Grade A (High), Grade B (Medium), or Grade C (General)."""
        if source_type in ("filing", "rating"):
            return "Grade A"

        combined = f"{title} {summary}".lower()
        if any(re.search(pat, combined) for pat in GRADE_A_KEYWORDS):
            return "Grade A"
        if any(re.search(pat, combined) for pat in GRADE_B_KEYWORDS):
            return "Grade B"
        return "Grade C"

    def extract_body_text(self, html_content: str | bytes) -> str:
        """Extract main readable article body using trafilatura."""
        try:
            extracted = trafilatura.extract(html_content, include_comments=False, include_tables=False)
            return clean_text(extracted or "")
        except Exception as e:  # noqa: BLE001
            log.debug("Trafilatura extraction failed: %s", e)
            return ""
