"""Allied-raaga comparison (D29 Explorer, first step): when the model says "close call — X vs Y",
tell the learner how to hear them apart from the raagas' swara SETS (which of the 12 notes each
uses — a documented fact, not fabricated musicology). The set-difference is the distinguisher.

    python tests/test_compare.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from raaga_id import learn


def test_distinguish_by_missing_notes():
    # Mōhanaṁ (S R2 G3 P D2) vs Bilahari (S R2 G3 M1 P D2 N3): Bilahari adds ma & ni.
    d = learn.distinguish("Mōhanaṁ", "Bilahari")
    assert d is not None
    assert d["same"] is False
    assert set(d["b_only"]) == {"M1", "N3"}      # Bilahari has these, Mōhanaṁ doesn't
    assert d["a_only"] == []                      # Mōhanaṁ adds nothing Bilahari lacks


def test_distinguish_by_swara_variety():
    # Śankarābharaṇaṁ (M1, N3) vs Kalyāṇi (M2, N3): differ in the madhyama (ma).
    d = learn.distinguish("Śankarābharaṇaṁ", "Kalyāṇi")
    assert "M1" in d["a_only"] and "M2" in d["b_only"]


def test_missing_data_returns_none():
    assert learn.distinguish("Mōhanaṁ", "a raaga with no data") is None


def test_comparison_md_is_plain_and_names_the_notes():
    md = learn.comparison_md("Mōhanaṁ", "Bilahari")
    assert "Mōhanaṁ" in md and "Bilahari" in md
    low = md.lower()
    assert "ma" in low and "ni" in low            # names the distinguishing notes in plain terms
    for jargon in ("M1", "N3", "pitch-class", "vector"):
        assert jargon not in md, f"jargon leaked: {jargon}"


def test_comparison_md_same_set_defers_to_gamaka():
    # two ragas with the SAME swara set -> honest "same notes, differ in gamaka" (no fake claim)
    learn._SEED_OVERRIDE = {"X": ["S", "R2", "G3", "P", "D2"], "Y": ["S", "R2", "G3", "P", "D2"]}
    try:
        md = learn.comparison_md("X", "Y")
        assert "same notes" in md.lower() and "gamaka" in md.lower()
    finally:
        learn._SEED_OVERRIDE = None


if __name__ == "__main__":
    test_distinguish_by_missing_notes()
    test_distinguish_by_swara_variety()
    test_missing_data_returns_none()
    test_comparison_md_is_plain_and_names_the_notes()
    test_comparison_md_same_set_defers_to_gamaka()
    print("COMPARE OK — distinguish by set-diff, plain-language, same-set defers to gamaka")
