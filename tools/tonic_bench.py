"""Score the production tonic (Sa) estimator against hand-annotated tonics.

    python -m tools.tonic_bench [--root data/saraga_carnatic] [--seconds 150]   # inference env

Each Saraga recording ships a `.ctonic.txt` (the annotated Sa, Hz) beside its mix `.mp3`. The
estimator runs exactly as in production (raaga_id.pitch_extract: 44.1 kHz, the first
INFER_SECONDS) and each estimate is classified (see classify): only `pa` / `ma` and `other` are
harmful, because every model feature folds octaves. Results are appended per recording to
supporting-docs/tonic_bench.jsonl, so a stopped run resumes and a finished one does no new work.

Why it matters: a wrong Sa reads the whole melody in the wrong key and gives a confident wrong
raaga, so tonic accuracy caps everything downstream (benchmark/leaderboard.md, 2026-09-14).
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "supporting-docs" / "tonic_bench.jsonl"
TOLERANCE = 50.0   # cents


def classify(estimate_hz: float, truth_hz: float) -> str:
    """exact | octave | pa | ma | other, for an estimate against the annotated Sa."""
    c = 1200 * math.log2(estimate_hz / truth_hz)
    if abs(c) <= TOLERANCE:
        return "exact"
    folded = c % 1200
    near = lambda target: abs(folded - target) <= TOLERANCE   # noqa: E731
    if near(0) or near(1200):
        return "octave"
    if near(700):
        return "pa"
    if near(500):
        return "ma"
    return "other"


def summarize(labels: list[str]) -> dict:
    n = len(labels)
    c = Counter(labels)
    frac = lambda k: c[k] / n if n else float("nan")   # noqa: E731
    return {"n": n, "exact": frac("exact"), "usable": frac("exact") + frac("octave"),
            "pa_ma": frac("pa") + frac("ma"), "other": frac("other"), "counts": dict(c)}


def recordings(root: Path):
    """(id, mix mp3, annotated Sa) for every recording with both. Skips macOS '._' metadata files."""
    for ct in sorted(root.rglob("*.ctonic.txt")):
        if ct.name.startswith("._"):
            continue
        stem = ct.name.removesuffix(".ctonic.txt")
        mix = next((m for m in (ct.with_name(stem + ".mp3"), ct.with_name(stem + ".mp3.mp3")) if m.exists()), None)
        if mix:
            yield str(ct.relative_to(root)), mix, float(ct.read_text().split()[0])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(ROOT / "data" / "saraga_carnatic"))
    ap.add_argument("--seconds", type=float, default=None, help="default: config.INFER_SECONDS")
    args = ap.parse_args()

    import librosa

    from raaga_id import pitch_extract
    from raaga_id.config import INFER_SECONDS

    seconds = args.seconds or INFER_SECONDS
    done = {}
    if RESULTS.exists():
        for line in RESULTS.read_text().splitlines():
            r = json.loads(line)
            done[(r["id"], r["seconds"])] = r
    todo = [r for r in recordings(Path(args.root)) if (r[0], seconds) not in done]
    print(f"{len(todo)} to score, {sum(1 for k in done if k[1] == seconds)} already scored at {seconds:.0f} s", flush=True)

    _, tonic = pitch_extract._extractors()
    t0 = time.time()
    with open(RESULTS, "a") as out:
        for i, (rid, mix, truth) in enumerate(todo, 1):
            y, _ = librosa.load(str(mix), sr=pitch_extract.TONIC_SR, mono=True, duration=seconds)
            try:
                est = float(tonic.extract(y, input_sr=pitch_extract.TONIC_SR))
            except Exception:  # noqa: BLE001  essentia raises on audio with no clear drone
                est = 0.0
            label = classify(est, truth) if est > 0 else "failed"
            r = {"id": rid, "seconds": seconds, "truth_hz": truth, "estimate_hz": est, "label": label}
            out.write(json.dumps(r) + "\n")
            out.flush()
            done[(rid, seconds)] = r
            if i % 25 == 0:
                print(f"  {i}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)

    labels = [r["label"] for k, r in done.items() if k[1] == seconds]
    s = summarize(labels)
    print(f"\nTONIC at {seconds:.0f} s, n={s['n']}: exact {s['exact']:.3f} | usable (exact or octave) "
          f"{s['usable']:.3f} | on Pa/Ma {s['pa_ma']:.3f} | other {s['other']:.3f}   {s['counts']}")


if __name__ == "__main__":
    main()
