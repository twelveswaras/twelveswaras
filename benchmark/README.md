# benchmark/ — the frozen evaluation set

The often-forgotten load-bearing module (PRD §15). **Freeze a test set the moment it
exists** (build-order step 6) so every model rung — XGBoost floor → CNN → TDMS →
transformer — is scored on the same clips and the leaderboard stays honest.

## Contents (to be added)

- `test_track_ids.json` — the frozen list of held-out Saraga track ids. `raaga_id.evaluate`
  scores only these. Once written, **do not change it**; a new benchmark = a new file + a note.
- `leaderboard.md` — one row per model: date, features, top-1, top-3, notes.

## Metric

Top-1 and top-3 accuracy over the v0 raaga vocabulary (`raagas.json`). Top-3 is the
headline, since the product always surfaces top-3 + confidence (D6). Later: benchmark
against compIAM `DEEPSRGM` (D16).
