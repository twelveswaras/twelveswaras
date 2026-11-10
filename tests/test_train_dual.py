"""Helpers shared by the training recipe (tools/train_dual) and the swara-chain fit (tools/train_swara).

    python tests/test_train_dual.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from tools.train_dual import track_means


def test_track_means_average_each_track_in_first_seen_order():
    proba = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5], [0.2, 0.8]])
    groups = np.array(["b", "a", "b", "a"])
    tracks, P = track_means(proba, groups)
    assert tracks == ["b", "a"]
    assert np.allclose(P, [[0.75, 0.25], [0.1, 0.9]])


if __name__ == "__main__":
    test_track_means_average_each_track_in_first_seen_order()
    print("ok")
