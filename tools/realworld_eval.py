"""Real-world benchmark: score the production recognizer on YOUR clips (concert / phone / YT).

    python -m tools.realworld_eval [--clips benchmark/realworld/clips.csv] \
                                   [--model models/raaga_xgb.json]

Our frozen benchmark is clean *studio* audio (top1 0.798). This measures the number that
actually matters — accuracy on real-world clips (phone mics, room acoustics, concert halls) —
and breaks it down BY DRONE PRESENCE, which directly tests the tonic/drone-dependency
hypothesis. You supply a clip-list CSV (see benchmark/realworld/README.md); each clip runs
through the EXACT production pipeline (audio_to_features -> model). Requires the numpy<2
inference env (essentia + compiam), same as the demo.

Legal line: use clips privately to MEASURE accuracy. Do not redistribute copyrighted audio;
that is separate from the rights-clean CC-BY commons. The audio dir + filled clips.csv are
gitignored — only the schema template and this harness are tracked.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from raaga_id.config import fold_raaga

TRUTHY = {"yes", "y", "true", "1", "drone"}
FALSY = {"no", "n", "false", "0", "nodrone", "none"}


@dataclass
class Clip:
    file: str
    raga: str          # canonical (model-class) spelling
    source: str
    license: str
    drone: bool | None
    notes: str = ""


@dataclass
class Skipped:
    file: str
    reason: str


@dataclass
class Result:
    file: str
    raga: str
    top1: bool | None   # None = no prediction (no tonic/melody found — itself a real failure mode)
    top3: bool | None
    rank: int | None
    drone: bool | None = None


def _parse_drone(v: str) -> bool | None:
    v = (v or "").strip().lower()
    if v in TRUTHY:
        return True
    if v in FALSY:
        return False
    return None


def parse_clip_list(rows, vocab) -> tuple[list[Clip], list[Skipped]]:
    """Validate rows against the model vocabulary. A row is kept only if it has a file and its
    raga folds to one of the model's classes; the canonical (model-class) spelling is stored so
    scoring compares like-for-like. Returns (clips, skipped-with-reasons)."""
    fold_to_canon = {fold_raaga(c): c for c in vocab}
    clips, skipped = [], []
    for row in rows:
        f = (row.get("file") or "").strip()
        raw_raga = (row.get("raga") or "").strip()
        if not f:
            skipped.append(Skipped(f or "(blank)", "no file given"))
            continue
        canon = fold_to_canon.get(fold_raaga(raw_raga))
        if canon is None:
            skipped.append(Skipped(f, f"raga '{raw_raga}' not in the 40-raaga vocab"))
            continue
        clips.append(Clip(file=f, raga=canon, source=(row.get("source") or "").strip(),
                          license=(row.get("license") or "").strip(),
                          drone=_parse_drone(row.get("drone", "")), notes=(row.get("notes") or "").strip()))
    return clips, skipped


def score_clip(preds, true_raga) -> tuple[bool, bool, int | None]:
    """(top1, top3, rank) for a decoded top-k prediction list vs the true raaga."""
    names = [p.raaga for p in preds]
    rank = names.index(true_raga) + 1 if true_raga in names else None
    return names[0] == true_raga, rank is not None, rank


def summarize(results: list[Result]) -> dict:
    """Overall top-1/top-3 over SCORED clips (those that got a prediction), plus a drone
    breakdown and the count of clips that produced no prediction at all."""
    scored = [r for r in results if r.top1 is not None]
    no_pred = [r for r in results if r.top1 is None]

    def rate(rs, attr):
        return sum(getattr(r, attr) for r in rs) / len(rs) if rs else 0.0

    by_drone = {}
    for key, want in (("yes", True), ("no", False), ("unknown", None)):
        grp = [r for r in scored if r.drone is want]
        if grp:
            by_drone[key] = {"n": len(grp), "top1": rate(grp, "top1"), "top3": rate(grp, "top3")}
    return {
        "n": len(results), "scored": len(scored), "no_prediction": len(no_pred),
        "top1": rate(scored, "top1"), "top3": rate(scored, "top3"), "by_drone": by_drone,
    }


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return [r for r in csv.DictReader(fh) if not (r.get("file", "") or "").lstrip().startswith("#")]


def main() -> None:
    ap = argparse.ArgumentParser(description="Score the recognizer on real-world clips.")
    ap.add_argument("--clips", default="benchmark/realworld/clips.csv")
    ap.add_argument("--audio-dir", default="benchmark/realworld/audio")
    ap.add_argument("--model", default="models/raaga_xgb.json")
    args = ap.parse_args()

    import librosa

    from raaga_id import pitch_extract
    from raaga_id.config import TOP_K
    from raaga_id.model import RaagaXGB

    clips_path = Path(args.clips)
    if not clips_path.exists():
        raise SystemExit(f"no clip-list at {clips_path} — copy benchmark/realworld/clips.example.csv "
                         f"to {clips_path} and fill it in (see benchmark/realworld/README.md).")

    model = RaagaXGB.load(args.model)
    clips, skipped = parse_clip_list(_read_csv(clips_path), model.classes)
    for s in skipped:
        print(f"  skip {s.file}: {s.reason}", flush=True)
    if not clips:
        raise SystemExit("no valid clips to score — check labels are in-vocab and files are listed.")

    pitch_extract.warmup()
    audio_dir = Path(args.audio_dir)
    results = []
    for c in clips:
        path = audio_dir / c.file
        if not path.exists():
            print(f"  MISSING {path}", flush=True)
            continue
        try:
            y, sr = librosa.load(str(path), sr=None, mono=True)
        except Exception as e:  # noqa: BLE001
            print(f"  DECODE-FAIL {c.file}: {e}", flush=True)
            continue
        windows, tonic, _, _ = pitch_extract.audio_to_features(y, sr)
        if not windows:
            results.append(Result(c.file, c.raga, None, None, None, drone=c.drone))
            print(f"  {c.file:32s} -> NO PREDICTION (no tonic/melody)   true={c.raga}", flush=True)
            continue
        import numpy as np
        preds = model.aggregate_top_k(np.vstack(windows), k=TOP_K)
        t1, t3, rank = score_clip(preds, c.raga)
        results.append(Result(c.file, c.raga, t1, t3, rank, drone=c.drone))
        mark = "✓" if t1 else ("·3" if t3 else "✗")
        print(f"  {c.file:32s} -> {preds[0].raaga:18s} {mark}  true={c.raga} "
              f"(rank {rank}, Sa≈{tonic:.0f})", flush=True)

    s = summarize(results)
    print(f"\nREAL-WORLD: n={s['n']} scored={s['scored']} no-prediction={s['no_prediction']}")
    print(f"  top1={s['top1']:.3f}  top3={s['top3']:.3f}   (studio frozen: top1 0.798 / top3 0.938)")
    for k, v in s["by_drone"].items():
        print(f"  drone={k:7s} n={v['n']:2d}  top1={v['top1']:.3f}  top3={v['top3']:.3f}")


if __name__ == "__main__":
    main()
