"""Inference-time audio -> PCD windows.

Extracts the predominant-melody pitch (essentia PredominantPitchMelodia) and the tonic
(compiam TonicIndianMultiPitch = the Salamon/Gulati multipitch method, which exploits the
drone), then builds the tonic-normalized PCD via features.pitch_windows. This is the
audio->feature path for a RAW upload; the annotated-corpus path (data.iter_pitch_clips)
uses each dataset's own pitch+tonic instead.

REQUIRES the numpy<2 inference env (environment-inference.yml): essentia's compute is
broken under numpy 2.x. essentia/compiam are imported lazily so this module still imports
(harmlessly) in the numpy-2.x training env.
"""
from __future__ import annotations

import numpy as np

from . import features
from .config import INFER_MAX_WINDOWS, INFER_SECONDS, MIN_CLIP_SECONDS, PCD_BINS

TONIC_SR = 44100          # essentia's native rate for pitch + tonic
MELODIA_HOP = 128

_MELODIA = None
_TONIC = None


def _extractors():
    """Import + instantiate the essentia/compiam extractors ONCE, then reuse. Importing
    compiam is the slow (~tens of s) one-time cost; instantiating and reusing the
    algorithms keeps every identify ~3.5s. Call warmup() at startup to pay it upfront."""
    global _MELODIA, _TONIC
    if _MELODIA is None:
        from compiam.melody.tonic_identification.tonic_multipitch import TonicIndianMultiPitch
        from essentia.standard import PredominantPitchMelodia

        _MELODIA = PredominantPitchMelodia(hopSize=MELODIA_HOP, sampleRate=TONIC_SR)
        _TONIC = TonicIndianMultiPitch()
    return _MELODIA, _TONIC


def warmup() -> None:
    """Pre-load the extractors so the first identify isn't slow (call at demo startup)."""
    _extractors()


def audio_to_pcd(audio, sr, max_seconds: float = INFER_SECONDS, max_windows: int = INFER_MAX_WINDOWS):
    """Raw mono audio -> (list of PCD windows, tonic_hz).

    Returns ([], None) when the tonic or pitch can't be estimated (no clear melody/drone),
    which the caller surfaces as a "not sure" message.
    """
    import librosa

    melodia, tonic_algo = _extractors()
    y = np.asarray(audio, dtype=np.float32)
    if y.ndim > 1:
        y = y.mean(axis=1).astype(np.float32)
    if sr != TONIC_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=TONIC_SR).astype(np.float32)
    if max_seconds:
        y = y[: int(max_seconds * TONIC_SR)]
    if y.size < int(MIN_CLIP_SECONDS * TONIC_SR):
        return [], None

    try:
        tonic = float(tonic_algo.extract(y, input_sr=TONIC_SR))
    except Exception:  # noqa: BLE001 — essentia raises "No peak locations" on unclear audio
        return [], None
    if not tonic or tonic <= 0:
        return [], None

    f0, _ = melodia(y)
    times = np.arange(len(f0)) * MELODIA_HOP / TONIC_SR
    windows = features.pitch_windows(times, f0, tonic, max_windows=max_windows, n_bins=PCD_BINS)
    return windows, tonic
