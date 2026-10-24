"""Cold-start priming. A sleeping recognizer took 42.6 s to give its first answer (2026-10-24), and
most visitors gave up inside that window. /warm pays every first-call cost in the background as
soon as the page loads: the model load, the essentia import, and one real pass of the pipeline.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from raaga_id import pitch_extract  # noqa: E402
from raaga_id.config import TDMS_WINDOW_S  # noqa: E402


def test_priming_clip_is_long_enough_to_exercise_the_whole_pipeline():
    """Shorter than one TDMS window and the model never runs, so its first-call cost stays put."""
    y = pitch_extract.priming_clip()
    assert y.dtype == np.float32 and y.ndim == 1
    assert y.size / pitch_extract.TONIC_SR > TDMS_WINDOW_S
    assert 0.05 < float(np.abs(y).max()) <= 1.0


def test_priming_clip_actually_produces_model_windows():
    """The point of priming: tonic, melody and TDMS all run, so the classifier gets called too.
    Needs essentia, so it runs in the inference env, not in CI."""
    pytest.importorskip("essentia")
    windows, tonic, secs, _ = pitch_extract.audio_to_features(pitch_extract.priming_clip(),
                                                             pitch_extract.TONIC_SR)
    assert tonic and windows, "a priming clip that yields no windows never reaches the model"


@pytest.fixture
def api(monkeypatch):
    pytest.importorskip("fastapi")
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "space"))
    import importlib

    import api as module
    module = importlib.reload(module)
    return module


def test_warm_starts_priming_once_and_answers_immediately(api, monkeypatch):
    from fastapi.testclient import TestClient

    started = []
    gate = threading.Event()
    monkeypatch.setattr(api, "_prime", lambda: (started.append(1), gate.wait(5)))
    client = TestClient(api.app)
    first = client.get("/warm").json()
    second = client.get("/warm").json()
    gate.set()
    assert first == {"warm": False} and second == {"warm": False}   # answers without waiting
    assert len(started) == 1, "repeat pings must not start a second priming run"


def test_model_loads_once_under_concurrent_first_calls(api, monkeypatch):
    """The warm thread and a visitor's first identify can race; the model must load exactly once."""
    loads = []

    class Fake:
        classes = ["x"]

    def slow_load(_):
        loads.append(1)
        threading.Event().wait(0.2)
        return Fake()

    monkeypatch.setattr(api, "_model", None)
    monkeypatch.setattr(api.RaagaXGB, "load", staticmethod(slow_load))
    monkeypatch.setattr(api.pitch_extract, "warmup", lambda: None)
    ts = [threading.Thread(target=api.model) for _ in range(4)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(loads) == 1


# ---- priming must take the SAME decode path as a real upload -----------------------------------
# PR #33's priming handed the pipeline an in-memory array, skipping file decoding. Measured on
# production afterwards, the first identify still took 35.4 s: the one-time cost was the first
# librosa.load (numba compiling librosa's code), which only decoding a real file pays.
def test_identify_and_priming_decode_through_the_same_helper(api, monkeypatch):
    from fastapi.testclient import TestClient

    seen = []
    real_decode = api.decode

    def spy(raw, suffix):
        seen.append(suffix)
        return real_decode(raw, suffix)

    class FakeModel:
        classes = ["x"]

        def aggregate_top_k(self, X, k):
            return []

    monkeypatch.setattr(api, "decode", spy)
    monkeypatch.setattr(api, "model", lambda: FakeModel())
    monkeypatch.setattr(api.pitch_extract, "audio_to_features", lambda y, sr: ([], None, 0.0, None))

    api._prime()
    assert seen == [".wav"], "priming must decode a real file, not hand over an array"

    import io

    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, api.pitch_extract.priming_clip(seconds=6), api.pitch_extract.TONIC_SR, format="WAV")
    TestClient(api.app).post("/identify", files={"audio": ("clip.wav", buf.getvalue(), "audio/wav")})
    assert seen == [".wav", ".wav"], "identify must use the same decode helper"


# ---- the compiled code must ship inside the image ----------------------------------------------
# A numba cache written at build time removes the compile from every cold boot. It is only reused
# if the CPU name at runtime matches the one it was built for; the image is built under emulation
# on a Mac and runs on Cloudflare hardware, so it must be built for a generic CPU, or the cache
# silently misses in production and the 30 s compile comes back.
def test_dockerfile_bakes_a_portable_numba_cache():
    import re

    df = (Path(__file__).resolve().parent.parent / "cloudflare" / "recognizer" / "Dockerfile").read_text()
    assert re.search(r"NUMBA_CACHE_DIR=\S+", df), "numba must cache to a fixed path inside the image"
    assert "NUMBA_CPU_NAME=generic" in df, "a host-specific cache would miss on Cloudflare's CPUs"
    copy_at = df.index("COPY app/ .")
    prime_at = df.index("api._prime()")
    assert copy_at < prime_at, "the build-time warm-up must run after the app is copied in"
    assert df.index("MODEL_PATH=") < prime_at, "MODEL_PATH must be set before the warm-up loads it"
