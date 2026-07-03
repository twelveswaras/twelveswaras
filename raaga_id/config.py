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
INFER_MAX_WINDOWS = 60     # analyse ~first 10 min of a long upload (matches training)

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
