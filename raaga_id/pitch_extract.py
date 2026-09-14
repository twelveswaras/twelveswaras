"""Inference-time audio -> model feature windows.

Extracts the predominant-melody pitch (essentia PredominantPitchMelodia) and the tonic
(essentia TonicIndianArtMusic, which exploits the drone), then builds windowed TDMS (D28)
via features.model_windows — the SAME feature the model trains on. This is the audio->feature
path for a RAW upload; the annotated-corpus path (data.iter_pitch_clips) uses each dataset's
own pitch+tonic instead.

Tonic was compiam TonicIndianMultiPitch until 2026-09-14. Swapped after the first
ground-truth benchmark (tools/tonic_bench, vs Saraga ctonic, identical audio, 150s, n=39):
TonicIndianArtMusic scores 90% vs 87% clean and 59% vs 46% on degraded audio. compiam is no
longer imported here, but stays in the env because it pins numpy<2.

REQUIRES the numpy<2 inference env (environment-inference.yml): essentia's compute is
broken under numpy 2.x. essentia is imported lazily so this module still imports
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


# Sa search range. 100 Hz is deliberately NOT raised: a higher floor scores better on the degraded
# benchmark, but only because Saraga's annotated tonics span just 131-197 Hz. Real tonics go lower
# (the Shaale corpus reaches 103.9 Hz), and a floor above those makes a low-voiced singer's Sa
# unfindable by construction. Better to keep the honest range than to buy points on a narrow sample.
TONIC_MIN_HZ = 100.0
TONIC_MAX_HZ = 375.0


class _TonicEstimator:
    """Sa from the drone, via essentia TonicIndianArtMusic.

    Benchmarked against Saraga's ground-truth ctonic (tools/tonic_bench), identical audio, 150s,
    n=39: this beats the previous compiam TonicIndianMultiPitch wrapper 90% vs 87% on clean and
    **59% vs 46% on degraded audio**, which is where we actually lose (a wrong Sa mis-normalises the
    TDMS and yields a confident WRONG raaga, the worst failure a learning tool can have).

    A FRESH algorithm is built per call on purpose. Essentia algorithm objects are stateful: reusing
    one raises "No peak locations" on its second compute. compiam hid this by re-instantiating
    internally, so caching its wrapper was safe; caching a raw essentia algorithm would NOT be, and
    would fail every request after the first. Construction is cheap next to the analysis itself.
    """

    def extract(self, y, input_sr: int = TONIC_SR) -> float:
        from essentia.standard import TonicIndianArtMusic

        sig = np.asarray(y, dtype=np.float32)
        if input_sr != TONIC_SR:
            import librosa

            sig = librosa.resample(sig, orig_sr=input_sr, target_sr=TONIC_SR).astype(np.float32)
        algo = TonicIndianArtMusic(minTonicFrequency=TONIC_MIN_HZ, maxTonicFrequency=TONIC_MAX_HZ)
        try:
            return float(algo(sig))
        finally:
            del algo


def _extractors():
    """Import + instantiate the extractors ONCE, then reuse. The essentia import is the slow
    (~tens of s) one-time cost; reusing Melodia keeps every identify ~3.5s. Call warmup() at
    startup to pay it upfront. The tonic estimator is a thin stateless wrapper (see above: the
    underlying essentia algorithm must NOT be cached)."""
    global _MELODIA, _TONIC
    if _MELODIA is None:
        from essentia.standard import PredominantPitchMelodia

        _MELODIA = PredominantPitchMelodia(hopSize=MELODIA_HOP, sampleRate=TONIC_SR)
        _TONIC = _TonicEstimator()
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

    # On a tonic failure return the REAL analysed_seconds (not 0.0). Callers distinguish the three
    # no-window outcomes from the triple alone, with no extra return value:
    #   secs == 0            -> too_short (returned above)
    #   tonic is None        -> tonic_failed (the estimator threw or gave <=0)
    #   tonic is not None    -> no_windows (the voiced-fraction junk gate dropped everything)
    # Before this, every early failure reported 0.0 and the three were indistinguishable in
    # telemetry, which is why our biggest production failure mode was unreadable.
    try:
        tonic = float(tonic_algo.extract(y, input_sr=TONIC_SR))
    except Exception:  # noqa: BLE001 — essentia raises "No peak locations" on unclear audio
        return [], None, analysed_seconds, None
    if not tonic or tonic <= 0:
        return [], None, analysed_seconds, None

    f0, _ = melodia(y)
    times = np.arange(len(f0)) * MELODIA_HOP / TONIC_SR
    # Overlap windows at inference (hop < window) so a short clip still yields several to average.
    windows = features.model_windows(times, f0, tonic, max_windows=max_windows, hop_s=TDMS_HOP_S / 2)
    display_pcd = features.pitch_class_histogram(f0, tonic, n_bins=PCD_BINS)
    return windows, tonic, analysed_seconds, display_pcd
