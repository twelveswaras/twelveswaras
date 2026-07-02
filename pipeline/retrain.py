"""Retraining job (PRD §14, D17) — manual for v1, data-volume-triggered later.

verified commons data  ->  retrain the model  ->  score against the FROZEN
benchmark  ->  publish only if it beats the incumbent. A model retrained purely on
contributor data can be clean CC-BY (vs the CC-BY-NC-SA Saraga-seeded model, D9).
"""
from __future__ import annotations

# TODO(v1+): implement. Reuses raaga_id.train.build_dataset over the commons splits,
# then raaga_id.evaluate against benchmark/test_track_ids.json before promotion.


def main() -> None:
    raise NotImplementedError("v1+ retraining job — see module docstring")


if __name__ == "__main__":
    main()
