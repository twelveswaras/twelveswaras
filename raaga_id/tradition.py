"""Tradition metadata: which musical tradition a raaga label belongs to.

The recognizer is moving from Carnatic-only to Carnatic + Hindustani (see the Phase 0 spike).
A unified model tags its class labels by tradition, because a few names (Tōḍī/Tōḍi, Śrī/Śrī)
are shared spellings but different raagas. This module is the single place that decides the
tradition of a label, so the API and site never re-implement it.

Additive and backward-compatible: it does not touch raagas.json or the Carnatic path. The
shipped 40-class model returns plain Carnatic names; those resolve to "carnatic" here, so the
API gains a `tradition` field with no retrain.
"""
from __future__ import annotations

import json

from .config import ROOT, fold_raaga, load_raagas

HINDUSTANI_PATH = ROOT / "raagas.hindustani.json"

CARNATIC = "carnatic"
HINDUSTANI = "hindustani"
UNKNOWN = "unknown"

# Class labels in a dual model carry a human-readable tradition tag: "<name> (Carnatic)".
_TAGS = {f" ({CARNATIC.capitalize()})": CARNATIC, f" ({HINDUSTANI.capitalize()})": HINDUSTANI}


def load_hindustani_raagas() -> dict:
    """The Hindustani controlled vocabulary (canonical + ASCII/English aliases)."""
    with open(HINDUSTANI_PATH, encoding="utf-8") as fh:
        return json.load(fh)


HINDUSTANI_CANONICAL = set(load_hindustani_raagas()["canonical"])
_HINDUSTANI_FOLDS = {fold_raaga(r) for r in HINDUSTANI_CANONICAL}
_CARNATIC_FOLDS = {fold_raaga(r) for r in load_raagas()["canonical"]}


def tradition_of(label: str) -> tuple[str, str]:
    """(display_name, tradition) for a model class label.

    A tradition tag on the label always wins. Otherwise resolve by vocabulary: a name unique to
    one tradition takes that tradition; a name shared by both (an untagged collision) defaults to
    carnatic, since only the Carnatic model emits untagged labels; an unrecognised name is
    flagged UNKNOWN rather than guessed.
    """
    for tag, trad in _TAGS.items():
        if label.endswith(tag):
            return label[: -len(tag)], trad

    fold = fold_raaga(label)
    in_c, in_h = fold in _CARNATIC_FOLDS, fold in _HINDUSTANI_FOLDS
    if in_c:                       # includes the shared-name collisions -> default carnatic
        return label, CARNATIC
    if in_h:
        return label, HINDUSTANI
    return label, UNKNOWN


def tradition_counts(classes) -> dict:
    """How many of a model's classes are Carnatic vs Hindustani (for /health). UNKNOWN labels
    are not counted under either tradition."""
    counts = {CARNATIC: 0, HINDUSTANI: 0}
    for c in classes:
        _, trad = tradition_of(c)
        if trad in counts:
            counts[trad] += 1
    return counts
