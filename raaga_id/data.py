"""Data loading: labelled pitch tracks (mirdata corpora such as the Raga Recognition Dataset and
Saraga), commons contributions, and the frozen benchmark split. Datasets are downloaded
separately into data/; everything here degrades to a clear error if the data is absent.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import BENCHMARK_DIR, DATA_DIR, canonical_raaga, fold_raaga, load_raagas

FROZEN_TEST_PATH = BENCHMARK_DIR / "test_track_ids.json"

# Commons corpus materialized by pipeline.pull_commons (verified contributions).
COMMONS_DIR = DATA_DIR / "commons"
COMMONS_MANIFEST = COMMONS_DIR / "manifest.jsonl"


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


@dataclass
class CommonsClip:
    """A contributor recording pulled from the commons. Raw uploads carry no pre-annotated
    pitch/tonic, so the melody + tonic are extracted here via the SAME path a live upload
    takes (pitch_extract), leaving `windows` ready to pool with the corpus clips."""
    track_id: str
    raaga: str
    windows: "object"          # list of model feature windows (windowed TDMS, D28)
    tradition: str = "carnatic"


def iter_commons_clips(manifest_path: Path = COMMONS_MANIFEST):
    """Yield a CommonsClip per pulled contribution in the manifest (pipeline.pull_commons).

    Extracts predominant-melody pitch + tonic from the raw audio, then windowed TDMS —
    identical to how the model sees a live upload — so a contribution pools with the Saraga/
    IAMRRD clips in training. Skips clips whose audio is missing or yields no usable window
    (no clear melody/drone). Commons track_ids never appear in the frozen benchmark, so these
    clips are training-only by construction (the frozen test set is never touched).

    REQUIRES the numpy<2 inference env (essentia); imported lazily so this module still
    imports cleanly under the numpy-2 training env.
    """
    manifest_path = Path(manifest_path)
    if not manifest_path.exists():
        return
    from . import features, pitch_extract
    from .pitch_extract import TONIC_SR

    base = manifest_path.parent
    for line in manifest_path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        audio_path = base / entry["audio_path"]
        if not audio_path.exists():
            continue
        y = features.load_audio(str(audio_path), sr=TONIC_SR)
        windows, _tonic, _secs, _pcd, _phrases = pitch_extract.audio_to_features(y, TONIC_SR)
        if not windows:
            continue
        yield CommonsClip(
            track_id=f"commons:{entry['id']}",
            raaga=entry["raaga"],
            windows=windows,
            tradition=entry.get("tradition", "carnatic"),
        )


def load_frozen_test() -> set[str] | None:
    """The frozen held-out track ids, or None if no benchmark is frozen yet."""
    if FROZEN_TEST_PATH.exists():
        return set(json.loads(FROZEN_TEST_PATH.read_text()))
    return None


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
