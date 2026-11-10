"""Smoke test of the live feature/model path on synthetic pitch tracks, so it runs without any
dataset. Run:

    python tests/test_smoke.py

The synthetic "raagas" are distinct swara SETS sung at a VARYING tonic, so a passing test also
confirms the tonic-relative features are both tonic-invariant (the same raaga recognised at a
tonic it never saw) and discriminative.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root importable

import numpy as np

from raaga_id import features
from raaga_id.model import RaagaXGB

HOP = 0.01
# Distinct scale-degree sets (semitones from Sa): the synthetic "raagas".
SCALES = {
    "sunny": [0, 2, 4, 5, 7, 9, 11, 12],
    "moody": [0, 2, 3, 5, 7, 8, 10, 12],
    "exotic": [0, 1, 4, 5, 7, 8, 11, 12],
}


def melody(scale, tonic_semitone, seconds=90.0, seed=0):
    """A pitch track walking the scale up and down (0.25 s per note) above a tonic at
    tonic_semitone from A3, with slight pitch wobble. Returns (times, f0, tonic_hz)."""
    rng = np.random.default_rng(seed)
    tonic = 220.0 * 2 ** (tonic_semitone / 12)
    walk = scale + scale[-2:0:-1]
    n = int(seconds / HOP)
    notes = np.repeat(np.tile(walk, n // (len(walk) * 25) + 1), 25)[:n]
    f0 = tonic * 2 ** ((notes + rng.normal(0, 0.05, n)) / 12)
    return np.arange(n) * HOP, f0, tonic


def test_pitch_class_histogram():
    tonic = 200.0
    fifth = tonic * 2 ** (7 / 12)                     # 700 cents above Sa
    f0 = np.array([tonic] * 30 + [fifth] * 10 + [0.0] * 5)  # unvoiced (0) must be ignored
    h = features.pitch_class_histogram(f0, tonic, n_bins=12)
    assert h.shape == (12,)
    assert np.isclose(h.sum(), 1.0)                   # normalized distribution
    assert h.argmax() == 0                            # most mass at Sa (bin 0)
    assert h[7] > 0 and np.isclose(h[7], 0.25)        # a quarter of voiced mass at the fifth
    # octave-folding: same pitch class an octave up lands in the same bin
    h2 = features.pitch_class_histogram(np.array([tonic * 2]), tonic, n_bins=12)
    assert h2[0] == 1.0
    # all-unvoiced -> zeros, not a crash
    assert features.pitch_class_histogram(np.zeros(10), tonic, n_bins=12).sum() == 0.0


def test_pcd_to_swaras():
    pcd = np.zeros(120)
    pcd[3] = 1.0                                    # mass in the Sa region (bins 0-9)
    sw = features.pcd_to_swaras(pcd)
    assert sw.shape == (12,) and np.isclose(sw.sum(), 1.0) and np.isclose(sw[0], 1.0)
    assert len(features.SWARA_LABELS) == 12 and features.SWARA_LABELS[0] == "S"
    pcd2 = np.zeros(120)
    pcd2[70] = 1.0                                  # 700 cents = the fifth = P (index 7)
    assert np.isclose(features.pcd_to_swaras(pcd2)[7], 1.0)


def test_pitch_windows():
    times = np.arange(0.0, 26.0, 0.01)               # 26s pitch track, 100 Hz frame rate
    f0 = np.full_like(times, 200.0)                  # all voiced at the tonic (Sa)
    wins = features.pitch_windows(times, f0, tonic_hz=200.0, n_bins=12)
    assert len(wins) == 3                            # [0,10) [10,20) [20,26) — 6s tail kept
    for h in wins:
        assert h.shape == (12,) and np.isclose(h.sum(), 1.0) and h.argmax() == 0
    # max_windows caps; a silent (all-unvoiced) track yields nothing
    assert len(features.pitch_windows(times, f0, 200.0, max_windows=2)) == 2
    assert features.pitch_windows(times, np.zeros_like(times), 200.0) == []


def test_tonic_invariant_and_discriminative():
    X, y = [], []
    names = sorted(SCALES)
    for label, scale in SCALES.items():
        for s, tonic in enumerate([-5, -2, 0, 3]):                 # each raaga at 4 tonics
            t, f0, sa = melody(scale, tonic, seed=s)
            for w in features.model_windows(t, f0, sa):
                X.append(w)
                y.append(names.index(label))
    model = RaagaXGB(names).fit(np.vstack(X), np.array(y), n_estimators=60)

    with tempfile.TemporaryDirectory() as d:                      # save/load roundtrip
        model = RaagaXGB.load(model.save(Path(d) / "m.json"))

    # a fresh "moody" melody at an UNSEEN tonic must still be recognised -> tonic-invariant
    t, f0, sa = melody(SCALES["moody"], 7, seed=99)
    top = model.aggregate_top_k(np.vstack(features.model_windows(t, f0, sa)))
    assert top[0].raaga == "moody", [(p.raaga, round(p.confidence, 2)) for p in top]
    assert len(top) == 3


if __name__ == "__main__":
    test_pitch_class_histogram()
    test_pcd_to_swaras()
    test_pitch_windows()
    test_tonic_invariant_and_discriminative()
    print("SMOKE OK: PCD, swara folding, windowing, tonic-invariant features, train/save/load, aggregate")
