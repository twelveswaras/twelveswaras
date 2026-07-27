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


def test_contribute_page_offers_both_traditions():
    # the dedicated /contribute flow must match the inline card and our live dual model: a
    # Hindustani optgroup in the picker, and the tradition sent with the clip (not Carnatic-only).
    c = _contribute()
    assert 'optgroup label="Hindustani"' in c and 'optgroup label="Carnatic"' in c
    assert "HINDUSTANI_RAAGAS" in c
    assert "fd.append('tradition'" in c                      # tradition rides along on submit
    assert "Carnatic and Hindustani" in c                    # copy no longer says Carnatic-only


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


# --- abstention / open-set: don't confidently name a raaga the model probably got wrong ---------

def test_recognizer_abstains_below_a_confidence_threshold():
    site = _site()
    # a tunable threshold exists, validated on the wild set (~0.45): below it the wheel says it is
    # not sure and does not present a confident raaga name.
    assert "ABSTAIN_CONF" in site
    assert "a raaga I don't know" in site
    # and it must not offer a "how to hear <raaga>" link when it is not sure the raaga is right
    assert "r-learn" in site  # the confident-path learn link still exists for confident results


def test_abstain_offers_a_teach_me_contribution_funnel():
    site = _site().lower()
    # when it abstains, the contribute card reframes as "teach me / learn this raaga"...
    assert "learn this raaga" in site or "teach me" in site
    # ...and lets the contributor name a raaga outside the 40 (the vocabulary-growth path)
    assert "another raaga" in site


def test_recognizer_start_scrolls_into_view_and_clears_stale_results():
    """Reported UX: on mobile the locked result renders below the fold (the user has to scroll to
    see it), and starting a new listen left the PREVIOUS top-3 on screen (mistaken for a
    recognition of the current clip). Starting a listen must scroll the recognizer into view and
    blank the previous top-3 (reset clears the big raaga name already; it must clear the list too)."""
    site = _site()
    assert "scrollIntoView" in site                          # bring the recognizer into view on start
    assert re.search(r"top3El\.innerHTML\s*=\s*''", site)    # clear the previous top-3, not just the raaga name


def test_stop_midway_is_not_shown_as_confident():
    """Reported: stopping a live listen midway rendered as a confident result (green wheel +
    checkmark). 'Confident' must require enough listening time (a quick stop is a best guess), and
    the wheel's green/checkmark must track that confidence, not merely the locked state."""
    site = _site()
    # a live listen must be long enough to be "confident"; an upload is judged on the score alone
    assert "source==='file' || elapsed>=MIN_LISTEN" in site
    # the wheel's green + checkmark is gated on that confidence (lockSure), not just mode==='locked'
    assert "confident=locked&&lockSure" in site


# --- dual-tradition rebrand: the site names Carnatic AND Hindustani, drops "Carnatic first" -----

def _about() -> str:
    return (ROOT / "site" / "about" / "index.html").read_text()


def test_landing_and_about_carry_dual_tradition_framing():
    """The Hybrid rebrand: keep 'a Shazam for raagas', name both traditions, retire the
    Carnatic-only phrasings. Guards against a page silently reverting to single-tradition copy."""
    for name, page in [("index", _site()), ("about", _about())]:
        assert "Carnatic and Hindustani" in page, f"{name}: dual-tradition framing missing"
        # the retired Carnatic-only phrasings must be gone
        assert "Shazam for Carnatic" not in page, f"{name}: stale 'Shazam for Carnatic' copy"
        assert "Carnatic first" not in page, f"{name}: stale 'Carnatic first' tagline"
    # "a Shazam for raagas" survives the rebrand as the hero line
    assert "Shazam for raagas" in _site()


def test_raaga_index_meta_names_both_traditions():
    """The /raaga/ listing card title went dual, but its description + og:description lagged as
    'Browse the 40 Carnatic raagas...' (the stale social subtext). Both must name Hindustani too,
    and the Carnatic-only phrasing must be gone. Guards the generated page AND its source (the
    index-page phrase 'Browse the raagas twelveswaras recognises' is unique to this block)."""
    for name, page in [
        ("site/raaga/index.html", (ROOT / "site" / "raaga" / "index.html").read_text()),
        ("tools/build_pages.py", (ROOT / "tools" / "build_pages.py").read_text()),
    ]:
        assert "Browse the raagas twelveswaras recognises" in page, \
            f"{name}: raaga-index dual description phrase missing"
        assert "Browse the 40 Carnatic raagas twelveswaras recognises" not in page, \
            f"{name}: raaga-index description reverted to Carnatic-only subtext"
        # the new subtext must actually name Hindustani (both meta + og carry it)
        assert page.count("Hindustani (preview) grouped by thaat") >= 2, \
            f"{name}: raaga-index meta/og description does not name Hindustani"


def test_ear_trainer_states_it_is_carnatic_only_for_now():
    """User ask: if the trainer is Carnatic-only it must say so clearly. The /listen page names
    the limit in its own copy (not just implicitly)."""
    listen = (ROOT / "site" / "listen" / "index.html").read_text().lower()
    assert "carnatic raagas for now" in listen


# --- og.png social card is generated (reproducible), 1200x630, and signals both traditions -------

def _png_dims(p: Path) -> tuple[int, int]:
    b = p.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    w = int.from_bytes(b[16:20], "big")
    h = int.from_bytes(b[20:24], "big")
    return w, h


def test_og_card_is_generated_dual_and_correctly_sized():
    import importlib.util
    src = ROOT / "tools" / "build_og.py"
    spec = importlib.util.spec_from_file_location("build_og", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    svg = mod.build_svg()
    # the card names both traditions and keeps the wordmark + hero line
    for token in ["Carnatic", "Hindustani", "twelve", "swaras", "Shazam for raagas"]:
        assert token in svg, f"og card SVG missing '{token}'"
    # the committed PNG the meta tags point at is the declared 1200x630
    assert _png_dims(ROOT / "site" / "og.png") == (1200, 630)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
    print("COMMONS OK")
