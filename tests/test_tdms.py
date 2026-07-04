"""Unit tests for the Time-Delayed Melody Surface (gamaka feature, refines D16).

    python tests/test_tdms.py

TDMS = a 2-D histogram of (pitch(t), pitch(t+delay)) over the tonic-normalized, octave-folded
melody (Gulati et al., ISMIR 2016). A *steady* note puts all mass on the diagonal; *movement*
(gamaka, note transitions) puts mass off-diagonal — exactly the information the 1-D PCD throws
away, and what should separate allied raagas that share a scale.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from raaga_id import features

N = 60
HOP = 0.01                      # 10 ms frames
TONIC = 200.0
P_HZ = TONIC * 2 ** (700 / 1200)  # the fifth (P), 700 cents -> bin 35 at 60 bins


def _times(n):
    return np.arange(n) * HOP


def test_shape_and_normalization():
    f0 = np.full(400, TONIC)
    surf = features.tdms(_times(400), f0, TONIC, delay=0.05, n_bins=N)
    assert surf.shape == (N * N,)
    assert np.isclose(surf.sum(), 1.0)


def test_steady_note_is_pure_diagonal():
    # A held Sa never moves -> every (t, t+d) pair is (bin0, bin0).
    f0 = np.full(400, TONIC)
    surf = features.tdms(_times(400), f0, TONIC, delay=0.05, n_bins=N).reshape(N, N)
    assert np.isclose(surf[0, 0], 1.0)
    assert np.isclose(surf.sum() - surf[0, 0], 0.0)          # nothing off-diagonal


def test_movement_lands_off_diagonal():
    # Alternate Sa <-> P every frame with a 1-frame delay -> mass at (0,35) and (35,0).
    n = 400
    f0 = np.where(np.arange(n) % 2 == 0, TONIC, P_HZ)
    surf = features.tdms(_times(n), f0, TONIC, delay=HOP, n_bins=N).reshape(N, N)
    off = surf.sum() - np.trace(surf)
    assert off > 0.9                                          # almost all mass is off-diagonal
    assert surf[0, 35] > 0 and surf[35, 0] > 0


def test_unvoiced_frames_are_skipped():
    # Second half unvoiced (f0<=0); pairs there are dropped, the voiced first half still counts.
    f0 = np.full(400, TONIC)
    f0[200:] = 0.0
    surf = features.tdms(_times(400), f0, TONIC, delay=0.05, n_bins=N)
    assert np.isclose(surf.sum(), 1.0)                       # normalized over valid pairs only

    silent = features.tdms(_times(400), np.zeros(400), TONIC, delay=0.05, n_bins=N)
    assert np.isclose(silent.sum(), 0.0)                     # nothing voiced -> zeros


def test_tdms_windows_match_pitch_windows():
    # The windowed variant must slice the pitch track the same way pitch_windows does (so the
    # model can aggregate TDMS windows exactly like PCD windows), and each surface normalizes.
    t = np.arange(2500) * HOP          # 25 s of steady Sa
    f0 = np.full(2500, TONIC)
    wins = features.tdms_windows(t, f0, TONIC, delay=0.05, n_bins=N)
    assert len(wins) == len(features.pitch_windows(t, f0, TONIC)) >= 2
    for w in wins:
        assert w.shape == (N * N,) and np.isclose(w.sum(), 1.0)


def test_junk_gate_drops_low_voiced_windows():
    # 60 s track: window 1 is percussion-like (20% voiced), window 2 is melody (90% voiced).
    t = np.arange(6000) * HOP           # 60 s at 10 ms frames
    f0 = np.zeros(6000)
    f0[0:600] = TONIC                   # window 1: 600/3000 = 20% voiced -> below the 0.5 gate
    f0[3000:5700] = TONIC               # window 2: 2700/3000 = 90% voiced -> kept
    gated = features.tdms_windows(t, f0, TONIC, window_s=30, hop_s=30, n_bins=N, min_voiced=0.5)
    assert len(gated) == 1              # junk window dropped, melody kept
    ungated = features.tdms_windows(t, f0, TONIC, window_s=30, hop_s=30, n_bins=N, min_voiced=0.0)
    assert len(ungated) == 2            # the gate — not "no voiced pairs" — is what dropped it


if __name__ == "__main__":
    test_shape_and_normalization()
    test_steady_note_is_pure_diagonal()
    test_movement_lands_off_diagonal()
    test_unvoiced_frames_are_skipped()
    test_tdms_windows_match_pitch_windows()
    test_junk_gate_drops_low_voiced_windows()
    print("TDMS OK — shape/normalize, steady=diagonal, movement=off-diagonal, unvoiced-skip, "
          "windowed-count, junk-gate pass")
