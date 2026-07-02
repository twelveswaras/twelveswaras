"""v1 community verification queue (PRD §14, D13).

Serves unverified clips from incoming/, collects agree/disagree votes, and applies
the promotion rule: >=3 agree AND >=80% agreement -> train; disagreement -> disputed
-> expert queue (Sathya + a small trusted circle). Thresholds live in config.py and
are configurable.
"""
from __future__ import annotations

from raaga_id.config import PROMOTE_MIN_AGREEMENT, PROMOTE_MIN_VOTES


def decide(votes_agree: int, votes_disagree: int) -> str:
    """Return the verification_status for a clip given its current votes (D13)."""
    total = votes_agree + votes_disagree
    if total < PROMOTE_MIN_VOTES:
        return "unverified"
    if votes_agree / total >= PROMOTE_MIN_AGREEMENT:
        return "verified"
    return "disputed"


# TODO(v1): Gradio queue UI — play a clip, show the declared raaga, agree/disagree;
# persist votes back to incoming/{id}.json; hand `disputed` to the expert queue.
