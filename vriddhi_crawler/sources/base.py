from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from dateutil import parser as dateparser  # type: ignore[import-untyped]

from ..config import IST


@dataclass
class RawItem:
    source_name: str
    source_type: str               # filing | news | rating | press | page
    title: str
    url: str | None = None
    published_at: datetime | None = None
    summary: str = ""
    lang: str = "en"
    filing_id: str | None = None   # exchange's own announcement id
    company_ids: list[str] = field(default_factory=list)   # set when the source already knows the company
    body_check: bool = False       # open the article page to look for companies not named in the headline


def parse_date(value, assume_ist: bool = False) -> datetime | None:
    """Parse any date string; times with no zone are taken as IST if assume_ist, else UTC."""
    if not value:
        return None
    try:
        parsed = dateparser.parse(str(value), dayfirst=False)
    except (ValueError, OverflowError, TypeError):
        return None
    if parsed is None:
        return None
    dt = parsed[0] if isinstance(parsed, tuple) else parsed
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST if assume_ist else timezone.utc)
    return dt.astimezone(timezone.utc)
