"""Inference-time audio -> model feature windows.

Extracts the predominant-melody pitch (essentia PredominantPitchMelodia) and the tonic
(compiam TonicIndianMultiPitch = the Salamon/Gulati multipitch method, which exploits the
drone), then builds windowed TDMS (D28) via features.model_windows — the SAME feature the
model trains on. This is the audio->feature path for a RAW upload; the annotated-corpus path
(data.iter_pitch_clips) uses each dataset's own pitch+tonic instead.

REQUIRES the numpy<2 inference env (environment-inference.yml): essentia's compute is
broken under numpy 2.x. essentia/compiam are imported lazily so this module still imports
(harmlessly) in the numpy-2.x training env.
"""
from __future__ import annotations

import numpy as np

from . import features
from .config import INFER_MAX_WINDOWS, INFER_SECONDS, MIN_CLIP_SECONDS, PCD_BINS, TDMS_HOP_S

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


def audio_to_features(audio, sr, max_seconds: float = INFER_SECONDS, max_windows: int = INFER_MAX_WINDOWS):
    """Raw mono audio -> (list of model-feature windows, tonic_hz, analysed_seconds, display_pcd).

    The model windows are windowed TDMS (D28), IDENTICAL to training via features.model_windows.
    display_pcd is the tonic-normalized pitch-class distribution over the whole analysed span —
    used ONLY for the learner panel's human-readable swara fingerprint, never by the model.
    analysed_seconds is how much audio (from 0:00) was actually fed to the model — capped at
    max_seconds — so the UI can tell the user exactly what it heard (D24: legible recognition).
    Returns ([], None, 0.0, None) when the tonic or pitch can't be estimated (no clear melody/drone).
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
        return [], None, 0.0, None
    analysed_seconds = y.size / TONIC_SR

    try:
        tonic = float(tonic_algo.extract(y, input_sr=TONIC_SR))
    except Exception:  # noqa: BLE001 — essentia raises "No peak locations" on unclear audio
        return [], None, 0.0, None
    if not tonic or tonic <= 0:
        return [], None, 0.0, None

    f0, _ = melodia(y)
    times = np.arange(len(f0)) * MELODIA_HOP / TONIC_SR
    # Overlap windows at inference (hop < window) so a short clip still yields several to average.
    windows = features.model_windows(times, f0, tonic, max_windows=max_windows, hop_s=TDMS_HOP_S / 2)
    display_pcd = features.pitch_class_histogram(f0, tonic, n_bins=PCD_BINS)
    return windows, tonic, analysed_seconds, display_pcd
