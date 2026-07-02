"""Finalize the v0 raaga set (PRD D4) data-driven from Saraga.

D4: "~12 raagas, chosen data-driven from Saraga/CMD, mutually distinct; avoid
allied-raaga pairs for v0." This tool counts raagas across the downloaded Saraga
Carnatic corpus and proposes the commonest N that are mutually distinct, greedily
skipping a raaga whose known allied partner is already chosen.

    python -m tools.select_v0_raagas            # report the distribution + proposal
    python -m tools.select_v0_raagas --write    # write the proposal to raagas.json

Review the proposal before --write; the allied-pair list is curated, not exhaustive.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter

from raaga_id import data
from raaga_id.config import RAAGAS_PATH


def _norm(name: str) -> str:
    return name.strip().lower().replace(" ", "").replace("-", "")


# Well-known confusable/allied Carnatic pairs (normalized). Keeps the commoner of a
# pair for v0 so the classifier isn't graded on distinctions even experts contest.
ALLIED_PAIRS = [
    ("kambhoji", "yadukulakambhoji"),
    ("kambhoji", "kedaragowla"),
    ("bhairavi", "manji"),
    ("bhairavi", "mukhari"),
    ("nayaki", "darbar"),
    ("darbar", "devamanohari"),
    ("sriranjani", "jayamanohari"),
    ("kalyani", "mohanakalyani"),
    ("kalyani", "yamunakalyani"),
    ("shankarabharanam", "bilahari"),
    ("shankarabharanam", "kedaragowla"),
    ("kharaharapriya", "abheri"),
    ("nattai", "gambhiranattai"),
    ("todi", "sindhubhairavi"),
    ("anandabhairavi", "reetigowla"),
]


def _allied(a: str, b: str) -> bool:
    na, nb = _norm(a), _norm(b)
    return any({na, nb} == {_norm(x), _norm(y)} for x, y in ALLIED_PAIRS)


def raaga_counts() -> Counter:
    counts: Counter = Counter()
    for clip in data.iter_clips(only_vocab=False):  # count ALL raagas, not just current vocab
        counts[clip.raaga] += 1
    return counts


def propose(counts: Counter, k: int = 12) -> tuple[list[str], list[tuple[str, str]]]:
    chosen: list[str] = []
    skipped: list[tuple[str, str]] = []  # (raaga, "allied with X")
    for raaga, _ in counts.most_common():
        clash = next((c for c in chosen if _allied(raaga, c)), None)
        if clash:
            skipped.append((raaga, clash))
            continue
        chosen.append(raaga)
        if len(chosen) == k:
            break
    return chosen, skipped


def main() -> None:
    ap = argparse.ArgumentParser(description="Propose/write the v0 raaga set (D4).")
    ap.add_argument("-k", type=int, default=12)
    ap.add_argument("--write", action="store_true", help="overwrite raagas.json canonical list")
    args = ap.parse_args()

    counts = raaga_counts()
    if not counts:
        raise SystemExit("No raagas found — is Saraga downloaded? (raaga_id.data.download_saraga)")

    print(f"=== raaga distribution ({sum(counts.values())} tracks, {len(counts)} raagas) ===")
    for raaga, n in counts.most_common():
        print(f"  {n:3d}  {raaga}")

    chosen, skipped = propose(counts, args.k)
    print(f"\n=== proposed v0 set (top {args.k}, allied-pairs avoided) ===")
    for r in chosen:
        print(f"  ✓ {r}  ({counts[r]} tracks)")
    if skipped:
        print("  skipped (allied with a chosen raaga):")
        for r, clash in skipped:
            print(f"    – {r} (allied with {clash})")

    if args.write:
        existing = json.loads(RAAGAS_PATH.read_text())
        existing["canonical"] = chosen
        existing["_note"] = (
            f"v0 set finalized data-driven from Saraga Carnatic 1.5 (D4): top {args.k} by "
            "track count, mutually distinct (allied pairs skipped). Regenerate with "
            "tools/select_v0_raagas.py."
        )
        RAAGAS_PATH.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n")
        print(f"\nwrote {len(chosen)} raagas -> {RAAGAS_PATH}")


if __name__ == "__main__":
    main()
