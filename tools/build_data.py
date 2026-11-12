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

from raaga_id.features import SWARA_LABELS

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "raaga_guide.json"
SITE = ROOT / "site"

LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
SITE_URL = "https://twelveswaras.com"
# schema version; bump on any structural change to the record shape
SCHEMA_VERSION = "0.1"

# canonical 12-position swara alphabet (index = semitones from Sa)
SWARA12 = SWARA_LABELS
SEMITONE = {s: i for i, s in enumerate(SWARA12)}


# The all-versions Zenodo DOI (always resolves to the latest release).
DOI = "10.5281/zenodo.24096813"

def _n_carnatic() -> int:
    """Size of the tracked Carnatic vocabulary (the model's Carnatic half)."""
    import json
    return len(json.load(open(ROOT / "raagas.json", encoding="utf-8"))["canonical"])


def _n_hindustani() -> int:
    """Size of the tracked Hindustani vocabulary (the model's Hindustani half)."""
    import json
    return len(json.load(open(ROOT / "raagas.hindustani.json", encoding="utf-8"))["canonical"])


def slug(name: str, suffix: str = "") -> str:
    """URL/id slug: strip diacritics, drop spaces, lowercase. Mirrors the page path."""
    d = unicodedata.normalize("NFKD", name)
    d = "".join(c for c in d if not unicodedata.combining(c))
    return d.lower().replace("ṁ", "m").replace(" ", "-") + suffix


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


def _hindustani_names() -> list[str]:
    """The Hindustani raagas with reference pages (raaga/<slug>-hindustani), in guide order."""
    guide = json.loads((ROOT / "raaga_guide.hindustani.json").read_text(encoding="utf-8"))
    return [k for k in guide if not k.startswith("_")]


def build_llms_txt(recs: list[dict]) -> str:
    reviewed = sum(1 for r in recs if r["reviewed"])
    with_swaras = sum(1 for r in recs if r["swaras"])
    n_c, n_h = _n_carnatic(), _n_hindustani()
    lines = [
        "# twelveswaras",
        "",
        "> An open-source, non-commercial 'Shazam for raagas': play it about a minute of Carnatic or "
        "Hindustani music and it identifies the raaga, then helps a beginner learn to hear it. "
        "Paired with an openly-licensed (CC-BY) data commons. Owned by no company; a public good.",
        "",
        f"Site: {SITE_URL}",
        "Code: https://github.com/twelveswaras/twelveswaras (MIT; the running recognizer is "
        "AGPL-3.0 because it uses Essentia)",
        f"Cite: Sankaran, S. (2026). twelveswaras [Computer software]. Zenodo. https://doi.org/{DOI}",
        # Counts come from the tracked vocabularies, never from len(recs): recs is the Carnatic
        # REFERENCE dataset, and using it here described a 70-class dual-tradition model as
        # "40 Carnatic raagas" for as long as the Hindustani side has existed.
        "Recognizer model: XGBoost on tonic-normalized Time-Delayed Melody Surfaces (TDMS), fused "
        f"with per-raaga swara-sequence chains; {n_c + n_h} raagas ({n_c} Carnatic, {n_h} "
        "Hindustani). See METHODOLOGY.md in the repo for the full pipeline + citations.",
        "",
        "## How to use the recognizer",
        "",
        "- Give it about a minute of Carnatic or Hindustani melody WITH a tanpura/shruti drone (a "
        "live concert always has one). A live listen shows the notes it hears for the first minute "
        "and names raagas only after that; it settles within two and a half minutes. The tonic (Sa) "
        "is found from the drone; solo singing with no drone is unreliable.",
        "- It returns the top-3 raagas with calibrated confidence, the detected Sa, and a plain note "
        "on how to hear that raaga. Below a confidence threshold it says it is not sure.",
        "",
        "## Accuracy",
        "",
        "- On 80 real-world recordings (phone, concert, YouTube), analysed for 150 s: the top answer "
        "is right 71% of the time and the right raaga is in the top three 80% of the time. Allied "
        "raagas (same scale, different phrasing) are the main confusion. Full benchmarks, including "
        "negative results: benchmark/leaderboard.md in the repo.",
        "",
        "## MCP server (for AI agents)",
        "",
        f"- Endpoint: {SITE_URL}/mcp (Streamable HTTP, no sign-in). Tools: find_raaga (look a raaga up "
        "by any spelling), raagas_with_notes (raagas by their notes, Carnatic or Hindustani), "
        "list_raagas, identify_raaga (the raaga in a recording at a public URL; not stored).",
        "",
        "## Open data and licences",
        "",
        f"- The raaga pages as data: {SITE_URL}/data/raaga-reference.json (CC-BY-4.0): 70 raagas "
        "with scale, parent, scale and phrase notes, key notes, songs.",
        f"- Machine-readable raaga reference: {SITE_URL}/data/raagas.json (CC-BY-4.0).",
        f"  {len(recs)} Carnatic raagas; {with_swaras} have note-sets; {reviewed} are "
        "musician-reviewed so far.",
        "- Model weights: CC-BY-4.0, downloadable from the v1.0.0 release on GitHub. Trained only on "
        "the Indian Art Music Raga Recognition Dataset features (CC-BY-4.0).",
        "- Please attribute as: twelveswaras (twelveswaras.com), CC-BY-4.0.",
        "- Per-raaga pages carry schema.org DefinedTerm JSON-LD.",
        "",
        "## Honesty",
        "",
        "- Reference facts (scale, phrases, ornaments) are being verified by a musician; records "
        "marked reviewed=false in raagas.json are provisional, and the Hindustani pages are drafts. "
        "Do not present provisional raaga facts as authoritative. When in doubt, cite the raaga page "
        "and note it is under review.",
        "- twelveswaras does not offer musical instruction as fact until it is expert-verified.",
        "",
        "## Carnatic raaga pages",
        "",
    ]
    lines += [f"- [{r['name']}]({r['url']})" for r in recs]
    lines += ["", "## Hindustani raaga pages (draft)", ""]
    lines += [f"- [{nm}]({SITE_URL}/raaga/{slug(nm, '-hindustani')})" for nm in _hindustani_names()]
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
