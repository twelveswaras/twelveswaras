"""Data loading — Saraga Carnatic via mirdata (PRD §6.3, D10).

Seed corpus for v0 is Saraga (D10). The multi-GB download is deliberately NOT run
at import time; call `download_saraga()` explicitly (held until storage is
confirmed). Everything here degrades to a clear error if the data is absent.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import DATA_DIR, canonical_raaga, load_raagas

SARAGA_DATASET = "saraga_carnatic"
SARAGA_HOME = DATA_DIR / "saraga_carnatic"


@dataclass
class Clip:
    """One labelled audio example: a path + its canonical raaga."""
    track_id: str
    audio_path: Path
    raaga: str            # canonical (raagas.json)
    tradition: str = "carnatic"


def _dataset(download: bool = False):
    import mirdata

    ds = mirdata.initialize(SARAGA_DATASET, data_home=str(SARAGA_HOME))
    if download:
        ds.download()
    return ds


def download_saraga() -> Path:
    """Download Saraga Carnatic into data/ (a few GB). Run once, on demand."""
    SARAGA_HOME.mkdir(parents=True, exist_ok=True)
    _dataset(download=True)
    return SARAGA_HOME


def iter_clips(only_vocab: bool = True):
    """Yield Clip(track_id, audio_path, raaga) for every Saraga track with a raaga.

    only_vocab=True keeps just the v0 controlled-vocabulary raagas (raagas.json).
    """
    ds = _dataset(download=False)
    vocab = load_raagas()
    keep = {r.lower().replace(" ", "") for r in vocab["canonical"]}

    for track_id, track in ds.load_tracks().items():
        raw = _raaga_of(track)
        if not raw:
            continue
        canon = canonical_raaga(raw, vocab)
        if only_vocab and canon.lower().replace(" ", "") not in keep:
            continue
        audio_path = getattr(track, "audio_path", None)
        if not audio_path or not Path(audio_path).exists():
            continue
        yield Clip(track_id=track_id, audio_path=Path(audio_path), raaga=canon)


def _raaga_of(track) -> str | None:
    """Pull the raaga label off a mirdata Saraga track (schema varies by version)."""
    for attr in ("raaga", "raagas"):
        val = getattr(track, attr, None)
        if not val:
            continue
        if isinstance(val, str):
            return val
        if isinstance(val, (list, tuple)) and val:
            first = val[0]
            return first.get("name") if isinstance(first, dict) else str(first)
    return None
