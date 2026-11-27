"""Tests for the isolated Custom Web News Tracker ('News' tab)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from vriddhi_crawler import db, server
from vriddhi_crawler.sources.custom_news import (
    _build_search_query,
    _extract_rss_snippet,
    _unwrap_bing_url,
    deduplicate_custom_articles,
    fetch_bing_news_for_topic,
    fetch_gdelt_news_for_topic,
    fetch_google_news_for_topic,
    fetch_yahoo_news_for_topic,
    is_paid_or_paywalled_news,
    is_relevant_to_topic,
    match_data_sources_for_topic,
    preload_data_sources_rss,
)


def _build_rss(items: list[dict]) -> bytes:
    """Build a realistic Google News RSS XML payload."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel><title>Google News</title>',
    ]
    for it in items:
        pub_rfc = format_datetime(it["pub_dt"])
        parts.append(
            f"<item>"
            f"<title>{it['title']}</title>"
            f"<link>{it['link']}</link>"
            f"<pubDate>{pub_rfc}</pubDate>"
            f"<description><![CDATA[{it.get('description', '')}]]></description>"
            f"<source url=\"https://example.com\">{it['publisher']}</source>"
            f"</item>"
        )
    parts.append("</channel></rss>")
    return "".join(parts).encode("utf-8")


def test_snippet_cleanup_drops_headline_duplicate():
    title = "Nvidia unveils next-gen Rubin AI chips"
    dup_desc = '<a href="https://news.google.com/rss/articles/1">Nvidia unveils next-gen Rubin AI chips - TechCrunch</a>&nbsp;&nbsp;<font color="#6f6f6f">TechCrunch</font>'
    assert _extract_rss_snippet(dup_desc, title, "TechCrunch") == ""

    rich_desc = "Nvidia unveils next-gen Rubin AI chips. Analysts expect data center revenue to accelerate sharply in FY27."
    cleaned = _extract_rss_snippet(rich_desc, title, "TechCrunch")
    assert "Analysts expect data center revenue" in cleaned


