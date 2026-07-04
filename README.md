# twelveswaras

An open-source "Shazam for raagas" — play it a clip of Carnatic music and it identifies the
**raaga**, shows the top-3 with honest confidence and the tonic (Sa) it found, and helps you
learn to hear that raaga. Paired with a planned community-contributed, openly-licensed **data
commons** so the model improves over time.

**Live:** [twelveswaras.com](https://twelveswaras.com) · recognizer on a
[Hugging Face Space](https://huggingface.co/spaces/twelveswaras/twelveswaras)

> **Status:** v0 shipped — 40 Carnatic raagas, live and recognizing.
> **Focus:** Carnatic first — the name, schema, and pipeline are **tradition-neutral** by
> design, with Hindustani planned as a fast-follow.
> **Scope:** Non-commercial, open-source only. A public good stewarded in the neutral
> [`twelveswaras`](https://github.com/twelveswaras) GitHub + HF org — not owned by any company.

## Why "twelveswaras"?

The twelve swaras are the twelve note-positions of the octave — the shared alphabet of **both**
Carnatic and Hindustani music. The name is tradition-neutral on purpose: Carnatic is where we
start, but nothing in the name, schema, or pipeline locks us to one tradition.

## Why this is different from Shazam

Shazam does audio *fingerprinting* — it matches a specific recording. twelveswaras does audio
*classification* — it infers the musical structure (the raaga) of **any** performance, including
one it has never heard. That's a Music Information Retrieval problem, not a lookup.

## How it works

Fully automatic, no user input beyond the audio (see [`METHODOLOGY.md`](METHODOLOGY.md) for the
full detail and citations):

1. **Predominant-melody pitch** from the audio (essentia `PredominantPitchMelodia`).
2. **Tonic (Sa)** from the tanpura drone (compiam / essentia, the Salamon–Gulati–Serra
   multipitch method). *Tonic-normalization — heard relative to Sa — is the key unlock the
   Harvard reference thesis skipped.*
3. **Feature:** a tonic-normalized, windowed **Time-Delayed Melody Surface (TDMS)** — a 2-D
   histogram of `(pitch(t), pitch(t+delay))` that captures **gamaka** (the *movement* between
   notes), not just which notes occur.
4. **Classifier:** XGBoost over the surfaces, window-aggregated, with **temperature-calibrated**
   confidences (a shown "70%" is right ~70% of the time).

**Accuracy (frozen 129-track benchmark, 40 raagas):** top-1 **0.798**, top-3 **0.938**
(~32× / 12× chance). Full progression in [`benchmark/leaderboard.md`](benchmark/leaderboard.md).
Needs a drone: concert/TV audio works; solo voice with no drone is unreliable.

## Data & attribution

Trained on openly-available research corpora — **attribution required by their licenses**:

- **Saraga Carnatic** (CompMusic / MTG-UPF) — CC-BY-**NC-SA**. Predominant pitch + tonic annotations.
- **Indian Art Music Raga Recognition Dataset — Carnatic Music Dataset (CMD)** (CompMusic /
  MTG-UPF; Gulati et al.) — CC-BY-**NC-ND** 3.0, [Zenodo](https://doi.org/10.5281/zenodo.7278510),
  accessed via `mirdata` (`compmusic_raga`). Its paired **Hindustani dataset (HMD)** is the
  training data for the planned Hindustani fast-follow.

Built with **essentia** and **compiam** (both **AGPL** — the deployed Space carries AGPL
obligations, satisfied by publishing all source), plus librosa, xgboost, and gradio.

## Prior work we build on

- **S. Gulati et al.**, *Time-Delayed Melody Surfaces for Rāga Recognition* (ISMIR 2016) — the
  TDMS feature at the heart of our model.
- **S. Gulati**, *Computational Approaches for Melodic Description in Indian Art Music Corpora*
  (PhD thesis, UPF 2016) — the definitive reference; tonic + melody methods.
- **H. Narayanan**, *Classifying Ragams in Carnatic Music with Machine Learning* (Harvard, 2024)
  — the "Shazam for ragas" reference implementation; we improve on it with tonic-normalization
  and TDMS, and adopt its data-augmentation idea (see METHODOLOGY.md).
- **Madhusudhan & Beigi**, *DEEPSRGM* — sequence-model benchmark target.

Full bibliography in [`METHODOLOGY.md`](METHODOLOGY.md).

## Roadmap

- **v0 — proof (shipped):** identify only. 40-raaga tonic-normalized TDMS model + live demo +
  learner panel. No contribution loop yet.
- **v0.5 — trust (shipped):** legible recognition, calibrated confidence, gamaka features.
- **v1 — commons:** contribute + verify loop, publish the open dataset, consolidation job.
- **v2 — quality:** TDMS→CNN, phrase/gamaka disambiguation of allied raagas, retraining
  pipeline, expert-annotation tier, and Hindustani.

## Licensing

- **Code:** MIT.
- **Contributor dataset (the commons):** CC-BY-4.0 — kept **separate** from non-commercial source
  data so it stays cleanly reusable.
- **Seed model:** trained on Saraga (CC-BY-**NC-SA**), so the seed weights carry CC-BY-NC-SA; a
  later model retrained purely on the contributor commons can be clean CC-BY.

This is a non-commercial, open-source public good. See [`GOVERNANCE.md`](GOVERNANCE.md) for
stewardship and [`METHODOLOGY.md`](METHODOLOGY.md) for the full method + references.
