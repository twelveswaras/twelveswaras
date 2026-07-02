"""Evaluation against the frozen benchmark (PRD §15 EVALUATION, build-order step 6).

    python -m raaga_id.evaluate --model models/raaga_xgb.json

Reports top-1 and top-3 accuracy (D6 surfaces top-3, so top-3 accuracy is the
headline metric). The benchmark test set is frozen the moment it exists so scores
stay comparable across model rungs (XGBoost -> CNN -> TDMS).
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from . import data, features
from .config import BENCHMARK_DIR, TOP_K
from .model import RaagaXGB

BENCHMARK_IDS = BENCHMARK_DIR / "test_track_ids.json"


def _frozen_ids() -> set[str] | None:
    if BENCHMARK_IDS.exists():
        return set(json.loads(BENCHMARK_IDS.read_text()))
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the raaga model on the frozen benchmark.")
    ap.add_argument("--model", required=True)
    args = ap.parse_args()

    model = RaagaXGB.load(args.model)
    frozen = _frozen_ids()
    if frozen is None:
        print("⚠ no frozen benchmark yet (benchmark/test_track_ids.json missing) — "
              "freeze one before trusting these numbers.")

    top1 = top3 = n = 0
    for clip in data.iter_clips(only_vocab=True):
        if frozen is not None and clip.track_id not in frozen:
            continue
        preds = model.top_k(features.extract(str(clip.audio_path)), k=TOP_K)
        names = [p.raaga for p in preds]
        n += 1
        top1 += int(names[0] == clip.raaga)
        top3 += int(clip.raaga in names)

    if n == 0:
        raise SystemExit("no evaluation clips matched — check the benchmark split / data.")
    print(f"n={n}  top1={top1 / n:.3f}  top{TOP_K}={top3 / n:.3f}")


if __name__ == "__main__":
    main()
