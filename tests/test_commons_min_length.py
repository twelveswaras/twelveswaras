"""A contribution must be at least a minute long to train (short clips rarely give a usable Sa).

    python tests/test_commons_min_length.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from raaga_id import config, data, features, pitch_extract  # noqa: E402


def _manifest(tmp_path: Path) -> Path:
    (tmp_path / "audio").mkdir()
    (tmp_path / "audio" / "a.webm").write_bytes(b"x")
    m = tmp_path / "manifest.jsonl"
    m.write_text(json.dumps({"id": 1, "raaga": "Tōḍi", "tradition": "carnatic", "audio_path": "audio/a.webm"}) + "\n")
    return m


def _run(tmp_path, monkeypatch, seconds):
    calls = []
    sr = pitch_extract.TONIC_SR
    monkeypatch.setattr(features, "load_audio", lambda p, sr=sr, duration=None: np.zeros(int(seconds * sr), np.float32))
    monkeypatch.setattr(pitch_extract, "audio_to_features",
                        lambda y, sr: calls.append(1) or ([np.zeros(3)], 140.0, seconds, None, []))
    return list(data.iter_commons_clips(_manifest(tmp_path))), calls


def test_the_minimum_is_a_minute():
    assert config.MIN_CONTRIB_SECONDS == 60


def test_a_short_contribution_never_trains(tmp_path, monkeypatch):
    clips, calls = _run(tmp_path, monkeypatch, 59)
    assert clips == [] and calls == []


def test_a_minute_long_contribution_trains(tmp_path, monkeypatch):
    clips, calls = _run(tmp_path, monkeypatch, 61)
    assert len(clips) == 1 and calls == [1]


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
