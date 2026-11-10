"""Feature extraction from a predominant-melody pitch track and its tonic (Sa).

The production feature is windowed TDMS (model_windows), with each window's swara phrases cut
from the same frames for the swara chains. The tonic-normalized pitch-class distribution (PCD)
remains as the learner panel's display feature and for the reference swara profiles.
"""
from __future__ import annotations

import numpy as np

from .config import CLIP_SECONDS, MIN_CLIP_SECONDS, MIN_VOICED_FRAC, SAMPLE_RATE


def _voiced_fraction(seg) -> float:
    """Fraction of a window's predominant-melody frames that carry a pitch (f0>0). Low for
    percussion/speech/applause/silence (the junk gate, D6/D8); high for real melody."""
    seg = np.asarray(seg, dtype=float)
    return float((seg > 0).mean()) if seg.size else 0.0


def load_audio(path: str, sr: int = SAMPLE_RATE, duration: float | None = None) -> np.ndarray:
    """Decode any format to mono float32 at `sr` (ffmpeg handles mp3/m4a).

    `duration` caps the decode length — Saraga tracks run 20-30 min, so decoding the
    whole file to use only the first N windows wastes most of the work.
    """
    import librosa

    y, _ = librosa.load(path, sr=sr, mono=True, duration=duration)
    return y.astype(np.float32)


# 12 semitone positions relative to Sa (common Carnatic labels for the swara-sthanas).
SWARA_LABELS = ["S", "R1", "R2", "G2", "G3", "M1", "M2", "P", "D1", "D2", "N2", "N3"]

# The seven swaras every learner knows. For the "how to hear this raaga" panel we fold the 12
# chromatic positions down to these names (sa ri ga ma pa da ni) — the beginner's vocabulary,
# not the R1/R2/G2/G3 sthana subscripts. Each name groups its sthana variants.
SWARA7 = ["Sa", "Ri", "Ga", "Ma", "Pa", "Da", "Ni"]
_SWARA7_GROUPS = [[0], [1, 2], [3, 4], [5, 6], [7], [8, 9], [10, 11]]  # indices into SWARA_LABELS


def to_swaras7(profile):
    """Fold a 12-position swara profile to the seven named swaras (SWARA7), summing each swara's
    sthana variants. Returns (names, values). The friendly display unit for new learners."""
    p = np.asarray(profile, dtype=float)
    vals = np.array([p[g].sum() for g in _SWARA7_GROUPS])
    return SWARA7, vals


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
    surf = np.bincount(a * n_bins + b, minlength=n_bins * n_bins).astype(np.float64)
    return (surf / surf.sum()).astype(np.float32)


def tdms_windows(
    times,
    f0_hz,
    tonic_hz: float,
    window_s: float = CLIP_SECONDS,
    hop_s: float = CLIP_SECONDS,
    max_windows: int | None = None,
    delay: float = 0.3,
    n_bins: int = 48,
    min_voiced: float = MIN_VOICED_FRAC,
) -> list[np.ndarray]:
    """Slide a window over a predominant-melody pitch track -> one TDMS surface per window
    (D28), cut exactly like pitch_windows. Windows voiced less than `min_voiced` of the
    time are dropped (junk gate, D6/D8 — percussion/speech/silence, no stable melody to track).
    """
    return [surf for surf, _ in _tdms_window_masks(times, f0_hz, tonic_hz, window_s, hop_s,
                                                    max_windows, delay, n_bins, min_voiced)]


def _window_slices(times, window_s, hop_s):
    """Frame ranges of the windows over a pitch track: [start, start + window_s) every hop_s, a
    trailing window kept only if it lasts MIN_CLIP_SECONDS. `times` is sorted, so each window is
    a binary search instead of a mask over every frame."""
    if times.size == 0 or times[-1] < MIN_CLIP_SECONDS:
        return
    end, start = float(times[-1]), 0.0
    while start < end and min(start + window_s, end) - start >= MIN_CLIP_SECONDS:
        yield slice(int(np.searchsorted(times, start)), int(np.searchsorted(times, start + window_s)))
        start += hop_s


def _kept_windows(times, f0, window_s, hop_s, max_windows, min_voiced, feature):
    """(feature, frame slice) for each window that passes the voiced-fraction junk gate and
    gives a non-empty feature, up to max_windows. One loop for every windowed feature, so the
    TDMS surfaces, the swara phrases and the PCDs are always cut from the same frames."""
    out = []
    for s in _window_slices(times, window_s, hop_s):
        if _voiced_fraction(f0[s]) >= min_voiced:
            v = feature(s)
            if v.sum() > 0:
                out.append((v, s))
        if max_windows and len(out) >= max_windows:
            break
    return out


def _tdms_window_masks(times, f0_hz, tonic_hz, window_s, hop_s, max_windows, delay, n_bins, min_voiced):
    """(surface, frame slice) for every kept TDMS window."""
    times = np.asarray(times, dtype=float)
    f0 = np.asarray(f0_hz, dtype=float)
    return _kept_windows(times, f0, window_s, hop_s, max_windows, min_voiced,
                         lambda s: tdms(times[s], f0[s], tonic_hz, delay=delay, n_bins=n_bins))


def model_windows(times, f0_hz, tonic_hz: float, max_windows: int | None = None,
                  hop_s: float | None = None, phrases: bool = False):
    """THE production model feature (D28): windowed TDMS at the config's winning settings.
    train / evaluate / calibrate / inference all call this one function, so the feature can
    never drift between how the model is trained and how it's served. `hop_s` overrides only the
    stride — inference passes a smaller hop so a short clip yields more windows to average (each
    window is still classified independently, so overlap is safe and doesn't change the feature).
    phrases=True returns (surfaces, swara phrases per window), cut from the same frames.
    """
    from .config import TDMS_BINS, TDMS_DELAY, TDMS_HOP_S, TDMS_MAX_WINDOWS, TDMS_WINDOW_S

    kept = _tdms_window_masks(times, f0_hz, tonic_hz, TDMS_WINDOW_S, hop_s or TDMS_HOP_S,
                              max_windows or TDMS_MAX_WINDOWS, TDMS_DELAY, TDMS_BINS, MIN_VOICED_FRAC)
    surfs = [surf for surf, _ in kept]
    if not phrases:
        return surfs
    from . import swara

    t, f0 = np.asarray(times, dtype=float), np.asarray(f0_hz, dtype=float)
    return surfs, [swara.phrases(t[m], f0[m], tonic_hz) for _, m in kept]


def pitch_windows(
    times,
    f0_hz,
    tonic_hz: float,
    window_s: float = CLIP_SECONDS,
    hop_s: float = CLIP_SECONDS,
    max_windows: int | None = None,
    n_bins: int = 120,
    min_voiced: float = MIN_VOICED_FRAC,
) -> list[np.ndarray]:
    """Slide a window over a predominant-melody pitch track -> one tonic-normalized PCD
    per window (D7). Windows that are voiced less
    than `min_voiced` of the time are dropped (junk gate, D6/D8 — percussion/speech/silence);
    a trailing window >= MIN_CLIP_SECONDS is kept. Works on any (pitch, tonic) source.
    """
    times = np.asarray(times, dtype=float)
    f0 = np.asarray(f0_hz, dtype=float)
    return [hist for hist, _ in _kept_windows(times, f0, window_s, hop_s, max_windows, min_voiced,
                                               lambda s: pitch_class_histogram(f0[s], tonic_hz, n_bins))]
