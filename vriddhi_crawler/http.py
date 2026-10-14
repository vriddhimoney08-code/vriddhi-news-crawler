"""Polite HTTP Fetcher with per-host rate limiting, robots.txt support, and custom User-Agent."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from .config import CRAWLER_CONTACT_EMAIL, PER_HOST_DELAY_SEC, RESPECT_ROBOTS

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8,hi;q=0.7",
}


class Fetcher:
    """HTTP client with per-domain rate limiting and polite backoff."""

    def __init__(self, default_delay: float = PER_HOST_DELAY_SEC, respect_robots: bool = RESPECT_ROBOTS):
        self.default_delay = default_delay
        self.respect_robots = respect_robots
        self._last_request_time: dict[str, float] = {}
        self._robots_cache: dict[str, RobotFileParser | None] = {}
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def _host(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _wait_for_host(self, host: str, delay: float | None = None):
        target_delay = self.default_delay if delay is None else delay
        last_time = self._last_request_time.get(host)
        if last_time is not None:
            elapsed = time.time() - last_time
            if elapsed < target_delay:
                time.sleep(target_delay - elapsed)
        self._last_request_time[host] = time.time()

    def _is_allowed_by_robots(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if not host:
            return True
        if host not in self._robots_cache:
            robots_url = f"{parsed.scheme}://{host}/robots.txt"
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                # 5-second quick fetch for robots.txt
                res = requests.get(robots_url, headers=DEFAULT_HEADERS, timeout=5)
                if res.status_code == 200:
                    rp.parse(res.text.splitlines())
                    self._robots_cache[host] = rp
                else:
                    self._robots_cache[host] = None
            except Exception:
                self._robots_cache[host] = None

        rp = self._robots_cache.get(host)
        if rp is None:
            return True
        try:
            return rp.can_fetch(DEFAULT_HEADERS["User-Agent"], url)
        except Exception:
            return True

    def get(
        self,
        url: str,
        params: dict | None = None,
        headers: dict | None = None,
        session: requests.Session | None = None,
        check_robots: bool = True,
        delay: float | None = None,
        timeout: int = 25,
    ) -> requests.Response:
        """Issue an HTTP GET with polite delay and robots check."""
        host = self._host(url)

        if check_robots and not self._is_allowed_by_robots(url):
            raise PermissionError(f"robots.txt disallows crawling: {url}")

        self._wait_for_host(host, delay)

        sess = session or self.session
        req_headers = dict(sess.headers)
        if headers:
            req_headers.update(headers)

        res = sess.get(url, params=params, headers=req_headers, timeout=timeout)
        res.raise_for_status()
        return res
