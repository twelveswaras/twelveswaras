"""Evaluation against the frozen benchmark (PRD §15, build-order step 6).

    python -m raaga_id.evaluate --model models/raaga_xgb.json

Scores per TRACK on the frozen test split: PCD-window each held-out recording, average
the window probabilities (D7), take top-k, compare to the true raaga. Top-3 is the
headline (the product shows top-3, D6). The frozen benchmark stays the original Saraga
test tracks so numbers compare across features/data.
"""
from __future__ import annotations

import argparse

import numpy as np

from . import data, features
from .config import TOP_K
from .model import RaagaXGB


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the raaga model on the frozen benchmark.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--datasets", nargs="+", default=["saraga_carnatic"])
    ap.add_argument("--max-windows", type=int, default=None)
    args = ap.parse_args()

    model = RaagaXGB.load(args.model)
    frozen = data.load_frozen_test()
    if frozen is None:
        raise SystemExit("No frozen benchmark yet — run `python -m raaga_id.train` first "
                         "(it freezes benchmark/test_track_ids.json).")

    top1 = top3 = n = 0
    for pc in data.iter_pitch_clips(only_vocab=True, datasets=tuple(args.datasets)):
        if pc.track_id not in frozen:
            continue
        wins = features.model_windows(pc.times, pc.freqs, pc.tonic_hz, max_windows=args.max_windows)
        if not wins:
            continue
        names = [p.raaga for p in model.aggregate_top_k(np.vstack(wins), k=TOP_K)]
        n += 1
        top1 += int(names[0] == pc.raaga)
        top3 += int(pc.raaga in names)

    if n == 0:
        raise SystemExit("no evaluation tracks matched the frozen split — check the data.")
    print(f"n={n} tracks  top1={top1 / n:.3f}  top{TOP_K}={top3 / n:.3f}")


if __name__ == "__main__":
    main()
