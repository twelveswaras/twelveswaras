# Leaderboard — frozen benchmark

Test set: `benchmark/test_track_ids.json` — 12 held-out Saraga Carnatic 1.5 tracks
(1 per raaga), track-level split (no window leakage). 12-way raaga ID, track-level
top-k with window probabilities averaged (D7). **Chance: top1 = 0.083, top3 = 0.250.**

| date | features | model | top1 | top3 | notes |
|------|----------|-------|------|------|-------|
| 2026-07-03 | chroma + MFCC + spectral (raw, no tonic) | XGBoost | 0.083 | 0.250 | **at chance** — train top1=1.0 (overfit); model memorized recording timbre, not raaga |
| 2026-07-03 | tonic-relative pitch-class histogram, **drone-argmax** tonic (D5/D16) | XGBoost | 0.167 | 0.583 | Sa estimated from the drone, chroma shifted to Sa; timbre features dropped. Above chance. |
| 2026-07-03 | tonic-relative, **precise Saraga ctonic** (D5, Phase 2) | XGBoost | **0.417** | **0.583** | per-track ground-truth tonic; drone-argmax was wrong on 7/12 clips. |

**Cross-validated (the reliable estimate).** The single 12-track holdout is noisy
(each track = 8.3 pts). 4-fold track-level CV over all 57 tracks (every track held out
once), reproduce with `python -m tools.cross_validate`:

| tonic source | CV top1 | CV top3 |
|---|---|---|
| drone-argmax heuristic | 0.281 (3.4×) | 0.509 (2.0×) |
| **precise Saraga ctonic** | **0.316 (3.8×)** | **0.544 (2.2×)** |

Precise tonic gives a consistent lift on both the holdout and CV — confirming tonic
normalization is a real lever (D5). The gain is moderate because the drone estimate was
already right ~40% of the time; the binding constraint now is data + feature richness.

**Caveats.** Tiny data (57 tracks / 12 raagas, 3–7 each). Precise tonic here is Saraga's
annotation (train/eval only); **inference on unlabelled clips still needs a tonic
estimator** (essentia `TonicIndianArtMusic` is fragile on Saraga — "No peak locations" on
5/6 clips — so it needs parameter work, or the demo keeps the drone heuristic).

**Next levers (expected to move these):**
- More data: CMD / IAMRRD to grow per-raaga track counts (D4/D10) — now the top limiter.
- Richer features: TDMS, then CNN on tonic-normalized mel/CQT (D16); gamaka-aware feats.
- Robust inference-time tonic (tune essentia params, or a better heuristic).
