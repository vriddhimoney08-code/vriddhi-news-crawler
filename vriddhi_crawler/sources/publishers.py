"""Publisher sources: news sitemaps (every recent article), RSS feeds, and watched web pages
(company press pages, rating agencies, SEBI orders) where new links are reported."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urljoin

import feedparser

from ..controlpanel import Source
from ..http import Fetcher
from ..normalize import canonical_url, clean_text
from .base import RawItem, parse_date

log = logging.getLogger(__name__)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _keep(src: Source, url: str) -> bool:
    return not src.keep_pattern or re.search(src.keep_pattern, url or "", re.IGNORECASE) is not None


def _source_type(src: Source) -> str:
    n = src.name.lower()
    if any(k in n for k in ("crisil", "icra", "care rating", "careedge", "india ratings", "rating")):
        return "rating"
    return "press" if src.company else "news"


def read_sitemap(fetcher: Fetcher, src: Source, since: datetime, _depth: int = 0) -> list[RawItem]:
    """Reads a news sitemap, or a sitemap index pointing at several (newest children only)."""
    r = fetcher.get(src.url)
    root = ET.fromstring(r.content)
    out: list[RawItem] = []
    if _local(root.tag) == "sitemapindex":
        children = []
        for sm in root:
            loc = lastmod = None
            for el in sm:
                if _local(el.tag) == "loc":
                    loc = (el.text or "").strip()
                elif _local(el.tag) == "lastmod":
                    lastmod = parse_date(el.text)
            if loc:
                children.append((lastmod, loc))
        # child sitemaps updated since the last run (or the 3 newest when dates are missing)
        children.sort(key=lambda x: x[0] or datetime.min.replace(tzinfo=since.tzinfo), reverse=True)
        fresh = [c for c in children if c[0] and c[0] >= since] or children[:3]
        if _depth < 2:
            for _, loc in fresh[:10]:
                sub = Source(**{**src.__dict__, "url": loc})
                try:
                    out.extend(read_sitemap(fetcher, sub, since, _depth + 1))
                except Exception as e:  # one bad child should not lose the rest
                    log.warning("%s: child sitemap %s failed: %s", src.name, loc, e)
        return out
    for url_el in root:
        loc, title, pub, lang = None, "", None, src.language
        for el in url_el.iter():
            name = _local(el.tag)
            if name == "loc" and loc is None:
                loc = (el.text or "").strip()
            elif name == "title":
                title = clean_text(el.text)
            elif name == "publication_date":
                pub = parse_date(el.text)
            elif name == "lastmod" and pub is None:
                pub = parse_date(el.text)
            elif name == "language":
                lang = (el.text or lang).strip()
        if not loc or not _keep(src, loc):
            continue
        if not pub or pub < since:
            continue
        if not title:   # plain sitemap with no news:title: derive words from the address
            slug_part = loc.rstrip("/").rsplit("/", 1)[-1]
            title = re.sub(r"[-_]+", " ", re.sub(r"\.\w+$|\d{5,}", "", slug_part)).strip()
        if not title:
            continue
        out.append(RawItem(source_name=src.name, source_type=_source_type(src), title=title, url=loc,
                           published_at=pub, lang=lang, body_check=src.body_check))
    return out


def read_rss(fetcher: Fetcher, src: Source, since: datetime) -> list[RawItem]:
    r = fetcher.get(src.url)
    feed = feedparser.parse(r.content)
    if feed.bozo and not feed.entries:
        raise ValueError(f"unreadable feed: {feed.bozo_exception}")
    out = []
    for e in feed.entries:
        link = e.get("link")
        if not _keep(src, link):
            continue
        pub = parse_date(e.get("published") or e.get("updated"))
        if not pub or pub < since:
            continue
        title = clean_text(e.get("title"))
        if not title:
            continue
        out.append(RawItem(source_name=src.name, source_type=_source_type(src), title=title, url=link,
                           published_at=pub, summary=clean_text(e.get("summary"))[:1000], lang=src.language,
                           body_check=src.body_check))
    return out


_LINK = re.compile(r"<a\b[^>]*href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)


def read_page(fetcher: Fetcher, src: Source, seen_links: set[str] | None) -> tuple[list[RawItem], set[str]]:
    """Reports links that were not on the page last time. The first visit only records what is there."""
    r = fetcher.get(src.url)
    links: dict[str, str] = {}
    for href, text in _LINK.findall(r.text):
        url = urljoin(src.url, href.strip())
        if not url.startswith("http") or not _keep(src, url):
            continue
        label = clean_text(text)
        if len(label) < 8:      # skip icons, "Read more", page numbers
            continue
        links.setdefault(canonical_url(url), label)
    current = set(links)
    if seen_links is None:          # first visit: baseline only
        return [], current
    items = [RawItem(source_name=src.name, source_type=_source_type(src), title=links[u], url=u,
                     lang=src.language, body_check=False)
             for u in current - seen_links]
    return items, current | seen_links
