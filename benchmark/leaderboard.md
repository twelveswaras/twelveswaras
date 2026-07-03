# Leaderboard — frozen benchmark

Test set: `benchmark/test_track_ids.json` — 12 held-out Saraga Carnatic 1.5 tracks
(1 per raaga), track-level split (no window leakage). 12-way raaga ID, track-level
top-k with window probabilities averaged (D7). **Chance: top1 = 0.083, top3 = 0.250.**

| date | features | model | top1 | top3 | notes |
|------|----------|-------|------|------|-------|
| 2026-07-03 | chroma + MFCC + spectral (raw, no tonic) | XGBoost | 0.083 | 0.250 | **at chance** — train top1=1.0 (overfit); model memorized recording timbre, not raaga |
| 2026-07-03 | tonic-relative pitch-class histogram, **drone-argmax** tonic (D5/D16) | XGBoost | 0.167 | 0.583 | Sa estimated from the drone, chroma shifted to Sa; timbre features dropped. Above chance. |
| 2026-07-03 | tonic-relative chroma, **precise Saraga ctonic** (D5, Phase 2) | XGBoost | 0.417 | 0.583 | per-track ground-truth tonic; drone-argmax was wrong on 7/12 clips. |
| 2026-07-03 | **tonic-normalized PCD, 120-bin, from pitch tracks** (D16) | XGBoost | **0.500** | **0.833** | predominant-melody pitch (not audio chroma) — the actual raaga fingerprint. |

**Cross-validated (the reliable estimate).** The single 12-track holdout is noisy
(each track = 8.3 pts). 4-fold track-level CV over all 57 tracks (every track held out
once), reproduce with `python -m tools.cross_validate`:

| feature | CV top1 | CV top3 |
|---|---|---|
| chroma, drone-argmax tonic | 0.281 (3.4×) | 0.509 (2.0×) |
| chroma, precise Saraga ctonic | 0.316 (3.8×) | 0.544 (2.2×) |
| **pitch-track PCD, 120-bin** | **0.684 (8.2×)** | **0.877 (3.5×)** |

The feature — not the data — was the bottleneck: a 120-bin tonic-normalized histogram of
the **predominant-melody pitch** (Saraga's `pitch` annotation) more than doubled CV top1
(0.316 → 0.684) and pushed top3 to ~0.88, on the same 57 tracks. Audio-chroma was noisy
(harmonics, percussion, 12-TET quantization); PCD is the classic raga descriptor (D16),
capturing swara positions + gamaka. 12-bin PCD = 0.614/0.789 (finer 120-bin wins).

**Caveats / open items.** Tiny data still (57 tracks / 12 raagas). PCD needs a pitch
track + tonic: on annotated corpora (Saraga, IAMRRD) both are given, so training/eval are
clean — but **inference on a raw user clip needs on-device predominant-pitch extraction +
tonic** (not yet wired; the demo still runs the old chroma model). Next: pool IAMRRD
(downloading), then inference-time PCD.

**Next levers (expected to move these):**
- More data: CMD / IAMRRD to grow per-raaga track counts (D4/D10) — now the top limiter.
- Richer features: TDMS, then CNN on tonic-normalized mel/CQT (D16); gamaka-aware feats.
- Robust inference-time tonic (tune essentia params, or a better heuristic).
