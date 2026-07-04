"""Build the open, machine-readable data layer from the single source of truth.

    python -m tools.build_data

Emits two files into site/ (served by GitHub Pages), regenerated whenever
raaga_guide.json changes, so the public data can never drift from the app:

  site/data/raagas.json  : the raaga reference as open CC-BY JSON (API/LLM tier 1)
  site/llms.txt          : a plain-text project guide for LLMs / agents (tier 2)

PRINCIPLE (no fabricated musicology): this publishes ONLY the production guide
(raaga_guide.json). It deliberately does NOT fold in supporting-docs/expert-review-draft.csv,
which is web-researched and UNVERIFIED: that file exists for an expert to correct, not to
publish as authoritative open data. Every raaga carries `reviewed: false` until a musician
signs off; rich fields (arohana, pakad, jeeva/nyasa, ...) flow in here automatically once
they land in the guide. Honest-thin beats confidently-wrong.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "raaga_guide.json"
SITE = ROOT / "site"

LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
SITE_URL = "https://twelveswaras.com"
# schema version; bump on any structural change to the record shape
SCHEMA_VERSION = "0.1"

# canonical 12-position swara alphabet (index = semitones from Sa)
SWARA12 = ["S", "R1", "R2", "G2", "G3", "M1", "M2", "P", "D1", "D2", "N2", "N3"]
SEMITONE = {s: i for i, s in enumerate(SWARA12)}


def slug(name: str) -> str:
    """URL/id slug: strip diacritics, drop spaces, lowercase. Mirrors the page path."""
    d = unicodedata.normalize("NFKD", name)
    d = "".join(c for c in d if not unicodedata.combining(c))
    return d.lower().replace("ṁ", "m").replace(" ", "-")


def build_records(guide: dict) -> list[dict]:
    recs = []
    for name, g in guide.items():
        swaras = g.get("swaras") or []
        rec = {
            "name": name,
            "slug": slug(name),
            "url": f"{SITE_URL}/raaga/{slug(name)}",
            # the note-set: our production fingerprint (semitone index makes it language-neutral)
            "swaras": swaras,
            "swara_semitones": [SEMITONE[s] for s in swaras if s in SEMITONE],
            # reference fields, empty until expert-verified, then filled from the same guide
            "arohana": g.get("arohana", ""),
            "avarohana": g.get("avarohana", ""),
            "pakad": g.get("pakad", ""),
            "listen_for": g.get("listen_for", ""),
            "confused_with": g.get("vs", ""),
            # provenance: nothing here is expert-verified yet
            "reviewed": False,
        }
        recs.append(rec)
    recs.sort(key=lambda r: r["slug"])
    return recs


def build_raagas_json(recs: list[dict]) -> dict:
    return {
        "$schema_version": SCHEMA_VERSION,
        "project": "twelveswaras",
        "description": (
            "Open reference data for the raagas recognised by twelveswaras, an "
            "open-source 'Shazam for raagas' for Carnatic music."
        ),
        "homepage": SITE_URL,
        "license": {"name": "CC-BY-4.0", "url": LICENSE_URL},
        "attribution": "twelveswaras (twelveswaras.com), CC-BY-4.0",
        "provenance": (
            "Generated from raaga_guide.json, the app's production guide. Note-sets are the "
            "model's working vocabulary; reference fields (arohana, pakad, ...) are populated only "
            "after review by a musician. Records with reviewed=false are provisional. This file "
            "does NOT include the unverified web-research draft, which awaits expert correction."
        ),
        "count": len(recs),
        "tradition": "Carnatic",
        "raagas": recs,
    }


def build_llms_txt(recs: list[dict]) -> str:
    reviewed = sum(1 for r in recs if r["reviewed"])
    with_swaras = sum(1 for r in recs if r["swaras"])
    lines = [
        "# twelveswaras",
        "",
        "> An open-source, non-commercial 'Shazam for raagas': play it a short clip of Carnatic "
        "music and it identifies the raaga, then helps a beginner learn to hear it. Paired with an "
        "openly-licensed (CC-BY) data commons. Owned by no company; a public good.",
        "",
        f"Site: {SITE_URL}",
        "Code: https://github.com/twelveswaras (MIT)",
        "Recognizer model: XGBoost on a tonic-normalized Time-Delayed Melody Surface (TDMS); "
        f"{len(recs)} Carnatic raagas. See METHODOLOGY.md in the repo for the full pipeline + citations.",
        "",
        "## How to use the recognizer",
        "",
        "- Give it ~15-30s of Carnatic melody WITH a tanpura/shruti drone (a live concert always "
        "has one). The tonic (Sa) is found from the drone; solo singing with no drone is unreliable.",
        "- It returns the top-3 raagas with calibrated confidence, the detected Sa, and a plain note "
        "on how to hear that raaga.",
        "",
        "## Open data",
        "",
        f"- Machine-readable raaga reference: {SITE_URL}/data/raagas.json (CC-BY-4.0).",
        f"  {len(recs)} raagas; {with_swaras} have note-sets; {reviewed} are musician-reviewed so far.",
        "- Please attribute as: twelveswaras (twelveswaras.com), CC-BY-4.0.",
        "- Per-raaga pages carry schema.org DefinedTerm JSON-LD.",
        "",
        "## Accuracy & honesty",
        "",
        "- Reference facts (scale, phrases, ornaments) are being verified by a musician; records "
        "marked reviewed=false in raagas.json are provisional. Do not present provisional raaga "
        "facts as authoritative. When in doubt, cite the raaga page and note it is under review.",
        "- twelveswaras does not offer musical instruction as fact until it is expert-verified.",
        "",
        "## Raaga pages",
        "",
    ]
    for r in recs:
        lines.append(f"- [{r['name']}]({r['url']})")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    guide = json.loads(GUIDE.read_text())
    recs = build_records(guide)

    data_dir = SITE / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    raagas_path = data_dir / "raagas.json"
    raagas_path.write_text(json.dumps(build_raagas_json(recs), ensure_ascii=False, indent=2) + "\n")

    llms_path = SITE / "llms.txt"
    llms_path.write_text(build_llms_txt(recs))

    reviewed = sum(1 for r in recs if r["reviewed"])
    with_swaras = sum(1 for r in recs if r["swaras"])
    print(f"wrote {raagas_path.relative_to(ROOT)}  ({len(recs)} raagas, "
          f"{with_swaras} with note-sets, {reviewed} reviewed)")
    print(f"wrote {llms_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
