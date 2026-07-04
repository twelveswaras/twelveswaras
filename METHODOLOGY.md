# Methodology

How twelveswaras identifies the raaga of a Carnatic clip, why each choice was made, and the
literature it builds on. Results and the full progression live in
[`benchmark/leaderboard.md`](benchmark/leaderboard.md); the private product spec + decisions log
(D1–D31) live in `supporting-docs/PRD.md`.

## The problem

Raaga identification is audio **classification**, not fingerprinting: infer the melodic mode of
*any* performance, including unheard ones. A raaga is defined by its swaras (notes relative to
the tonic Sa) **and** its gamakas (characteristic ornamented movement between them). Both matter —
especially for *allied* raagas that share a scale but differ in phrasing.

## Pipeline

Fully automatic; the only input is audio.

1. **Predominant-melody pitch** — essentia `PredominantPitchMelodia` extracts the lead melodic
   line as an f0 contour (`raaga_id/pitch_extract.py`).
2. **Tonic (Sa)** — from the tanpura drone, via compiam `TonicIndianMultiPitch` / essentia
   `TonicIndianArtMusic` (the Salamon–Gulati–Serra 2012 multipitch method). In training we use
   each corpus's tonic annotation; at inference we estimate it.
   **Tonic-normalization — hearing every note *relative to Sa* — is the central unlock.** The
   reference Harvard thesis skipped it (used absolute pitch-class chroma); adding it roughly
   doubled our accuracy.
