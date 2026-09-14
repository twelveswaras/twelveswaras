"""Unit tests for the identify UI logic (D24 — legible recognition).

    python tests/test_identify.py

The point of D24: the answer must be tied to what it heard, and the app must visibly
"listen" before answering. So identify() is a generator that yields a **listening** state
FIRST (before any pitch extraction — reachable without essentia), then a final result whose
info line names the **analysed segment** ("heard 0:00-1:30"). Also covers the mm:ss format.
"""
from __future__ import annotations

import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root importable

import numpy as np

from apps import identify as I

P = namedtuple("P", "raaga confidence")
DASH = "–"  # en dash used in "0:00-1:30"


def test_mmss():
    assert I._mmss(0) == "0:00"
    assert I._mmss(5) == "0:05"
    assert I._mmss(90) == "1:30"
    assert I._mmss(1524) == "25:24"


def test_listening_state_is_yielded_first():
    # The listening state must appear BEFORE any pitch extraction, so reaching it needs no
    # essentia/model — next() runs the generator only up to its first yield.
    gen = I.identify((16000, np.zeros(16000, np.float32)), model=object())
    labels, info, plot, learn_md = next(gen)
    assert labels == {}
    assert "listening" in info.lower()
    assert plot is None and learn_md == ""


def test_idle_prompt_when_no_audio():
    gen = I.identify(None, model=object())
    labels, info, _, _ = next(gen)
    assert labels == {}
    assert info.strip()  # some prompt, not blank


def test_result_names_the_heard_segment():
    # Hermetic: stub the essentia path + the matplotlib plot so this runs in the train env.
    # audio_to_features -> (model windows, tonic, heard_seconds, display_pcd).
    I.pitch_extract.audio_to_features = lambda wav, sr: ([np.ones(2304) / 2304], 200.0, 90.0,
                                                         np.ones(120) / 120)
    I._learn_plot = lambda *a, **k: None

    class FakeModel:
        def aggregate_top_k(self, X, k=3):
            return [P("Tōḍi", 0.42), P("Sāvēri", 0.30), P("Bhairavi", 0.28)]

    outs = list(I.identify((16000, np.zeros(16000, np.float32)), FakeModel()))
    assert "listening" in outs[0][1].lower()            # listened first
    labels, info, _, _ = outs[-1]                       # then answered
    assert set(labels) == {"Tōḍi", "Sāvēri", "Bhairavi"}
    assert f"0:00{DASH}1:30" in info, info              # named the 90 s it heard
    assert "200 Hz" in info


if __name__ == "__main__":
    test_mmss()
    test_listening_state_is_yielded_first()
    test_idle_prompt_when_no_audio()
    test_result_names_the_heard_segment()
    print("IDENTIFY OK — mmss, listening-state-first, idle prompt, heard-segment label all pass")


# ---- tonic estimator: the algorithm must never be cached ---------------------------------------
def test_tonic_estimator_builds_a_fresh_algorithm_per_call(monkeypatch):
    """Essentia algorithm objects are STATEFUL: a reused instance raises "No peak locations" on its
    second compute. The old compiam wrapper re-instantiated internally, so caching it was safe;
    caching a raw essentia algorithm is not, and would break every request after the first. This
    pins the contract so the cache can never creep back in. (Stubs essentia, so it runs in CI,
    which has no essentia installed.)"""
    import sys
    import types

    built = []

    class FakeAlgo:
        def __init__(self, **kw):
            self.kw = kw
            self.calls = 0
            built.append(self)

        def __call__(self, sig):
            self.calls += 1
            if self.calls > 1:                      # mimic essentia's real failure on reuse
                raise RuntimeError("No peak locations")
            return 146.2

    fake = types.ModuleType("essentia.standard")
    fake.TonicIndianArtMusic = FakeAlgo
    monkeypatch.setitem(sys.modules, "essentia", types.ModuleType("essentia"))
    monkeypatch.setitem(sys.modules, "essentia.standard", fake)

    from raaga_id import pitch_extract

    est = pitch_extract._TonicEstimator()
    sig = np.zeros(1024, dtype=np.float32)
    # three calls on the SAME estimator must all succeed, each with its own algorithm
    assert [round(est.extract(sig), 1) for _ in range(3)] == [146.2, 146.2, 146.2]
    assert len(built) == 3, "a fresh TonicIndianArtMusic must be built per call, not cached"
    assert all(a.calls == 1 for a in built)
    # and the honest Sa range is passed through (not silently narrowed)
    assert built[0].kw["minTonicFrequency"] == pitch_extract.TONIC_MIN_HZ == 100.0
