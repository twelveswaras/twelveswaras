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
from .features import to_swaras7

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
    """The k swaras the raaga rests on most, by their everyday names (Sa Ri Ga Ma Pa Da Ni),
    dropping ones it barely touches."""
    names, vals = to_swaras7(profile)
    order = np.argsort(vals)[::-1][:k]
    return [names[i] for i in order if vals[i] > 0.03]


def guide(raaga: str) -> dict:
    """Curated per-raaga notes, empty fields dropped ({} until an expert fills them in)."""
    return {k: v for k, v in _guide().get(raaga, {}).items() if v}


# --- Allied-raaga comparison (D29 Explorer): how to tell two close-call raagas apart, from their
# swara SETS (which of the 12 notes each uses — a documented fact). Seed sets live in
# raaga_guide.json["swaras"]; empty until seeded/expert-filled. Beginner-friendly note names below;
# a variety qualifier is only added when two raagas share a base note but differ in its variety.
from .features import SWARA_LABELS  # noqa: E402

_BASE = {"S": "sa", "R1": "ri", "R2": "ri", "G2": "ga", "G3": "ga", "M1": "ma", "M2": "ma",
         "P": "pa", "D1": "da", "D2": "da", "N2": "ni", "N3": "ni"}
_VARIETY = {"R1": "the lower ri", "R2": "ri", "G2": "the lower ga", "G3": "ga",
            "M1": "the natural ma", "M2": "the sharp ma (prati-madhyama)", "D1": "the lower da",
            "D2": "da", "N2": "ni", "N3": "the sharp ni"}
_SEED_OVERRIDE = None  # tests inject swara sets here without touching the guide file


def swaras(raaga: str):
    """The raaga's swara set (12-position labels), or None if not seeded/filled."""
    if _SEED_OVERRIDE is not None and raaga in _SEED_OVERRIDE:
        return _SEED_OVERRIDE[raaga]
    s = _guide().get(raaga, {}).get("swaras")
    return s or None


def distinguish(a: str, b: str):
    """Set-difference of two raagas' swaras, or None if either lacks data. Returns which notes
    each has that the other doesn't (ordered), and whether the sets are identical."""
    sa, sb = swaras(a), swaras(b)
    if not sa or not sb:
        return None
    order = {lab: i for i, lab in enumerate(SWARA_LABELS)}
    A, B = set(sa), set(sb)
    return {"a_only": sorted(A - B, key=lambda x: order.get(x, 99)),
            "b_only": sorted(B - A, key=lambda x: order.get(x, 99)),
            "same": A == B}


_ORDER7 = ["sa", "ri", "ga", "ma", "pa", "da", "ni"]


def _join(names) -> str:
    names = list(dict.fromkeys(names))  # dedupe, keep order
    if len(names) <= 2:
        return " and ".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]


def _variety_desc(labels) -> str:
    """Describe the varieties of ONE base note a raaga uses (e.g. both dhaivatas, or the sharp ni)."""
    return f"both {_BASE[labels[0]]}s" if len(labels) >= 2 else _VARIETY[labels[0]]


def comparison_md(a: str, b: str) -> str:
    """A plain-language 'how to tell them apart' line for a close call, or '' if no data.
    Compares base note by base note so it stays correct for bhashanga raagas that use *both*
    varieties of a note (e.g. Bhairavi's two dhaivatas)."""
    sa, sb = swaras(a), swaras(b)
    if not sa or not sb:
        return ""
    A, B = set(sa), set(sb)
    if A == B:
        return (f"**Telling {a} from {b}:** they use the **same notes** — the difference is in the "
                f"*gamaka* (how each note is shaken and slid) and the phrasing, not the scale. "
                f"(Phrase guidance coming soon.)")
    a_extra, b_extra, variety = [], [], []
    for base in _ORDER7:
        av = [x for x in A if _BASE[x] == base]
        bv = [x for x in B if _BASE[x] == base]
        if set(av) == set(bv):
            continue
        if av and not bv:
            a_extra.append(base)          # a has this note entirely, b doesn't
        elif bv and not av:
            b_extra.append(base)
        else:                              # both have the note but in different varieties
            variety.append((base, av, bv))
    parts = [f"the **{base}** differs — {a} uses {_variety_desc(av)}, {b} uses {_variety_desc(bv)}"
             for base, av, bv in variety]
    if b_extra:
        parts.append(f"{b} uses **{_join(b_extra)}**, which {a} leaves out")
    if a_extra:
        parts.append(f"{a} uses **{_join(a_extra)}**, which {b} leaves out")
    return f"**Telling {a} from {b}:** " + "; ".join(parts) + ". Listen for those notes."


def summary_md(raaga: str, user_profile=None) -> str:
    """A warm, plain-language 'how to hear this raaga' note for someone new to Carnatic music —
    which of the seven swaras the raaga rests on, what their clip leaned on, and (when an expert
    has filled it in) the raaga's ascent/descent and its telltale phrase."""
    lines = [f"### How to hear **{raaga}**",
             "Every raaga is a way of moving through the seven swaras — "
             "**sa · ri · ga · ma · pa · da · ni**. Here's what to listen for."]
    # NB: we do NOT auto-state which swaras the *raaga* uses — the data profiles are gamaka-
    # smeared (ornaments glide pitch across neighbours), so that claim can be wrong. The raaga's
    # actual notes belong to the expert guide below. We only describe the user's own clip.
    if user_profile is not None:
        lines.append(f"In your clip, the melody sat mostly on **{' · '.join(top_swaras(user_profile))}** — "
                     "the notes it kept returning to.")

    g = guide(raaga)
    if g:
        for label, key in (("Going up", "arohana"), ("Coming down", "avarohana"),
                           ("Its signature phrase", "pakad"), ("Listen for", "listen_for"),
                           ("Easy to mix up with", "vs")):
            if g.get(key):
                lines.append(f"- **{label}:** {g[key]}")
    else:
        lines.append("_More on the way — how the raaga rises and falls, its signature phrase, "
                     "and the raagas it's easy to mix up with (written by musicians, not guessed)._")
    return "\n\n".join(lines)