3. **Feature — windowed Time-Delayed Melody Surface (TDMS)** — a 2-D histogram of
   `(pitch(t), pitch(t+τ))` over the tonic-normalized, octave-folded melody (τ = 0.3 s, 48×48
   bins). A steady note sits on the diagonal; **gamaka smears off-diagonal** in a
   raaga-characteristic way — so TDMS sees the *movement* the static pitch histogram discards.
   Computed over 30 s windows (`features.model_windows` — the single feature shared by train,
   evaluate, calibrate, and inference, so they can't drift).
4. **Classifier** — XGBoost (`multi:softprob`, 40 classes). Per-clip prediction averages the
   softmax over the clip's window surfaces (`RaagaXGB.aggregate_top_k`).
5. **Calibrated confidence** — a single temperature scalar (fit offline on leak-free 4-fold
   out-of-fold predictions; `tools/calibrate.py`) reshapes the softmax so the number means what
   it says. A **confidence state** turns a tight top-2 into an honest *"close call — X vs Y"*
   instead of a false-precise single answer.

## Feature evolution (why TDMS)

| feature | what it captures | frozen top-1 |
|---------|------------------|--------------|
| librosa chroma + MFCC | absolute pitch class + timbre | ≈ chance (overfit / track-memorization) |
| tonic-normalized PCD (120-bin) | *which* notes, relative to Sa | strong lift |
| **windowed TDMS (48×48)** | *how* notes move (gamaka) | **0.798 / top-3 0.938** |
| CNN on TDMS (spike, not shipped) | spatial gamaka structure | 0.868 (held behind the real-world benchmark) |

We deliberately **exclude timbre features (MFCC, spectral, ZCR)**: they encode instrument /
recording identity and invite the model to memorize tracks rather than learn raaga. The Harvard
thesis's own feature-importance analysis independently found chroma dominant and ZCR/timbre least
relevant — corroborating the pitch-focused choice.

## Evaluation

- **Frozen benchmark** — a fixed held-out set of 129 tracks across 40 raagas, split **by track**
  (no window leakage). Reported: top-1 **0.798**, top-3 **0.938** (chance 0.025 / 0.075).
- **k-fold track-level cross-validation** (`tools/cross_validate.py`) for lower-variance estimates.
- **Real-world benchmark harness** (`tools/realworld_eval.py`) — scores the model on
  concert/phone clips broken down **by drone presence**, to measure the studio→real-world gap the
  frozen (studio) benchmark can't.

## Known limitations

- **Drone dependency** — the tonic is found from the tanpura; drone-less solo audio collapses
  accuracy (measured ~0.67→0.33). Concert/TV audio (always has a drone) is fine.
- **Allied raagas** — janya raagas of the same parent mela share a scale and differ mainly in
  gamaka/phrasing (e.g. the Harikāmbhōji and Karaharapriya families). TDMS narrows these
  confusions but doesn't eliminate them; phrase-level modelling is the next lever.
- **Domain gap** — trained on studio corpora; real-world phone/concert accuracy is being measured
  (harness above), not yet closed.

## Roadmap of methods

- **TDMS → 2-D CNN** — the surface is an image; a small CNN beat XGBoost 0.798→0.868 in a spike,
  held pending the real-world benchmark and the cost of a torch dependency.
- **Phrase / sañcāra matching** — mine characteristic gamaka-laden motifs to disambiguate allied
  raagas (the musician's own method) and power the "how to hear this raaga" learner panel.
- **Data augmentation** (adopted from the Harvard thesis; see PRD D31) — augment raw audio with
  **background noise** (first, to attack the domain gap), speed, and light pitch jitter, then
  re-extract pitch+tonic and retrain.

## What we do differently from the reference thesis

| | Harvard thesis (Narayanan 2024) | twelveswaras |
|---|---|---|
| tonic | none (raw absolute chroma) | tonic-normalized (relative to Sa) |
| gamaka | MFCC timbre + spectral bandwidth (indirect) | TDMS pitch-trajectory (direct) |
| model | ANN / LSTM / CNN / BERT on 50-dim vectors or mel-spectrograms | XGBoost on TDMS |
| timbre features | included (MFCC, spectral, ZCR) | excluded (avoid track-memorization) |
| augmentation | 4 kinds, 9× data | none yet — adopting (D31) |
| scope | up to 15 raagas (86%) | 40 raagas (0.798) |

The thesis's headline results (its BERT failed at 10 raagas; its simple ANN beat CNN/LSTM at
scale) support our "strong model on a good, raaga-specific feature" bet over heavier
architectures. Its future-work list — *retrieve similar raagas + explain the difference*, and
*characteristic-phrase "tells" for faster recognition* — matches our planned learner/Explorer and
phrase-matching work.

## Bibliography

1. S. Gulati, J. Serrà, K. K. Ganguli, S. Şentürk, X. Serra. *Time-Delayed Melody Surfaces for
   Rāga Recognition.* ISMIR 2016. — the TDMS feature.
2. S. Gulati. *Computational Approaches for Melodic Description in Indian Art Music Corpora.*
   PhD thesis, Universitat Pompeu Fabra, 2016.
3. J. Salamon, S. Gulati, X. Serra. *A Multipitch Approach to Tonic Identification in Indian
   Classical Music.* ISMIR 2012. — the tonic method.
4. H. Narayanan. *Classifying Ragams in Carnatic Music with Machine Learning Models: A Shazam for
   South Indian Classical Music.* B.A. thesis, Harvard University, 2024. — reference implementation.
5. S. Madhusudhan, T. Beigi. *DEEPSRGM — Sequence Classification for Rāga Identification.* 2019.
   — sequence-model benchmark target.
5a. S. Natesan, H. Beigi. *Carnatic Raga Identification System using Rigorous Time-Delay Neural
   Network.* Recognition Technologies Inc. Technical Report RTI-20240524-01, 2024. — a TDNN+LSTM
   hybrid with **attention over *relative* frequency changes for shruti-invariance** (no explicit
   tonic estimation). Preliminary (676 recordings, no reported metrics), but the relative-pitch
   idea is worth revisiting for our **tonic/drone-robustness** work — it targets the exact failure
   mode (drone-less audio) where our explicit tonic estimation breaks.
6. M. Müller. *Fundamentals of Music Processing.* Springer, 2016. (chroma, CENS, STFT).
7. **Datasets:** Saraga Carnatic (CompMusic / MTG-UPF, CC-BY-NC-SA); *Indian Art Music Raga
   Recognition Dataset* — Carnatic Music Dataset (CMD) (CompMusic, CC-BY-NC-ND 3.0,
   doi:10.5281/zenodo.7278510), accessed via `mirdata` (`compmusic_raga`). The paired Hindustani
   dataset (HMD) is the corpus for the planned Hindustani fast-follow.
8. **Libraries:** essentia, compiam (both AGPL); librosa; xgboost; gradio.
