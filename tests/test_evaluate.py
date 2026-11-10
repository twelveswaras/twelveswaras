"""The frozen-benchmark scorer works on the live model (raaga_id.evaluate).

    python tests/test_evaluate.py

The live model's classes carry a tradition tag ("Kalyāṇi (Carnatic)") and it needs each window's
swara phrases; the corpus labels are bare names. The scorer must bridge both, or it scores zero
(no name ever matches) or refuses to run (no phrases).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from raaga_id import evaluate, features, swara, tradition
from raaga_id.data import PitchClip
from raaga_id.model import RaagaXGB

HOP = 0.01
SA = 146.8
UP, DOWN = [0, 4, 7, 12, 7, 4], [0, 3, 7, 12, 7, 3]


def _clip(name, pattern, seconds=60, seed=0):
    rng = np.random.default_rng(seed)
    n = int(seconds / HOP)
    notes = np.repeat(np.tile(pattern, n // (len(pattern) * 25) + 1), 25)[:n]
    f0 = SA * 2 ** ((notes + rng.normal(0, 0.05, n)) / 12)
    return PitchClip("test", f"{name}-{seed}", name, SA, np.arange(n) * HOP, f0)


def _model():
    classes = [tradition.tag("Up", "carnatic"), tradition.tag("Down", "carnatic")]
    X, y, ph = [], [], []
    for label, pattern in ((0, UP), (1, DOWN)):
        for seed in range(3):
            c = _clip("x", pattern, seed=seed)
            w, p = features.model_windows(c.times, c.freqs, c.tonic_hz, phrases=True)
            X += w
            y += [label] * len(w)
            ph += p
    chains = swara.SwaraChains.fit(ph, np.array(y), 2, weight=20.0)
    return RaagaXGB(classes, chains=chains).fit(np.vstack(X), np.array(y), n_estimators=10)


def test_tag_builds_and_replaces_the_tradition_suffix():
    assert tradition.tag("Kalyāṇi", "carnatic") == "Kalyāṇi (Carnatic)"
    assert tradition.tag("Tōḍī (Hindustani)", "Hindustani") == "Tōḍī (Hindustani)"
    assert tradition.tag("Śrī (Carnatic)", "hindustani") == "Śrī (Hindustani)"


def test_scores_bare_corpus_labels_against_tagged_classes_with_phrases():
    m = _model()
    clips = [_clip("Up", UP, seed=9), _clip("Down", DOWN, seed=9)]
    n, top1, top3 = evaluate.score(m, clips)
    assert n == 2 and top1 == 2 and top3 == 2


def test_untagged_models_still_score():
    m = _model()
    m.classes = ["Up", "Down"]
    assert evaluate.score(m, [_clip("Up", UP, seed=9)])[:2] == (1, 1)


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
