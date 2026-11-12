"""Shared constants, grounded in the PRD decisions log."""
from __future__ import annotations

import os
from pathlib import Path

# Repo layout (PRD §17). data/ and models/ are gitignored; benchmark/ is tracked.
# Point the corpus at an external SSD without editing code: export TWELVESWARAS_DATA=/Volumes/....
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TWELVESWARAS_DATA", ROOT / "data"))
MODELS_DIR = ROOT / "models"
BENCHMARK_DIR = ROOT / "benchmark"
RAAGAS_PATH = ROOT / "raagas.json"

# Audio (PRD §6.7 + D7).
SAMPLE_RATE = 16_000       # 16 kHz mono throughout
CLIP_SECONDS = 10.0        # D7: 10 s analysis window
MIN_CLIP_SECONDS = 5.0     # D7: accept >=5 s with a warning
# A contribution must be this long to train. On the wild set, named-and-right was 48% at 30 s and
# 64% at 60 s; all six contributions under 40 s were wrong (2026-11-12). The contribute page asks
# for it too; this is the backstop for clips that got past the page.
MIN_CONTRIB_SECONDS = 60

# Output UX (D6).
TOP_K = 3                  # always show top-3 + confidence
# Below this averaged top-1 probability -> "not sure" in the local demo and the API's state (the
# site applies its own, stricter threshold). Set on the first model, where real clips averaged
# ~0.28-0.60 for the top class and noise ~0.08-0.12; it gates only noise.
LOW_CONFIDENCE = 0.15
# When the top two raagas are within this (calibrated) margin, call it a "close call — X vs Y"
# rather than a confident single answer (D25). Allied raagas (Mōhanaṁ/Bilahari/Bēgaḍa …) share
# a pitch-class profile, so an honest close-call is common and correct.
CLOSE_MARGIN = 0.06
INFER_MAX_WINDOWS = 60     # cap on windows per clip; at INFER_SECONDS and a 15 s hop it is never reached
INFER_SECONDS = 150        # cap raw-audio analysed at inference; wild benchmark is monotonic in
                           # listen time (90s -> 0.475, 150s -> 0.512), and tonic salience keeps
                           # improving to ~150s, so listen long. Hard/ambiguous clips benefit most.
TONIC_SECONDS = 300        # the tonic (Sa) hears more than the melody: on 197 annotated recordings
                           # usable Sa is 0.68 at 30 s, 0.81 at 150 s, 0.86 at 300 s (tools/tonic_bench),
                           # and real-world top-1 rose 0.688 -> 0.713. Only long uploads reach it.
PCD_BINS = 120             # pitch-class-distribution resolution (10-cent bins); the display feature

# Production model feature = windowed Time-Delayed Melody Surface (D28). The gate benchmark
# (benchmark/leaderboard.md, 2026-07-03) put TDMS-30s at top1 0.866 / top3 0.954 vs windowed-PCD 0.780 / 0.926,
# and the allied triple at 0.881 vs 0.714 — gamaka/movement is what the static PCD threw away.
TDMS_BINS = 48             # surface is TDMS_BINS x TDMS_BINS (10-cent-ish, 25-cent bins over an octave)
TDMS_DELAY = 0.3           # seconds; the (pitch(t), pitch(t+delay)) lag that exposes gamaka
TDMS_WINDOW_S = 30.0       # 30 s windows — dense enough to fill the surface (10 s was too sparse)
TDMS_HOP_S = 30.0
TDMS_MAX_WINDOWS = 20      # cap windows/track in training (20 x 30 s = 600 s, matches the gate)
# Junk gate (D6/D8): drop windows whose predominant-melody pitch is voiced less than this fraction
# of the time — i.e. percussion solos, speech, applause, long silences, where there's no stable
# melody for Melodia to track. Real melody is voiced most of the window; junk is mostly unvoiced.
MIN_VOICED_FRAC = 0.5


def load_raagas() -> dict:
    """Return the controlled vocabulary from raagas.json (canonical + aliases)."""
    import json

    with open(RAAGAS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def fold_raaga(name: str) -> str:
    """Normalize a raaga name for matching: strip diacritics + case + separators, then
    normalize common Indic romanization variants.

    Saraga/IAMRRD use diacritics (Mōhanaṁ, Tōḍi, Śaṅkarābharaṇaṁ); contributors use varied
    ASCII (Mohanam, Thodi, Shankarabharana). NFKD-decompose, drop combining marks, lowercase,
    keep only alphanumerics — then fold the aspirate/sibilant spellings (sh/s, th/t, dh/d, …),
    the long vowels ('oo' for ū, 'ee' for ī) and the 'ow' spelling of au (Gowla/Gauḷa), and
    collapse doubled letters, so
    'Shankarabharanam' and 'Śaṅkarābharaṇaṁ' fold together, as do 'Poorvi Kalyani' and
    'Pūrvīkaḷyāṇi'.

    ORDER IS LOAD-BEARING. The long-vowel rules must run before the doubled-letter collapse,
    or 'poorvi' collapses to 'porvi' and never reaches 'purvi'. 'ow' must run before 'w'->'v', or
    it has already become 'ov' and can never reach 'au'. Each such miss silently drops the
    recording from training as an unknown raaga.

    Verified not to collapse two distinct model classes of the SAME tradition into one key. The
    one cross-tradition duplicate (Carnatic Tōḍi vs Hindustani Tōḍī) folds together by design and
    is separated by the tradition tag, not by this key.
    """
    import re
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    key = "".join(c for c in stripped.lower() if c.isalnum())
    for a, b in (("shh", "s"), ("sh", "s"), ("chh", "c"), ("ch", "c"), ("th", "t"),
                 ("dh", "d"), ("bh", "b"), ("gh", "g"), ("kh", "k"), ("ph", "p"),
                 ("ow", "au"), ("w", "v"), ("z", "j"), ("oo", "u"), ("ee", "i")):
        key = key.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", key)  # collapse doubled letters (naata -> nata)


def canonical_raaga(name: str, vocab: dict | None = None) -> str:
    """Map a raw raaga label to its canonical form via the alias table (diacritic-insensitive)."""
    vocab = vocab or load_raagas()
    key = fold_raaga(name)
    for canon in vocab["canonical"]:
        if key == fold_raaga(canon):
            return canon
    for canon, aliases in vocab.get("aliases", {}).items():
        if key in {fold_raaga(a) for a in aliases}:
            return canon
    return name  # unknown -> pass through (surfaces as an out-of-vocab label)