def test_fetch_google_news_for_topic_open_web_and_time_windows():
    now = datetime.now(timezone.utc)
    rss_xml = _build_rss([
        {
            "title": "Nvidia launches open-source robotics model - TechCrunch",
            "link": "https://news.google.com/rss/articles/art-1",
            "pub_dt": now - timedelta(hours=3),
            "publisher": "TechCrunch",
            "description": "Nvidia introduces new robotics stack for global manufacturers and developers.",
        },
        {
            "title": "Nvidia supplier expands India R&D hub - Economic Times",
            "link": "https://news.google.com/rss/articles/art-2",
            "pub_dt": now - timedelta(hours=36),
            "publisher": "The Economic Times",
            "description": "Expansion adds 2,000 engineering roles across Bengaluru and Pune.",
        },
        {
            "title": "Nvidia partners with European lab - BBC News",
            "link": "https://news.google.com/rss/articles/art-3",
            "pub_dt": now - timedelta(days=5),
            "publisher": "BBC News",
            "description": "Joint research initiative focuses on climate supercomputing models.",
        },
        {
            "title": "Nvidia announces quarterly data center beat - CNBC-TV18",
            "link": "https://news.google.com/rss/articles/art-4",
            "pub_dt": now - timedelta(days=20),
            "publisher": "CNBC-TV18",
            "description": "Within 1M window.",
        },
        {
            "title": "Nvidia signs sovereign AI cloud partnership in Mumbai - Livemint",
            "link": "https://news.google.com/rss/articles/art-5",
            "pub_dt": now - timedelta(days=120),
            "publisher": "Livemint",
            "description": "Within 6M window.",
        },
        {
            "title": "Nvidia opens Taiwan design facility - TechCrunch",
            "link": "https://news.google.com/rss/articles/art-6",
            "pub_dt": now - timedelta(days=280),
            "publisher": "TechCrunch",
            "description": "Within 1 Year window.",
        },
        {
            "title": "Nvidia legacy archive release - BBC News",
            "link": "https://news.google.com/rss/articles/art-7",
            "pub_dt": now - timedelta(days=400),
            "publisher": "BBC News",
            "description": "Outside 1 Year window.",
        },
    ])

    mock_fetcher = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = rss_xml
    mock_fetcher.get.return_value = mock_resp

    # 24h window -> only the 3h-old TechCrunch (non-financial open-web!) article
    items_24h, err = fetch_google_news_for_topic("nvidia", "Nvidia", hours=24, scope="all", fetcher=mock_fetcher)
    assert err is None
    assert len(items_24h) == 1
    assert items_24h[0]["publisher"] == "TechCrunch"
    assert "when%3A1d" in mock_fetcher.get.call_args[0][0]

    # 48h window -> 3h + 36h articles
    items_48h, err = fetch_google_news_for_topic("nvidia", "Nvidia", hours=48, scope="all", fetcher=mock_fetcher)
    assert err is None
    assert len(items_48h) == 2
    assert "when%3A2d" in mock_fetcher.get.call_args[0][0]

    # 1M (720h / 30d) window -> 3h + 36h + 5d + 20d articles
    items_1m, err = fetch_google_news_for_topic("nvidia", "Nvidia", hours=720, scope="all", fetcher=mock_fetcher)
    assert err is None
    assert len(items_1m) == 4
    assert "after%3A" in mock_fetcher.get.call_args[0][0]

    # 6M (4320h / 180d) window -> adds 120d article and issues both full & older-half date slices
    mock_fetcher.get.reset_mock()
    items_6m, err = fetch_google_news_for_topic("nvidia", "Nvidia", hours=4320, scope="all", fetcher=mock_fetcher)
    assert err is None
    assert len(items_6m) == 5
    urls_6m = [c[0][0] for c in mock_fetcher.get.call_args_list]
    assert len(urls_6m) == 2
    assert "after%3A" in urls_6m[0] and "before%3A" not in urls_6m[0]
    assert "after%3A" in urls_6m[1] and "before%3A" in urls_6m[1]

    # 1 Year (8760h / 365d) window -> adds 280d article (excludes 400d old) and uses 2 date slices
    mock_fetcher.get.reset_mock()
    items_1y, err = fetch_google_news_for_topic("nvidia", "Nvidia", hours=8760, scope="all", fetcher=mock_fetcher)
    assert err is None
    assert len(items_1y) == 6
    urls_1y = [c[0][0] for c in mock_fetcher.get.call_args_list]
    assert len(urls_1y) == 2
    assert "after%3A" in urls_1y[0] and "before%3A" not in urls_1y[0]
    assert "after%3A" in urls_1y[1] and "before%3A" in urls_1y[1]


