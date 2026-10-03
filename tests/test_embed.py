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


def test_site_hosts_first_party_recognizer():
    # The wheel is first-party now (no Gradio iframe): the page captures mic audio,
    # posts it to /identify, and lights swaras from the response on its own canvas.
    site = _site()
    assert "<canvas" in site                      # the wheel is drawn in-page
    assert "MediaRecorder" in site                # mic capture lives in the page itself
    assert "/identify" in site                    # posts audio to the recognizer API
    assert "swara_activation" in site             # and lights swaras from the response
    assert "<iframe" not in site                  # nothing embedded to resize away


def test_api_base_uses_worker_off_production():
    # /api is same-origin ONLY on the real domain. On localhost / *.pages.dev previews a static server
    # has no /api, so the wheel must hit the workers.dev URL directly — otherwise the fetch 404s and
    # the upload path reads it as "That file could not be analysed."
    site = _site()
    assert "twelveswaras-api.knerav.workers.dev" in site        # the off-production backend
    assert "host === 'twelveswaras.com'" in site                # /api reserved for the canonical host
    assert "host === 'www.twelveswaras.com'" in site


def test_no_huggingface_in_user_copy():
    # Hugging Face is plumbing — never named to users, no "open it directly" link.
    # Covers EVERY user-facing page, not just the landing one: the about page named it for months
    # because this check only ever read index.html, and the recognizer has since moved off HF
    # entirely (the Space is gone; the org holds no models or datasets).
    root = Path(__file__).resolve().parent.parent / "site"
    for page in sorted(root.rglob("index.html")):
        html = page.read_text()
        for phrase in ("Hugging Face", "Hugging&nbsp;Face", "huggingface.co",
                       "open it directly", "open the recognizer"):
            assert phrase not in html, f"HF exposed in {page.relative_to(root)}: {phrase!r}"


if __name__ == "__main__":
    test_detects_iframe_not_query_param()
    test_hides_the_three_by_id()
    test_retries_for_async_render()
    test_build_ui_wires_head_and_element_ids()
    test_reports_height_for_auto_resize()
    test_site_hosts_first_party_recognizer()
    test_api_base_uses_worker_off_production()
    test_no_huggingface_in_user_copy()
    print("EMBED OK — iframe-detect + hide chrome, auto-resize (no nested scroll), no HF in copy")


def test_listen_guidance_matches_the_real_minimum():
    """The page must not promise a result from less audio than the recognizer can actually use.

    It needs a full TDMS window (30 s) before ANY reading is possible, and the wheel will not lock
    before MIN_LISTEN. The page used to say "15-30 seconds is enough", which set people up to stop
    early; short captures are one of the largest causes of a no-prediction in production.
    """
    import re

    site = _site()
    m = re.search(r"MIN_LISTEN\s*=\s*(\d+)", site)
    assert m, "MIN_LISTEN not found in the page"
    min_listen = int(m.group(1))

    # any "N seconds" the copy offers as sufficient must not undercut the real floor
    for num in re.findall(r"(?:about\s+)?(\d+)(?:\s*[–-]\s*\d+)?\s*seconds? (?:of melody )?is enough", site):
        assert int(num) >= min_listen, f"copy promises {num}s, but the wheel needs {min_listen}s"
    assert "15–30 seconds of melody is enough" not in site
    assert "15-30 seconds" not in site
