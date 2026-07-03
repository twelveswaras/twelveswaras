"""'How to hear this raaga' — the data-derived learner layer (PRD §16.1).

Reference swara profiles are computed from the corpus (tools/build_raaga_profiles.py);
the summary is auto-generated from the pitch data (safe). The curated guide
(arohana/avarohana/pakad/contrasts) is EXPERT-vetted content loaded from
raaga_guide.json — never auto-generated here, because wrong musicology is worse than
none. All loaders degrade gracefully when the files are absent.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

from .config import ROOT
from .features import SWARA_LABELS

PROFILES_PATH = ROOT / "raaga_profiles.json"
GUIDE_PATH = ROOT / "raaga_guide.json"


@lru_cache(maxsize=1)
def _profiles() -> dict:
    return json.loads(PROFILES_PATH.read_text()) if PROFILES_PATH.exists() else {}


@lru_cache(maxsize=1)
def _guide() -> dict:
    return json.loads(GUIDE_PATH.read_text()) if GUIDE_PATH.exists() else {}


def reference_profile(raaga: str):
    """The raaga's average 12-position swara profile, or None if not built yet."""
    p = _profiles().get(raaga)
    return np.asarray(p, dtype=float) if p else None


def top_swaras(profile, k: int = 4) -> list[str]:
    """Names of the k most-emphasized swaras (dropping negligible ones)."""
    profile = np.asarray(profile, dtype=float)
    order = np.argsort(profile)[::-1][:k]
    return [SWARA_LABELS[i] for i in order if profile[i] > 0.03]


def guide(raaga: str) -> dict:
    """Curated per-raaga notes, empty fields dropped ({} until an expert fills them in)."""
    return {k: v for k, v in _guide().get(raaga, {}).items() if v}


def summary_md(raaga: str, user_profile=None) -> str:
    """Markdown: the swaras the raaga leans on + what the user's clip emphasized + any
    curated notes (else a 'coming soon' line)."""
    lines = [f"### How to hear **{raaga}**"]
    ref = reference_profile(raaga)
    if ref is not None:
        lines.append(f"**{raaga}** leans on **{' · '.join(top_swaras(ref))}** "
                     "(the swaras it emphasizes, relative to Sa).")
    if user_profile is not None:
        lines.append(f"Your clip's melody sat on **{' · '.join(top_swaras(user_profile))}**.")

    g = guide(raaga)
    if g:
        for label, key in (("Ārōhaṇa", "arohana"), ("Avarōhaṇa", "avarohana"),
                           ("Pakaḍ / signature phrase", "pakad"), ("Listen for", "listen_for"),
                           ("Not to be confused with", "vs")):
            if g.get(key):
                lines.append(f"- **{label}:** {g[key]}")
    else:
        lines.append("_Expert notes — ārōhaṇa/avarōhaṇa, characteristic phrases, allied-raaga "
                     "contrasts — coming soon (vetted, not auto-generated)._")
    return "\n\n".join(lines)
