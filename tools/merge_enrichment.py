"""Merge the lakshana enrichment into the draft reference, in place.

    python -m tools.merge_enrichment

Reads supporting-docs/raaga_enrichment.json (a per-raaga dict of the four "thin" fields:
jeeva_swaras, nyasa_swaras, prayogas, gamakas) and folds each non-empty value into
supporting-docs/raaga_reference_draft.json, overriding the base web-research value for those
four fields only (the enrichment pass was the deeper, treatise-first lakshana lookup). Empty
enrichment values leave the base untouched. Idempotent: safe to re-run as more enrichment lands.
Everything stays reviewed=false until a musician verifies it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REF = ROOT / "supporting-docs" / "raaga_reference_draft.json"
ENR = ROOT / "supporting-docs" / "raaga_enrichment.json"
BEG = ROOT / "supporting-docs" / "raaga_beginner.json"      # tell + rasa (beginner-facing)
FIELDS = ["jeeva_swaras", "nyasa_swaras", "prayogas", "gamakas"]
BEG_FIELDS = ["tell", "rasa"]


def dedash(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = re.sub(r"\s*—\s*", ", ", s)
    return re.sub(r"^,\s*", "", s)


def main() -> None:
    ref = json.loads(REF.read_text())
    enr = json.loads(ENR.read_text())
    unknown, changed = [], 0
    for name, e in enr.items():
        if name not in ref:
            unknown.append(name)
            continue
        touched = False
        for f in FIELDS:
            v = dedash((e.get(f) or "").strip())
            if v and v != ref[name].get(f, ""):
                ref[name][f] = v
                touched = True
        ref[name]["enriched"] = True
        if touched:
            changed += 1

    # beginner-facing tell + rasa (separate file, same fill-if-nonempty rule)
    beg = json.loads(BEG.read_text()) if BEG.exists() else {}
    for name, b in beg.items():
        if name not in ref:
            unknown.append(name)
            continue
        for f in BEG_FIELDS:
            v = dedash((b.get(f) or "").strip())
            if v:
                ref[name][f] = v

    REF.write_text(json.dumps(ref, ensure_ascii=False, indent=2) + "\n")

    if unknown:
        print("  !! draft names not found in reference:", unknown)
    print(f"merged enrichment for {len(enr)} raagas ({changed} updated) + beginner for {len(beg)}")
    print("field coverage (non-empty / 40) after merge:")
    for f in FIELDS + BEG_FIELDS:
        n = sum(1 for v in ref.values() if v.get(f))
        print(f"  {f:14s} {n:2d}/40")


if __name__ == "__main__":
    main()
