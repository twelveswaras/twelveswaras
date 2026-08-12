"""Retraining job (PRD §14, D17) — manual for v1, data-volume-triggered later.

verified commons data  ->  retrain the model  ->  score against the FROZEN
benchmark  ->  publish only if it beats the incumbent. A model retrained purely on
contributor data can be clean CC-BY (vs the CC-BY-NC-SA Saraga-seeded model, D9).
"""
from __future__ import annotations

# The commons -> corpus half is done: pipeline.pull_commons pulls verified contributions
# into data/commons/, and `raaga_id.train --datasets saraga_carnatic commons` folds them in.
# TODO(v1+): the promotion half — retrain, score against benchmark/test_track_ids.json, and
# publish only if it beats the incumbent.


def main() -> None:
    raise NotImplementedError("v1+ retraining job — see module docstring")


if __name__ == "__main__":
    main()
