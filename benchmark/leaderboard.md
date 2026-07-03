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