def test_db_persistence_and_isolation_from_watchlist(tmp_path: Path):
    test_db = tmp_path / "custom_news_test.db"
    db.init_db(db_path=test_db, seed_defaults=False)

    # Save multiple topics with case-insensitive duplicate
    res = db.add_custom_news_topics(["Tata Motors", "Nvidia", "tata motors", "  "], db_path=test_db)
    assert len(res["added"]) == 2
    assert res["skipped"] == ["tata motors"]
    assert len(res["topics"]) == 2

    # Confirm total isolation: companies, stories, and sent_ledger remain untouched
    conn = db.get_connection(test_db)
    try:
        assert conn.execute("SELECT count(*) FROM companies").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM stories").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM sent_ledger").fetchone()[0] == 0
    finally:
        conn.close()

    # Insertion order is preserved (Tata Motors first, Nvidia second)
    assert [t["id"] for t in res["topics"]] == ["tata-motors", "nvidia"]

    now = datetime.now(timezone.utc)
    db.save_custom_news_articles(
        "nvidia",
        "Nvidia",
        [
            {
                "id": "a1",
                "title": "Nvidia 24h story",
                "summary": "Fresh update",
                "publisher": "TechCrunch",
                "url": "https://techcrunch.com/nvidia-1",
                "published_at": (now - timedelta(hours=4)).isoformat(),
            },
            {
                "id": "a2",
                "title": "Nvidia 48h financial story",
                "summary": "Market update",
                "publisher": "The Economic Times",
                "url": "https://economictimes.indiatimes.com/nvidia-2",
                "published_at": (now - timedelta(hours=30)).isoformat(),
            },
            {
                "id": "a3",
                "title": "Nvidia 1 week story",
                "summary": "Weekly update",
                "publisher": "BBC News",
                "url": "https://bbc.com/nvidia-3",
                "published_at": (now - timedelta(days=5)).isoformat(),
            },
            {
                "id": "a4",
                "title": "Nvidia 1 month story",
                "summary": "Monthly update",
                "publisher": "CNBC-TV18",
                "url": "https://cnbctv18.com/nvidia-4",
                "published_at": (now - timedelta(days=20)).isoformat(),
            },
            {
                "id": "a5",
                "title": "Nvidia 6 month story",
                "summary": "Half-year update",
                "publisher": "TechCrunch",
                "url": "https://techcrunch.com/nvidia-5",
                "published_at": (now - timedelta(days=140)).isoformat(),
            },
            {
                "id": "a6",
                "title": "Nvidia 1 year story",
                "summary": "Annual update",
                "publisher": "Livemint",
                "url": "https://livemint.com/nvidia-6",
                "published_at": (now - timedelta(days=300)).isoformat(),
            },
        ],
        fetched_hours=8760,
        db_path=test_db,
    )

    state_24 = db.get_custom_news_state(hours=24, scope="all", db_path=test_db)
    assert state_24["total_articles"] == 1
    nvidia_24 = next(g for g in state_24["groups"] if g["topic_id"] == "nvidia")
    assert nvidia_24["articles"][0]["published_ist"].endswith("IST")

    state_48 = db.get_custom_news_state(hours=48, scope="all", db_path=test_db)
    assert state_48["total_articles"] == 2

    state_48_fin = db.get_custom_news_state(hours=48, scope="financial", db_path=test_db)
    assert state_48_fin["total_articles"] == 1
    nvidia_48_fin = next(g for g in state_48_fin["groups"] if g["topic_id"] == "nvidia")
    assert nvidia_48_fin["articles"][0]["publisher"] == "The Economic Times"

    state_1m = db.get_custom_news_state(hours=720, scope="all", db_path=test_db)
    assert state_1m["total_articles"] == 4

    state_6m = db.get_custom_news_state(hours=4320, scope="all", db_path=test_db)
    assert state_6m["total_articles"] == 5

    state_1y = db.get_custom_news_state(hours=8760, scope="all", db_path=test_db)
    assert state_1y["total_articles"] == 6

    # Deleting a topic removes its cached articles as well
    assert db.delete_custom_news_topic("nvidia", db_path=test_db) is True
    after_del = db.get_custom_news_state(hours=8760, db_path=test_db)
    assert len(after_del["topics"]) == 1
    assert after_del["total_articles"] == 0


