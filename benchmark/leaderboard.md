# Leaderboard — frozen benchmark

Test set: `benchmark/test_track_ids.json` — 12 held-out Saraga Carnatic 1.5 tracks
(1 per raaga), track-level split (no window leakage). 12-way raaga ID, track-level
top-k with window probabilities averaged (D7). **Chance: top1 = 0.083, top3 = 0.250.**

| date | features | model | top1 | top3 | notes |
|------|----------|-------|------|------|-------|
| 2026-07-03 | chroma + MFCC + spectral (raw, no tonic) | XGBoost | 0.083 | 0.250 | **at chance** — train top1=1.0 (overfit); model memorized recording timbre, not raaga |
| 2026-07-03 | tonic-relative pitch-class histogram, **drone-argmax** tonic (D5/D16) | XGBoost | 0.167 | 0.583 | Sa estimated from the drone, chroma shifted to Sa; timbre features dropped. Above chance. |
| 2026-07-03 | tonic-relative chroma, **precise Saraga ctonic** (D5, Phase 2) | XGBoost | 0.417 | 0.583 | per-track ground-truth tonic; drone-argmax was wrong on 7/12 clips. |
| 2026-07-03 | tonic-normalized PCD, 120-bin, from pitch tracks (D16) | XGBoost | 0.500 | 0.833 | predominant-melody pitch (not audio chroma) — the actual raaga fingerprint. |
| 2026-07-03 | **PCD + IAMRRD pooled** (Saraga 45 + IAMRRD 131 train tracks, D10) | XGBoost | **0.667** | **0.917** | cross-dataset: train includes IAMRRD, test = held-out Saraga. More data on top of the feature win. |

**Cross-validated (the reliable estimate).** 4-fold track-level CV, every track held out
once, reproduce with `python -m tools.cross_validate [--datasets ...]`:

| feature / data | tracks | CV top1 | CV top3 |
|---|---|---|---|
| chroma, drone-argmax tonic | 57 | 0.281 (3.4×) | 0.509 (2.0×) |
| chroma, precise Saraga ctonic | 57 | 0.316 (3.8×) | 0.544 (2.2×) |
| pitch-track PCD, 120-bin (Saraga) | 57 | 0.684 (8.2×) | 0.877 (3.5×) |
| **pitch PCD + IAMRRD (pooled)** | 188 | **0.840 (10×)** | **0.947 (3.8×)** |

Two levers, both real: **(1) feature** — a 120-bin tonic-normalized histogram of the
**predominant-melody pitch** more than doubled CV top1 (0.316 → 0.684) vs audio-chroma,
which was noisy (harmonics/percussion/12-TET). **(2) data** — pooling IAMRRD's 131
Carnatic tracks (11 of our 12 raagas overlap; only Saurāṣtraṁ is Saraga-only) lifted the
held-out-Saraga holdout 0.500 → 0.667 and pooled CV to 0.840/0.947. (The pooled CV's 188
denominator differs from the Saraga-only 57, so the honest cross-data comparison is the
0.500 → 0.667 holdout on the fixed benchmark.)

**Caveats / open items.** Traditions filtered to Carnatic (Hindustani shares raaga names
but they're different ragas). PCD needs a pitch track + tonic: annotated corpora give
both, so training/eval are clean — but **inference on a raw user clip needs on-device
predominant-pitch extraction + tonic** (not yet wired; the demo still runs the old chroma
model). That's the next gap to close.

**Next levers (expected to move these):**
- More data: CMD / IAMRRD to grow per-raaga track counts (D4/D10) — now the top limiter.
- Richer features: TDMS, then CNN on tonic-normalized mel/CQT (D16); gamaka-aware feats.
- Robust inference-time tonic (tune essentia params, or a better heuristic).

---

## 40-raaga model (scaled up, 2026-07-03)

Expanded the vocabulary to the **full 40-raaga Carnatic set** (every raaga in IAMRRD,
~12 tracks each; Saraga pools in). Same PCD pipeline, retrained on 567 pooled tracks; new
frozen benchmark = 129 held-out tracks across 40 raagas.

| eval | top1 | top3 |
|------|------|------|
| holdout (129 tracks) | 0.682 | 0.899 |
| **4-fold CV (567 tracks)** | **0.780** | **0.926** |

Chance at 40-way = top1 0.025 / top3 0.075 → the model is **31× / 12× chance**. Going
12→40 raagas cost only ~6 pts top1 / ~2 pts top3 — IAMRRD's extra data carried it.

**Inference is now wired (fully automatic):** essentia Melodia pitch + compiam
TonicIndianMultiPitch tonic (numpy<2 inference env, see `environment-inference.yml`) →
PCD → model; the demo (`apps/identify`) runs this. **Needs a drone** — drone-less test
(isolated vocal) collapses tonic 0.67→0.33 and top1 0.73→0.33, so a-cappella is
unreliable, but concert/TV audio (has a tanpura) is fine.

### Calibration (D25, 2026-07-03)

Window-averaging left the softmax **under-confident**, so displayed %s read as falsely flat.
Temperature scaling (one scalar, fit on 4-fold OOF predictions; `tools/calibrate.py`):

| metric | before | after |
|--------|--------|-------|
| ECE (↓ better) | 0.374 | **0.057** |
| NLL (↓ better) | 1.291 | 0.892 |
| mean top-1 confidence | 0.406 | 0.724 |
| top-1 accuracy | 0.780 | 0.780 (argmax-preserving) |

**T = 0.448** (< 1 ⇒ sharpen). Stored in `models/raaga_xgb.calib.json`, applied in
`RaagaXGB._decode`. Accuracy is untouched — only the confidence numbers become honest
(a "70%" is now right ~70% of the time). Allied raagas (Mōhanaṁ/Bilahari/Bēgaḍa) stay
relatively close because PCD is blind to gamaka — that's the next lever (TDMS, refines D16).

### Gamaka feature — TDMS vs PCD (D28, 2026-07-03)

Track-level 4-fold CV (567 tracks, 40 raagas; `tools/tdms_experiment.py`) — does the
Time-Delayed Melody Surface (Gulati et al., ISMIR 2016; `features.tdms`, 48×48, delay 0.3 s)
capture the gamaka/movement the static PCD discards?

| feature | top1 | top3 | allied triple (Mōhanaṁ/Bilahari/Bēgaḍa, n=42) |
|---------|------|------|-----------------------------------------------|
| PCD (120d) | 0.658 | 0.840 | 0.548 |
| **TDMS (2304d)** | **0.725** | **0.869** | **0.714** |
| PCD+TDMS (2424d) | 0.709 | 0.852 | 0.667 |

**TDMS wins outright (+6.7 pts top1) and lifts the allied triple +17 pts** — gamaka is the
missing signal. PCD+TDMS is *worse* than TDMS alone (the surface's diagonal already carries the
pitch marginal, so PCD is redundant). NB these are *track-level*; production PCD is windowed +
aggregated (0.780), so the next step is a windowed-TDMS run on the frozen set before swapping the
inference feature. Then TDMS→CNN.
