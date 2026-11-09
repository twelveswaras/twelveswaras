"""Unit tests for the tonic benchmark's scoring (tools/tonic_bench).

    python tests/test_tonic_bench.py

An estimate is `exact` within 50 cents of the annotated Sa; `octave` when it is Sa an octave away
(harmless: every feature folds octaves); `pa` / `ma` when it landed on the fifth or fourth (fatal:
the whole melody is read in the wrong key); anything else is `other`.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.tonic_bench import classify, recordings, summarize

SA = 146.8


def cents(c):
    return SA * 2 ** (c / 1200)


def test_within_fifty_cents_is_exact():
    assert classify(cents(30), SA) == "exact"
    assert classify(cents(-49), SA) == "exact"


def test_octave_away_is_its_own_class():
    assert classify(SA * 2, SA) == "octave"
    assert classify(SA / 2 * 2 ** (20 / 1200), SA) == "octave"


def test_fifth_and_fourth_are_named():
    assert classify(cents(700), SA) == "pa"        # estimate on Pa: the fifth above Sa
    assert classify(cents(-700), SA) == "ma"       # Pa below = Sa sits a fourth above it: Ma
    assert classify(cents(500), SA) == "ma"
    assert classify(cents(-500 + 1200), SA) == "pa"


def test_anything_else_is_other():
    assert classify(cents(200), SA) == "other"
    assert classify(cents(80), SA) == "other"      # just outside the 50-cent band


def test_summary_counts_usable_as_exact_plus_octave():
    s = summarize(["exact", "exact", "octave", "pa", "other"])
    assert s["n"] == 5
    assert math.isclose(s["exact"], 0.4) and math.isclose(s["usable"], 0.6) and math.isclose(s["pa_ma"], 0.2)


def test_macos_metadata_files_are_not_recordings(tmp_path=None):
    """'._x.ctonic.txt' files are binary macOS metadata that sit beside the real annotations."""
    import tempfile

    root = Path(tmp_path or tempfile.mkdtemp())
    (root / "a.ctonic.txt").write_text("146.8\n")
    (root / "a.mp3").write_bytes(b"")
    (root / "._a.ctonic.txt").write_bytes(b"\x00\x05\x16\x07\xb4")
    (root / "._a.mp3").write_bytes(b"")
    assert [(rid, truth) for rid, _, truth in recordings(root)] == [("a.ctonic.txt", 146.8)]


def test_mixes_named_mp3_mp3_are_found(tmp_path=None):
    """More than half of Saraga Carnatic's mixes are named 'x.mp3.mp3'."""
    import tempfile

    root = Path(tmp_path or tempfile.mkdtemp())
    (root / "b.ctonic.txt").write_text("150.0\n")
    (root / "b.mp3.mp3").write_bytes(b"")
    (root / "b.multitrack-violin.mp3").write_bytes(b"")
    found = [(rid, mix.name) for rid, mix, _ in recordings(root)]
    assert found == [("b.ctonic.txt", "b.mp3.mp3")]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
