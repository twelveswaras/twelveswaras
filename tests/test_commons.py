"""Commons Phase-1 contract (contribute flow). These lock the load-bearing invariants of an
outward-facing, legally-sensitive feature: the rights gate is enforced server-side, contributions
are quarantined, the audio is opt-in-public, and the UI copy uses the correct "my own performance"
wording with the features-first framing. The runtime is JS/HTML + a Cloudflare Worker; like
test_embed, these are structural assertions over the source, not a live-DB test.

    python tests/test_commons.py
"""
from __future__ import annotations
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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print("ok", name)
    print("COMMONS OK")
