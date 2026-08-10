"""Unit tests for pipeline.pull_commons — the pure eligibility + manifest logic only.

    python tests/test_pull_commons.py

The pull step reads verified commons contributions out of D1/R2 and materializes them
into a local training-ready corpus. These tests lock the load-bearing rules WITHOUT
touching D1, R2, or essentia: how a contribution is classified (train / vocab-growth /
skip), how in-vocabulary membership is decided against the tradition-tagged model
classes, and the manifest round-trip that makes the pull idempotent (dedup by sha256).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import pull_commons as P

# A slice of the real 70-class dual model vocab (tradition-tagged), enough to exercise
# the folding + tradition split: the two Todis are DIFFERENT classes.
DUAL = {
    "Tōḍi (Carnatic)",
    "Tōḍī (Hindustani)",
    "Mōhanaṁ (Carnatic)",
    "Kalyāṇi (Carnatic)",
    "Bhairav (Hindustani)",
}


def _row(**kw):
    """A contribution row with sane, training-eligible defaults; override per test."""
    base = dict(
        id=1,
        raaga="Tōḍi",
        tradition="carnatic",
        r2_key="contrib/2026-08-01/abc123.webm",
        audio_sha256="a" * 64,
        is_own=1,
        verification_status="verified",
        label_source="contributor_declared",
        release_public=1,
        license="CC-BY-4.0",
        instrument="Vocal",
        tonic_hz=None,
    )
    base.update(kw)
    return base


# ---- in_vocab: diacritic-folding + tradition split -------------------------------

def test_in_vocab_folds_diacritics_and_ascii():
    assert P.in_vocab("Todi", "carnatic", DUAL) is True        # ASCII folds to Tōḍi
    assert P.in_vocab("Mohanam", "carnatic", DUAL) is True


def test_in_vocab_respects_tradition_tag():
    # "Todi" exists in BOTH traditions as distinct classes — the tag must match.
    assert P.in_vocab("Todi", "hindustani", DUAL) is True      # -> Tōḍī (Hindustani)
    assert P.in_vocab("Bhairav", "carnatic", DUAL) is False    # Bhairav is Hindustani-only here
    assert P.in_vocab("Bhairav", "hindustani", DUAL) is True


def test_in_vocab_rejects_unknown_raaga():
    assert P.in_vocab("Arabhi", "carnatic", DUAL) is False
    assert P.in_vocab("Kuntala varali", "carnatic", DUAL) is False


# ---- classify: the three-way eligibility gate -----------------------------------

def test_classify_verified_in_vocab_is_trainable():
    bucket, _ = P.classify(_row(), DUAL, set())
    assert bucket == P.TRAIN


def test_classify_model_confirmed_is_self_verifying():
    # A contributor who confirmed the model's own prediction needs no extra votes.
    bucket, _ = P.classify(
        _row(verification_status="unverified", label_source="model_confirmed"), DUAL, set()
    )
    assert bucket == P.TRAIN


def test_classify_out_of_vocab_goes_to_vocab_growth():
    # Out-of-vocab is a NEW-RAAGA signal, not a training row — held, never trained,
    # and never silently dropped. Verification status is irrelevant here.
    bucket, reason = P.classify(_row(raaga="Arabhi", verification_status="verified"), DUAL, set())
    assert bucket == P.VOCAB_GROWTH
    assert "vocab" in reason.lower()


def test_classify_skips_when_rights_not_attested():
    bucket, reason = P.classify(_row(is_own=0), DUAL, set())
    assert bucket == P.SKIP
    assert "rights" in reason.lower()


def test_classify_skips_unverified_in_vocab():
    bucket, reason = P.classify(
        _row(verification_status="unverified", label_source="contributor_declared"), DUAL, set()
    )
    assert bucket == P.SKIP
    assert "unverified" in reason.lower()


def test_classify_skips_disputed():
    bucket, reason = P.classify(_row(verification_status="disputed"), DUAL, set())
    assert bucket == P.SKIP
    assert "disput" in reason.lower()


def test_classify_skips_missing_audio():
    bucket, reason = P.classify(_row(r2_key=None), DUAL, set())
    assert bucket == P.SKIP
    assert "audio" in reason.lower()


def test_classify_skips_missing_tradition():
    bucket, reason = P.classify(_row(tradition=""), DUAL, set())
    assert bucket == P.SKIP
    assert "tradition" in reason.lower()


def test_classify_dedups_already_pulled():
    sha = "d" * 64
    bucket, reason = P.classify(_row(audio_sha256=sha), DUAL, {sha})
    assert bucket == P.SKIP
    assert "already" in reason.lower()


# ---- manifest: entry shape + idempotent round-trip ------------------------------

def test_manifest_entry_canonicalizes_and_keeps_provenance():
    e = P.manifest_entry(_row(raaga="Todi", tradition="carnatic"))
    assert e["raaga"] == "Tōḍi"                       # folded to the canonical spelling
    assert e["tradition"] == "carnatic"
    assert e["audio_sha256"] == "a" * 64
    assert e["r2_key"] == "contrib/2026-08-01/abc123.webm"
    assert e["audio_path"].endswith(".webm")          # ext carried from the r2 key
    assert e["source"] == "commons"


def test_audio_ext_from_key():
    assert P.audio_ext("contrib/x/y.webm") == ".webm"
    assert P.audio_ext("contrib/x/y.mp3") == ".mp3"
    assert P.audio_ext("contrib/x/y") == ""


def test_manifest_roundtrip_and_pulled_shas(tmp_path):
    path = tmp_path / "manifest.jsonl"
    e1 = P.manifest_entry(_row(id=1, audio_sha256="1" * 64))
    e2 = P.manifest_entry(_row(id=2, audio_sha256="2" * 64))
    P.append_manifest(path, e1)
    P.append_manifest(path, e2)
    rows = P.load_manifest(path)
    assert [r["id"] for r in rows] == [1, 2]
    assert P.pulled_shas(rows) == {"1" * 64, "2" * 64}


def test_load_manifest_missing_is_empty(tmp_path):
    assert P.load_manifest(tmp_path / "nope.jsonl") == []


# ---- summary: honest per-bucket accounting --------------------------------------

def test_summarize_counts_each_bucket():
    classified = [
        (_row(id=1), P.TRAIN, "eligible"),
        (_row(id=2), P.VOCAB_GROWTH, "out-of-vocab (Arabhi (Carnatic))"),
        (_row(id=3), P.VOCAB_GROWTH, "out-of-vocab (Lathangi (Carnatic))"),
        (_row(id=4), P.SKIP, "unverified"),
    ]
    s = P.summarize(classified)
    assert s["train"] == 1
    assert s["vocab_growth"] == 2
    assert s["skip"] == 1
    assert s["total"] == 4


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
