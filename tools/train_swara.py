"""Add swara chains to the shipped dual model: the order of notes, which TDMS cannot see.

    python -m tools.train_swara phrases      # swara phrases per cached window (~5 min, cached)
    python -m tools.train_swara fit          # tune the chain weight + calibration, save the model
    python -m tools.realworld_eval --model models/raaga_xgb.swara.json   # inference env

Why: TDMS sees how pitch moves over one 0.3 s step; a raaga's grammar is longer (vakra movement,
phrase-only notes, sañcāras). A second-order swara chain per raaga captures it (raaga_id/swara).
The shipped model is kept as it is; a clip's answer fuses its probabilities with the chains'
scores (log p + weight * score). Measured 2026-10-24 on the 80 real-world clips: shipped
0.537 / 0.762 top-1 / top-3, with chains 0.688 / 0.787 (16 clips fixed, 4 broken).

Tuning uses only the 25% of tracks the shipped model never trained on (the first 75/25
GroupKFold split by track, as tools/hindustani_spike.fitfull), each cut to its first 150 s
(what the app analyses), with chains fit on the other 75%. The weight minimises held-out
log-loss; the temperature is then fit on the fused output. The saved chains use every track.

The split depends on the scikit-learn version (1.5 and 1.9 assign groups to folds differently),
so the tool checks that the shipped model really never saw the held-out tracks before tuning
on them: held-out windows score ~0.6 top-1, windows it trained on ~0.9.
"""
from __future__ import annotations

import json
import pickle
import shutil
import sys
import time

import numpy as np

from raaga_id import data, features
from raaga_id.config import MODELS_DIR, TDMS_MAX_WINDOWS
from raaga_id.swara import SwaraChains, fuse
from tools.hindustani_spike import CACHE, CARNATIC, HINDUSTANI, FULL_MODEL, iter_hindustani_clips, tag

PHRASES = CACHE.with_name("swara_phrases_cache.pkl")
MODEL = MODELS_DIR / "raaga_xgb.swara.json"
WEIGHTS = [0, 1, 2, 3, 5, 8, 12, 20, 30, 50]
FIRST_WINDOWS = 5          # 5 x 30 s = the 150 s the app analyses (config.INFER_SECONDS)
UNSEEN_MAX_TOP1 = 0.75     # shipped model on truly unseen windows ~0.61; on its training windows ~0.88


def phrases() -> None:
    """Swara phrases for every cached window, in cache order. Checks row for row that the
    rebuilt TDMS windows are the cached ones, so phrases and surfaces can't be misaligned."""
    if PHRASES.exists():
        print(f"{PHRASES} exists; delete it to rebuild", flush=True)
        return
    t0 = time.time()
    labels, groups, surfs, phs = [], [], [], []
    car = data.iter_pitch_clips(only_vocab=True, datasets=("compmusic_raga",), tradition="carnatic")
    for tradition, clips in ((CARNATIC, car), (HINDUSTANI, iter_hindustani_clips())):
        for i, pc in enumerate(clips, 1):
            s, p = features.model_windows(pc.times, pc.freqs, pc.tonic_hz,
                                          max_windows=TDMS_MAX_WINDOWS, phrases=True)
            labels += [tag(pc.raaga, tradition)] * len(s)
            groups += [pc.track_id] * len(s)
            surfs += s
            phs += p
            if i % 50 == 0:
                print(f"  {tradition} {i} tracks, {len(surfs)} windows ({time.time() - t0:.0f}s)", flush=True)
    ref = np.load(CACHE, allow_pickle=True)
    if not (labels == ref["y"].tolist() and groups == ref["groups"].tolist()
            and np.allclose(np.vstack(surfs), ref["X"], atol=1e-6)):
        raise SystemExit("rebuilt windows differ from the TDMS cache; rebuild the cache first")
    with open(PHRASES, "wb") as f:
        pickle.dump([[p.tolist() for p in w] for w in phs], f)
    print(f"{len(phs)} windows match the cache; phrases -> {PHRASES} ({time.time() - t0:.0f}s)", flush=True)


def fit() -> None:
    from sklearn.model_selection import GroupKFold

    from raaga_id import calibrate as C
    from raaga_id.model import RaagaXGB

    d = np.load(CACHE, allow_pickle=True)
    X, groups = d["X"], d["groups"]
    with open(PHRASES, "rb") as f:
        ph = [[np.array(p) for p in w] for w in pickle.load(f)]
    shipped = RaagaXGB.load(FULL_MODEL)
    classes = shipped.classes
    yi = np.array([classes.index(v) for v in d["y"]])
    n = len(classes)
    tr, te = next(GroupKFold(n_splits=4).split(X, yi, groups))

    Pw = shipped.predict_proba(X[te])
    unseen = float((Pw.argmax(1) == yi[te]).mean())
    print(f"shipped model on the held-out windows: top-1 {unseen:.3f}", flush=True)
    if unseen > UNSEEN_MAX_TOP1:
        raise SystemExit("the shipped model has seen these 'held-out' tracks: this scikit-learn splits "
                         "differently from the one it was trained with. Tuning here would be biased.")

    chains75 = SwaraChains.fit([ph[i] for i in tr], yi[tr], n)
    Sw = chains75.score_windows([ph[i] for i in te])
    tracks = list(dict.fromkeys(groups[te].tolist()))
    rows = {t: np.flatnonzero(groups[te] == t)[:FIRST_WINDOWS] for t in tracks}
    P = np.vstack([Pw[rows[t]].mean(0) for t in tracks])
    S = np.vstack([Sw[rows[t]].mean(0) for t in tracks])
    y = np.array([yi[te][rows[t][0]] for t in tracks])
    print(f"tuning on {len(tracks)} held-out tracks, first {FIRST_WINDOWS * 30} s each", flush=True)
    losses = []
    for w in WEIGHTS:
        F = fuse(P, S, w)
        losses.append(C.nll(F, y))
        top3 = np.mean([y[i] in np.argsort(-F[i])[:3] for i in range(len(y))])
        print(f"  weight {w:3d}: top-1 {(F.argmax(1) == y).mean():.3f}  top-3 {top3:.3f}  "
              f"log-loss {losses[-1]:.3f}", flush=True)
    weight = WEIGHTS[int(np.argmin(losses))]
    T = C.fit_temperature(fuse(P, S, weight), y)
    print(f"chosen: weight {weight}, temperature {T:.3f}", flush=True)

    shutil.copyfile(FULL_MODEL, MODEL)
    MODEL.with_suffix(".classes.json").write_text(json.dumps(classes, ensure_ascii=False))
    SwaraChains.fit(ph, yi, n, weight=weight).save(MODEL.with_suffix(".chain.npz"), classes)
    C.save_temperature(MODEL, T, extra={"fit": {"method": "temperature-heldout", "n_tracks": len(tracks),
                                                "chain_weight": weight,
                                                "note": "dual model + swara chains, fused; first 150 s"}})
    print(f"model -> {MODEL} (+ .classes.json, .chain.npz, .calib.json)", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "phrases":
        phrases()
    elif cmd == "fit":
        fit()
    else:
        raise SystemExit("usage: python -m tools.train_swara [phrases|fit]")
