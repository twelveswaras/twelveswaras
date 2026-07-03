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
