"""Probability calibration + confidence state (D25).

The shown %s are the mean of XGBoost softmax over a clip's windows — a *relative* ranking,
not a true likelihood. Two fixes live here:

1. **Temperature scaling** — one scalar T (fit offline on leak-free out-of-fold predictions,
   `tools/calibrate.py`) reshapes the probabilities so the number means what it says, WITHOUT
   changing which raaga wins (argmax-preserving). Stored in a `<model>.calib.json` sidecar.
2. **Confidence state** — turns a flat top-2 into an honest "close call — X vs Y" instead of a
   falsely-precise single answer.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import CLOSE_MARGIN, LOW_CONFIDENCE


def apply_temperature(proba, temperature: float):
    """Temperature-scale a probability vector (or a batch; classes = last axis).

    q_i ∝ p_i**(1/T). T>1 flattens (less confident), T<1 sharpens, T=1 is identity. Monotone,
    so the argmax (winning raaga) never changes — only the spread of the confidences does.
    """
    p = np.asarray(proba, dtype=float)
    q = np.power(np.clip(p, 0.0, None), 1.0 / temperature)
    s = q.sum(axis=-1, keepdims=True)
    s = np.where(s == 0.0, 1.0, s)
    return q / s


def nll(P, y_idx, eps: float = 1e-12) -> float:
    """Mean negative log-likelihood of the true class — the thing temperature scaling minimizes."""
    P = np.atleast_2d(np.asarray(P, dtype=float))
    y = np.asarray(y_idx)
    picked = P[np.arange(len(y)), y]
    return float(-np.mean(np.log(np.clip(picked, eps, 1.0))))


def ece(P, y_idx, n_bins: int = 10) -> float:
    """Expected calibration error: |confidence − accuracy| averaged over confidence bins.
    0 = perfectly calibrated (a bin of "70% sure" predictions is right 70% of the time)."""
    P = np.atleast_2d(np.asarray(P, dtype=float))
    y = np.asarray(y_idx)
    conf = P.max(axis=1)
    correct = (P.argmax(axis=1) == y).astype(float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    e = 0.0
    for b in range(n_bins):
        m = (conf > edges[b]) & (conf <= edges[b + 1])
        if m.any():
            e += m.mean() * abs(conf[m].mean() - correct[m].mean())
    return float(e)


def fit_temperature(P, y_idx, lo: float = 0.2, hi: float = 6.0, n: int = 60) -> float:
    """Return the temperature over [lo, hi] (geometric grid) that minimizes NLL. Grid search —
    no scipy dependency, and T needs no great precision."""
    P = np.atleast_2d(np.asarray(P, dtype=float))
    grid = np.geomspace(lo, hi, n)
    losses = [nll(apply_temperature(P, T), y_idx) for T in grid]
    return float(grid[int(np.argmin(losses))])


def confidence_state(preds, low: float = LOW_CONFIDENCE, close_margin: float = CLOSE_MARGIN):
    """Map a decoded top-k list to (state, note). `unsure` when the top score is below `low`;
    else `close` when the top two are within `close_margin`; else `confident`."""
    p1 = preds[0].confidence
    p2 = preds[1].confidence if len(preds) > 1 else 0.0
    if p1 < low:
        return "unsure", "🤔 not sure — melody or tonic unclear; try a longer, cleaner clip with a drone"
    if p1 - p2 < close_margin:
        return "close", f"🤔 close call — {preds[0].raaga} vs {preds[1].raaga}"
    return "confident", "✓ confident"


# --- sidecar persistence: temperature lives next to the model as <model>.calib.json ---
def temperature_path(model_path) -> Path:
    return Path(model_path).with_suffix(".calib.json")


def load_temperature(model_path, default: float = 1.0) -> float:
    p = temperature_path(model_path)
    if p.exists():
        return float(json.loads(p.read_text()).get("temperature", default))
    return default


def save_temperature(model_path, temperature: float, extra: dict | None = None) -> Path:
    p = temperature_path(model_path)
    payload = {"temperature": float(temperature)}
    if extra:
        payload.update(extra)
    p.write_text(json.dumps(payload, indent=2))
    return p
