# benchmark/: the frozen evaluation set

The often-forgotten load-bearing module. **Freeze a test set the moment it
exists** so every model rung (XGBoost floor → CNN → TDMS → transformer) is scored
on the same clips and the leaderboard stays honest.

## Contents

The frozen set is **40 raagas, 129 tracks**, held out from Saraga Carnatic.

- `test_track_ids.json`: the frozen list of 129 held-out Saraga Carnatic track ids across
  40 raagas. `raaga_id.evaluate` scores only these. **Do not change it**; a new benchmark =
  a new file + a note.
- `leaderboard.md`: one row per model: date, features, top-1, top-3, notes.

## Metric

Top-1 and top-3 accuracy over the 40-raaga vocabulary (`raagas.json`). Top-3 is the
headline, since the product always surfaces top-3 + confidence. Later: benchmark
against compIAM `DEEPSRGM`.
