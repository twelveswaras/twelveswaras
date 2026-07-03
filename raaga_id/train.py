"""Training entrypoint (PRD §17, build-order step 5).

    python -m raaga_id.train

Floor path (D16 step 1): split Saraga tracks train/test BY TRACK (frozen benchmark,
no window leakage) -> window the train tracks into 10 s clips (D7) -> extract frame
vectors -> fit the XGBoost baseline -> save.
"""
from __future__ import annotations

import argparse

import numpy as np

from . import data, features
from .config import MODELS_DIR
from .model import RaagaXGB


def build_windowed(clips, max_windows: int | None):
    """Return (X, y) of per-window vectors labelled with each window's track raaga."""
    X, y = [], []
    for clip in clips:
        try:
            vecs = features.extract_windows(str(clip.audio_path), max_windows=max_windows,
                                            tonic_hz=clip.tonic_hz)
        except Exception as exc:  # noqa: BLE001 — skip unreadable clips, keep going
            print(f"  skip {clip.track_id}: {exc}")
            continue
        X.extend(vecs)
        y.extend([clip.raaga] * len(vecs))
    if not X:
        raise SystemExit(
            "No windows extracted. Download Saraga first: "
            "python -c 'from raaga_id.data import download_saraga; download_saraga()'"
        )
    return np.vstack(X), np.array(y)


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the v0 raaga floor (XGBoost).")
    ap.add_argument("--out", default=str(MODELS_DIR / "raaga_xgb.json"))
    ap.add_argument("--max-windows", type=int, default=60, help="cap windows/track (bounds compute)")
    ap.add_argument("--test-frac", type=float, default=0.25)
    args = ap.parse_args()

    clips = list(data.iter_clips(only_vocab=True))
    if not clips:
        raise SystemExit("No labelled clips in the v0 vocab — check raagas.json / Saraga download.")

    train_ids, test_ids = data.split_by_track(clips, test_frac=args.test_frac)
    train_clips = [c for c in clips if c.track_id in train_ids]
    print(f"{len(clips)} tracks -> {len(train_clips)} train / {len(test_ids)} test "
          f"(frozen: {data.FROZEN_TEST_PATH})")

    X, y = build_windowed(train_clips, args.max_windows)
    classes = sorted(set(y))
    idx = {c: i for i, c in enumerate(classes)}
    y_idx = np.array([idx[c] for c in y])

    print(f"training on {len(X)} windows across {len(classes)} raagas: {classes}")
    model = RaagaXGB(classes).fit(X, y_idx)
    path = model.save(args.out)
    print(f"saved -> {path}\nnext: python -m raaga_id.evaluate --model {path}")


if __name__ == "__main__":
    main()
