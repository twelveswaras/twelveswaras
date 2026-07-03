# Leaderboard — frozen benchmark

Test set: `benchmark/test_track_ids.json` — 12 held-out Saraga Carnatic 1.5 tracks
(1 per raaga), track-level split (no window leakage). 12-way raaga ID, track-level
top-k with window probabilities averaged (D7). **Chance: top1 = 0.083, top3 = 0.250.**

| date | features | model | top1 | top3 | notes |
|------|----------|-------|------|------|-------|
| 2026-07-03 | chroma + MFCC + spectral (raw, no tonic) | XGBoost | 0.083 | 0.250 | **at chance** — train top1=1.0 (overfit); model memorized recording timbre, not raaga |
| 2026-07-03 | tonic-relative pitch-class histogram (D5/D16) | XGBoost | **0.167** | **0.583** | Sa estimated from the drone, chroma shifted to Sa; timbre features dropped. Above chance. |

**Cross-validated (the reliable estimate).** The single 12-track holdout is noisy
(each track = 8.3 pts). 4-fold track-level CV over all 57 tracks (every track held out
once) gives **top1 = 0.281, top3 = 0.509** — i.e. **3.4× / 2× chance**. This confirms
the above-chance result is robust across splits, not an artifact of one holdout.
(Reproduce: `python -m tools.cross_validate`.)

**Caveats.** Still tiny data (57 tracks / 12 raagas, 3–7 tracks each); a crude
drone-argmax tonic; no gamaka features. The load-bearing result is the jump from
chance (raw features) to 3.4× chance (tonic-relative), matching the smoke test.

**Next levers (expected to move these):**
- Precise tonic via essentia `TonicIndianArtMusic` / compIAM (D5, Phase 2) — replaces
  the drone-argmax heuristic.
- More data: CMD / IAMRRD to grow per-raaga track counts (D4/D10).
- Richer features: TDMS, then CNN on tonic-normalized mel/CQT (D16); gamaka-aware feats.
- Stabler estimate on tiny data: k-fold CV instead of a single 12-track holdout.
