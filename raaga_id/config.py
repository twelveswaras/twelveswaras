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
HOP_SECONDS = 5.0          # stride when aggregating predictions across a long clip

# Output UX (D6).
TOP_K = 3                  # always show top-3 + confidence
# Below this averaged top-1 probability -> "not sure". Calibrated to the v0 floor:
# real clips average ~0.28-0.60 for the top class, near-random/percussion ~0.08-0.12
# (uniform = 1/12 = 0.083), so 0.15 shows top-3 for real music and gates only noise.
LOW_CONFIDENCE = 0.15
# When the top two raagas are within this (calibrated) margin, call it a "close call — X vs Y"
# rather than a confident single answer (D25). Allied raagas (Mōhanaṁ/Bilahari/Bēgaḍa …) share
# a pitch-class profile, so an honest close-call is common and correct.
CLOSE_MARGIN = 0.06
INFER_MAX_WINDOWS = 60     # analyse ~first 10 min of a long upload (matches training)
INFER_SECONDS = 90         # cap raw-audio analysed at inference — tonic salience is ~1min/2min
PCD_BINS = 120             # pitch-class-distribution resolution (10-cent bins); the display feature

# Production model feature = windowed Time-Delayed Melody Surface (D28). The gate benchmark
# (tools/tdms_benchmark) put TDMS-30s at top1 0.866 / top3 0.954 vs windowed-PCD 0.780 / 0.926,
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

# Verification (D13). Configurable; these are the v0 defaults.
PROMOTE_MIN_VOTES = 3
PROMOTE_MIN_AGREEMENT = 0.80


def load_raagas() -> dict:
    """Return the controlled vocabulary from raagas.json (canonical + aliases)."""
    import json

    with open(RAAGAS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def fold_raaga(name: str) -> str:
    """Normalize a raaga name for matching: strip diacritics + case + separators.

    Saraga uses diacritics (Mōhanaṁ, Tōḍi, Śudda sāvēri); our vocab/aliases are ASCII.
    NFKD-decompose, drop combining marks, lowercase, keep only alphanumerics so
    'Mōhanaṁ' and 'Mohanam' fold to the same key.
    """
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", name)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return "".join(c for c in stripped.lower() if c.isalnum())


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
