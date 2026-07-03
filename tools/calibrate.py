"""Fit the calibration temperature for the raaga floor (D25).

    python -m tools.calibrate [-k 4] [--datasets saraga_carnatic compmusic_raga] \
                              [--model models/raaga_xgb.json]

Temperature scaling needs held-out predictions, so we reuse the track-level k-fold scheme
(same as tools/cross_validate): every track is predicted exactly once by a model that did NOT
train on it. We fit one scalar T on those out-of-fold aggregated probabilities (minimizing
NLL), report ECE/NLL before vs after, and write it to <model>.calib.json. T is argmax-
preserving, so top-1/top-3 accuracy is unchanged — only the confidence numbers become honest.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict

import numpy as np

from raaga_id import calibrate, data, features
from raaga_id.config import MODELS_DIR, PCD_BINS
from raaga_id.model import RaagaXGB


def oof_predictions(per_track, classes, k, n_estimators):
    """Aggregated softmax + true index for every track, from a fold that excluded it."""
    cidx = {c: i for i, c in enumerate(classes)}
    by_raaga: dict[str, list[int]] = defaultdict(list)
    for i, (_, r, _) in enumerate(per_track):
        by_raaga[r].append(i)
    rng = random.Random(0)
    folds: list[list[int]] = [[] for _ in range(k)]
    for idxs in by_raaga.values():
        idxs = idxs[:]
        rng.shuffle(idxs)
        for j, i in enumerate(idxs):
            folds[j % k].append(i)

    P, y = np.zeros((len(per_track), len(classes))), np.zeros(len(per_track), dtype=int)
    for kf in range(k):
        test_idx = set(folds[kf])
        Xtr, ytr = [], []
        for i, (_, r, Xw) in enumerate(per_track):
            if i not in test_idx:
                Xtr.append(Xw)
                ytr += [r] * len(Xw)
        model = RaagaXGB(classes).fit(np.vstack(Xtr), np.array([cidx[c] for c in ytr]),
                                      n_estimators=n_estimators)
        for i in folds[kf]:
            _, r, Xw = per_track[i]
            P[i] = model.predict_proba(Xw).mean(axis=0)   # pre-temperature aggregate
            y[i] = cidx[r]
        print(f"  fold {kf + 1}/{k} done", flush=True)
    return P, y


def main() -> None:
    ap = argparse.ArgumentParser(description="Fit the calibration temperature (D25).")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--datasets", nargs="+", default=["saraga_carnatic", "compmusic_raga"])
    ap.add_argument("--max-windows", type=int, default=60)
    ap.add_argument("--n-estimators", type=int, default=300)
    ap.add_argument("--model", default=str(MODELS_DIR / "raaga_xgb.json"))
    args = ap.parse_args()

    per_track = []
    for pc in data.iter_pitch_clips(only_vocab=True, datasets=tuple(args.datasets)):
        wins = features.pitch_windows(pc.times, pc.freqs, pc.tonic_hz,
                                      max_windows=args.max_windows, n_bins=PCD_BINS)
        if wins:
            per_track.append((pc.track_id, pc.raaga, np.vstack(wins)))
    if not per_track:
        raise SystemExit("No PCD features — datasets downloaded (pitch + tonic)?")
    classes = sorted({r for _, r, _ in per_track})
    print(f"tracks: {len(per_track)} · raagas: {len(classes)} · {args.k}-fold OOF calibration")

    P, y = oof_predictions(per_track, classes, args.k, args.n_estimators)
    T = calibrate.fit_temperature(P, y)
    Pc = calibrate.apply_temperature(P, T)
    acc = float((P.argmax(1) == y).mean())
    print(f"\ntop-1 (unchanged by calibration): {acc:.3f}   fitted temperature T = {T:.3f}")
    print(f"  NLL  {calibrate.nll(P, y):.3f} -> {calibrate.nll(Pc, y):.3f}")
    print(f"  ECE  {calibrate.ece(P, y):.3f} -> {calibrate.ece(Pc, y):.3f}   (lower = better)")
    print(f"  mean top-1 confidence  {P.max(1).mean():.3f} -> {Pc.max(1).mean():.3f}")

    path = calibrate.save_temperature(args.model, T, extra={
        "fit": {"method": "temperature", "k": args.k, "n_tracks": len(per_track),
                "nll_before": round(calibrate.nll(P, y), 4), "nll_after": round(calibrate.nll(Pc, y), 4),
                "ece_before": round(calibrate.ece(P, y), 4), "ece_after": round(calibrate.ece(Pc, y), 4)}})
    print(f"saved -> {path}")


if __name__ == "__main__":
    main()
