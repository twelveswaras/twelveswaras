"""The 'how to hear this raaga' learner panel must speak to NEW learners — plain language,
the seven swaras everyone knows (sa ri ga ma pa da ni), no chromatic-sthana subscripts or
signal-processing jargon.

    python tests/test_learn.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from raaga_id import features, learn

# jargon a beginner shouldn't be shown
JARGON = ["R1", "R2", "G2", "G3", "M1", "M2", "D1", "D2", "N2", "N3",
          "pitch-class", "pitch class", "PCD", "histogram", "fingerprint", "profile",
          "relative to Sa", "distribution", "vector", "bin"]


def test_swaras7_fold():
    # 12 chromatic positions fold to the 7 named swaras, mass preserved.
    p12 = np.zeros(12)
    p12[0] = 0.5    # S  -> Sa
    p12[4] = 0.3    # G3 -> Ga
    p12[7] = 0.2    # P  -> Pa
    names, vals = features.to_swaras7(p12)
    assert names == ["Sa", "Ri", "Ga", "Ma", "Pa", "Da", "Ni"]
    assert np.isclose(vals.sum(), 1.0)
    assert vals[0] == 0.5 and vals[2] == 0.3 and vals[4] == 0.2   # Sa, Ga, Pa
    assert vals[1] == 0.0                                        # Ri untouched


def test_top_swaras_uses_friendly_names():
    p12 = np.zeros(12)
    p12[0], p12[7], p12[4] = 0.4, 0.35, 0.25   # Sa, Pa, Ga
    tops = learn.top_swaras(p12, k=3)
    assert tops[:2] == ["Sa", "Pa"]            # ordered by emphasis, friendly names
    assert all(t in {"Sa", "Ri", "Ga", "Ma", "Pa", "Da", "Ni"} for t in tops)


def test_summary_is_jargon_free():
    md = learn.summary_md("Mōhanaṁ", user_profile=_demo_profile())
    for bad in JARGON:
        assert bad.lower() not in md.lower(), f"jargon leaked into learner copy: {bad!r}"
    assert "sa" in md.lower()  # speaks in swara names


def _demo_profile():
    p = np.zeros(12)
    p[0], p[2], p[4], p[7], p[9] = 0.3, 0.2, 0.2, 0.2, 0.1   # a Mohanam-ish pentatonic shape
    return p


if __name__ == "__main__":
    test_swaras7_fold()
    test_top_swaras_uses_friendly_names()
    test_summary_is_jargon_free()
    print("LEARN OK — 7-swara fold, friendly names, jargon-free summary all pass")