def test_fastapi_custom_news_endpoints_and_ui_placement(tmp_path: Path, monkeypatch):
    test_db = tmp_path / "api_test.db"
    db.init_db(db_path=test_db, seed_defaults=False)

    # Point DB helpers used by server endpoints at isolated temp DB
    monkeypatch.setattr(db, "DB_PATH", test_db)
    monkeypatch.setattr(server, "get_custom_news_topics", lambda: db.get_custom_news_topics(test_db))
    monkeypatch.setattr(server, "add_custom_news_topics", lambda names: db.add_custom_news_topics(names, test_db))
    monkeypatch.setattr(server, "set_custom_news_topic_selected", lambda tid, sel: db.set_custom_news_topic_selected(tid, sel, test_db))
    monkeypatch.setattr(server, "set_all_custom_news_topics_selected", lambda sel: db.set_all_custom_news_topics_selected(sel, test_db))
    monkeypatch.setattr(server, "delete_custom_news_topic", lambda tid: db.delete_custom_news_topic(tid, test_db))
    monkeypatch.setattr(server, "save_custom_news_articles", lambda tid, tname, arts, fetched_hours=24: db.save_custom_news_articles(tid, tname, arts, fetched_hours=fetched_hours, db_path=test_db))
    monkeypatch.setattr(server, "get_custom_news_state", lambda hours=24, topic_ids=None, search=None, scope="all": db.get_custom_news_state(hours=hours, topic_ids=topic_ids, search=search, scope=scope, db_path=test_db))

    now = datetime.now(timezone.utc)

    def fake_batch(topics, hours=24, scope="all", max_per_topic=40):
        res = {}
        total = 0
        for t in topics:
            items = [
                {
                    "id": f"{t['id']}-1",
                    "topic_id": t["id"],
                    "topic_name": t["name"],
                    "title": f"{t['name']} announces major expansion",
                    "summary": "Expansion covers new product lines across India.",
                    "publisher": "Tech News Daily",
                    "url": f"https://example.com/{t['id']}/1",
                    "published_at": (now - timedelta(hours=2)).isoformat(),
                }
            ]
            res[t["id"]] = items
            total += len(items)
        return {"results_by_topic": res, "total_found": total, "errors": []}

    import vriddhi_crawler.sources.custom_news as cn_mod
    monkeypatch.setattr(cn_mod, "fetch_google_news_batch", fake_batch)

    client = TestClient(server.app)

    # 1. Verify HTML sidebar places News directly after Portfolios & Watchlist and before Clients & Subscribers
    html = client.get("/").text
    pos_watchlist = html.index('data-view="view-watchlist"')
    pos_news = html.index('data-view="view-custom-news"')
    pos_clients = html.index('data-view="view-analysts"')
    assert pos_watchlist < pos_news < pos_clients

    # 2. Save multiple comma-separated names
    r_add = client.post("/api/custom-news/topics", json={"raw_input": "Reliance Industries, OpenAI"})
    assert r_add.status_code == 200
    assert len(r_add.json()["added"]) == 2

    # 3. Fetch live news (mocked) and verify grouped persistence
    r_fetch = client.post("/api/custom-news/fetch", json={"hours": 24, "scope": "all"})
    assert r_fetch.status_code == 200
    body = r_fetch.json()
    assert body["total_articles"] == 2
    assert len(body["groups"]) == 2
    assert body["fetch_summary"]["total_found"] == 2

    # 4. Re-query GET /api/custom-news (simulating reopening the tab) -> persisted articles returned
    r_get = client.get("/api/custom-news?hours=24")
    assert r_get.status_code == 200
    assert r_get.json()["total_articles"] == 2

    # 5. Toggle selection on one topic and verify filtering
    r_patch = client.patch("/api/custom-news/topics/openai", json={"is_selected": False})
    assert r_patch.status_code == 200
    r_filtered = client.get("/api/custom-news?hours=24").json()
    assert len(r_filtered["groups"]) == 1
    assert r_filtered["groups"][0]["topic_id"] == "reliance-industries"

    # 6. Delete topic
    r_del = client.delete("/api/custom-news/topics/openai")
    assert r_del.status_code == 200
    assert len(client.get("/api/custom-news?hours=24").json()["topics"]) == 1


