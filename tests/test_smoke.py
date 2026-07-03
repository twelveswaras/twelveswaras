"""Smoke test — exercises the feature/model/split path on synthetic audio, so the
pipeline is validated without waiting on the Saraga download. Run:

    python tests/test_smoke.py

The synthetic "raagas" are distinct pitch-class SETS voiced over a strong drone at a
VARYING tonic, so a passing test also confirms tonic-relative features are both
tonic-invariant (same class recognized across tonics) and discriminative.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root importable

import numpy as np

from raaga_id import data, features
from raaga_id.config import SAMPLE_RATE
from raaga_id.data import Clip
from raaga_id.model import RaagaXGB

A4 = 440.0
# Distinct scale-degree sets (semitones from tonic) — the synthetic "raagas".
SCALES = {
    "sunny": [0, 2, 4, 5, 7, 9, 11],
    "moody": [0, 2, 3, 5, 7, 8, 10],
    "exotic": [0, 1, 4, 5, 7, 8, 11],
}


def synth(scale, tonic_semitone, seconds=30.0, sr=SAMPLE_RATE, seed=0):
    """Strong drone on the tonic (Sa) + the scale degrees above it, at a given tonic."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    tonic_f = A4 * 2 ** (tonic_semitone / 12)
    y = 2.0 * np.sin(2 * np.pi * tonic_f * t)                  # drone dominates -> Sa detectable
    for d in scale:
        y += np.sin(2 * np.pi * (tonic_f * 2 ** (d / 12)) * t)
    y += 0.01 * rng.standard_normal(t.shape)
    return (y / np.max(np.abs(y))).astype(np.float32)


def test_window_vectors_shape():
    vecs = features.window_vectors(synth(SCALES["sunny"], 0, seconds=25))
    assert len(vecs) == 3, len(vecs)                            # 25s @ 10s -> 2 full + 5s tail
    assert all(v.shape == (24,) for v in vecs), [v.shape for v in vecs]
    assert not any(np.isnan(v).any() for v in vecs)


def test_split_no_leak():
    clips = [Clip(f"t{i}", Path("x"), raaga=("A" if i % 2 else "B")) for i in range(8)]
    train, test = data.split_by_track(clips, test_frac=0.5, seed=1)
    assert train and test
    assert train.isdisjoint(test)                              # no track in both splits
    assert train | test == {c.track_id for c in clips}


def test_precise_tonic_hz_is_used():
    # known frequencies -> pitch classes (A4=440 -> A=9, C4 -> C=0)
    assert features.tonic_pc_from_hz(440.0) == 9
    assert features.tonic_pc_from_hz(261.63) == 0
    # passing tonic_hz must route through tonic_pc_from_hz, not the drone estimate.
    # 8s => exactly one window == the whole clip, so it equals frame_vector directly.
    y = synth(SCALES["sunny"], 0, seconds=8)
    given = features.window_vectors(y, tonic_hz=261.63)          # forces tonic pc 0
    manual = features.frame_vector(y, tonic_pc=0)
    assert len(given) == 1 and np.allclose(given[0], manual), "tonic_hz not applied as expected"


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
    tonics = [-5, -2, 0, 3]                                    # each class seen at 4 tonics
    for label, scale in SCALES.items():
        for s, tonic in enumerate(tonics):
            for v in features.window_vectors(synth(scale, tonic, seconds=30, seed=s)):
                X.append(v)
                y.append(label)
    X = np.vstack(X)
    names = sorted(set(y))
    idx = {c: i for i, c in enumerate(names)}
    model = RaagaXGB(names).fit(X, np.array([idx[c] for c in y]), n_estimators=80)

    with tempfile.TemporaryDirectory() as d:                  # save/load roundtrip
        model = RaagaXGB.load(model.save(Path(d) / "m.json"))

    # a fresh "moody" clip at an UNSEEN tonic must still be recognized -> tonic-invariant
    fresh = features.window_vectors(synth(SCALES["moody"], 7, seconds=30, seed=99))
    top = model.aggregate_top_k(np.vstack(fresh))
    assert top[0].raaga == "moody", [(t.raaga, round(t.confidence, 2)) for t in top]
    assert len(top) == 3


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        data.FROZEN_TEST_PATH = Path(d) / "test_track_ids.json"  # don't clobber real benchmark
        test_window_vectors_shape()
        test_split_no_leak()
        test_precise_tonic_hz_is_used()
        test_pitch_class_histogram()
        test_pcd_to_swaras()
        test_pitch_windows()
        test_tonic_invariant_and_discriminative()
    print("SMOKE OK — windowing, split, tonic-invariant features, train/save/load, aggregate all pass")
