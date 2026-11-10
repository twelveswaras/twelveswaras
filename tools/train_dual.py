"""Training recipe for the live dual-tradition model (40 Carnatic + 30 Hindustani raagas).

    python -m tools.train_dual extract          # windowed TDMS for every IAMRRD track -> CACHE
    python -m tools.train_dual fitfull [400]    # chunked, resumable XGBoost fit -> FULL_MODEL
    python -m tools.train_dual calib            # temperature on the held-out tracks
    python -m tools.train_swara phrases && python -m tools.train_swara fit   # then the swara chains

Carnatic tracks come through data.iter_pitch_clips (IAMRRD, 40-raaga vocabulary). Hindustani
tracks are read straight from the IAMRRD feature files (Hindustani/features/<ragaId>/.../*.pitch
+ .tonic), which mirdata's index does not expose; same pitch format and tonic, so the features
are comparable. Every label carries its tradition ("<name> (Carnatic)"), so the two Todi and the
two Sri stay distinct classes. The model trains on the first 75/25 GroupKFold split by track
(load_split), clean plus one degraded copy (degrade); the held-out 25% calibrates it.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from raaga_id import data, features
from raaga_id.config import DATA_DIR, MODELS_DIR, TDMS_MAX_WINDOWS
from raaga_id.tradition import tag

HRD_ROOT = DATA_DIR / "compmusic_raga" / "RagaDataset" / "Hindustani"
HRD_MAP = HRD_ROOT / "_info_" / "ragaId_to_ragaName_mapping.json"
CACHE = Path(__file__).resolve().parent.parent / "supporting-docs" / "hindustani_spike_cache.npz"
# scratchpad path is session-specific; keep the cache in the gitignored supporting-docs so a
# re-run of analyze does not recompute features.

CARNATIC = "Carnatic"
HINDUSTANI = "Hindustani"


def _read_pitch(path: Path):
    """(times, freqs) from a 2-column IAMRRD .pitch file. 0.0 marks unvoiced (Melodia)."""
    import pandas as pd

    arr = pd.read_csv(path, sep="\t", header=None, dtype="float32").to_numpy()
    return arr[:, 0], arr[:, 1]


def iter_hindustani_clips():
    """Yield PitchClip for every Hindustani IAMRRD recording, read straight off disk.

    Layout: features/<ragaId>/<artist>/<album>/<title_mbid>.pitch (+ sibling .tonic). The
    top-level dir under features/ is the ragaId, mapped to a raaga name via the info json.
    """
    mapping = json.loads(HRD_MAP.read_text(encoding="utf-8"))
    feat_root = HRD_ROOT / "features"
    for pitch_path in sorted(feat_root.rglob("*.pitch")):
        rel = pitch_path.relative_to(feat_root)
        raga_id = rel.parts[0]
        name = mapping.get(raga_id)
        if not name:
            continue
        tonic_path = pitch_path.with_suffix(".tonic")
        if not tonic_path.exists():
            continue
        try:
            tonic = float(tonic_path.read_text().strip())
        except ValueError:
            continue
        if tonic <= 0:
            continue
        times, freqs = _read_pitch(pitch_path)
        yield data.PitchClip(
            dataset="iamrrd_hindustani",
            track_id=pitch_path.stem,             # <title>_<mbid>, unique per recording
            raaga=f"{name} ({HINDUSTANI})",
            tonic_hz=tonic,
            times=times,
            freqs=freqs,
        )


def _windows_for(pc):
    return features.model_windows(pc.times, pc.freqs, pc.tonic_hz, max_windows=TDMS_MAX_WINDOWS)


def extract() -> None:
    """Build the combined per-window TDMS matrix and cache it (X, y, groups, tradition)."""
    X, y, groups, trad = [], [], [], []

    def add(pc, tradition, i, total):
        label = tag(pc.raaga, tradition)   # Hindustani arrives pre-tagged, Carnatic plain
        wins = _windows_for(pc)
        for w in wins:
            X.append(w)
            y.append(label)
            groups.append(pc.track_id)
            trad.append(tradition)
        if i % 25 == 0:
            print(f"  [{tradition}] {i}/{total} tracks, {len(X)} windows so far", flush=True)

    t0 = time.time()
    print("loading Carnatic (IAMRRD, 40-vocab) via the existing pipeline ...", flush=True)
    car = list(data.iter_pitch_clips(only_vocab=True, datasets=("compmusic_raga",), tradition="carnatic"))
    print(f"  {len(car)} Carnatic clips", flush=True)
    for i, pc in enumerate(car, 1):
        add(pc, CARNATIC, i, len(car))

    print("loading Hindustani (IAMRRD feature files, direct) ...", flush=True)
    hin = list(iter_hindustani_clips())
    print(f"  {len(hin)} Hindustani clips", flush=True)
    for i, pc in enumerate(hin, 1):
        add(pc, HINDUSTANI, i, len(hin))

    X = np.vstack(X).astype("float32")
    y = np.array(y)
    groups = np.array(groups)
    trad = np.array(trad)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CACHE, X=X, y=y, groups=groups, trad=trad)
    print(f"cached {X.shape[0]} windows x {X.shape[1]}d -> {CACHE}  ({time.time()-t0:.0f}s)", flush=True)
    _support(y, trad)


def _support(y, trad):
    from collections import Counter
    print("\nclass support (windows):")
    c = Counter(y)
    for tradition in (CARNATIC, HINDUSTANI):
        names = sorted(n for n in c if n.endswith(f"({tradition})"))
        print(f"  {tradition}: {len(names)} classes")


FULL_MODEL = MODELS_DIR / "raaga_xgb.dual.json"       # RaagaXGB-loadable (booster + .classes.json)
FULL_RESULTS = Path(__file__).resolve().parent.parent / "supporting-docs" / "hindustani_dual_full_results.json"


def load_split():
    """(X, labels, groups, traditions, classes, class index per window, train rows, held-out rows).
    The split is the first GroupKFold(4) split by track: the one the live model held out. It
    depends on the scikit-learn version (1.5 and 1.9 split differently), so train and evaluate
    in the same environment the model was trained in."""
    from sklearn.model_selection import GroupKFold

    d = np.load(CACHE, allow_pickle=True)
    X, y, groups, trad = d["X"], d["y"], d["groups"], d["trad"]
    classes = sorted(set(y.tolist()))
    cidx = {c: i for i, c in enumerate(classes)}
    yi = np.array([cidx[v] for v in y])
    tr, te = next(GroupKFold(n_splits=4).split(X, yi, groups))
    return X, y, groups, trad, classes, yi, tr, te


def track_means(proba, groups):
    """(tracks in first-seen order, per-track mean of the window probabilities): the
    granularity the app answers at."""
    tracks = list(dict.fromkeys(groups.tolist()))
    return tracks, np.vstack([proba[groups == t].astype(np.float64).mean(0) for t in tracks])


def degrade(X, seed: int = 0):
    """One wild-like degraded copy of TDMS windows (n, 2304): reshape 48x48, gaussian blur (pitch
    smearing) + additive spurious mass + a +-1-bin circular tonic jitter, renormalize.

    Surface-level augmentation of the feature (not the audio, which we lack for IAMRRD). It
    regularises against the exact corruption wild recordings produce (reverb/noise/weak drone ->
    a noisier melody surface), so the model learns raaga structure that survives it. VALIDATED:
    training on clean + one degraded copy beat the incumbent on every eval — held-out 25% CV
    0.877 -> 0.908 (Carnatic +0.05, Hindustani flat), frozen benchmark 0.806 -> 0.830, and the
    in-the-wild set top-1 +0.04 / top-3 +0.11 (stable across degradation seeds).
    """
    from scipy.ndimage import gaussian_filter
    rng = np.random.default_rng(seed)
    out = np.empty_like(X)
    for i in range(X.shape[0]):
        w = X[i].reshape(48, 48)
        w = gaussian_filter(w, sigma=rng.uniform(0.4, 1.0))
        w = w + rng.uniform(0, 0.02) * w.max() * rng.random(w.shape)
        s = int(rng.integers(-1, 2))
        if s:
            w = np.roll(np.roll(w, s, 0), s, 1)
        t = w.sum()
        out[i] = (w / t if t > 0 else w).ravel()
    return out.astype(np.float32)


def fitfull(total: int = 400, chunk: int = 50, augment: bool = True) -> None:
    """Train the full-dim (no PCA), full-data dual model with INCREMENTAL warm-start.

    A single full-dim, 70-class fit does not finish inside this environment's compute window, so
    training is done in chunks of `chunk` boosting rounds: after each chunk the booster is saved
    to FULL_MODEL, so a kill mid-way loses at most one chunk and the next run resumes from the
    saved trees. Same product hyperparameters (depth 6, eta 0.1, hist) and the SAME 75/25
    grouped-by-track split the product uses, so the held-out number is honest.

    augment=True (default) trains on the clean train split PLUS one surface-degraded copy of it
    (see degrade()); a memory-lean QuantileDMatrix keeps the doubled data trainable here. This is
    the shipped recipe — it beat the un-augmented incumbent on every eval (CV, frozen benchmark,
    and the in-the-wild set). augment=False reproduces the old clean-only model.
    """
    import xgboost as xgb

    X, y, groups, trad, classes, yi, tr_i, te_i = load_split()
    params = {"objective": "multi:softprob", "num_class": len(classes),
              "max_depth": 6, "eta": 0.1, "tree_method": "hist", "max_bin": 128, "nthread": 0}
    if augment:
        Xtr = np.vstack([X[tr_i], degrade(X[tr_i])])
        dtrain = xgb.QuantileDMatrix(Xtr, label=np.concatenate([yi[tr_i], yi[tr_i]]), max_bin=128)
        del Xtr
        print(f"augment: {len(tr_i)} clean + {len(tr_i)} degraded train windows", flush=True)
    else:
        dtrain = xgb.DMatrix(X[tr_i], label=yi[tr_i])

    booster, done = None, 0
    if FULL_MODEL.exists():
        booster = xgb.Booster()
        booster.load_model(str(FULL_MODEL))
        done = booster.num_boosted_rounds()
        print(f"resuming from {done}/{total} rounds", flush=True)
    print(f"train {len(tr_i)} windows x {X.shape[1]}d, {len(classes)} classes, "
          f"{len(set(groups[tr_i].tolist()))} tracks; chunk={chunk}", flush=True)

    while done < total:
        t0 = time.time()
        step = min(chunk, total - done)
        booster = xgb.train(params, dtrain, num_boost_round=step, xgb_model=booster)
        booster.save_model(str(FULL_MODEL))
        FULL_MODEL.with_suffix(".classes.json").write_text(json.dumps(classes, ensure_ascii=False))
        done = booster.num_boosted_rounds()
        print(f"  rounds {done}/{total} saved ({time.time()-t0:.0f}s for {step})", flush=True)

    # held-out evaluation, per track
    tracks, P = track_means(booster.predict(xgb.DMatrix(X[te_i])), groups[te_i])
    track_true = {g: lab for g, lab in zip(groups, y)}
    track_trad = {g: t for g, t in zip(groups, trad)}
    trad_of_class = {c: (CARNATIC if c.endswith(f"({CARNATIC})") else HINDUSTANI) for c in classes}
    pred = {g: classes[int(p.argmax())] for g, p in zip(tracks, P)}

    def acc(sel):
        pts = [(pred[g], track_true[g]) for g in pred if sel(g)]
        return float(np.mean([p == t for p, t in pts])) if pts else float("nan"), len(pts)
    ov, nov = acc(lambda g: True)
    ca, nca = acc(lambda g: track_trad[g] == CARNATIC)
    hi, nhi = acc(lambda g: track_trad[g] == HINDUSTANI)
    leak = sum(1 for g in pred if track_trad[g] != trad_of_class[pred[g]])
    res = {"model": "full-dim (2304) no PCA", "rounds": done, "test_tracks": nov,
           "overall_top1": ov, "carnatic_top1": ca, "carnatic_n": nca,
           "hindustani_top1": hi, "hindustani_n": nhi,
           "cross_tradition_leak": leak, "cross_tradition_leak_frac": leak / nov}
    FULL_RESULTS.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print("\n===== FULL-DIM DUAL MODEL (held-out 25%) =====")
    print(f"rounds {done} | overall {ov:.3f} (n={nov}) | Carnatic {ca:.3f} (n={nca}) | "
          f"Hindustani {hi:.3f} (n={nhi}) | cross-tradition leak {leak}/{nov}={leak/nov:.3f}")
    print(f"model -> {FULL_MODEL}  (RaagaXGB-loadable; shipped model untouched)")
    print(f"results -> {FULL_RESULTS}", flush=True)


def calib() -> None:
    """Fit the dual model's temperature and analyze abstention, on the leak-free held-out 25%.

    Full k-fold OOF calibration would retrain the model k times, ~1.5h at
    full-dim. The held-out split the model never trained on is a valid, cheap calibration set for
    a single temperature scalar. Writes <dual>.calib.json (picked up automatically by
    RaagaXGB.load) and prints an abstention table to pick the site thresholds for BOTH traditions.
    """
    import xgboost as xgb

    from raaga_id import calibrate as C

    X, y, groups, trad, classes, yi, _, te_i = load_split()
    booster = xgb.Booster()
    booster.load_model(str(FULL_MODEL))
    tracks, P = track_means(booster.predict(xgb.DMatrix(X[te_i])), groups[te_i])
    first = {g: i for i, g in reversed(list(enumerate(groups[te_i].tolist())))}
    ytrue = np.array([yi[te_i][first[g]] for g in tracks])
    trad_arr = np.array([trad[te_i][first[g]] for g in tracks])

    T = C.fit_temperature(P, ytrue)
    Pc = C.apply_temperature(P, T)
    print(f"tracks {len(tracks)} | fitted T = {T:.3f}  (argmax-preserving, top-1 unchanged)")
    print(f"  NLL {C.nll(P, ytrue):.3f} -> {C.nll(Pc, ytrue):.3f}   "
          f"ECE {C.ece(P, ytrue):.3f} -> {C.ece(Pc, ytrue):.3f}   "
          f"mean top-1 conf {P.max(1).mean():.3f} -> {Pc.max(1).mean():.3f}")

    C.save_temperature(FULL_MODEL, T, extra={"fit": {"method": "temperature-heldout",
                        "n_tracks": len(tracks), "note": "fit on the 75/25 held-out split, not full k-fold OOF"}})
    print(f"saved -> {C.temperature_path(FULL_MODEL)}")

    # abstention table on the CALIBRATED per-track top-1 confidence
    conf = Pc.max(1)
    correct = (Pc.argmax(1) == ytrue)
    print("\nabstention (calibrated): threshold -> shown-top1 (kept) / abstain-rate, overall | Carnatic | Hindustani")
    for thr in (0.20, 0.30, 0.40, 0.45, 0.50, 0.60):
        def cell(mask):
            kept = mask & (conf >= thr)
            shown = correct[kept].mean() if kept.any() else float("nan")
            abst = 1 - kept.sum() / max(mask.sum(), 1)
            return f"{shown:.2f}/{abst:.0%}"
        allm = np.ones(len(tracks), bool)
        cm = trad_arr == CARNATIC
        hm = trad_arr == HINDUSTANI
        print(f"  {thr:.2f} -> {cell(allm):>9} | {cell(cm):>9} | {cell(hm):>9}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "extract"
    if cmd == "extract":
        extract()
    elif cmd == "calib":
        calib()
    elif cmd == "fitfull":
        total = int(sys.argv[2]) if len(sys.argv) > 2 else 400
        chunk = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        fitfull(total, chunk)
    else:
        raise SystemExit("usage: python -m tools.train_dual [extract|calib|fitfull [total] [chunk]]")