def test_multi_engine_fetchers_and_cross_source_deduplication(tmp_path: Path):
    now = datetime.now(timezone.utc)

    # 1. Bing redirect unwrapping
    bing_link = "https://www.bing.com/news/apiclick.aspx?ref=FexRss&url=https%3A%2F%2Fwww.livemint.com%2Fcompanies%2Ftata-ev-launch.html"
    assert _unwrap_bing_url(bing_link) == "https://www.livemint.com/companies/tata-ev-launch.html"

    # 2. Bing News RSS parsing
    bing_rss = _build_rss([
        {
            "title": "Tata Motors launches Sierra EV in India - Livemint",
            "link": bing_link,
            "pub_dt": now - timedelta(hours=2),
            "publisher": "Livemint",
            "description": "Tata Motors unveiled the Sierra EV with a 550km range across major Indian cities.",
        }
    ])
    mock_bing_resp = MagicMock(content=bing_rss)
    bing_items, err = fetch_bing_news_for_topic("tata-motors", "Tata Motors", hours=24, http_get=lambda *a, **kw: mock_bing_resp)
    assert err is None and len(bing_items) == 1
    assert bing_items[0]["source_engine"] == "Bing News"
    assert bing_items[0]["url"] == "https://www.livemint.com/companies/tata-ev-launch.html"

    # 3. Yahoo News RSS parsing
    yahoo_rss = _build_rss([
        {
            "title": "Tata Motors unveils new Sierra EV in India",
            "link": "https://www.livemint.com/companies/tata-ev-launch.html?utm_source=yahoo",
            "pub_dt": now - timedelta(hours=3),
            "publisher": "Livemint",
            "description": "Short stub.",
        },
        {
            "title": "Tata Motors expands Gujarat battery plant capacity",
            "link": "https://www.ndtvprofit.com/business/autos/tata-gujarat-battery",
            "pub_dt": now - timedelta(hours=4),
            "publisher": "NDTV Profit",
            "description": "New battery pack line targets 150,000 units per year.",
        },
    ])
    mock_yahoo_resp = MagicMock(content=yahoo_rss)
    yahoo_items, err = fetch_yahoo_news_for_topic("tata-motors", "Tata Motors", hours=24, http_get=lambda *a, **kw: mock_yahoo_resp)
    assert err is None and len(yahoo_items) == 2
    assert yahoo_items[0]["source_engine"] == "Yahoo News"

    # 4. GDELT JSON parsing
    gdelt_payload = {
        "articles": [
            {
                "title": "Tata Motors partners with European charging network",
                "url": "https://techcrunch.com/2026/11/tata-charging-network",
                "seendate": (now - timedelta(hours=5)).strftime("%Y%m%dT%H%M%SZ"),
                "domain": "techcrunch.com",
            }
        ]
    }
    mock_gdelt_resp = MagicMock(text='{"articles": []}')
    mock_gdelt_resp.json.return_value = gdelt_payload
    gdelt_items, err = fetch_gdelt_news_for_topic("tata-motors", "Tata Motors", hours=24, http_get=lambda *a, **kw: mock_gdelt_resp)
    assert err is None and len(gdelt_items) == 1
    assert gdelt_items[0]["source_engine"] == "GDELT"
    assert gdelt_items[0]["publisher"] == "TechCrunch"

    # 5. Read-only Data Sources RSS whole-word keyword matching (no false partial match!)
    ds_rss = _build_rss([
        {
            "title": "RBI keeps repo rate unchanged in November review",
            "link": "https://economictimes.indiatimes.com/rbi-repo-rate",
            "pub_dt": now - timedelta(hours=1),
            "publisher": "Economic Times",
            "description": "Central bank maintains neutral policy stance.",
        },
        {
            "title": "Space startup completes orbital satellite test",
            "link": "https://economictimes.indiatimes.com/orbital-test",
            "pub_dt": now - timedelta(hours=1),
            "publisher": "Economic Times",
            "description": "Low-earth orbital launch succeeds.",
        },
    ])
    mock_ds_resp = MagicMock(content=ds_rss)
    preloaded = preload_data_sources_rss(
        [{"name": "Economic Times Markets RSS", "url": "https://economictimes.indiatimes.com/rss", "type": "rss", "is_active": 1}],
        hours=24,
        http_get=lambda *a, **kw: mock_ds_resp,
    )
    rbi_matches = match_data_sources_for_topic("rbi", "RBI", preloaded)
    assert len(rbi_matches) == 1
    assert "repo rate" in rbi_matches[0]["title"].lower()
    assert rbi_matches[0]["source_engine"] == "Data Sources"

    # 6. Cross-source deduplication merges Google + Bing + Yahoo duplicates into 1 best copy
    google_dup = {
        "id": "g-dup",
        "topic_id": "tata-motors",
        "topic_name": "Tata Motors",
        "title": "Tata Motors launches Sierra EV in India",
        "summary": "",
        "publisher": "Livemint",
        "source_engine": "Google News",
        "url": "https://news.google.com/rss/articles/CBMiRedirectStub",
        "published_at": (now - timedelta(hours=2)).isoformat(),
    }
    combined = [google_dup] + bing_items + yahoo_items + gdelt_items
    unique, dups = deduplicate_custom_articles(combined)
    # 5 raw items -> 3 unique stories (Sierra EV merged across Google/Bing/Yahoo, Gujarat plant, Charging network)
    assert len(unique) == 3
    assert dups == 2
    sierra = next(a for a in unique if "Sierra EV" in a["title"])
    # Direct Livemint URL + richer Bing summary must beat the Google redirect stub
    assert sierra["url"] == "https://www.livemint.com/companies/tata-ev-launch.html"
    assert "550km" in sierra["summary"]

    # 7. SQLite cross-fetch deduplication: saving Google stub first, then Bing direct copy upgrades in-place (no duplicate!)
    test_db = tmp_path / "dedup_test.db"
    db.init_db(db_path=test_db, seed_defaults=False)
    db.add_custom_news_topics(["Tata Motors"], db_path=test_db)
    db.save_custom_news_articles("tata-motors", "Tata Motors", [google_dup], fetched_hours=24, db_path=test_db)
    db.save_custom_news_articles("tata-motors", "Tata Motors", bing_items, fetched_hours=24, db_path=test_db)
    st = db.get_custom_news_state(hours=24, db_path=test_db)
    assert st["total_articles"] == 1
    stored = st["groups"][0]["articles"][0]
    assert stored["url"] == "https://www.livemint.com/companies/tata-ev-launch.html"
    assert "550km" in stored["summary"]
    assert stored["source_engine"] == "Bing News"


