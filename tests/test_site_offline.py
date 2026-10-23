"""Graceful offline fallback for the static site.

Identifying a raaga needs the network (the recording is analysed on the server), so
twelveswaras is not an offline app. But opening it with no connection should show the
site's own page saying so, not the browser's error page. The worker (site/sw.js) does
only that: it caches one page, offline/index.html (/offline/), and serves it when a page fails to load.
Nothing else is cached or answered from a cache, so nothing can go stale.

    python -m pytest tests/test_site_offline.py
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
SW = (SITE / "sw.js").read_text(encoding="utf-8")
OFFLINE = (SITE / "offline" / "index.html").read_text(encoding="utf-8")


def test_offline_page_says_why_and_is_kept_out_of_search():
    assert '<meta name="robots" content="noindex">' in OFFLINE
    assert re.search(r"<h1>[^<]*offline[^<]*</h1>", OFFLINE, re.I)
    # The reason, in plain words: the recording is analysed on the server.
    assert "needs a connection" in OFFLINE
    assert 'href=""' in OFFLINE  # "Try again" reloads the page that was asked for
    assert "viewport-fit=cover" in OFFLINE


def test_offline_page_is_not_in_the_sitemap():
    assert "offline" not in (SITE / "sitemap.xml").read_text(encoding="utf-8")


def test_worker_caches_only_the_offline_page_and_answers_only_failed_page_loads():
    # A directory page: Cloudflare Pages redirects a .html address, which the worker can't cache.
    assert re.search(r"const OFFLINE = '/offline/'", SW)
    assert "respondWith" in SW and "'navigate'" in SW
    # Never caches anything else: one cache.add, no cache.put.
    assert SW.count("cache.add(") == 1 and "cache.put(" not in SW


def test_worker_version_follows_the_offline_page():
    """Changing offline.html must ship a new worker, or phones keep the old copy."""
    digest = hashlib.sha256(OFFLINE.encode("utf-8")).hexdigest()[:12]
    assert f"const VERSION = '{digest}'" in SW, f"set VERSION in site/sw.js to '{digest}'"


def test_pages_with_the_install_button_also_register_the_worker():
    for page in (SITE / "index.html", SITE / "about" / "index.html"):
        html = page.read_text(encoding="utf-8")
        assert re.search(r"import \{ registerOfflinePage \} from '(\./|\.\./)+offline\.js'", html), page
        assert "registerOfflinePage();" in html, page


def test_the_site_says_when_identifying_failed_for_lack_of_a_connection():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert "No connection. Identifying a raaga needs the internet" in html
