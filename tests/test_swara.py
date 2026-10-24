"""Unit tests for swara phrases and the per-raaga swara chains.

    python tests/test_swara.py

A melody becomes phrases of swaras (semitones above Sa): notes held under 60 ms are gamaka
transit and dropped, a repeated note is one swara, and a pause longer than 250 ms ends the
phrase. Each raaga gets a second-order chain over those swaras; a clip is scored by how likely
each raaga's chain finds its phrases (the order TDMS cannot see).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from raaga_id import features, swara

HOP = 0.0044
SA = 146.8


def _melody(parts, sa=SA):
    """parts: (semitones above Sa or None for silence, seconds) -> (times, f0)."""
    f0 = []
    for semi, dur in parts:
        f0 += [0.0 if semi is None else sa * 2 ** (semi / 12)] * int(round(dur / HOP))
    f0 = np.array(f0)
    return np.arange(f0.size) * HOP, f0


PARTS = [(0, .3), (2, .03), (0, .2), (4, .3), (None, .4), (7, .3), (12, .3), (None, .1), (11, .3)]


def test_phrases_drop_gamaka_merge_repeats_split_on_pauses():
    t, f0 = _melody(PARTS)
    got = [p.tolist() for p in swara.phrases(t, f0, SA)]
    assert got == [[0, 4], [7, 12, 11]]


def test_phrases_are_tonic_relative():
    t, f0 = _melody(PARTS, sa=220.0)
    assert [p.tolist() for p in swara.phrases(t, f0, 220.0)] == [[0, 4], [7, 12, 11]]


def test_unvoiced_window_has_no_phrases():
    t = np.arange(100) * HOP
    assert swara.phrases(t, np.zeros(100), SA) == []


def _long_melody(seconds=89):
    rng = np.random.default_rng(0)
    parts = [(int(s), .25) for s in rng.choice([0, 2, 4, 7, 9, 12], int(seconds / .25))]
    t, f0 = _melody(parts)
    f0[int(32 / HOP):int(58 / HOP)] = 0.0       # window 2 (30-60 s) mostly silent: junk-gated
    return t, f0


def test_window_phrases_align_with_model_windows():
    t, f0 = _long_melody()
    plain = features.model_windows(t, f0, SA)
    surfs, phs = features.model_windows(t, f0, SA, phrases=True)
    assert len(plain) == len(surfs) == len(phs) == 2          # 0-30 s and 60-90 s; 30-60 s gated
    assert all(np.array_equal(a, b) for a, b in zip(plain, surfs))
    t0, f00 = t[t < 30], f0[t < 30]
    assert [p.tolist() for p in phs[0]] == [p.tolist() for p in swara.phrases(t0, f00, SA)]


def _two_raagas():
    up = [np.array([0, 4, 7, 12, 7, 4, 0])] * 5         # major-ish arch
    down = [np.array([0, 3, 7, 12, 7, 3, 0])] * 5       # minor-ish arch
    return swara.SwaraChains.fit([up, up, down, down], np.array([0, 0, 1, 1]), 2)


def test_chain_prefers_the_raaga_that_moves_like_the_clip():
    ch = _two_raagas()
    s = ch.score([np.array([0, 4, 7, 12])])
    assert s.shape == (2,) and s[0] > s[1]
    s = ch.score([np.array([12, 7, 3, 0])])
    assert s[1] > s[0]


def test_chain_learns_order_not_just_notes():
    # same notes, opposite direction: only a sequence model can tell these apart
    asc = [np.array([0, 2, 4, 5, 7])] * 5
    desc = [np.array([7, 5, 4, 2, 0])] * 5
    ch = swara.SwaraChains.fit([asc, desc], np.array([0, 1]), 2)
    assert ch.score([np.array([0, 2, 4, 5])]).argmax() == 0
    assert ch.score([np.array([5, 4, 2, 0])]).argmax() == 1


def test_empty_window_scores_neutral():
    assert np.array_equal(_two_raagas().score([]), np.zeros(2))


def test_save_load_roundtrip(tmp_path=None):
    import tempfile

    ch = _two_raagas()
    path = Path(tmp_path or tempfile.mkdtemp()) / "m.chain.npz"
    ch.save(path, ["A", "B"])
    back = swara.SwaraChains.load(path, ["A", "B"])
    q = [np.array([0, 4, 7]), np.array([12, 7])]
    assert np.allclose(back.score(q), ch.score(q))


def test_score_windows_stacks_per_window_scores():
    ch = _two_raagas()
    wins = [[np.array([0, 4, 7])], [], [np.array([7, 3, 0])]]
    S = ch.score_windows(wins)
    assert S.shape == (3, 2)
    assert np.allclose(S[0], ch.score(wins[0])) and np.allclose(S[1], 0)


def _model_with_chains(weight=50.0):
    """A tiny model whose TDMS input is noise, so only the swara chains can tell the raagas apart."""
    from raaga_id.model import RaagaXGB

    rng = np.random.default_rng(0)
    up, down = [np.array([0, 4, 7, 12, 7, 4, 0])], [np.array([0, 3, 7, 12, 7, 3, 0])]
    ch = swara.SwaraChains.fit([up, down] * 20, np.array([0, 1] * 20), 2, weight=weight)
    m = RaagaXGB(["Up", "Down"], chains=ch).fit(rng.random((40, 5)), np.array([0, 1] * 20), n_estimators=5)
    return m, up, down


def test_chains_decide_when_the_surface_cannot():
    m, up, down = _model_with_chains()
    noise = np.random.default_rng(1).random((2, 5))
    assert m.aggregate_top_k(noise, k=1, phrases=[up, up])[0].raaga == "Up"
    assert m.aggregate_top_k(noise, k=1, phrases=[down, down])[0].raaga == "Down"


def test_zero_weight_is_the_plain_model():
    m, up, _ = _model_with_chains(weight=0.0)
    x = np.random.default_rng(1).random((2, 5))
    fused = m.aggregate_top_k(x, k=2, phrases=[up, up])
    plain = m._decode(m.predict_proba(x).mean(0), 2)
    assert [p.raaga for p in fused] == [p.raaga for p in plain]
    assert np.allclose([p.confidence for p in fused], [p.confidence for p in plain])


def test_fuse_adds_weighted_chain_evidence_in_log_space():
    P = np.array([0.6, 0.4])
    S = np.array([-1.0, -0.5])
    got = swara.fuse(P, S, weight=2.0)
    want = np.exp(np.log(P) + 2.0 * S)
    assert np.allclose(got, want / want.sum())


def test_model_with_chains_refuses_to_guess_without_phrases():
    m, _, _ = _model_with_chains()
    try:
        m.aggregate_top_k(np.zeros((1, 5)))
    except ValueError:
        return
    raise AssertionError("a chain model must not silently answer without swara phrases")


def test_model_chains_survive_save_and_load(tmp_path=None):
    import tempfile

    from raaga_id.model import RaagaXGB

    m, up, _ = _model_with_chains(weight=7.0)
    path = m.save(Path(tmp_path or tempfile.mkdtemp()) / "raaga_xgb.test.json")
    assert path.with_suffix(".chain.npz").exists()
    back = RaagaXGB.load(path)
    assert back.chains.weight == 7.0
    x = np.zeros((1, 5))
    a, b = back.aggregate_top_k(x, k=2, phrases=[up]), m.aggregate_top_k(x, k=2, phrases=[up])
    assert [p.raaga for p in a] == [p.raaga for p in b]
    assert np.allclose([p.confidence for p in a], [p.confidence for p in b])


def test_model_without_chains_is_unchanged():
    from raaga_id.model import RaagaXGB

    rng = np.random.default_rng(0)
    m = RaagaXGB(["A", "B"]).fit(rng.random((20, 4)), np.array([0, 1] * 10), n_estimators=5)
    assert m.chains is None
    assert len(m.aggregate_top_k(rng.random((3, 4)), k=2)) == 2

def test_chains_for_other_classes_are_refused(tmp_path=None):
    import tempfile

    from raaga_id.model import RaagaXGB

    m, _, _ = _model_with_chains()
    path = m.save(Path(tmp_path or tempfile.mkdtemp()) / "raaga_xgb.test.json")
    path.with_suffix(".classes.json").write_text('["Down", "Up"]')   # same size, other order
    try:
        RaagaXGB.load(path)
    except ValueError:
        return
    raise AssertionError("chains built for a different class list must not load silently")


def test_saving_without_chains_removes_a_stale_sidecar(tmp_path=None):
    import tempfile

    from raaga_id.model import RaagaXGB

    m, _, _ = _model_with_chains()
    path = m.save(Path(tmp_path or tempfile.mkdtemp()) / "raaga_xgb.test.json")
    m.chains = None
    m.save(path)
    assert not path.with_suffix(".chain.npz").exists()
    assert RaagaXGB.load(path).chains is None


def test_phrases_must_match_the_windows():
    m, up, _ = _model_with_chains()
    try:
        m.aggregate_top_k(np.zeros((2, 5)), phrases=[up])
    except ValueError:
        return
    raise AssertionError("one phrase list per window, or the evidence is misaligned")


def test_assemble_fails_without_the_chains(tmp_path=None):
    """A swara build without its chains would serve unfused answers under the fused temperature."""
    import shutil
    import subprocess
    import tempfile

    root = Path(tmp_path or tempfile.mkdtemp())
    repo = Path(__file__).resolve().parent.parent
    (root / "cloudflare/recognizer").mkdir(parents=True)
    shutil.copy(repo / "cloudflare/recognizer/assemble.sh", root / "cloudflare/recognizer/")
    for d in ("space", "raaga_id", "models"):
        (root / d).mkdir()
    for f in ("space/api.py", "space/requirements-api.txt", "raagas.json", "raagas.hindustani.json",
              "models/raaga_xgb.swara.json", "models/raaga_xgb.swara.calib.json"):
        (root / f).write_text("{}")
    (root / "models/raaga_xgb.swara.classes.json").write_text("[]")
    r = subprocess.run(["bash", str(root / "cloudflare/recognizer/assemble.sh"), "swara"], capture_output=True)
    assert r.returncode != 0, "assemble.sh swara must fail when the .chain.npz is missing"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
