"""Unit tests for the real-world benchmark harness — the pure logic only (no audio/essentia).

    python tests/test_realworld_eval.py

Covers: clip-list parsing + in-vocabulary validation, per-clip scoring (top-1/top-3/rank),
and the aggregate summary incl. the drone breakdown (which directly measures the tonic /
drone-dependency hypothesis).
"""
from __future__ import annotations

import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import realworld_eval as R

P = namedtuple("P", "raaga confidence")
VOCAB = ["Tōḍi", "Mōhanaṁ", "Bilahari", "Kalyāṇi"]


def test_parse_validates_vocab_and_required_fields():
    rows = [
        {"file": "a.m4a", "raga": "Todi", "source": "own", "license": "own", "drone": "yes"},
        {"file": "b.m4a", "raga": "Nonexistent", "source": "yt", "license": "private-eval", "drone": "no"},
        {"file": "", "raga": "Mōhanaṁ", "source": "own", "license": "own", "drone": "yes"},  # no file
    ]
    clips, skipped = R.parse_clip_list(rows, VOCAB)
    assert len(clips) == 1                       # only the valid, in-vocab, has-file row
    assert clips[0].raga == "Tōḍi"               # 'Todi' folded to the canonical vocab spelling
    assert clips[0].drone is True
    assert len(skipped) == 2                     # out-of-vocab + missing-file both skipped
    assert any("vocab" in s.reason for s in skipped)
    assert any("file" in s.reason for s in skipped)


def test_score_clip_top1_top3_rank():
    preds = [P("Mōhanaṁ", 0.5), P("Bilahari", 0.3), P("Tōḍi", 0.2)]
    assert R.score_clip(preds, "Mōhanaṁ") == (True, True, 1)
    assert R.score_clip(preds, "Tōḍi") == (False, True, 3)
    assert R.score_clip(preds, "Kalyāṇi") == (False, False, None)   # not in top-3 at all


def test_summary_overall_and_drone_breakdown():
    results = [
        R.Result("a", "Tōḍi", True, True, 1, drone=True),
        R.Result("b", "Mōhanaṁ", False, True, 2, drone=True),
        R.Result("c", "Bilahari", False, False, None, drone=False),   # drone-less miss
        R.Result("d", "Kalyāṇi", None, None, None, drone=False),       # no prediction (no tonic)
    ]
    s = R.summarize(results)
    assert s["n"] == 4
    assert s["scored"] == 3 and s["no_prediction"] == 1     # 'd' had no tonic -> not scored
    assert abs(s["top1"] - 1 / 3) < 1e-9                    # 1 of 3 scored
    assert abs(s["top3"] - 2 / 3) < 1e-9
    assert s["by_drone"]["yes"]["top1"] == 0.5              # a,b -> 1 of 2
    assert s["by_drone"]["no"]["top1"] == 0.0              # only c scored (0), d unscored


if __name__ == "__main__":
    test_parse_validates_vocab_and_required_fields()
    test_score_clip_top1_top3_rank()
    test_summary_overall_and_drone_breakdown()
    print("REALWORLD-EVAL OK — parse/vocab-validate, score top1/top3/rank, drone breakdown pass")


# The dual (production) model tags its classes with a tradition: "Kalyāṇi (Carnatic)". A clip list
# holds the bare name. Folding the tagged class directly matched NOTHING, so every clip was skipped
# and this benchmark silently scored zero clips against the production model.
DUAL_VOCAB = ["Kalyāṇi (Carnatic)", "Tōḍi (Carnatic)", "Tōḍi (Hindustani)", "Yaman kalyāṇ (Hindustani)"]


def test_parse_matches_tradition_tagged_dual_model_classes():
    rows = [{"file": "a.m4a", "raga": "Kalyani", "source": "yt", "license": "private-eval", "drone": "yes"}]
    clips, skipped = R.parse_clip_list(rows, DUAL_VOCAB)
    assert skipped == []
    assert len(clips) == 1
    # stored label is the FULL model class, so scoring compares like-for-like against predictions
    assert clips[0].raga == "Kalyāṇi (Carnatic)"


def test_parse_resolves_cross_tradition_collisions():
    """Tōḍi exists in both traditions. An explicit `tradition` column wins; absent one it defaults
    to Carnatic, matching tradition_of's documented tie-break."""
    rows = [
        {"file": "c.m4a", "raga": "Todi", "tradition": "hindustani", "drone": "yes"},
        {"file": "d.m4a", "raga": "Todi", "drone": "yes"},
    ]
    clips, _ = R.parse_clip_list(rows, DUAL_VOCAB)
    assert [c.raga for c in clips] == ["Tōḍi (Hindustani)", "Tōḍi (Carnatic)"]


def test_parse_still_skips_genuinely_out_of_vocab():
    rows = [{"file": "e.m4a", "raga": "NotARaaga", "drone": "no"}]
    clips, skipped = R.parse_clip_list(rows, DUAL_VOCAB)
    assert clips == []
    assert len(skipped) == 1 and "vocab" in skipped[0].reason
