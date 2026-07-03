"""Unit tests for probability calibration + confidence state (D25).

    python tests/test_calibrate.py

Two ideas: (1) temperature scaling makes the shown %s mean what they say without changing
which raaga wins (argmax-preserving); (2) a confidence *state* turns a flat top-2 into an
honest "close call — X vs Y" instead of a falsely-precise single answer.
"""
from __future__ import annotations

import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from raaga_id import calibrate as C

P = namedtuple("P", "raaga confidence")


def test_apply_temperature_identity_and_normalization():
    p = np.array([0.6, 0.3, 0.1])
    assert np.allclose(C.apply_temperature(p, 1.0), p)          # T=1 is a no-op
    for T in (0.5, 1.0, 2.0, 5.0):
        q = C.apply_temperature(p, T)
        assert np.isclose(q.sum(), 1.0)                         # still a distribution
        assert np.argmax(q) == np.argmax(p)                    # winner never changes


def test_temperature_direction():
    p = np.array([0.6, 0.3, 0.1])
    hot = C.apply_temperature(p, 4.0)                           # T>1 -> flatter
    cold = C.apply_temperature(p, 0.4)                          # T<1 -> peakier
    assert hot.max() < p.max() < cold.max()


def test_apply_temperature_batched():
    P2 = np.array([[0.6, 0.3, 0.1], [0.2, 0.2, 0.6]])
    q = C.apply_temperature(P2, 2.0)
    assert q.shape == P2.shape
    assert np.allclose(q.sum(axis=1), 1.0)


def test_fit_temperature_softens_an_overconfident_model():
    # Model always screams [0.95, 0.05] but is right only half the time -> overconfident.
    rng = np.random.default_rng(0)
    n = 400
    Pm = np.tile([0.95, 0.05], (n, 1))
    y = rng.integers(0, 2, size=n)                              # true label ~ coin flip
    T = C.fit_temperature(Pm, y)
    assert T > 1.0                                             # should cool it down
    assert C.nll(C.apply_temperature(Pm, T), y) < C.nll(Pm, y)  # calibration lowers NLL


def test_confidence_state():
    assert C.confidence_state([P("Tōḍi", 0.70), P("Sāvēri", 0.10)])[0] == "confident"
    close = C.confidence_state([P("Sāvēri", 0.24), P("Sencuruṭṭi", 0.20)])
    assert close[0] == "close" and "Sāvēri" in close[1] and "Sencuruṭṭi" in close[1]
    unsure = C.confidence_state([P("X", 0.12), P("Y", 0.11)])  # p1<low wins over margin
    assert unsure[0] == "unsure"


if __name__ == "__main__":
    test_apply_temperature_identity_and_normalization()
    test_temperature_direction()
    test_apply_temperature_batched()
    test_fit_temperature_softens_an_overconfident_model()
    test_confidence_state()
    print("CALIBRATE OK — temperature (identity/direction/batched/fit) + confidence-state pass")
