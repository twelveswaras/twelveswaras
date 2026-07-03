"""Feature extraction.

Modeling ladder (D16): tonic-normalized pitch-class/swara histogram + XGBoost floor
-> TDMS -> CNN on mel/CQT. This module starts at the FLOOR (D16 step 1) with a
librosa-only fixed-length vector — deliberately no essentia/compIAM yet so Phase 1
runs anywhere. `tonic_normalize` is the Phase-2 seam (D5) where the real quality
unlock plugs in.
"""
from __future__ import annotations

import numpy as np

from .config import CLIP_SECONDS, MIN_CLIP_SECONDS, SAMPLE_RATE


def load_audio(path: str, sr: int = SAMPLE_RATE, duration: float | None = None) -> np.ndarray:
    """Decode any format to mono float32 at `sr` (ffmpeg handles mp3/m4a).

    `duration` caps the decode length — Saraga tracks run 20-30 min, so decoding the
    whole file to use only the first N windows wastes most of the work.
    """
    import librosa

    y, _ = librosa.load(path, sr=sr, mono=True, duration=duration)
    return y.astype(np.float32)


def tonic_normalize(y: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """PHASE 2 SEAM (D5). Identify the tonic (Sa) and shift so pitch classes align
    to the swara grid. Until essentia/compIAM land, this is a no-op passthrough;
    the librosa floor leans on pitch-shift augmentation instead (like the thesis).
    """
    # TODO(phase2): essentia TonicIndianArtMusic / compiam -> shift to Sa.
    return y


def estimate_tonic_pc(y: np.ndarray, sr: int = SAMPLE_RATE) -> int:
    """Cheap tonic (Sa) estimate: the most energetic pitch class over the clip.

    Carnatic performances carry a continuous tanpura drone on Sa, so the summed
    chromagram peaks at the tonic. This is the librosa-only stand-in for the precise
    essentia `TonicIndianArtMusic` used in Phase 2 (D5).
    """
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    return int(chroma.mean(axis=1).argmax())


def frame_vector(y: np.ndarray, sr: int = SAMPLE_RATE, tonic_pc: int = 0) -> np.ndarray:
    """Tonic-relative pitch-class descriptor for one window (D16 step 1).

    Raaga lives in the pitch classes *relative to Sa*, so we roll the chromagram so
    the tonic pitch class -> bin 0, then summarize as a normalized 12-bin pitch-class
    histogram (the raaga fingerprint) + per-bin spread. Timbre features (MFCC,
    spectral shape) are deliberately EXCLUDED: they encode recording/instrument
    identity and make the model memorize tracks instead of learning raaga.
    """
    import librosa

    if y.size == 0:
        raise ValueError("empty audio")

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma = np.roll(chroma, -tonic_pc, axis=0)          # tonic -> bin 0
    hist = chroma.mean(axis=1)
    hist = hist / (hist.sum() + 1e-8)                     # pitch-class distribution
    return np.concatenate([hist, chroma.std(axis=1)]).astype(np.float32)  # 24-dim


def window_vectors(
    y: np.ndarray,
    sr: int = SAMPLE_RATE,
    window_s: float = CLIP_SECONDS,
    hop_s: float = CLIP_SECONDS,
    max_windows: int | None = None,
) -> list[np.ndarray]:
    """Slide a `window_s` window over a (long) clip -> one frame vector per window.

    Saraga tracks are full concert recordings, so one vector per track would be a
    single over-smoothed sample. Windowing (D7: 10 s) turns each recording into many
    training examples. Tail segments shorter than MIN_CLIP_SECONDS are dropped;
    hop_s == window_s gives non-overlapping windows (the training default).
    """
    win = int(round(window_s * sr))
    hop = max(1, int(round(hop_s * sr)))
    min_len = int(round(MIN_CLIP_SECONDS * sr))
    if len(y) < min_len:
        return []
    tonic_pc = estimate_tonic_pc(y, sr)  # one Sa estimate per recording (drone is stable)
    out: list[np.ndarray] = []
    start = 0
    while start < len(y):
        seg = y[start : start + win]
        if len(seg) < min_len:
            break
        out.append(frame_vector(seg, sr, tonic_pc))
        if max_windows and len(out) >= max_windows:
            break
        start += hop
    return out


def extract(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Single-vector path for short clips: load -> estimate Sa -> tonic-relative vector."""
    y = load_audio(path, sr)
    return frame_vector(y, sr, estimate_tonic_pc(y, sr))


def extract_windows(
    path: str, sr: int = SAMPLE_RATE, max_windows: int | None = None
) -> list[np.ndarray]:
    """Load a (long) recording and return one frame vector per 10 s window."""
    duration = None if max_windows is None else max_windows * CLIP_SECONDS + 1.0
    y = load_audio(path, sr, duration=duration)
    y = tonic_normalize(y, sr)
    return window_vectors(y, sr, max_windows=max_windows)
