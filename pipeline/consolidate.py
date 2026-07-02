"""Consolidation job (PRD §13, D18) — runs nightly as a GitHub Action.

incoming/{id}.{flac,json}  ->  dedup (audio_sha256, D12)  ->  validate against
schema.py + raagas.json  ->  apply the verification rule (apps/verify.decide, D13)
->  write verified rows into dataset shards.  Junk/rights failures are quarantined,
not deleted (D14).
"""
from __future__ import annotations

# TODO(v1): implement. Sketch:
#   1. list incoming/*.json in the dataset repo
#   2. drop rows whose audio_sha256 already exists in a shard (dedup)
#   3. validate each against schema.FEATURES and the raagas.json vocab
#   4. status = apps.verify.decide(votes_agree, votes_disagree)
#   5. verified -> append to train/test shard; disputed -> expert queue; junk -> quarantine
#   6. commit the updated shards back to the HF dataset repo


def main() -> None:
    raise NotImplementedError("v1 consolidation job — see module docstring for the sketch")


if __name__ == "__main__":
    main()
