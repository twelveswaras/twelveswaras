"""Unit tests for pipeline.import_shaale — the pure row-building + manifest logic only.

    python tests/test_import_shaale.py

The importer writes a licensed folder (Shaale, train-only) into the same private commons store
the web form uses. These tests lock the load-bearing rules WITHOUT touching R2, D1, or audio:
the fixed Shaale rights on every row (private, not CC-BY, credited to Shaale), the SQL literal
escaping that stands between a filename/label and a D1 column, the eligibility gate (import vs
skip, dedup by sha256), and the scan/manifest round-trip.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import import_shaale as I

_DAY = "2026-09-12"
_SHA = "a" * 64


def _entry(**kw):
    base = dict(file="students/kalyani_01.mp3", raaga="Kalyani", tradition="carnatic", instrument="Vocal")
    base.update(kw)
    return base


# ---- filenames, keys, mime ------------------------------------------------------

def test_ext_and_audio_detection():
    assert I.ext_of("a/b/c.MP3") == ".mp3"
    assert I.is_audio("x.flac") is True
    assert I.is_audio("notes.txt") is False


def test_r2_key_matches_the_worker_shape():
    assert I.r2_key(_SHA, ".mp3", _DAY) == f"contrib/{_DAY}/{'a' * 20}.mp3"


def test_mime_for_known_and_unknown():
    assert I.mime_for(".mp3") == "audio/mpeg"
    assert I.mime_for(".xyz") == "application/octet-stream"


# ---- SQL literal escaping (the injection boundary) ------------------------------

def test_sql_lit_escapes_quotes_and_handles_null_and_numbers():
    assert I.sql_lit(None) == "NULL"
    assert I.sql_lit(0) == "0"
    assert I.sql_lit(1) == "1"
    assert I.sql_lit("Kalyani") == "'Kalyani'"
    assert I.sql_lit("Sant O'Neil") == "'Sant O''Neil'"      # a stray apostrophe cannot break out


# ---- record(): the fixed Shaale rights on every row -----------------------------

def test_record_bakes_in_train_only_rights():
    r = I.record(_entry(), _SHA, ".mp3", _DAY, _DAY + "T00:00:00Z", verified=True)
    assert r["license"] == "Shaale-train-only"
    assert r["credit"] == "Shaale"
    assert r["release_public"] == 0            # never public
    assert r["is_own"] == 1
    assert r["label_source"] == "expert"
    assert r["verification_status"] == "verified"
    assert r["split"] == "pending"
    assert r["tradition"] == "carnatic"
    assert r["audio_sha256"] == _SHA
    assert r["r2_key"].endswith(".mp3")
    assert r["raaga"]                          # canonicalised, non-empty


def test_record_unverified_when_not_trusted():
    r = I.record(_entry(), _SHA, ".mp3", _DAY, _DAY + "T00:00:00Z", verified=False)
    assert r["verification_status"] == "unverified"


def test_record_blank_instrument_becomes_null():
    r = I.record(_entry(instrument=""), _SHA, ".mp3", _DAY, _DAY + "T00:00:00Z", verified=True)
    assert r["instrument"] is None


def test_insert_sql_is_well_formed_and_private():
    sql = I.insert_sql(I.record(_entry(), _SHA, ".mp3", _DAY, _DAY + "T00:00:00Z", verified=True))
    assert sql.startswith("INSERT INTO contributions (")
    assert "'Shaale-train-only'" in sql
    assert "'Shaale'" in sql
    assert sql.rstrip().endswith(");")


# ---- classify_entry: import vs skip, dedup --------------------------------------

def test_classify_imports_a_valid_new_clip():
    assert I.classify_entry(_entry(), _SHA, set())[0] == "import"


def test_classify_skips_missing_raaga():
    action, reason = I.classify_entry(_entry(raaga=""), _SHA, set())
    assert action == "skip" and "raaga" in reason


def test_classify_skips_bad_tradition():
    action, reason = I.classify_entry(_entry(tradition="western"), _SHA, set())
    assert action == "skip" and "tradition" in reason


def test_classify_dedups_already_imported():
    action, reason = I.classify_entry(_entry(), _SHA, {_SHA})
    assert action == "skip" and "already" in reason.lower()


# ---- scan + manifest round-trip -------------------------------------------------

def test_scan_finds_audio_and_skips_the_rest(tmp_path):
    (tmp_path / "a.mp3").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("nope")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.wav").write_bytes(b"y")
    rows = I.scan_rows(tmp_path)
    files = sorted(r["file"] for r in rows)
    assert files == ["a.mp3", "sub/c.wav"]
    assert all(r["raaga"] == "" and r["tradition"] == "" for r in rows)


def test_manifest_write_then_parse_roundtrips(tmp_path):
    path = tmp_path / "manifest.csv"
    I.write_manifest(path, [_entry(), _entry(file="x/todi_02.wav", raaga="Todi", tradition="hindustani")])
    got = I.parse_manifest(path)
    assert [r["file"] for r in got] == ["students/kalyani_01.mp3", "x/todi_02.wav"]
    assert got[1]["tradition"] == "hindustani"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
