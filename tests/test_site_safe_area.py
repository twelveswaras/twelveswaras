"""Notch padding: every page that sets `viewport-fit=cover` must keep its content clear of the
notch, rounded corners and home bar.

`viewport-fit=cover` lets the page draw under those areas (installed, or in landscape on a notched
phone). Each edge therefore pads by `max(<usual padding>, env(safe-area-inset-<edge>))`: the inset
wins on a notched screen, and everywhere else the inset is 0 and the layout is unchanged.
Structural assertions over each page's <style>; e2e/tests/safe-area.spec.js checks the real layout
under a simulated notch.

    python -m pytest tests/test_site_safe_area.py
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
COVER_PAGES = sorted(
    p for p in SITE.rglob("*.html") if "viewport-fit=cover" in p.read_text(encoding="utf-8")
)


def _css(page: Path) -> str:
    return "\n".join(re.findall(r"<style>(.*?)</style>", page.read_text(encoding="utf-8"), re.S))


def _rules(css: str, selector: str) -> list[str]:
    """Bodies of every rule whose selector list is exactly `selector` (media queries included)."""
    esc = re.escape(selector)
    return re.findall(rf"(?:^|[{{}};\s]){esc}\s*\{{([^}}]*)\}}", css)


def _clears(body: str, edge: str) -> bool:
    return re.search(rf"max\([^;]*env\(safe-area-inset-{edge}\)", body) is not None


def _id(page: Path) -> str:
    return page.relative_to(SITE).as_posix()


def test_the_pages_that_need_it_are_all_found():
    found = {_id(p) for p in COVER_PAGES}
    assert {"index.html", "about/index.html", "contribute/index.html", "listen/index.html",
            "404.html", "offline/index.html", "raaga/index.html", "raaga/kalyani.html"} <= found
    assert sum(name.startswith("raaga/") for name in found) > 60


@pytest.mark.parametrize("page", COVER_PAGES, ids=_id)
def test_side_gutter_clears_the_left_and_right_insets(page):
    (wrap,) = _rules(_css(page), ".wrap")
    assert _clears(wrap, "left") and _clears(wrap, "right"), _id(page)


@pytest.mark.parametrize("page", COVER_PAGES, ids=_id)
def test_top_bar_clears_the_top_inset_at_every_width(page):
    tops = [b for b in _rules(_css(page), ".top") if "padding" in b]
    assert tops, _id(page)
    # The phone-width override sets its own padding-top: it must keep the inset too.
    for body in tops:
        assert _clears(body, "top"), (_id(page), body)


@pytest.mark.parametrize("page", COVER_PAGES, ids=_id)
def test_last_row_clears_the_bottom_inset(page):
    css = _css(page)
    bottom = [b for b in _rules(css, "footer") or _rules(css, ".foot") if "padding" in b]
    assert bottom and all(_clears(b, "bottom") for b in bottom), _id(page)


def test_listen_footer_sits_outside_the_gutter_so_pads_its_own_sides():
    (foot,) = _rules(_css(SITE / "listen" / "index.html"), ".foot")
    assert _clears(foot, "left") and _clears(foot, "right")


@pytest.mark.parametrize("page", COVER_PAGES, ids=_id)
def test_insets_only_ever_add_padding(page):
    """A bare env() would drop the usual padding to 0 on screens without a notch (desktop)."""
    css = _css(page)
    assert css.count("env(safe-area-inset-") == len(re.findall(r"max\([^,()]+,\s*env\(safe-area-inset-", css))
