"""Compute per-raaga reference swara profiles for the 'How to hear this raaga' learner
panel: each raaga's average 12-position pitch-class profile over its windows.

    python -m tools.build_raaga_profiles

Built from the Raga Recognition Dataset features (CC-BY-4.0) only, so the file can ship in this
repository: Saraga is CC-BY-NC-SA, and its terms would carry over to profiles averaged from it.
data/compmusic_raga is archived; unpack it first (zstd -dc compmusic_raga.tar.zst | tar -xf -).

Writes raaga_profiles.json {raaga: [12 floats]} at the repo root.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np

from raaga_id import data, features
from raaga_id.config import PCD_BINS, ROOT

DATASETS = ("compmusic_raga",)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build per-raaga reference swara profiles.")
    ap.add_argument("--max-windows", type=int, default=60)
    args = ap.parse_args()

    acc: dict[str, list] = defaultdict(list)
    for pc in data.iter_pitch_clips(only_vocab=True, datasets=DATASETS):
        for w in features.pitch_windows(pc.times, pc.freqs, pc.tonic_hz,
                                        max_windows=args.max_windows, n_bins=PCD_BINS):
            acc[pc.raaga].append(features.pcd_to_swaras(w))

    profiles = {r: np.mean(v, axis=0).round(4).tolist() for r, v in acc.items() if v}
    out = ROOT / "raaga_profiles.json"
    out.write_text(json.dumps(profiles, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {len(profiles)} raaga profiles -> {out}")


if __name__ == "__main__":
    main()
