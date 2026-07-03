"""Track-level k-fold cross-validation for the floor model.

    python -m tools.cross_validate [-k 4] [--max-windows 60]

The single frozen holdout (benchmark/) is small and noisy on Saraga's sparse data.
This extracts per-track window features ONCE, then refits XGBoost per fold so every
track is evaluated exactly once as a held-out test track — a more reliable estimate.
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict

import numpy as np

from raaga_id import data, features
from raaga_id.model import RaagaXGB


def main() -> None:
    ap = argparse.ArgumentParser(description="k-fold track-level CV of the raaga floor.")
    ap.add_argument("-k", type=int, default=4)
    ap.add_argument("--max-windows", type=int, default=60)
    args = ap.parse_args()

    # 1) extract per-track window features once
    per_track = []  # (track_id, raaga, X_windows)
    for c in data.iter_clips(only_vocab=True):
        vecs = features.extract_windows(str(c.audio_path), max_windows=args.max_windows)
        if vecs:
            per_track.append((c.track_id, c.raaga, np.vstack(vecs)))
    if not per_track:
        raise SystemExit("No features — is Saraga downloaded and raagas.json finalized?")
    print(f"tracks with features: {len(per_track)}")

    classes = sorted({r for _, r, _ in per_track})
    cidx = {c: i for i, c in enumerate(classes)}

    # 2) stratified assignment of tracks to K folds
    by_raaga: dict[str, list[int]] = defaultdict(list)
    for i, (_, r, _) in enumerate(per_track):
        by_raaga[r].append(i)
    rng = random.Random(0)
    folds: list[list[int]] = [[] for _ in range(args.k)]
    for _, idxs in by_raaga.items():
        idxs = idxs[:]
        rng.shuffle(idxs)
        for j, i in enumerate(idxs):
            folds[j % args.k].append(i)

    # 3) cross-validate
    t1 = t3 = n = 0
    for k in range(args.k):
        test_idx = set(folds[k])
        Xtr, ytr = [], []
        for i, (_, r, Xw) in enumerate(per_track):
            if i in test_idx:
                continue
            Xtr.append(Xw)
            ytr += [r] * len(Xw)
        model = RaagaXGB(classes).fit(np.vstack(Xtr), np.array([cidx[y] for y in ytr]), n_estimators=300)
        for i in folds[k]:
            _, r, Xw = per_track[i]
            names = [p.raaga for p in model.aggregate_top_k(Xw)]
            n += 1
            t1 += names[0] == r
            t3 += r in names
        print(f"  fold {k + 1}/{args.k} done")

    c = len(classes)
    print(f"\n{args.k}-fold track-level CV over n={n} tracks, {c} raagas:")
    print(f"  top1={t1/n:.3f}  top3={t3/n:.3f}   (chance: top1={1/c:.3f}, top3={3/c:.3f})")


if __name__ == "__main__":
    main()
