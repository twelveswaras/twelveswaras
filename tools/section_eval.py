"""Multi-section eval: score several spread-out sections of each clip, report consistency.

    python -m tools.section_eval [--sections 5] [--secs 25]

Mirrors listening to several parts of a performance (what Sathya did by hand: record ~20-30 s at
different points, note the answer, repeat). For each clip in clips.csv it takes N evenly-spread
sections of ~S seconds, runs each through the EXACT production pipeline, and reports every
section's top-1 plus a per-clip consistency summary. Aggregates three real-usage numbers:
  - majority     : the most-common section answer is correct (what a "best of N tries" user gets)
  - any-section  : at least one section got it (top-1) — the raaga is reachable
  - consistency  : mean fraction of sections that agree with the clip's majority answer
Needs the numpy<2 inference env (same as the demo).
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from tools.realworld_eval import _read_csv, parse_clip_list


def section_offsets(dur_s: float, n: int, secs: float) -> list[float]:
    if dur_s <= secs:
        return [0.0]
    import numpy as np
    return [float(x) for x in np.linspace(0.0, dur_s - secs, n)]


def main() -> None:
    ap = argparse.ArgumentParser(description="Score several sections per clip; report consistency.")
    ap.add_argument("--clips", default="benchmark/realworld/clips.csv")
    ap.add_argument("--audio-dir", default="benchmark/realworld/audio")
    ap.add_argument("--model", default="models/raaga_xgb.json")
    ap.add_argument("--sections", type=int, default=5)
    ap.add_argument("--secs", type=float, default=25.0)
    args = ap.parse_args()

    import librosa
    import numpy as np

    from raaga_id import pitch_extract
    from raaga_id.config import TOP_K
    from raaga_id.model import RaagaXGB

    model = RaagaXGB.load(args.model)
    clips, skipped = parse_clip_list(_read_csv(Path(args.clips)), model.classes)
    for s in skipped:
        print(f"  skip {s.file}: {s.reason}")
    pitch_extract.warmup()
    audio_dir = Path(args.audio_dir)

    maj_ok = any_ok = scored = 0
    consist = []
    for c in clips:
        path = audio_dir / c.file
        if not path.exists():
            print(f"  MISSING {path}")
            continue
        y, sr = librosa.load(str(path), sr=None, mono=True)
        dur = len(y) / sr
        picks = []
        for off in section_offsets(dur, args.sections, args.secs):
            seg = y[int(off * sr): int((off + args.secs) * sr)]
            windows, tonic, _, _ = pitch_extract.audio_to_features(seg, sr)
            if not windows:
                picks.append(("—", 0.0))
                continue
            top = model.aggregate_top_k(np.vstack(windows), k=TOP_K)[0]
            picks.append((top.raaga, float(top.confidence)))

        names = [p[0] for p in picks if p[0] != "—"]
        if not names:
            print(f"  {c.file:20s} true={c.raga:16s} NO PREDICTION in any section")
            continue
        scored += 1
        maj, maj_n = Counter(names).most_common(1)[0]
        cons = maj_n / len(names)
        consist.append(cons)
        maj_correct = maj == c.raga
        any_correct = c.raga in names
        maj_ok += maj_correct
        any_ok += any_correct
        cells = "  ".join(f"{n[:9]}" + (f" {int(p*100)}%" if p else "") for n, p in picks)
        flag = "✓maj" if maj_correct else ("·any" if any_correct else "✗")
        print(f"  {c.file:20s} true={c.raga:16s} [{flag}] cons={cons:.0%}  |  {cells}")

    print(f"\nSECTION EVAL  ({args.sections}×{args.secs:.0f}s per clip)  scored={scored}")
    if scored:
        print(f"  majority-correct   {maj_ok}/{scored} = {maj_ok/scored:.3f}   (best-of-N user)")
        print(f"  any-section-correct{any_ok}/{scored} = {any_ok/scored:.3f}   (raaga reachable)")
        print(f"  mean consistency   {sum(consist)/len(consist):.3f}          (sections agreeing)")


if __name__ == "__main__":
    main()
