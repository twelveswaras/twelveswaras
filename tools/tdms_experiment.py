"""Experiment: does a gamaka feature (TDMS) beat / augment the PCD floor? (refines D16)

    python -m tools.tdms_experiment [--datasets saraga_carnatic compmusic_raga] [-k 4] \
                                    [--delay 0.3] [--tdms-bins 48]

Track-level k-fold CV comparing three feature sets under an IDENTICAL XGBoost + split:
  PCD        — the current 120-bin tonic-normalized pitch-class distribution (WHICH notes)
  TDMS       — the time-delayed melody surface (HOW the notes move: gamaka)
  PCD+TDMS   — concatenation

Reports top-1/top-3 for each, plus accuracy on the allied triple (Mōhanaṁ/Bilahari/Bēgaḍa)
that PCD cannot separate. No new data — same annotated pitch+tonic the floor already uses.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict

import numpy as np

from raaga_id import data, features
from raaga_id.config import fold_raaga
from raaga_id.model import RaagaXGB

ALLIED = ["Mohanam", "Bilahari", "Begada"]   # matched diacritic-insensitively via fold_raaga


def make_folds(labels, k, seed=0):
    """Stratified track-level folds (same scheme as tools/cross_validate)."""
    by = defaultdict(list)
    for i, r in enumerate(labels):
        by[r].append(i)
    rng = random.Random(seed)
    folds = [[] for _ in range(k)]
    for idxs in by.values():
        idxs = idxs[:]
        rng.shuffle(idxs)
        for j, i in enumerate(idxs):
            folds[j % k].append(i)
    return folds


def oof_eval(F, labels, classes, folds, n_estimators):
    """Out-of-fold top-1 prediction + top-3 hit for every track under this feature set."""
    cidx = {c: i for i, c in enumerate(classes)}
    y = np.array([cidx[r] for r in labels])
    pred = np.full(len(labels), -1)
    top3 = np.zeros(len(labels), dtype=bool)
    for f, te in enumerate(folds):
        te_set = set(te)
        tr = [i for i in range(len(labels)) if i not in te_set]
        model = RaagaXGB(classes).fit(F[tr], y[tr], n_estimators=n_estimators)
        proba = model.predict_proba(F[te])
        for row, i in zip(proba, te):
            order = np.argsort(row)[::-1]
            pred[i] = order[0]
            top3[i] = y[i] in order[:3]
        print(f"    fold {f + 1}/{len(folds)} done", flush=True)
    return pred, y, float(top3.mean())


def main() -> None:
    ap = argparse.ArgumentParser(description="TDMS vs PCD gamaka experiment (refines D16).")
    ap.add_argument("--datasets", nargs="+", default=["saraga_carnatic", "compmusic_raga"])
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--delay", type=float, default=0.3)
    ap.add_argument("--tdms-bins", type=int, default=48)
    ap.add_argument("--n-estimators", type=int, default=300)
    args = ap.parse_args()

    pcd_l, tdms_l, labels = [], [], []
    for pc in data.iter_pitch_clips(only_vocab=True, datasets=tuple(args.datasets)):
        pcd = features.pitch_class_histogram(pc.freqs, pc.tonic_hz, n_bins=120)
        surf = features.tdms(pc.times, pc.freqs, pc.tonic_hz, delay=args.delay, n_bins=args.tdms_bins)
        if pcd.sum() == 0 or surf.sum() == 0:
            continue
        pcd_l.append(pcd)
        tdms_l.append(surf)
        labels.append(pc.raaga)
    if not labels:
        raise SystemExit("No features — datasets downloaded (pitch + tonic)?")

    PCD = np.vstack(pcd_l)
    TDMS = np.vstack(tdms_l)
    BOTH = np.hstack([PCD, TDMS])
    classes = sorted(set(labels))
    folds = make_folds(labels, args.k)
    allied = {c for c in classes if fold_raaga(c) in {fold_raaga(a) for a in ALLIED}}
    allied_idx = [i for i, r in enumerate(labels) if r in allied]
    c = len(classes)
    print(f"tracks {len(labels)} · raagas {c} · PCD {PCD.shape[1]}d · TDMS {TDMS.shape[1]}d "
          f"(delay {args.delay}s) · allied set {sorted(allied)} (n={len(allied_idx)})")
    print(f"chance: top1={1 / c:.3f} top3={3 / c:.3f}\n")

    for name, F in [("PCD", PCD), ("TDMS", TDMS), ("PCD+TDMS", BOTH)]:
        print(f"  {name} ({F.shape[1]}d):", flush=True)
        pred, y, top3 = oof_eval(F, labels, classes, folds, args.n_estimators)
        top1 = float((pred == y).mean())
        allied_top1 = float(np.mean([pred[i] == y[i] for i in allied_idx])) if allied_idx else float("nan")
        print(f"  => {name:9s} top1={top1:.3f}  top3={top3:.3f}   "
              f"ALLIED-triple top1={allied_top1:.3f}\n", flush=True)


if __name__ == "__main__":
    main()
