"""Evaluation against the frozen benchmark (PRD §15, build-order step 6).

    python -m raaga_id.evaluate --model models/raaga_xgb.json

Scores per TRACK on the frozen test split: window each held-out recording, average
the window probabilities (D7), take top-k, compare to the true raaga. Reports top-1
and top-3 accuracy — top-3 is the headline since the product shows top-3 (D6).
"""
from __future__ import annotations

import argparse

from . import data, features
from .config import TOP_K
from .model import RaagaXGB


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the raaga model on the frozen benchmark.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--max-windows", type=int, default=60)
    args = ap.parse_args()

    model = RaagaXGB.load(args.model)
    frozen = data.load_frozen_test()
    if frozen is None:
        raise SystemExit("No frozen benchmark yet — run `python -m raaga_id.train` first "
                         "(it freezes benchmark/test_track_ids.json).")

    top1 = top3 = n = 0
    for clip in data.iter_clips(only_vocab=True):
        if clip.track_id not in frozen:
            continue
        try:
            vecs = features.extract_windows(str(clip.audio_path), max_windows=args.max_windows)
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {clip.track_id}: {exc}")
            continue
        if not vecs:
            continue
        names = [p.raaga for p in model.aggregate_top_k(vecs, k=TOP_K)]
        n += 1
        top1 += int(names[0] == clip.raaga)
        top3 += int(clip.raaga in names)

    if n == 0:
        raise SystemExit("no evaluation tracks matched the frozen split — check the data.")
    print(f"n={n} tracks  top1={top1 / n:.3f}  top{TOP_K}={top3 / n:.3f}")


if __name__ == "__main__":
    main()
