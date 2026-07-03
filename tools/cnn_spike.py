"""SPIKE: does a 2-D CNN on the TDMS surface beat the XGBoost floor (frozen 0.798)? (D16 deep rung)

    python -m tools.cnn_spike [--datasets saraga_carnatic compmusic_raga] [--epochs 40]

The TDMS surface is a 48x48 image, so a small CNN can learn spatial gamaka structure the
flat-vector XGBoost can't. Reuses the FROZEN split (data.load_frozen_test) so top1/top3 compare
directly to the production XGBoost (frozen top1 0.798 / top3 0.938). Per-track aggregation = mean
softmax over the track's window surfaces, matching RaagaXGB.aggregate_top_k. Windowed-TDMS
extraction is cached to data/tdms_cache.npz (gitignored) so re-runs are fast.

This is an experiment: it prints the number and DOES NOT touch the production model. If the CNN
wins, promote RaagaCNN + add tests + retrain/recalibrate/redeploy (with sign-off).
"""
from __future__ import annotations

import argparse

import numpy as np

from raaga_id import data, features
from raaga_id.config import DATA_DIR, TDMS_BINS, TOP_K

CACHE = DATA_DIR / "tdms_cache.npz"


def build_cache(datasets) -> None:
    """Extract windowed-TDMS for every clip once and save a flat cache with per-window track
    ids + a track->raaga + frozen-test map."""
    frozen = data.load_frozen_test() or set()
    X, win_track, track_raaga, track_is_test = [], [], {}, {}
    tid = 0
    for pc in data.iter_pitch_clips(only_vocab=True, datasets=tuple(datasets)):
        wins = features.model_windows(pc.times, pc.freqs, pc.tonic_hz)
        if not wins:
            continue
        track_raaga[tid] = pc.raaga
        track_is_test[tid] = pc.track_id in frozen
        for w in wins:
            X.append(w)
            win_track.append(tid)
        tid += 1
        if tid % 50 == 0:
            print(f"  cached {tid} tracks…", flush=True)
    if not X:
        raise SystemExit("No TDMS windows — datasets downloaded (pitch + tonic)?")
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        CACHE, X=np.asarray(X, np.float32), win_track=np.asarray(win_track, np.int32),
        track_ids=np.asarray(sorted(track_raaga), np.int32),
        track_raaga=np.asarray([track_raaga[t] for t in sorted(track_raaga)]),
        track_is_test=np.asarray([track_is_test[t] for t in sorted(track_raaga)], bool))
    print(f"cached {len(X)} windows / {tid} tracks -> {CACHE}", flush=True)


def _prep(x):
    """Peaky-histogram transform: sqrt compresses the diagonal + emphasizes the faint off-diagonal
    gamaka smears; per-image max-norm makes it scale-free. Shape -> (N,1,B,B)."""
    x = np.sqrt(np.clip(x, 0, None))
    x = x / (x.max(axis=1, keepdims=True) + 1e-8)
    return x.reshape(-1, 1, TDMS_BINS, TDMS_BINS)


def main() -> None:
    ap = argparse.ArgumentParser(description="CNN-on-TDMS spike vs the XGBoost floor.")
    ap.add_argument("--datasets", nargs="+", default=["saraga_carnatic", "compmusic_raga"])
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args()

    import torch
    from torch import nn

    if args.rebuild_cache or not CACHE.exists():
        build_cache(args.datasets)
    z = np.load(CACHE, allow_pickle=True)
    X, win_track = z["X"], z["win_track"]
    track_raaga, track_is_test = z["track_raaga"], z["track_is_test"]

    classes = sorted(set(track_raaga.tolist()))
    cidx = {c: i for i, c in enumerate(classes)}
    dev = "mps" if torch.backends.mps.is_available() else "cpu"

    y_win = np.array([cidx[track_raaga[t]] for t in win_track])
    is_test_win = np.array([track_is_test[t] for t in win_track])
    Xtr = torch.tensor(_prep(X[~is_test_win]))
    ytr = torch.tensor(y_win[~is_test_win], dtype=torch.long)
    n_test_tracks = int(track_is_test.sum())
    print(f"windows: {len(X)} ({len(Xtr)} train) · {len(classes)} raagas · {n_test_tracks} frozen-test "
          f"tracks · device {dev}", flush=True)

    def block(cin, cout):
        return nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1), nn.BatchNorm2d(cout),
                             nn.ReLU(), nn.MaxPool2d(2))

    # NB: no global-average-pool head — the raga identity is the *spatial position* of the
    # off-diagonal gamaka mass, so we FLATTEN the 6x6x64 map (position preserved) into the FC,
    # then let the conv stack add local spatial inductive bias on top of what XGBoost already gets.
    feat = TDMS_BINS // 8  # three /2 pools: 48 -> 6
    model = nn.Sequential(
        block(1, 32), block(32, 64), block(64, 64),
        nn.Flatten(), nn.Dropout(0.3),
        nn.Linear(64 * feat * feat, 128), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(128, len(classes)),
    ).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    lossf = nn.CrossEntropyLoss()

    n = len(Xtr)
    for ep in range(args.epochs):
        model.train()
        perm = torch.randperm(n)
        tot = 0.0
        for i in range(0, n, args.batch):
            b = perm[i:i + args.batch]
            xb, yb = Xtr[b].to(dev), ytr[b].to(dev)
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            opt.step()
            tot += loss.item() * len(b)
        if (ep + 1) % 5 == 0 or ep == 0:
            print(f"  epoch {ep + 1}/{args.epochs}  loss={tot / n:.3f}", flush=True)

    # Per-track aggregation on the frozen test set: mean softmax over the track's windows.
    model.eval()
    top1 = top3 = 0
    test_tracks = [t for t in sorted(set(win_track.tolist())) if track_is_test[t]]
    with torch.no_grad():
        for t in test_tracks:
            m = win_track == t
            xb = torch.tensor(_prep(X[m])).to(dev)
            proba = torch.softmax(model(xb), dim=1).mean(0).cpu().numpy()
            order = proba.argsort()[::-1]
            true = cidx[track_raaga[t]]
            top1 += int(order[0] == true)
            top3 += int(true in order[:TOP_K])
    nt = len(test_tracks)
    print(f"\nCNN-on-TDMS  frozen n={nt}  top1={top1 / nt:.3f}  top3={top3 / nt:.3f}")
    print("  baseline (XGBoost on TDMS): frozen top1 0.798 / top3 0.938")


if __name__ == "__main__":
    main()
