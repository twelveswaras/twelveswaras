"""Evaluation against the frozen studio benchmark (benchmark/test_track_ids.json).

    python -m raaga_id.evaluate --model models/raaga_xgb.swara.json [--datasets saraga_carnatic]

Scores per TRACK: window each held-out recording exactly as the model was trained (windowed
TDMS plus each window's swara phrases), average the window probabilities, take the top-3, and
compare with the true raaga. Corpus labels are bare Carnatic names; the live model's classes
carry a tradition tag, so a label is matched in its tagged form when the model uses one.
"""
from __future__ import annotations

import argparse

import numpy as np

from . import data, features
from .config import TOP_K
from .model import RaagaXGB
from .tradition import CARNATIC, tag


def score(model: RaagaXGB, clips, max_windows: int | None = None) -> tuple[int, int, int]:
    """(tracks scored, top-1 hits, top-k hits) for labelled pitch clips."""
    n = top1 = topk = 0
    for pc in clips:
        windows, phrases = features.model_windows(pc.times, pc.freqs, pc.tonic_hz,
                                                  max_windows=max_windows, phrases=True)
        if not windows:
            continue
        truth = tag(pc.raaga, CARNATIC) if tag(pc.raaga, CARNATIC) in model.classes else pc.raaga
        names = [p.raaga for p in model.aggregate_top_k(np.vstack(windows), k=TOP_K,
                                                        phrases=phrases if model.chains else None)]
        n += 1
        top1 += int(names[0] == truth)
        topk += int(truth in names)
    return n, top1, topk


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the raaga model on the frozen benchmark.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--datasets", nargs="+", default=["saraga_carnatic"])
    ap.add_argument("--max-windows", type=int, default=None)
    args = ap.parse_args()

    frozen = data.load_frozen_test()
    if frozen is None:
        raise SystemExit("no frozen benchmark at benchmark/test_track_ids.json")
    clips = (pc for pc in data.iter_pitch_clips(only_vocab=True, datasets=tuple(args.datasets))
             if pc.track_id in frozen)
    n, top1, topk = score(RaagaXGB.load(args.model), clips, args.max_windows)
    if n == 0:
        raise SystemExit("no evaluation tracks matched the frozen split; check the data.")
    print(f"n={n} tracks  top1={top1 / n:.3f}  top{TOP_K}={topk / n:.3f}")


if __name__ == "__main__":
    main()
