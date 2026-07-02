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
LOW_CONFIDENCE = 0.40      # below this -> "not sure" state (also gate on melody energy)

# Verification (D13). Configurable; these are the v0 defaults.
PROMOTE_MIN_VOTES = 3
PROMOTE_MIN_AGREEMENT = 0.80


def load_raagas() -> dict:
    """Return the controlled vocabulary from raagas.json (canonical + aliases)."""
    import json

    with open(RAAGAS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def canonical_raaga(name: str, vocab: dict | None = None) -> str:
    """Map a raw raaga label to its canonical form via the alias table."""
    vocab = vocab or load_raagas()
    key = name.strip().lower().replace(" ", "")
    for canon in vocab["canonical"]:
        if key == canon.lower().replace(" ", ""):
            return canon
    for canon, aliases in vocab.get("aliases", {}).items():
        if key in {a.lower().replace(" ", "") for a in aliases}:
            return canon
    return name  # unknown -> pass through (surfaces as an out-of-vocab label)
