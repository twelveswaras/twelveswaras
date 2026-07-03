"""Gate for productionizing TDMS (D28): does WINDOWED TDMS beat WINDOWED PCD?

    python -m tools.tdms_benchmark [--datasets saraga_carnatic compmusic_raga] [-k 4]

The D28 experiment was track-level (TDMS 0.725 < production 0.780). But production PCD is
windowed + aggregated, which lifted PCD ~+12 pts. This reruns the SAME windowed + mean-proba
aggregation the deployed model uses, on identical folds, so the numbers compare directly to the
0.780 frozen-CV production baseline. Every track carries all feature variants, so the split is
shared. If a windowed-TDMS variant wins, that's the config to retrain + ship.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict

import numpy as np

from raaga_id import data, features
from raaga_id.config import PCD_BINS, fold_raaga
from raaga_id.model import RaagaXGB

ALLIED = ["Mohanam", "Bilahari", "Begada"]


def make_folds(labels, k, seed=0):
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


def cv_aggregate(per_track, classes, folds, n_estimators):
    """per_track: list of (raaga, X_windows). Track top-1/top-3 by mean-proba aggregation."""
    cidx = {c: i for i, c in enumerate(classes)}
    y = np.array([cidx[r] for r, _ in per_track])
    pred = np.full(len(per_track), -1)
    top3 = np.zeros(len(per_track), dtype=bool)
    for f, te in enumerate(folds):
        te_set = set(te)
        Xtr, ytr = [], []
        for i, (r, Xw) in enumerate(per_track):
            if i not in te_set:
                Xtr.append(Xw)
                ytr += [cidx[r]] * len(Xw)
        model = RaagaXGB(classes).fit(np.vstack(Xtr), np.array(ytr), n_estimators=n_estimators)
        for i in te:
            proba = model.predict_proba(per_track[i][1]).mean(axis=0)
            order = np.argsort(proba)[::-1]
            pred[i] = order[0]
            top3[i] = y[i] in order[:3]
        print(f"    fold {f + 1}/{len(folds)} done", flush=True)
    return pred, y, float(top3.mean())


def main() -> None:
    ap = argparse.ArgumentParser(description="Windowed TDMS vs PCD gate (D28).")
    ap.add_argument("--datasets", nargs="+", default=["saraga_carnatic", "compmusic_raga"])
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--n-estimators", type=int, default=300)
    args = ap.parse_args()

    variants = {"PCD-10s": [], "TDMS-30s": [], "TDMS-track": []}
    labels = []
    for pc in data.iter_pitch_clips(only_vocab=True, datasets=tuple(args.datasets)):
        pcd = features.pitch_windows(pc.times, pc.freqs, pc.tonic_hz, max_windows=60, n_bins=PCD_BINS)
        td30 = features.tdms_windows(pc.times, pc.freqs, pc.tonic_hz, window_s=30, hop_s=30,
                                     max_windows=20, delay=0.3, n_bins=48)
        tdtrk = features.tdms(pc.times, pc.freqs, pc.tonic_hz, delay=0.3, n_bins=48)
        if not pcd or not td30 or tdtrk.sum() == 0:
            continue
        variants["PCD-10s"].append((pc.raaga, np.vstack(pcd)))
        variants["TDMS-30s"].append((pc.raaga, np.vstack(td30)))
        variants["TDMS-track"].append((pc.raaga, tdtrk.reshape(1, -1)))
        labels.append(pc.raaga)
    if not labels:
        raise SystemExit("No features — datasets downloaded (pitch + tonic)?")

    classes = sorted(set(labels))
    folds = make_folds(labels, args.k)
    allied = {c for c in classes if fold_raaga(c) in {fold_raaga(a) for a in ALLIED}}
    allied_idx = [i for i, r in enumerate(labels) if r in allied]
    c = len(classes)
    print(f"tracks {len(labels)} · raagas {c} · aggregated {args.k}-fold CV (matches production)")
    print("production baseline (windowed PCD): top1 0.780 / top3 0.926\n")

    for name, pt in variants.items():
        dim = pt[0][1].shape[1]
        print(f"  {name} ({dim}d):", flush=True)
        pred, y, top3 = cv_aggregate(pt, classes, folds, args.n_estimators)
        top1 = float((pred == y).mean())
        atop1 = float(np.mean([pred[i] == y[i] for i in allied_idx]))
        print(f"  => {name:11s} top1={top1:.3f}  top3={top3:.3f}   "
              f"ALLIED top1={atop1:.3f} (n={len(allied_idx)})\n", flush=True)


if __name__ == "__main__":
    main()
