"""Commons Phase-1 contract (contribute flow). These lock the load-bearing invariants of an
outward-facing, legally-sensitive feature: the rights gate is enforced server-side, contributions
are quarantined, the audio is opt-in-public, and the UI copy uses the correct "my own performance"
wording with the features-first framing. The runtime is JS/HTML + a Cloudflare Worker; like
test_embed, these are structural assertions over the source, not a live-DB test.

    python tests/test_commons.py
"""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _worker() -> str:
    return (ROOT / "cloudflare" / "worker" / "src" / "index.js").read_text()


def _schema() -> str:
    return (ROOT / "cloudflare" / "schema.sql").read_text()


def _site() -> str:
    return (ROOT / "site" / "index.html").read_text()


def test_worker_contribute_route_and_server_side_rights_gate():
    w = _worker()
    assert "endsWith('/contribute')" in w                 # the endpoint exists
    assert "handleContribute" in w
    # the rights attestation is enforced in the WORKER, not just the UI
    assert "rights not attested" in w
    assert "is_own" in w


def test_worker_quarantines_and_dedups():
    w = _worker()
    assert "'pending'" in w                                # never straight to training
    assert "sha256hex" in w and "audio_sha256" in w        # dedup identical clips


def test_worker_does_not_publish_audio_by_default():
    w = _worker()
    # the raw audio only becomes public on an explicit opt-in flag
    assert "release_public" in w


def test_schema_has_commons_fields():
    s = _schema()
    for field in ["is_own", "release_public", "split", "audio_sha256", "consent_version", "label_source"]:
        assert field in s, f"contributions schema missing {field}"


def test_frontend_contribute_posts_and_gates():
    site = _site()
    assert "/contribute" in site                           # the UI posts to the endpoint
    assert "is_own" in site                                # sends the rights flag


def test_frontend_uses_performance_not_recording_wording():
    site = _site().lower()
    # the corrected, loophole-closing wording (a concert recording is not "your own performance")
    assert "my own performance" in site
    # and it must NOT phrase the gate as "my own recording" (invites concert-recording donations)
    assert "my own recording" not in site


def test_frontend_features_first_framing():
    site = _site().lower()
    # default ask is "help improve the recognizer", and we publish the model, not the voice
    assert "improve the recognizer" in site
    assert ("not your recording" in site) or ("not your voice" in site)


# --- the dedicated /contribute page (for people who already know the raaga) -------------------

def _contribute() -> str:
    return (ROOT / "site" / "contribute" / "index.html").read_text()


def test_contribute_page_records_and_uploads():
    c = _contribute()
    # both entry paths exist: a live recording (MediaRecorder) and a file upload
    assert "MediaRecorder" in c
    assert 'type="file"' in c and 'accept="audio/' in c


def test_contribute_page_posts_and_gates():
    c = _contribute()
    assert "/contribute" in c                              # the clip is stored via the endpoint
    assert "is_own" in c                                   # server-side rights flag
    assert "my own performance" in c.lower()               # the rights-gate wording


def test_contribute_page_survives_phone_sleep():
    # a screen wake lock keeps the phone from locking mid-recording (the main mobile pitfall)
    assert "wakeLock" in _contribute()


def test_contribute_page_has_recording_instructions():
    c = _contribute().lower()
    assert "20 to 45 seconds" in c                          # how much to record
    assert "drone" in c                                     # needs a drone for the tonic


def test_contribute_quality_check_is_throwaway_identify_not_store():
    # the clip is run through /identify only to read the tonic + a drone signal (throw-away, never
    # stored or logged), and is stored ONLY via /contribute. Both endpoints are called from the page.
    c = _contribute()
    assert "/identify" in c and "/contribute" in c


def test_contribute_release_is_opt_in():
    assert "release_public" in _contribute()


def test_landing_links_to_contribute_page():
    assert "contribute/" in _site()                        # the landing surfaces the dedicated flow


# --- unified navigation across every page (main + generated) ----------------------------------

def _nav_block(path: str) -> str:
    m = re.search(r'<nav class="top">(.*?)</nav>', (ROOT / path).read_text(), re.S)
    return m.group(1) if m else ""


ALL_PAGES = [
    "site/index.html", "site/about/index.html", "site/contribute/index.html",
    "site/listen/index.html", "site/raaga/index.html", "site/raaga/kalyani.html",
]


def test_nav_is_unified_across_all_pages():
    # every page (including the generated raaga pages + index + the listen page) carries the same
    # top nav: raagas, train your ear, contribute, about.
    for p in ALL_PAGES:
        nav = _nav_block(p)
        assert nav, f'{p}: no <nav class="top"> found'
        for item in ["train your ear", ">contribute<", ">about<"]:
            assert item in nav, f"{p} nav is missing '{item}'"


def test_sitemap_includes_about_contribute_and_slashed_listen():
    # the generator must not drop the hand-added directory pages when it rewrites the sitemap
    sm = (ROOT / "site" / "sitemap.xml").read_text()
    assert "twelveswaras.com/about/" in sm
    assert "twelveswaras.com/contribute/" in sm
    assert "twelveswaras.com/listen/" in sm


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
    print("COMMONS OK")
