"""Embed mode: when the recognizer is loaded inside the twelveswaras.com page (an iframe), it
hides its own logo, footer, and drone tip so it reads as part of the page, not a separate site.

    python tests/test_embed.py

The runtime behaviour is DOM/browser and is verified live; this locks the wiring so it can't
silently regress (the head script, the iframe detection, the three element ids, the async retry).
apps.identify imports gradio lazily, so this runs in the plain training env.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apps import identify as I


def test_detects_iframe_not_query_param():
    # Embedding is detected by being in an iframe — robust, no dependence on a ?embed= param.
    assert "window.self !== window.top" in I.EMBED_HEAD


def test_hides_the_three_by_id():
    for eid in ("ts-title", "ts-drone", "ts-footer"):
        assert eid in I.EMBED_HEAD, f"{eid} not hidden by the embed script"


def test_hides_iframe_overflow():
    # frame is sized to content, so the iframe must not show its own scrollbar (the page scrolls)
    assert "overflow = 'hidden'" in I.EMBED_HEAD


def test_retries_for_async_render():
    # Gradio mounts components after first paint, so hiding must re-apply on timers + DOM ready.
    assert "setTimeout" in I.EMBED_HEAD
    assert "DOMContentLoaded" in I.EMBED_HEAD


def test_build_ui_wires_head_and_element_ids():
    src = inspect.getsource(I.build_ui)
    assert "head=EMBED_HEAD" in src               # script injected into <head>
    assert 'elem_id="ts-drone"' in src            # drone tip is tagged
    assert 'id="ts-title"' in I.TITLE_HTML        # logo is tagged
    assert 'id="ts-footer"' in I.FOOTER_HTML       # footer is tagged
    assert 'id="ts-end"' in src                    # height sentinel at the end of the content


def test_reports_height_for_auto_resize():
    # The recognizer posts its content height so the page grows the iframe to fit (no nested scroll).
    h = I.EMBED_HEAD
    assert "twelveswaras_height" in h and "postMessage" in h
    # poll (deduped) — Gradio's body is pinned to 100vh, so a ResizeObserver never fires when the
    # accordion opens / a result overflows the fixed body; the poll catches those height changes.
    assert "setInterval" in h and "lastH" in h
    # Measure the #ts-end sentinel's position — Gradio stretches every container to the frame
    # height, so measuring any container loops the resize to infinity. The sentinel can't stretch.
    assert "ts-end" in h and "getBoundingClientRect" in h
    assert "style.height = 'auto'" not in h    # must not collapse the layout (that blanks the app)


def _site():
    return (Path(__file__).resolve().parent.parent / "site" / "index.html").read_text()


def test_site_listens_and_resizes():
    site = _site()
    assert "twelveswaras_height" in site          # listens for the height message
    assert "frame.style.height" in site           # and resizes the iframe to it
    assert "Math.min(6000" in site                # runaway clamp (belt-and-suspenders)


def test_no_huggingface_in_user_copy():
    # Hugging Face is plumbing — never named to users, no "open it directly" link.
    site = _site()
    for phrase in ("Hugging Face", "Hugging&nbsp;Face", "open it directly", "open the recognizer"):
        assert phrase not in site, f"HF exposed to users: {phrase!r}"


if __name__ == "__main__":
    test_detects_iframe_not_query_param()
    test_hides_the_three_by_id()
    test_retries_for_async_render()
    test_build_ui_wires_head_and_element_ids()
    test_reports_height_for_auto_resize()
    test_site_listens_and_resizes()
    test_no_huggingface_in_user_copy()
    print("EMBED OK — iframe-detect + hide chrome, auto-resize (no nested scroll), no HF in copy")
