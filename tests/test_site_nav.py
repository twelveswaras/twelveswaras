"""The header (brand + navigation) is styled once, in site/nav.css, not pasted into every page.

    python tests/test_site_nav.py

It was copied into five files, and the copies drifted: the small-phone rule sat before a wider
one that overrode it. The offline and 404 pages keep their own logo-only header: the offline
page must work from the service worker's cache alone.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
LINK = '<link rel="stylesheet" href="/nav.css">'


def _pages_with_nav():
    return [p for p in sorted(SITE.rglob("*.html")) if 'class="nav"' in p.read_text(encoding="utf-8")]


def test_every_page_with_navigation_uses_the_shared_stylesheet():
    pages = _pages_with_nav()
    assert len(pages) >= 75                                   # home, about, contribute, listen, index, 70 raagas
    for p in pages:
        s = p.read_text(encoding="utf-8")
        assert LINK in s, p.relative_to(ROOT)
        assert ".top .nav" not in s and ".brand{" not in s, f"{p.relative_to(ROOT)} still styles the header inline"


def test_narrower_rules_come_after_wider_ones():
    css = (SITE / "nav.css").read_text(encoding="utf-8")
    at = [css.index(f"(max-width:{w}px)") for w in (560, 400, 360)]
    assert at == sorted(at), "a wider media rule after a narrower one overrides it"


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
