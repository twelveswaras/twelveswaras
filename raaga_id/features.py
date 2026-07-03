"""Feature extraction.

Modeling ladder (D16): tonic-normalized pitch-class/swara histogram + XGBoost floor
-> TDMS -> CNN on mel/CQT. The floor (D16 step 1) is a librosa chroma histogram rolled
so the tonic (Sa) sits at bin 0 (D5). The tonic comes from Saraga's ctonic annotation
when available (precise), else a drone-argmax estimate; essentia TonicIndianArtMusic is
the inference-time upgrade for unlabelled clips (Phase 2).
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


def estimate_tonic_pc(y: np.ndarray, sr: int = SAMPLE_RATE) -> int:
    """Cheap tonic (Sa) estimate: the most energetic pitch class over the clip.

    Carnatic performances carry a continuous tanpura drone on Sa, so the summed
    chromagram peaks at the tonic. This is the librosa-only stand-in for the precise
    essentia `TonicIndianArtMusic` used in Phase 2 (D5).
    """
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    return int(chroma.mean(axis=1).argmax())


def tonic_pc_from_hz(hz: float) -> int:
    """Map a tonic frequency (Hz) to its chroma pitch class (0-11). Used with a
    precise tonic — Saraga's ctonic annotation, or essentia at inference."""
    import librosa

    return int(round(librosa.hz_to_midi(hz))) % 12


# 12 semitone positions relative to Sa (common Carnatic labels for the swara-sthanas).
SWARA_LABELS = ["S", "R1", "R2", "G2", "G3", "M1", "M2", "P", "D1", "D2", "N2", "N3"]


def pcd_to_swaras(pcd) -> np.ndarray:
    """Fold a fine PCD (n_bins, a multiple of 12) to a 12-position swara profile
    (one bin per semitone), normalized — the human-readable raaga fingerprint."""
    a = np.asarray(pcd, dtype=float)
    a = a.reshape(12, a.size // 12).sum(axis=1)
    return a / (a.sum() + 1e-9)


def pitch_class_histogram(f0_hz, tonic_hz: float, n_bins: int = 120) -> np.ndarray:
    """Tonic-normalized pitch-class distribution (PCD) from a predominant-melody pitch
    track — the classic raaga fingerprint (D16). Each voiced f0 becomes cents relative
    to Sa, folded to one octave, binned and normalized; unvoiced frames (f0<=0) are
    ignored. Works on any (pitch, tonic) source, so Saraga and IAMRRD pool cleanly.
    Returns zeros when nothing is voiced.
    """
    f0 = np.asarray(f0_hz, dtype=float)
    voiced = f0[f0 > 0]
    if voiced.size == 0:
        return np.zeros(n_bins, dtype=np.float32)
    cents = 1200.0 * np.log2(voiced / tonic_hz)
    bins = np.mod((np.mod(cents, 1200.0) / (1200.0 / n_bins)).astype(int), n_bins)
    hist = np.bincount(bins, minlength=n_bins).astype(np.float32)
    return hist / hist.sum()


def tdms(times, f0_hz, tonic_hz: float, delay: float = 0.3, n_bins: int = 48) -> np.ndarray:
    """Time-Delayed Melody Surface (Gulati et al., ISMIR 2016) — the gamaka feature (refines
    D16). A 2-D histogram of (pitch(t), pitch(t+delay)) over the tonic-normalized, octave-folded
    melody: a held note sits on the diagonal, while gamaka/transitions smear off-diagonal in a
    raaga-characteristic way. This keeps the *movement* the 1-D PCD discards — the information
    that should separate allied raagas (Mōhanaṁ/Bilahari/Bēgaḍa) which share a scale.

    Returns a flat (n_bins*n_bins,) surface normalized to sum 1, or zeros when too few voiced
    pairs. `delay` is in seconds; the frame hop is inferred from `times`.
    """
    times = np.asarray(times, dtype=float)
    f0 = np.asarray(f0_hz, dtype=float)
    zeros = np.zeros(n_bins * n_bins, dtype=np.float32)
    if times.size < 2:
        return zeros
    voiced = f0 > 0
    cents = np.zeros_like(f0)
    cents[voiced] = np.mod(1200.0 * np.log2(f0[voiced] / tonic_hz), 1200.0)
    bins = np.mod((cents / (1200.0 / n_bins)).astype(int), n_bins)

    hop = float(np.median(np.diff(times)))
    d = max(1, int(round(delay / hop)))
    if d >= bins.size:
        return zeros
    a, b = bins[:-d], bins[d:]
    both = voiced[:-d] & voiced[d:]          # count a pair only if both endpoints are voiced
    a, b = a[both], b[both]
    if a.size == 0:
        return zeros
    surf = np.zeros((n_bins, n_bins), dtype=np.float64)
    np.add.at(surf, (a, b), 1.0)
    return (surf / surf.sum()).astype(np.float32).ravel()


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
    tonic_hz: float | None = None,
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
    if max_windows:  # only look at the span we'll use (fast tonic estimate on long uploads)
        y = y[: win + hop * (max_windows - 1)]
    # Prefer a precise tonic (Saraga ctonic) when given; else the drone-argmax heuristic.
    tonic_pc = tonic_pc_from_hz(tonic_hz) if tonic_hz else estimate_tonic_pc(y, sr)
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


def pitch_windows(
    times,
    f0_hz,
    tonic_hz: float,
    window_s: float = CLIP_SECONDS,
    hop_s: float = CLIP_SECONDS,
    max_windows: int | None = None,
    n_bins: int = 120,
) -> list[np.ndarray]:
    """Slide a window over a predominant-melody pitch track -> one tonic-normalized PCD
    per window (the pitch-track analog of window_vectors, D7). Windows with no voiced
    pitch are skipped; a trailing window >= MIN_CLIP_SECONDS is kept. Works on any
    (pitch, tonic) source, so Saraga and IAMRRD share this path.
    """
    times = np.asarray(times, dtype=float)
    f0 = np.asarray(f0_hz, dtype=float)
    if times.size == 0 or times[-1] < MIN_CLIP_SECONDS:
        return []
    end = float(times[-1])
    out: list[np.ndarray] = []
    start = 0.0
    while start < end:
        if min(start + window_s, end) - start < MIN_CLIP_SECONDS:
            break
        seg = f0[(times >= start) & (times < start + window_s)]
        hist = pitch_class_histogram(seg, tonic_hz, n_bins)
        if hist.sum() > 0:
            out.append(hist)
        if max_windows and len(out) >= max_windows:
            break
        start += hop_s
    return out


def extract_windows(
    path: str,
    sr: int = SAMPLE_RATE,
    max_windows: int | None = None,
    tonic_hz: float | None = None,
) -> list[np.ndarray]:
    """Load a (long) recording and return one frame vector per 10 s window.
    Pass tonic_hz (Saraga ctonic) for a precise tonic; otherwise it's estimated."""
    duration = None if max_windows is None else max_windows * CLIP_SECONDS + 1.0
    y = load_audio(path, sr, duration=duration)
    return window_vectors(y, sr, max_windows=max_windows, tonic_hz=tonic_hz)
