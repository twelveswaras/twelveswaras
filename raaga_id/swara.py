"""Swara phrases and per-raaga swara chains: the order of notes, which TDMS cannot see.

TDMS records how pitch moves over one 0.3 s step. A raaga also has a grammar over longer spans:
zig-zag (vakra) movement, notes that only appear inside certain phrases, characteristic
sañcāras. Each raaga gets a second-order Markov chain over swaras (P(next | previous two)), and
a clip is scored by how likely each raaga's chain finds its phrases.

Swaras are semitones above Sa, folded to one octave (12 states) when modelled. Held notes
shorter than MIN_NOTE_S are gamaka transit and dropped; repeats collapse to one swara; a pause
longer than GAP_S ends the phrase. Smoothing is recursive Jelinek-Mercer interpolation
(trigram -> bigram -> add-one unigram), so unseen contexts back off instead of scoring -inf.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

MIN_NOTE_S = 0.06     # shorter holds are gamaka transit, not a sung swara
GAP_S = 0.25          # a longer unvoiced pause ends the phrase
LAMBDA_TRI = 0.6      # weight on the trigram estimate (rest backs off to the bigram)
LAMBDA_BI = 0.7       # weight on the bigram estimate (rest backs off to the unigram)
_UNVOICED = -10_000


def phrases(times, f0_hz, tonic_hz: float) -> list[np.ndarray]:
    """Swara phrases (unfolded semitones above Sa) from a pitch track; 0 Hz marks unvoiced."""
    times = np.asarray(times, dtype=float)
    f0 = np.asarray(f0_hz, dtype=float)
    if times.size < 2:
        return []
    hop = float(np.median(np.diff(times)))
    voiced = f0 > 0
    key = np.full(f0.shape, _UNVOICED, dtype=int)
    key[voiced] = np.rint(1200 * np.log2(f0[voiced] / tonic_hz) / 100).astype(int)
    edges = np.flatnonzero(np.diff(key)) + 1
    out: list[np.ndarray] = []
    cur: list[int] = []
    for s, e in zip(np.r_[0, edges], np.r_[edges, key.size]):
        dur, k = (e - s) * hop, int(key[s])
        if k == _UNVOICED:
            if dur > GAP_S and cur:
                out.append(np.array(cur))
                cur = []
        elif dur >= MIN_NOTE_S and (not cur or cur[-1] != k):
            cur.append(k)
    if cur:
        out.append(np.array(cur))
    return out


def fuse(proba: np.ndarray, scores: np.ndarray, weight: float) -> np.ndarray:
    """Combine the model's clip probabilities with the chains' scores: log p + weight * score,
    renormalised. weight 0 returns the model's probabilities unchanged."""
    z = np.log(np.clip(proba, 1e-12, None)) + weight * scores
    e = np.exp(z - z.max(-1, keepdims=True))
    return e / e.sum(-1, keepdims=True)


class SwaraChains:
    """One second-order swara chain per class, stored as log-probability tables, plus the
    weight its scores get when fused with the model's probabilities (tools/train_swara)."""

    def __init__(self, log0: np.ndarray, log1: np.ndarray, log2: np.ndarray, weight: float = 0.0):
        self.log0, self.log1, self.log2 = log0, log1, log2   # (C,12), (C,12,12), (C,12,12,12)
        self.weight = float(weight)

    @classmethod
    def fit(cls, window_phrases, labels, n_classes: int, weight: float = 0.0) -> "SwaraChains":
        """window_phrases: one list of phrases per window; labels: class index per window."""
        c0 = np.zeros((n_classes, 12))
        c1 = np.zeros((n_classes, 12, 12))
        c2 = np.zeros((n_classes, 12, 12, 12))
        for phs, c in zip(window_phrases, labels):
            for p in phs:
                s = np.mod(p, 12)
                np.add.at(c0[c], s, 1)
                np.add.at(c1[c], (s[:-1], s[1:]), 1)
                np.add.at(c2[c], (s[:-2], s[1:-1], s[2:]), 1)
        p0 = (c0 + 1) / (c0.sum(-1, keepdims=True) + 12)
        n1 = c1.sum(-1, keepdims=True)
        p1 = np.where(n1 > 0, LAMBDA_BI * c1 / np.maximum(n1, 1) + (1 - LAMBDA_BI) * p0[:, None, :],
                      p0[:, None, :])
        n2 = c2.sum(-1, keepdims=True)
        p2 = np.where(n2 > 0, LAMBDA_TRI * c2 / np.maximum(n2, 1) + (1 - LAMBDA_TRI) * p1[:, :, None, :],
                      p1[:, :, None, :])
        return cls(np.log(p0), np.log(p1), np.log(p2), weight)

    def score(self, window_phrases: list[np.ndarray]) -> np.ndarray:
        """Mean log-likelihood per swara under each class's chain, (C,). Zeros (no evidence
        either way) when the window has no swaras."""
        total, n = np.zeros(self.log0.shape[0]), 0
        for p in window_phrases:
            s = np.mod(p, 12)
            total += self.log0[:, s[0]]
            if s.size > 1:
                total += self.log1[:, s[0], s[1]]
            if s.size > 2:
                total += self.log2[:, s[:-2], s[1:-1], s[2:]].sum(-1)
            n += s.size
        return total / n if n else total

    def score_windows(self, windows: list[list[np.ndarray]]) -> np.ndarray:
        """Per-window scores stacked, (n_windows, C)."""
        return np.vstack([self.score(w) for w in windows])

    def save(self, path: str | Path, classes: list[str]) -> Path:
        """Saved with the class list its rows follow, so it can't be paired with another model."""
        path = Path(path)
        np.savez_compressed(path, log0=self.log0, log1=self.log1, log2=self.log2, weight=self.weight,
                            classes=np.array(classes))
        return path

    @classmethod
    def load(cls, path: str | Path, classes: list[str]) -> "SwaraChains":
        """Refuses chains whose class list differs from the model's (order included)."""
        z = np.load(Path(path))
        if z["classes"].tolist() != list(classes):
            raise ValueError(f"{path} was built for a different class list than its model")
        return cls(z["log0"], z["log1"], z["log2"], float(z["weight"]))