def test_paid_and_paywalled_news_filtered_out(tmp_path: Path):
    # Hard-paywalled publishers and paid tiers must be blocked
    assert is_paid_or_paywalled_news("Reliance Q3 review", "Bloomberg", "https://news.google.com/rss/articles/1") is True
    assert is_paid_or_paywalled_news("India EV shift", "Financial Times", "https://www.ft.com/content/abc") is True
    assert is_paid_or_paywalled_news("Deep dive on Tata", "The Ken", "https://the-ken.com/story/tata") is True
    assert is_paid_or_paywalled_news("ETPrime analysis", "The Economic Times", "https://economictimes.indiatimes.com/prime/money/article") is True
    assert is_paid_or_paywalled_news("Mint Premium take", "Livemint", "https://www.livemint.com/mint-premium/story-123") is True
    assert is_paid_or_paywalled_news("Stock call", "Moneycontrol Pro", "https://news.google.com/rss/articles/2") is True
    assert is_paid_or_paywalled_news("Analysis [Premium]", "Business Standard", "https://www.business-standard.com/article") is True

    # Regular free articles from Indian & global publishers must stay allowed!
    assert is_paid_or_paywalled_news("Tata Motors Q3 revenue grows 12%", "The Economic Times", "https://economictimes.indiatimes.com/markets/stocks/news/tata-q3") is False
    assert is_paid_or_paywalled_news("RBI holds repo rate steady", "Times of India", "https://timesofindia.indiatimes.com/business/india-business/rbi") is False
    assert is_paid_or_paywalled_news("Infosys wins cloud contract", "Hindustan Times", "https://www.hindustantimes.com/business/infosys") is False
    assert is_paid_or_paywalled_news("Nvidia unveils new GPU", "TechCrunch", "https://techcrunch.com/2026/11/nvidia-gpu") is False
    assert is_paid_or_paywalled_news("Sensex ends higher on banking rally", "Livemint", "https://www.livemint.com/market/stock-market-news/sensex") is False
    assert is_paid_or_paywalled_news("HDFC Bank deposits up 15%", "Moneycontrol", "https://www.moneycontrol.com/news/business/hdfc-bank") is False

    # Already-cached paywalled rows in SQLite are automatically hidden & pruned on read
    test_db = tmp_path / "paywall_prune.db"
    db.init_db(db_path=test_db, seed_defaults=False)
    db.add_custom_news_topics(["Nvidia"], db_path=test_db)
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = db.get_connection(test_db)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO custom_news_articles (id, topic_id, topic_name, title, summary, publisher, source_engine, url, published_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("paid-1", "nvidia", "Nvidia", "Nvidia AI chip boom", "", "Bloomberg", "Google News", "https://www.bloomberg.com/news/nvidia", now_iso, now_iso),
            )
            conn.execute(
                """
                INSERT INTO custom_news_articles (id, topic_id, topic_name, title, summary, publisher, source_engine, url, published_at, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("free-1", "nvidia", "Nvidia", "Nvidia launches open-source model", "Free story", "TechCrunch", "Bing News", "https://techcrunch.com/nvidia-open", now_iso, now_iso),
            )
    finally:
        conn.close()

    st = db.get_custom_news_state(hours=24, db_path=test_db)
    assert st["total_articles"] == 1
    assert st["groups"][0]["articles"][0]["id"] == "free-1"

    # Reuters login-wall is also blocked in News tab
    assert is_paid_or_paywalled_news("Basecamp funding", "Reuters", "https://www.reuters.com/legal/basecamp") is True

    # Smart query builder: strips trailing vehicle suffixes without rigid exact quotes
    assert _build_search_query("Catalio Capital Fund") == "Catalio Capital"
    assert _build_search_query("Greysky Capital PMS") == "Greysky Capital"
    assert _build_search_query("Morphosis Fund") == "Morphosis (Fund OR Capital)"
    assert _build_search_query("Morphosis Fund", allow_or=False) == "Morphosis Fund"
    assert _build_search_query("Tata Motors") == "Tata Motors"
    assert _build_search_query("Nvidia") == "Nvidia"
    assert _build_search_query('"Exact Phrase"') == '"Exact Phrase"'

    # Topic relevance filter blocks off-topic generic matches (e.g. Basecamp under Catalio Capital Fund, Tata Steel under Tata Motors)
    assert is_relevant_to_topic(
        "Catalio Capital Fund",
        "AI-based drug developer Basecamp valued at $800 million after $140 million funding round",
        "Drug discovery startup raises new capital.",
        "https://example.com/basecamp-funding",
    ) is False
    assert is_relevant_to_topic(
        "Catalio Capital Fund",
        "Catalio Capital Management closes $400 million life sciences fund",
        "New fund targets biotech startups.",
    ) is True
    assert is_relevant_to_topic("Greysky Capital PMS", "Greysky Capital launches new India equity strategy", "") is True
    assert is_relevant_to_topic("Greysky Capital PMS", "Wayne Gretzky congratulates NHL star in Capitals locker room", "") is False
    assert is_relevant_to_topic("Tata Motors", "Tata Steel Q3 net profit surges 20%", "") is False
    assert is_relevant_to_topic("Tata Motors", "Tata Motors unveils Sierra EV", "") is True


def test_news_schedule_client_assignment_and_pdf_template(tmp_path: Path):
    from vriddhi_crawler.controlpanel import Analyst
    from vriddhi_crawler.pdf import render_news_digest_html

    test_db = tmp_path / "news_digest_test.db"
    db.init_db(db_path=test_db, seed_defaults=False)

    # 1. Editable schedule time + window persistence
    sched_default = db.get_custom_news_schedule(db_path=test_db)
    assert sched_default["dispatch_time"] == "11:00"
    assert sched_default["window_hours"] == 24

    sched_updated = db.save_custom_news_schedule(
        dispatch_time="14:45",
        dispatch_active=True,
        window_hours=4320,
        interakt_template="vriddhi_custom_news_01",
        db_path=test_db,
    )
    assert sched_updated["dispatch_time"] == "14:45"
    assert sched_updated["dispatch_time_12h"] == "02:45 PM"
    assert sched_updated["window_hours"] == 4320
    assert sched_updated["window_label"] == "Last 6M"
    assert sched_updated["interakt_template"] == "vriddhi_custom_news_01"

    # 2. Save topics & assign selectively to client (default is empty!)
    db.add_custom_news_topics(["Catalio Capital Fund", "Greysky Capital PMS", "Morphosis Fund"], db_path=test_db)

    client_unassigned = Analyst(id="bob", name="Bob", phone="9811111111")
    db.save_analyst(client_unassigned, db_path=test_db)
    fetched_analysts = {a.id: a for a in db.get_analysts(db_path=test_db)}
    assert fetched_analysts["bob"].assigned_news_topics == []

    client_assigned = Analyst(
        id="aashish",
        name="Aashish",
        phone="9822222222",
        assigned_news_topics=["catalio-capital-fund", "greysky-capital-pms"],
    )
    db.save_analyst(client_assigned, db_path=test_db)

    # Add 1 article from 3 days ago for Catalio, and 0 articles for Greysky
    now = datetime.now(timezone.utc)
    db.save_custom_news_articles(
        "catalio-capital-fund",
        "Catalio Capital Fund",
        [
            {
                "id": "cat-1",
                "title": "Catalio Capital Management closes $400M biotech fund",
                "summary": "New biotech vehicle backs early-stage therapeutics.",
                "publisher": "Livemint",
                "source_engine": "Bing News",
                "url": "https://www.livemint.com/catalio-400m",
                "published_at": (now - timedelta(days=3)).isoformat(),
            }
        ],
        fetched_hours=4320,
        db_path=test_db,
    )

    # 3. With saved 6M window: Catalio has 1 article, Greysky has 0 -> BOTH appear in PDF!
    digest_6m = db.get_custom_news_digest_for_analyst("aashish", db_path=test_db)
    assert digest_6m["hours"] == 4320
    assert digest_6m["total_articles"] == 1
    assert len(digest_6m["topic_groups"]) == 2
    html_6m = render_news_digest_html("Aashish", "aashish", digest_6m, group_logo_b64="")
    assert "Catalio Capital Management closes $400M biotech fund" in html_6m
    assert "No news from this topic" in html_6m

    # Calling again next day still returns the same 6M article (no sent-ledger blocking!)
    digest_6m_repeat = db.get_custom_news_digest_for_analyst("aashish", db_path=test_db)
    assert digest_6m_repeat["total_articles"] == 1

    # 4. Switching saved window to 24 hrs -> 0 articles for both topics, PDF STILL renders 'No news from this topic'
    db.save_custom_news_schedule(window_hours=24, db_path=test_db)
    digest_24h = db.get_custom_news_digest_for_analyst("aashish", db_path=test_db)
    assert digest_24h["hours"] == 24
    assert digest_24h["total_articles"] == 0
    assert len(digest_24h["topic_groups"]) == 2
    html_24h = render_news_digest_html("Aashish", "aashish", digest_24h, group_logo_b64="")
    assert html_24h.count('class="empty-topic-title">No news from this topic</div>') == 2

    # 5. Deleting a topic automatically unlinks it from assigned clients
    db.delete_custom_news_topic("greysky-capital-pms", db_path=test_db)
    updated_aashish = next(a for a in db.get_analysts(db_path=test_db) if a.id == "aashish")
    assert updated_aashish.assigned_news_topics == ["catalio-capital-fund"]

    # 6. Frequency options: Daily, Weekly, Monthly, Quarterly persistence, fire matching & next run
    ist = db.IST
    # Default frequency is daily
    assert sched_default["frequency"] == "daily"

    # Weekly (Monday = 0 at 10:30 IST)
    s_weekly = db.save_custom_news_schedule(
        dispatch_time="10:30",
        dispatch_active=True,
        frequency="weekly",
        day_of_week=0,
        db_path=test_db,
    )
    assert s_weekly["frequency"] == "weekly"
    assert s_weekly["day_of_week"] == 0
    assert s_weekly["frequency_summary"] == "Weekly (Mon)"
    mon_match = datetime(2026, 11, 30, 10, 30, tzinfo=ist)  # Monday
    tue_skip = datetime(2026, 12, 1, 10, 30, tzinfo=ist)    # Tuesday
    assert db.should_fire_custom_news_now(s_weekly, mon_match) is True
    assert db.should_fire_custom_news_now(s_weekly, tue_skip) is False

    # Monthly (15th at 09:15 IST)
    s_monthly = db.save_custom_news_schedule(
        dispatch_time="09:15",
        dispatch_active=True,
        frequency="monthly",
        day_of_month=15,
        db_path=test_db,
    )
    assert s_monthly["frequency"] == "monthly"
    assert s_monthly["day_of_month"] == 15
    assert s_monthly["frequency_summary"] == "Monthly (15th)"
    assert db.should_fire_custom_news_now(s_monthly, datetime(2026, 12, 15, 9, 15, tzinfo=ist)) is True
    assert db.should_fire_custom_news_now(s_monthly, datetime(2026, 12, 14, 9, 15, tzinfo=ist)) is False

    # Quarterly (1st of Jan, Apr, Jul, Oct at 11:00 IST)
    s_quarterly = db.save_custom_news_schedule(
        dispatch_time="11:00",
        dispatch_active=True,
        frequency="quarterly",
        day_of_month=1,
        db_path=test_db,
    )
    assert s_quarterly["frequency"] == "quarterly"
    assert s_quarterly["day_of_month"] == 1
    assert db.should_fire_custom_news_now(s_quarterly, datetime(2027, 1, 1, 11, 0, tzinfo=ist)) is True
    assert db.should_fire_custom_news_now(s_quarterly, datetime(2027, 4, 1, 11, 0, tzinfo=ist)) is True
    assert db.should_fire_custom_news_now(s_quarterly, datetime(2027, 2, 1, 11, 0, tzinfo=ist)) is False
    # Year wrap-around next-run calculation from late Nov -> Jan 1 next year
    nxt_q = db._compute_next_ist_run("11:00", "quarterly", 0, 1, now_ist=datetime(2026, 11, 27, 12, 0, tzinfo=ist))
    assert "01 Jan 2027" in nxt_q and "11:00 AM IST" in nxt_q




