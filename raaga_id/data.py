"""Data loading — Saraga Carnatic via mirdata (PRD §6.3, D10).

Seed corpus for v0 is Saraga (D10). The multi-GB download is deliberately NOT run
at import time; call `download_saraga()` explicitly (held until storage is
confirmed). Everything here degrades to a clear error if the data is absent.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .config import BENCHMARK_DIR, DATA_DIR, canonical_raaga, fold_raaga, load_raagas

FROZEN_TEST_PATH = BENCHMARK_DIR / "test_track_ids.json"

SARAGA_DATASET = "saraga_carnatic"
SARAGA_HOME = DATA_DIR / "saraga_carnatic"


@dataclass
class Clip:
    """One labelled audio example: a path + its canonical raaga."""
    track_id: str
    audio_path: Path
    raaga: str            # canonical (raagas.json)
    tradition: str = "carnatic"
    tonic_hz: float | None = None   # Saraga ctonic annotation (precise Sa), if present


@dataclass
class PitchClip:
    """A labelled predominant-melody pitch track + its tonic — the PCD feature source.
    Dataset-agnostic so Saraga and IAMRRD pool through the same path."""
    dataset: str
    track_id: str
    raaga: str
    tonic_hz: float
    times: "object"        # np.ndarray of frame times (s)
    freqs: "object"        # np.ndarray of f0 (Hz), 0/NaN where unvoiced


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
        yield Clip(track_id=track_id, audio_path=Path(audio_path), raaga=canon,
                   tonic_hz=_tonic_of(track))


def load_frozen_test() -> set[str] | None:
    """The frozen held-out track ids, or None if no benchmark is frozen yet."""
    if FROZEN_TEST_PATH.exists():
        return set(json.loads(FROZEN_TEST_PATH.read_text()))
    return None


def freeze_test(test_ids: set[str]) -> Path:
    """Write the benchmark test split ONCE. Refuses to overwrite an existing freeze
    (build-order step 6: a frozen set stays frozen so scores stay comparable)."""
    if FROZEN_TEST_PATH.exists():
        raise FileExistsError(f"{FROZEN_TEST_PATH} already frozen — delete it to re-split.")
    FROZEN_TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    FROZEN_TEST_PATH.write_text(json.dumps(sorted(test_ids), indent=2) + "\n")
    return FROZEN_TEST_PATH


def split_by_track(clips: list[Clip], test_frac: float = 0.25, seed: int = 0) -> tuple[set[str], set[str]]:
    """Return (train_ids, test_ids), split BY TRACK so windows never leak across the
    split, stratified per raaga. Honors an existing frozen test set; otherwise draws a
    deterministic split and freezes it.
    """
    all_ids = {c.track_id for c in clips}
    frozen = load_frozen_test()
    if frozen is not None:
        test = frozen & all_ids
        return all_ids - test, test

    by_raaga: dict[str, list[str]] = defaultdict(list)
    for c in clips:
        by_raaga[c.raaga].append(c.track_id)

    rng = random.Random(seed)
    test: set[str] = set()
    for raaga, ids in by_raaga.items():
        ids = sorted(ids)
        rng.shuffle(ids)
        n_test = int(len(ids) * test_frac)
        if len(ids) >= 2:                       # keep >=1 in each side when possible
            n_test = max(1, n_test)
        test.update(ids[:n_test])

    freeze_test(test)
    return all_ids - test, test


def _raga_name(val) -> str | None:
    """Extract a raaga name from the various shapes mirdata returns (str / dict / list)."""
    if isinstance(val, str) and val.strip():
        return val
    if isinstance(val, dict):
        return val.get("name")
    if isinstance(val, (list, tuple)) and val:
        first = val[0]
        return first.get("name") if isinstance(first, dict) else str(first)
    return None


def _raaga_of(track) -> str | None:
    """Raaga label across schemas: IAMRRD's ``track.raga`` (name string) or Saraga's
    ``track.metadata["raaga"]`` (list of dicts with a ``name``)."""
    try:
        name = _raga_name(getattr(track, "raga", None))   # IAMRRD (compmusic_raga)
    except Exception:  # noqa: BLE001
        name = None
    if name:
        return name
    try:
        meta = track.metadata                             # Saraga
    except Exception:  # noqa: BLE001 — missing/corrupt per-track metadata json
        return None
    return _raga_name(meta.get("raaga")) if meta else None


def _tradition_of(track, default: str = "carnatic") -> str:
    """Track tradition (carnatic/hindustani). IAMRRD sets ``track.tradition``; Saraga
    Carnatic has none, so it defaults to carnatic."""
    try:
        t = getattr(track, "tradition", None)
    except Exception:  # noqa: BLE001
        t = None
    return t.lower() if isinstance(t, str) and t else default


def _tonic_of(track) -> float | None:
    """Saraga's ctonic annotation (tonic in Hz), if present. mirdata exposes it as
    ``track.tonic`` (loads the .ctonic file) — the precise Sa for tonic normalization."""
    try:
        t = track.tonic
    except Exception:  # noqa: BLE001 — missing/unreadable ctonic file
        return None
    return float(t) if isinstance(t, (int, float)) and t > 0 else None


def _pitch_of(track):
    """(times, freqs) from a track's predominant-melody pitch annotation, or None.
    Handles Saraga (``track.pitch``) and IAMRRD (``pitch`` / ``pitch_post_processed``)."""
    for attr in ("pitch", "pitch_post_processed"):
        try:
            p = getattr(track, attr, None)
        except Exception:  # noqa: BLE001 — missing/unreadable pitch file
            continue
        if p is not None and getattr(p, "frequencies", None) is not None:
            return p.times, p.frequencies
    return None


def iter_pitch_clips(only_vocab: bool = True, datasets=("saraga_carnatic",), tradition="carnatic"):
    """Yield PitchClip across datasets — a labelled pitch track + tonic per recording.
    Filters to one tradition (Hindustani shares raaga names like Bhairavi/Todi but they
    are different ragas). Skips tracks missing a raaga, tonic, or pitch annotation."""
    import mirdata

    vocab = load_raagas()
    keep = {fold_raaga(r) for r in vocab["canonical"]}
    for name in datasets:
        ds = mirdata.initialize(name, data_home=str(DATA_DIR / name))
        for track_id, track in ds.load_tracks().items():
            if tradition and _tradition_of(track) != tradition:
                continue
            raw = _raaga_of(track)
            if not raw:
                continue
            canon = canonical_raaga(raw, vocab)
            if only_vocab and fold_raaga(canon) not in keep:
                continue
            tonic = _tonic_of(track)
            pitch = _pitch_of(track)
            if not tonic or pitch is None:
                continue
            yield PitchClip(name, track_id, canon, tonic, pitch[0], pitch[1])
