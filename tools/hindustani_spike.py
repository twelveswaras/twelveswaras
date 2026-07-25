"""Phase 0 Hindustani spike (derisking, no deploy, nothing existing is modified).

Question this answers: if we train ONE unified model over Carnatic-40 + Hindustani-30,
how good is it, and does the model confuse the two traditions on scale-identical pairs
(Bhup/Mohanam, Yaman/Kalyani, Malkauns/Hindolam)? That go/no-go decides unified-vs-router.

Design notes (why this is safe):
  - The existing Carnatic model, vocab, API and site are untouched. This is a standalone tool.
  - Carnatic clips come through the PROVEN path (data.iter_pitch_clips, IAMRRD, 40-vocab).
  - Hindustani clips are read directly from the IAMRRD feature files already in the repo
    (data/compmusic_raga/RagaDataset/Hindustani/features/<ragaId>/.../<title>.pitch + .tonic),
    which mirdata's compmusic_raga index does not expose. Same 2-column pitch format and same
    single-float .tonic as the Carnatic side, so features are numerically comparable.
  - Labels are tradition-tagged ("<name> (Carnatic)" / "<name> (Hindustani)") so the two Todi
    and the two Sri never collapse into one class.
  - The feature matrix is cached to the scratchpad; the trained dual model is written to a NEW
    path (models/raaga_xgb.dual.json), never over the shipped models/raaga_xgb.json.

Usage:
    python -m tools.hindustani_spike extract   # build + cache the combined TDMS features
    python -m tools.hindustani_spike analyze    # grouped CV + cross-tradition confusion + save dual model
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

from raaga_id import data, features
from raaga_id.config import DATA_DIR, MODELS_DIR, TDMS_MAX_WINDOWS

HRD_ROOT = DATA_DIR / "compmusic_raga" / "RagaDataset" / "Hindustani"
HRD_MAP = HRD_ROOT / "_info_" / "ragaId_to_ragaName_mapping.json"
CACHE = Path(__file__).resolve().parent.parent / "supporting-docs" / "hindustani_spike_cache.npz"
# scratchpad path is session-specific; keep the cache in the gitignored supporting-docs so a
# re-run of analyze does not recompute features.
DUAL_MODEL = MODELS_DIR / "raaga_xgb.dual.json"
RESULTS_JSON = Path(__file__).resolve().parent.parent / "supporting-docs" / "hindustani_spike_results.json"

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
        # Tag EVERY label with its tradition, regardless of whether pc.raaga arrived pre-tagged
        # (Hindustani) or plain (Carnatic, from iter_pitch_clips). Strip any existing tag first so
        # we never double-tag. This is what keeps the two Todi and the two Sri as distinct classes.
        base = pc.raaga
        for suf in (f" ({CARNATIC})", f" ({HINDUSTANI})"):
            if base.endswith(suf):
                base = base[: -len(suf)]
        label = f"{base} ({tradition})"
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
    tracks_by_class = {}
    # count DISTINCT tracks per class using the groups is better, but a window count is a proxy here
    print("\nclass support (windows):")
    c = Counter(y)
    for tradition in (CARNATIC, HINDUSTANI):
        names = sorted(n for n in c if n.endswith(f"({tradition})"))
        print(f"  {tradition}: {len(names)} classes")


def analyze(n_estimators: int = 250) -> None:
    """ONE grouped (by track) 75/25 split over the combined set: train once, evaluate on the
    held-out tracks, report per-tradition accuracy and cross-tradition confusion, and save the
    trained model to a NEW path. A single split (not k-fold) is enough for a go/no-go and is one
    XGBoost fit instead of five; the shipped model is never touched.

    Results (metrics + the confusion pairs) are written to a json next to the cache BEFORE the
    model save, so a kill during save still leaves the numbers on disk.
    """
    from collections import Counter, defaultdict

    from sklearn.model_selection import GroupKFold
    from xgboost import XGBClassifier

    d = np.load(CACHE, allow_pickle=True)
    X, y, groups, trad = d["X"], d["y"], d["groups"], d["trad"]
    classes = sorted(set(y.tolist()))
    cidx = {c: i for i, c in enumerate(classes)}
    yi = np.array([cidx[v] for v in y])
    trad_of_class = {c: (CARNATIC if c.endswith(f"({CARNATIC})") else HINDUSTANI) for c in classes}
    track_true = {g: lab for g, lab in zip(groups, y)}
    track_trad = {g: tr for g, tr in zip(groups, trad)}
    print(f"{X.shape[0]} windows x {X.shape[1]}d | {len(classes)} classes "
          f"({sum(v==CARNATIC for v in trad_of_class.values())} C / "
          f"{sum(v==HINDUSTANI for v in trad_of_class.values())} H) | "
          f"{len(set(groups.tolist()))} tracks | n_estimators={n_estimators}", flush=True)

    # one 75/25 grouped split (first fold of a 4-way group split)
    tr_i, te_i = next(GroupKFold(n_splits=4).split(X, yi, groups))
    t0 = time.time()
    # PCA-reduce the 2304-d TDMS surface to a compact basis BEFORE XGBoost. A full-dim,
    # 70-class softprob fit does not finish inside this environment's compute limit; PCA(150)
    # keeps almost all of the surface's variance while making the fit finish in minutes. This is
    # a separability spike estimate; the shipped model would train on the full TDMS vector.
    from sklearn.decomposition import PCA
    pca = PCA(n_components=150, random_state=0).fit(X[tr_i])
    Xtr, Xte = pca.transform(X[tr_i]), pca.transform(X[te_i])
    print(f"PCA 2304 -> 150 (retains {pca.explained_variance_ratio_.sum():.2f} variance)", flush=True)
    clf = XGBClassifier(objective="multi:softprob", num_class=len(classes), tree_method="hist",
                        n_estimators=n_estimators, max_depth=6, learning_rate=0.1, n_jobs=-1)
    clf.fit(Xtr, yi[tr_i])
    print(f"fit {len(tr_i)} windows on {len(set(groups[tr_i].tolist()))} tracks  ({time.time()-t0:.0f}s)", flush=True)

    proba = clf.predict_proba(Xte)
    agg = defaultdict(lambda: np.zeros(len(classes)))
    cnt = defaultdict(int)
    for row, gi in zip(proba, groups[te_i]):
        agg[gi] += row
        cnt[gi] += 1
    track_pred = {gi: classes[int((agg[gi] / cnt[gi]).argmax())] for gi in agg}

    def acc(pt):
        return float(np.mean([p == t for p, t in pt])) if pt else float("nan")

    tested = [g for g in track_pred]
    all_pt = [(track_pred[g], track_true[g]) for g in tested]
    car_pt = [(track_pred[g], track_true[g]) for g in tested if track_trad[g] == CARNATIC]
    hin_pt = [(track_pred[g], track_true[g]) for g in tested if track_trad[g] == HINDUSTANI]

    leak = 0
    cross_pairs = Counter()
    for g in tested:
        tt, pt = track_trad[g], trad_of_class[track_pred[g]]
        if tt != pt:
            leak += 1
            cross_pairs[(track_true[g], track_pred[g])] += 1

    pairs_of_interest = []
    for h, c in [("Bhūp", "Mōhanaṁ"), ("Yaman kalyāṇ", "Kalyāṇi"), ("Mālkauns", "Hindōḷaṁ"),
                 ("Tōḍī", "Tōḍi"), ("Śrī", "Śrī")]:
        hl, cl = f"{h} ({HINDUSTANI})", f"{c} ({CARNATIC})"
        both = hl in classes and cl in classes
        conf = cross_pairs.get((hl, cl), 0) + cross_pairs.get((cl, hl), 0) if both else None
        pairs_of_interest.append({"hindustani": hl, "carnatic": cl, "both_present": both, "cross": conf})

    results = {
        "windows": int(X.shape[0]), "dims": int(X.shape[1]), "classes": len(classes),
        "carnatic_classes": sum(v == CARNATIC for v in trad_of_class.values()),
        "hindustani_classes": sum(v == HINDUSTANI for v in trad_of_class.values()),
        "test_tracks": len(tested), "n_estimators": n_estimators,
        "overall_top1": acc(all_pt), "carnatic_top1": acc(car_pt), "hindustani_top1": acc(hin_pt),
        "cross_tradition_leak": leak, "cross_tradition_leak_frac": leak / len(all_pt),
        "top_cross_confusions": [{"true": t, "pred": p, "n": n} for (t, p), n in cross_pairs.most_common(15)],
        "scale_identical_pairs": pairs_of_interest,
    }
    RESULTS_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2))

    print("\n================ RESULTS (track-level, held-out 25%) ================")
    print(f"overall top-1:     {acc(all_pt):.3f}  (n={len(all_pt)})")
    print(f"  Carnatic top-1:  {acc(car_pt):.3f}  (n={len(car_pt)})")
    print(f"  Hindustani top-1:{acc(hin_pt):.3f}  (n={len(hin_pt)})")
    print(f"\ncross-tradition leakage: {leak}/{len(all_pt)} = {leak/len(all_pt):.3f}")
    print("  (a Carnatic recording predicted as a Hindustani raaga, or vice versa)")
    if cross_pairs:
        print("  top cross-tradition confusions (true -> predicted):")
        for (t, p), n in cross_pairs.most_common(12):
            print(f"    {n:2d}x  {t}  ->  {p}")
    print("\nscale-identical pairs (told apart? 0 = never cross-predicted on held-out set):")
    for pr in pairs_of_interest:
        if pr["both_present"]:
            print(f"  {pr['hindustani']}  vs  {pr['carnatic']}:  {pr['cross']} cross-predictions")
        else:
            print(f"  {pr['hindustani']}  vs  {pr['carnatic']}:  n/a (not both in held-out classes)")
    print(f"\nresults json -> {RESULTS_JSON}", flush=True)

    # save the spike artifact (PCA + classifier + classes) to a NEW path. It takes the full
    # TDMS vector in and applies PCA internally, so it is self-contained. The shipped
    # models/raaga_xgb.json is never touched. A full-dim, full-data dual model is a later step
    # (needs a longer compute budget than this environment's per-run limit).
    import joblib
    artifact = DUAL_MODEL.with_suffix(".pkl")
    joblib.dump({"pca": pca, "clf": clf, "classes": classes,
                 "note": "Phase 0 spike: PCA(150)+XGBoost on IAMRRD C40+H30, 75% grouped split"}, artifact)
    print(f"saved spike artifact -> {artifact}  (shipped model untouched)")


FULL_MODEL = MODELS_DIR / "raaga_xgb.dual.json"       # RaagaXGB-loadable (booster + .classes.json)
FULL_RESULTS = Path(__file__).resolve().parent.parent / "supporting-docs" / "hindustani_dual_full_results.json"


def fitfull(total: int = 400, chunk: int = 50) -> None:
    """Train the full-dim (no PCA), full-data dual model with INCREMENTAL warm-start.

    A single full-dim, 70-class fit does not finish inside this environment's compute window, so
    training is done in chunks of `chunk` boosting rounds: after each chunk the booster is saved
    to FULL_MODEL, so a kill mid-way loses at most one chunk and the next run resumes from the
    saved trees. Same product hyperparameters (depth 6, eta 0.1, hist) as the Carnatic model, and
    the SAME 75/25 grouped-by-track split the product uses, so the held-out number is honest and
    the saved model is trained exactly the way the shipped one is. Re-run until it reaches `total`;
    the final call evaluates on the held-out 25% and writes the results json.
    """
    from collections import defaultdict

    import xgboost as xgb
    from sklearn.model_selection import GroupKFold

    d = np.load(CACHE, allow_pickle=True)
    X, y, groups, trad = d["X"], d["y"], d["groups"], d["trad"]
    classes = sorted(set(y.tolist()))
    cidx = {c: i for i, c in enumerate(classes)}
    yi = np.array([cidx[v] for v in y])
    tr_i, te_i = next(GroupKFold(n_splits=4).split(X, yi, groups))
    dtrain = xgb.DMatrix(X[tr_i], label=yi[tr_i])
    params = {"objective": "multi:softprob", "num_class": len(classes),
              "max_depth": 6, "eta": 0.1, "tree_method": "hist", "nthread": 0}

    booster, done = None, 0
    if FULL_MODEL.exists():
        booster = xgb.Booster(); booster.load_model(str(FULL_MODEL))
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

    # held-out evaluation (track-level), same shape as analyze()
    proba = booster.predict(xgb.DMatrix(X[te_i]))
    agg = defaultdict(lambda: np.zeros(len(classes))); cnt = defaultdict(int)
    for row, g in zip(proba, groups[te_i]):
        agg[g] += row; cnt[g] += 1
    track_true = {g: lab for g, lab in zip(groups, y)}
    track_trad = {g: t for g, t in zip(groups, trad)}
    trad_of_class = {c: (CARNATIC if c.endswith(f"({CARNATIC})") else HINDUSTANI) for c in classes}
    pred = {g: classes[int((agg[g] / cnt[g]).argmax())] for g in agg}

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

    Full k-fold OOF calibration (tools/calibrate.py) would retrain the model k times, ~1.5h at
    full-dim. The held-out split the model never trained on is a valid, cheap calibration set for
    a single temperature scalar. Writes <dual>.calib.json (picked up automatically by
    RaagaXGB.load) and prints an abstention table to pick the site thresholds for BOTH traditions.
    """
    from collections import defaultdict

    import xgboost as xgb
    from sklearn.model_selection import GroupKFold

    from raaga_id import calibrate as C

    d = np.load(CACHE, allow_pickle=True)
    X, y, groups, trad = d["X"], d["y"], d["groups"], d["trad"]
    classes = sorted(set(y.tolist()))
    cidx = {c: i for i, c in enumerate(classes)}
    yi = np.array([cidx[v] for v in y])
    _, te_i = next(GroupKFold(n_splits=4).split(X, yi, groups))

    booster = xgb.Booster(); booster.load_model(str(FULL_MODEL))
    proba = booster.predict(xgb.DMatrix(X[te_i]))
    # aggregate per track (mean softmax over windows) -> the granularity the UI shows
    agg = defaultdict(lambda: np.zeros(len(classes))); cnt = defaultdict(int)
    tt, ttrad = {}, {}
    for row, g, lab, tr in zip(proba, groups[te_i], y[te_i], trad[te_i]):
        agg[g] += row; cnt[g] += 1; tt[g] = cidx[lab]; ttrad[g] = tr
    tracks = list(agg)
    P = np.vstack([agg[g] / cnt[g] for g in tracks])
    ytrue = np.array([tt[g] for g in tracks])
    trad_arr = np.array([ttrad[g] for g in tracks])

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
    elif cmd == "analyze":
        analyze()
    elif cmd == "calib":
        calib()
    elif cmd == "fitfull":
        total = int(sys.argv[2]) if len(sys.argv) > 2 else 400
        chunk = int(sys.argv[3]) if len(sys.argv) > 3 else 50
        fitfull(total, chunk)
    else:
        raise SystemExit("usage: python -m tools.hindustani_spike [extract|analyze|calib|fitfull [total] [chunk]]")
