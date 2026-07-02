"""Training entrypoint (PRD §17, build-order step 5).

    python -m raaga_id.train

Floor path: iterate Saraga clips (v0 vocab) -> extract frame vectors -> fit the
XGBoost baseline -> save. Freeze a test split immediately (build-order step 6) so
evaluate.py always scores against the same benchmark.
"""
from __future__ import annotations

import argparse

import numpy as np

from . import data, features
from .config import MODELS_DIR
from .model import RaagaXGB


def build_dataset(only_vocab: bool = True):
    X, y, ids = [], [], []
    for clip in data.iter_clips(only_vocab=only_vocab):
        try:
            X.append(features.extract(str(clip.audio_path)))
            y.append(clip.raaga)
            ids.append(clip.track_id)
        except Exception as exc:  # noqa: BLE001 — skip unreadable clips, keep going
            print(f"  skip {clip.track_id}: {exc}")
    if not X:
        raise SystemExit(
            "No clips found. Download Saraga first: "
            "python -c 'from raaga_id.data import download_saraga; download_saraga()'"
        )
    return np.vstack(X), np.array(y), ids


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the v0 raaga floor (XGBoost).")
    ap.add_argument("--out", default=str(MODELS_DIR / "raaga_xgb.json"))
    ap.add_argument("--all-raagas", action="store_true", help="train on all raagas, not just v0 vocab")
    args = ap.parse_args()

    X, y, _ = build_dataset(only_vocab=not args.all_raagas)
    classes = sorted(set(y))
    idx = {c: i for i, c in enumerate(classes)}
    y_idx = np.array([idx[c] for c in y])

    print(f"training on {len(X)} clips across {len(classes)} raagas: {classes}")
    model = RaagaXGB(classes).fit(X, y_idx)
    path = model.save(args.out)
    print(f"saved -> {path}")


if __name__ == "__main__":
    main()
