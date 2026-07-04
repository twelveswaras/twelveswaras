"""Rebuild the expert-review CSV from the (merged) draft reference + guide.

    python -m tools.build_expert_csv

Keeps supporting-docs/expert-review-draft.csv in sync with raaga_reference_draft.json so the
sheet the expert edits always reflects the latest enrichment. The final column is left blank
for the expert's corrections.
"""
from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "supporting-docs" / "raaga_reference_draft.json"
GUIDE = ROOT / "raaga_guide.json"
OUT = ROOT / "supporting-docs" / "expert-review-draft.csv"

COLUMNS = [
    ("raaga", "_name"),
    ("parent melakarta", "parent_mela"),
    ("janya type", "janya_type"),
    ("arohana (ascending)", "arohana"),
    ("avarohana (descending)", "avarohana"),
    ("our swara set (VERIFY)", "_swaras"),
    ("beginner tell", "tell"),
    ("rasa / mood", "rasa"),
    ("jeeva swaras", "jeeva_swaras"),
    ("nyasa swaras", "nyasa_swaras"),
    ("characteristic prayogas", "prayogas"),
    ("common gamakas", "gamakas"),
    ("closest confusing ragas", "confusing_with"),
    ("example kritis", "kritis"),
    ("representative film songs", "film_songs"),
    ("sources (web draft)", "sources"),
    ("web confidence", "confidence"),
    ("expert corrections / notes", "_blank"),
]


def fold(s: str) -> str:
    d = unicodedata.normalize("NFKD", s)
    d = "".join(c for c in d if not unicodedata.combining(c))
    return d.lower().replace(" ", "").replace("ṁ", "m")


def main() -> None:
    ref = json.loads(REF.read_text())
    guide = json.loads(GUIDE.read_text())
    guide_by_fold = {fold(k): v for k, v in guide.items()}

    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow([h for h, _ in COLUMNS])
        for name, r in ref.items():
            g = guide.get(name) or guide_by_fold.get(fold(name))
            swaras = " ".join(g["swaras"]) if g and g.get("swaras") else "‼ (blank in our guide)"
            row = []
            for _, key in COLUMNS:
                if key == "_name":
                    row.append(name)
                elif key == "_swaras":
                    row.append(swaras)
                elif key == "_blank":
                    row.append("")
                else:
                    row.append(r.get(key, ""))
            w.writerow(row)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(ref)} rows)")


if __name__ == "__main__":
    main()
