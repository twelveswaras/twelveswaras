"""Name folding: does a contributor's ASCII spelling reach the model's diacritic class name?

This is load-bearing and quietly so. A spelling that fails to fold onto its model class does not
error, it just means those recordings are treated as an unknown raaga and dropped from training.
We lost 20 recordings of Pūrvīkaḷyāṇi and 3 of Śrīranjani that way, to nothing but spelling.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from raaga_id.config import fold_raaga


def test_folds_long_vowel_romanisations():
    """'oo' for ū and 'ee' for ī are the commonest Indic transliterations, and the reason a
    contributor's "Poorvi Kalyani" never reached the class "Pūrvīkaḷyāṇi"."""
    assert fold_raaga("Poorvi Kalyāni") == fold_raaga("Pūrvīkaḷyāṇi")
    assert fold_raaga("Poorvikalyani") == fold_raaga("Pūrvīkaḷyāṇi")
    assert fold_raaga("Shreeranjani") == fold_raaga("Śrīranjani")
    assert fold_raaga("Bhoopalam") == fold_raaga("Bhūpāḷaṁ")


def test_still_folds_the_existing_variants():
    """The aspirate/sibilant folding that already worked must keep working."""
    assert fold_raaga("Shankarabharanam") == fold_raaga("Śaṅkarābharaṇaṁ")
    assert fold_raaga("Thodi") == fold_raaga("Tōḍi")
    assert fold_raaga("Mohanam") == fold_raaga("Mōhanaṁ")


def test_keeps_distinct_raagas_distinct():
    """The guard that matters: folding must never merge two genuinely different raagas. These are
    real, separate classes in the model and each pair is close enough to be a plausible casualty
    of over-aggressive normalisation."""
    distinct = [
        ("Bhairavi", "Bhūpāḷaṁ"), ("Mōhanaṁ", "Mādhyamāvati"), ("Kalyāṇi", "Kāpi"),
        ("Śrīranjani", "Śrī"), ("Pūrvīkaḷyāṇi", "Kalyāṇi"), ("Bilahari", "Bēgaḍa"),
        ("Kēdāragauḷa", "Kēdāraṁ"), ("Rītigauḷa", "Sāvēri"), ("Tōḍi", "Darbāri kānaḍa"),
    ]
    for a, b in distinct:
        assert fold_raaga(a) != fold_raaga(b), f"{a} and {b} must not fold together"


def test_transliteration_aliases_reach_their_class():
    """Spellings too far apart for the fold rules, so they need an explicit alias entry."""
    from raaga_id.config import canonical_raaga

    assert canonical_raaga("Sriranjini") == "Śrīranjani"
    assert canonical_raaga("Mayamalava Gowla") == "Māyāmāḷavagauḷa"
    assert canonical_raaga("Natakuranji") == "Nāṭakurinji"


def test_similar_names_that_are_DIFFERENT_raagas_are_not_merged():
    """The dangerous half of fuzzy matching. Each of these looks like a near-miss of a model class
    but is a genuinely different raaga, and two would merge a Carnatic recording into a Hindustani
    class. Aliasing any of them would quietly poison training data."""
    from raaga_id.config import canonical_raaga

    # Carnatic Darbar is not Hindustani Darbāri kānaḍa
    assert canonical_raaga("Darbar") != "Darbāri"
    # Asāvēri and Sāvēri are separate Carnatic raagas
    assert canonical_raaga("Asaveri") != "Sāvēri"
    # Malahari is a janya of Māyāmāḷavagauḷa, not the same raaga
    assert canonical_raaga("Malahari") != "Māyāmāḷavagauḷa"
    # Carnatic Kēdāraṁ is not Hindustani Kēdār
    assert canonical_raaga("Kedaram") != "Kēdār"
