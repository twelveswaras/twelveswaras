"""Training entrypoint (PRD §17, build-order step 5).

    python -m raaga_id.train [--datasets saraga_carnatic compmusic_raga]

Floor (D16): a tonic-normalized pitch-class distribution (PCD) over each recording's
predominant-melody pitch track, windowed (D7), classified by XGBoost. Split is BY
TRACK (frozen benchmark, no window leakage). Pools any datasets that expose pitch +
tonic (Saraga, IAMRRD).
"""
from __future__ import annotations

import argparse

import numpy as np

from . import data, features
from .config import MODELS_DIR, PCD_BINS
from .model import RaagaXGB


def build_pcd(pclips, max_windows: int | None):
    """(X, y) of per-window PCD vectors labelled with each window's track raaga."""
    X, y = [], []
    for pc in pclips:
        wins = features.pitch_windows(pc.times, pc.freqs, pc.tonic_hz,
                                      max_windows=max_windows, n_bins=PCD_BINS)
        X.extend(wins)
        y.extend([pc.raaga] * len(wins))
    if not X:
        raise SystemExit("No PCD windows — is the dataset downloaded (pitch + tonic present)?")
    return np.vstack(X), np.array(y)


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the raaga floor (PCD + XGBoost).")
    ap.add_argument("--out", default=str(MODELS_DIR / "raaga_xgb.json"))
    ap.add_argument("--datasets", nargs="+", default=["saraga_carnatic"])
    ap.add_argument("--max-windows", type=int, default=60, help="cap windows/track")
    ap.add_argument("--test-frac", type=float, default=0.25)
    args = ap.parse_args()

    pclips = list(data.iter_pitch_clips(only_vocab=True, datasets=tuple(args.datasets)))
    if not pclips:
        raise SystemExit("No labelled pitch clips — check datasets / raagas.json.")

    train_ids, test_ids = data.split_by_track(pclips, test_frac=args.test_frac)
    train_clips = [c for c in pclips if c.track_id in train_ids]
    print(f"{len(pclips)} clips {args.datasets} -> {len(train_clips)} train / {len(test_ids)} test "
          f"(frozen: {data.FROZEN_TEST_PATH})")

    X, y = build_pcd(train_clips, args.max_windows)
    classes = sorted(set(y))
    idx = {c: i for i, c in enumerate(classes)}
    print(f"training on {len(X)} PCD windows across {len(classes)} raagas: {classes}")
    model = RaagaXGB(classes).fit(X, np.array([idx[c] for c in y]))
    path = model.save(args.out)
    print(f"saved -> {path}\nnext: python -m raaga_id.evaluate --model {path}")


if __name__ == "__main__":
    main()
