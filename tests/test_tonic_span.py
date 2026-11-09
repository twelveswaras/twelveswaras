"""The tonic hears more audio than the melody analysis (raaga_id.pitch_extract).

    python tests/test_tonic_span.py

Sa accuracy keeps rising with audio length (tools/tonic_bench, n=197: 0.81 at 150 s, 0.86 at
300 s), while the melody analysis stays capped at INFER_SECONDS. These stub the essentia
extractors to record how many samples each one receives, so they run without essentia.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from raaga_id import pitch_extract as pe
from raaga_id.config import INFER_SECONDS, TONIC_SECONDS


def _spans(monkeypatch, seconds, sr=pe.TONIC_SR):
    seen = {}

    class Tonic:
        def extract(self, y, input_sr):
            seen["tonic"] = y.size / input_sr
            return 146.8

    def melodia(y):
        seen["melody"] = y.size / pe.TONIC_SR
        return np.zeros(y.size // pe.MELODIA_HOP, dtype=np.float32), None

    monkeypatch.setattr(pe, "_extractors", lambda: (melodia, Tonic()))
    out = pe.audio_to_features(np.zeros(int(seconds * sr), dtype=np.float32), sr)
    return seen, out


def test_long_audio_gives_the_tonic_more_than_the_melody(monkeypatch):
    seen, (_, _, heard, _, _) = _spans(monkeypatch, 400)
    assert seen == {"tonic": TONIC_SECONDS, "melody": INFER_SECONDS}
    assert heard == INFER_SECONDS            # what the visitor is told was analysed


def test_audio_between_the_caps_gives_the_tonic_all_of_it(monkeypatch):
    seen, _ = _spans(monkeypatch, 200)
    assert seen == {"tonic": 200, "melody": INFER_SECONDS}


def test_short_audio_is_unchanged(monkeypatch):
    seen, (_, _, heard, _, _) = _spans(monkeypatch, 100)
    assert seen == {"tonic": 100, "melody": 100} and heard == 100


def test_other_sample_rates_are_capped_the_same_way(monkeypatch):
    seen, _ = _spans(monkeypatch, 400, sr=16000)
    assert abs(seen["tonic"] - TONIC_SECONDS) < 0.01 and abs(seen["melody"] - INFER_SECONDS) < 0.01


def test_the_tonic_never_hears_less_than_the_melody():
    assert TONIC_SECONDS >= INFER_SECONDS


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
