# Contributing to twelveswaras

Thank you for helping build twelveswaras, an open-source "Shazam for raagas" and a
community-owned data commons for Carnatic (and, later, Hindustani) music. This is a
non-commercial public good, not owned by any company. Every kind of help below matters.

## The single most valuable thing you can do: contribute a clip

For most people, the highest-impact contribution is not code. It is **audio**.

1. Go to [twelveswaras.com](https://twelveswaras.com) and play or upload a clip.
2. Identify the raaga (the recognizer helps, and you confirm).
3. Contribute the clip so it joins the openly-licensed **data commons**.

Every confirmed clip makes the next model better, especially for raagas and voices that
are under-represented today. In-the-wild recordings (concerts, radio, TV, your own
practice with a drone) are exactly what the frozen research corpora do not cover, so
real-world clips are the most useful of all.

A few things to know before you contribute a clip:

- **Rights gate.** Only contribute audio that is **your own performance**, or that you
  otherwise have the right to share under the chosen license. A concert recording you
  merely captured is not your own performance.
- **Anonymous by default.** No login is required. An optional handle lets you claim
  attribution if you want it.
- **Audio is not published by default.** By default you help improve the recognizer (we
  publish the model, not your voice). Releasing the raw audio into the public commons is
  a separate, explicit opt-in.
- **License.** Clips you release into the commons are licensed **CC-BY-4.0**, kept
  separate from the non-commercial research corpora so the commons stays cleanly reusable.

See [`GOVERNANCE.md`](GOVERNANCE.md) for how contributions are verified and promoted.

## Reviewing the raaga reference (Carnatic musicians and teachers)

The [Raaga Explorer](https://twelveswaras.com) ships a browsable reference for the raaga
set: a beginner "tell", how-to-hear notes, a playable swara wheel, and allied /
graha-bhedam links. These reference facts are **draft, pending expert review**.

If you are a Carnatic musician, teacher, or serious student, reviewing this reference is a
genuinely valuable contribution. The underlying data lives in the tracked JSON files at
the repo root (`raagas.json`, `raaga_guide.json`, `raaga_profiles.json`). You can open an
issue with corrections, or a pull request editing the JSON directly. Please cite your
reasoning (a standard text, a sampradaya, a recording) where a claim is contested.

## Code contributions

Code is welcome: model quality, features, the pipeline, the site, tooling, and tests.

### Dev setup

The project uses **two conda environments**, because the audio-to-pitch path
(`essentia`) needs `numpy < 2` while training uses `numpy 2.x`. They are separate on
purpose.

**1. Training and feature work** (`environment.yml`, env name `twelveswaras`): the main
environment for the model, features, data, benchmark, and most tests. On Apple Silicon
the native/scientific packages come from conda-forge as prebuilt `osx-arm64` binaries, so
nothing compiles from source.

```bash
conda env create -f environment.yml
conda activate twelveswaras
```

**2. Inference and demo** (`environment-inference.yml`, env name `twelveswaras-infer`):
the audio -> pitch -> tonic path used by the recognizer and demo. It pins `numpy < 2` and
installs `essentia` (predominant-melody pitch) plus `compiam` (the working tonic recipe).

```bash
conda env create -f environment-inference.yml
conda activate twelveswaras-infer
python -m apps.identify
```

On Linux (for example the Hugging Face Space) the pip manifest `requirements.txt` is used
instead of `environment.yml`, since wheels exist there.

### Running the tests

From the `twelveswaras` environment, at the repo root:

```bash
pytest tests/
```

Every test file is also runnable directly as a script (each has a `python
tests/test_*.py` header) for a quick check without pytest. The commons and worker tests
are structural assertions over the source, so they run without audio dependencies; the
feature and model tests run on synthetic audio and need no dataset download.

### Project layout

Top-level directories:

| Path          | What it is |
|---------------|------------|
| `raaga_id/`   | The core library: pitch extraction, features (TDMS), model, training, calibration, evaluation. |
| `apps/`       | Entry-point apps: `identify`, `contribute`, `verify`, usage logging. |
| `space/`      | The Hugging Face Space (Gradio app + API) that hosts the recognizer. |
| `cloudflare/` | The Cloudflare Worker API, D1 schema, and Pages config behind twelveswaras.com. |
| `site/`       | The static website front-end. |
| `tools/`      | Developer and data scripts: cross-validation, real-world eval, page/data builders, clip fetchers. |
| `pipeline/`   | Batch jobs: `consolidate` (commons) and `retrain`. |
| `benchmark/`  | The frozen evaluation set, leaderboard, and real-world clips. |

Please do not edit `site/` or `cloudflare/` casually; those are the live deployment.

### Pull requests

- Keep changes focused and add or update tests where it makes sense.
- Run `pytest tests/` before opening a PR.
- The repo uses `ruff` for linting.
- House style: **no em-dashes** in prose. Use commas, colons, or parentheses.

## Reporting issues

Open a GitHub issue at <https://github.com/twelveswaras/twelveswaras/issues>. Helpful bug
reports include what you did, what you expected, what happened, and (for recognition
issues) the raaga, whether a drone was present, and the clip source if you can share it.

For **security** reports, do not open a public issue: see [`SECURITY.md`](SECURITY.md).

## Licensing of contributions

- **Code** contributions are made under the **MIT** license.
- **Data** contributions (audio clips released into the commons) are licensed
  **CC-BY-4.0**.

By contributing, you agree that your contribution is licensed as above.

## Code of conduct

Participation in this project is governed by our
[Code of Conduct](CODE_OF_CONDUCT.md). By taking part, you agree to uphold it.
