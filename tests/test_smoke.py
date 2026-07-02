"""Smoke test — exercises the feature/model/split path on synthetic audio, so the
pipeline is validated without waiting on the Saraga download. Run:

    python tests/test_smoke.py
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


def _tone(freqs, seconds=30.0, sr=SAMPLE_RATE, seed=0):
    """A distinct, deterministic pseudo-'raaga': a fixed set of partials + light noise."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    y = sum(np.sin(2 * np.pi * f * t) / (i + 1) for i, f in enumerate(freqs))
    y += 0.01 * rng.standard_normal(t.shape)
    return (y / np.max(np.abs(y))).astype(np.float32)


def test_window_vectors_shape():
    y = _tone([220, 440, 660], seconds=25)
    vecs = features.window_vectors(y)                 # 25s @ 10s non-overlap -> 2 full + 5s tail
    assert len(vecs) == 3, len(vecs)
    assert all(v.shape == vecs[0].shape for v in vecs)
    assert not any(np.isnan(v).any() for v in vecs)


def test_split_no_leak():
    clips = [Clip(f"t{i}", Path("x"), raaga=("A" if i % 2 else "B")) for i in range(8)]
    train, test = data.split_by_track(clips, test_frac=0.5, seed=1)
    assert train and test
    assert train.isdisjoint(test)                     # no track in both splits
    assert train | test == {c.track_id for c in clips}


def test_train_eval_roundtrip():
    classes = {"raagaA": [180, 360, 540], "raagaB": [233, 466, 699], "raagaC": [277, 554, 831]}
    X, y = [], []
    for label, freqs in classes.items():
        for s in range(4):                            # 4 "tracks" per class
            for v in features.window_vectors(_tone(freqs, seconds=30, seed=s)):
                X.append(v); y.append(label)
    X = np.vstack(X)
    names = sorted(set(y))
    idx = {c: i for i, c in enumerate(names)}
    model = RaagaXGB(names).fit(X, np.array([idx[c] for c in y]), n_estimators=60)

    # save/load roundtrip
    with tempfile.TemporaryDirectory() as d:
        p = model.save(Path(d) / "m.json")
        model = RaagaXGB.load(p)

    # aggregate_top_k on a fresh clip of raagaB should rank raagaB first
    fresh = features.window_vectors(_tone(classes["raagaB"], seconds=30, seed=99))
    top = model.aggregate_top_k(np.vstack(fresh))
    assert top[0].raaga == "raagaB", [(t.raaga, round(t.confidence, 2)) for t in top]
    assert len(top) == 3


if __name__ == "__main__":
    # redirect the frozen-benchmark file to a temp path so the test can't clobber it
    with tempfile.TemporaryDirectory() as d:
        data.FROZEN_TEST_PATH = Path(d) / "test_track_ids.json"
        test_window_vectors_shape()
        test_split_no_leak()
        test_train_eval_roundtrip()
    print("SMOKE OK — windowing, split, train/save/load, aggregate_top_k all pass")
