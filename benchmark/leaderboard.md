# Leaderboard — frozen benchmark

Test set: `benchmark/test_track_ids.json` — 12 held-out Saraga Carnatic 1.5 tracks
(1 per raaga), track-level split (no window leakage). 12-way raaga ID, track-level
top-k with window probabilities averaged (D7). **Chance: top1 = 0.083, top3 = 0.250.**

| date | features | model | top1 | top3 | notes |
|------|----------|-------|------|------|-------|
| 2026-07-03 | chroma + MFCC + spectral (raw, no tonic) | XGBoost | 0.083 | 0.250 | **at chance** — train top1=1.0 (overfit); model memorized recording timbre, not raaga |
| 2026-07-03 | tonic-relative pitch-class histogram (D5/D16) | XGBoost | **0.167** | **0.583** | Sa estimated from the drone, chroma shifted to Sa; timbre features dropped. Above chance. |

**Caveats.** n=12 is a noisy benchmark (each track = 8.3 pts), so treat absolute
numbers as directional. The train/test signal (chance → above-chance after tonic
normalization) is the load-bearing result; it matches the tonic-invariance smoke test.

**Next levers (expected to move these):**
- Precise tonic via essentia `TonicIndianArtMusic` / compIAM (D5, Phase 2) — replaces
  the drone-argmax heuristic.
- More data: CMD / IAMRRD to grow per-raaga track counts (D4/D10).
- Richer features: TDMS, then CNN on tonic-normalized mel/CQT (D16); gamaka-aware feats.
- Stabler estimate on tiny data: k-fold CV instead of a single 12-track holdout.
