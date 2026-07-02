"""Feature extraction.

Modeling ladder (D16): tonic-normalized pitch-class/swara histogram + XGBoost floor
-> TDMS -> CNN on mel/CQT. This module starts at the FLOOR (D16 step 1) with a
librosa-only fixed-length vector — deliberately no essentia/compIAM yet so Phase 1
runs anywhere. `tonic_normalize` is the Phase-2 seam (D5) where the real quality
unlock plugs in.
"""
from __future__ import annotations

import numpy as np

from .config import SAMPLE_RATE


def load_audio(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any format to mono float32 at `sr` (ffmpeg handles mp3/m4a)."""
    import librosa

    y, _ = librosa.load(path, sr=sr, mono=True)
    return y.astype(np.float32)


def tonic_normalize(y: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """PHASE 2 SEAM (D5). Identify the tonic (Sa) and shift so pitch classes align
    to the swara grid. Until essentia/compIAM land, this is a no-op passthrough;
    the librosa floor leans on pitch-shift augmentation instead (like the thesis).
    """
    # TODO(phase2): essentia TonicIndianArtMusic / compiam -> shift to Sa.
    return y


def frame_vector(y: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Thesis-style fixed-length descriptor over one clip (the ~50-dim floor).

    Concatenates means+stds of: chroma (12), MFCC (20), spectral centroid,
    bandwidth, rolloff, and zero-crossing rate. Fixed length regardless of clip
    duration, so it drops straight into XGBoost/SVM.
    """
    import librosa

    if y.size == 0:
        raise ValueError("empty audio")

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
    bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)
    zcr = librosa.feature.zero_crossing_rate(y)

    parts = [chroma, mfcc, centroid, bandwidth, rolloff, zcr]
    stats = [np.concatenate([m.mean(axis=1), m.std(axis=1)]) for m in parts]
    return np.concatenate(stats).astype(np.float32)


def extract(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Full floor path: load -> tonic-normalize (no-op in Phase 1) -> frame vector."""
    y = load_audio(path, sr)
    y = tonic_normalize(y, sr)
    return frame_vector(y, sr)
