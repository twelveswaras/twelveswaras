"""Tradition lookup: split a model class label into (display raaga, tradition).

The dual model tags its classes by tradition ("Tōḍī (Hindustani)"), because Tōḍī/Tōḍi and
Śrī/Śrī are the same spelling across traditions but DIFFERENT raagas. The shipped Carnatic
model uses plain, untagged Carnatic names; tradition_of must keep working for those too, so the
API can add a `tradition` field without a retrain.
"""
from raaga_id.tradition import (
    tradition_of, tradition_counts, load_hindustani_raagas, HINDUSTANI_CANONICAL,
)


def test_tagged_labels_parse_to_name_and_tradition():
    assert tradition_of("Tōḍī (Hindustani)") == ("Tōḍī", "hindustani")
    assert tradition_of("Tōḍi (Carnatic)") == ("Tōḍi", "carnatic")
    assert tradition_of("Yaman kalyāṇ (Hindustani)") == ("Yaman kalyāṇ", "hindustani")


def test_untagged_carnatic_name_is_carnatic():
    # the shipped 40-class model returns plain Carnatic names
    assert tradition_of("Kalyāṇi") == ("Kalyāṇi", "carnatic")
    assert tradition_of("Mōhanaṁ") == ("Mōhanaṁ", "carnatic")


def test_untagged_hindustani_only_name_is_hindustani():
    # a Hindustani-unique name (not in the Carnatic-40) resolves to hindustani even untagged
    assert tradition_of("Mālkauns") == ("Mālkauns", "hindustani")
    assert tradition_of("Bhūp") == ("Bhūp", "hindustani")


def test_untagged_collision_defaults_to_carnatic():
    # Tōḍī/Tōḍi and Śrī/Śrī collide by spelling; with no tag we cannot know, and the shipped
    # model is Carnatic, so default there. A tagged label (test above) always wins over this.
    assert tradition_of("Śrī") == ("Śrī", "carnatic")
    assert tradition_of("Tōḍi") == ("Tōḍi", "carnatic")


def test_unknown_label_is_flagged_not_guessed():
    name, trad = tradition_of("Totally Not A Raaga")
    assert name == "Totally Not A Raaga"
    assert trad == "unknown"


def test_tradition_counts_for_the_shipped_carnatic_model():
    # the shipped model's 40 plain Carnatic names all count as carnatic, none hindustani
    classes = ["Kalyāṇi", "Tōḍi", "Mōhanaṁ", "Śrī"]
    assert tradition_counts(classes) == {"carnatic": 4, "hindustani": 0}


def test_tradition_counts_for_a_dual_model():
    classes = ["Kalyāṇi (Carnatic)", "Tōḍi (Carnatic)", "Tōḍī (Hindustani)", "Mālkauns (Hindustani)"]
    assert tradition_counts(classes) == {"carnatic": 2, "hindustani": 2}


def test_hindustani_vocab_has_the_thirty():
    v = load_hindustani_raagas()
    assert v["tradition"] == "hindustani"
    assert len(v["canonical"]) == 30
    assert len(HINDUSTANI_CANONICAL) == 30
    assert "Mālkauns" in HINDUSTANI_CANONICAL and "Bhūp" in HINDUSTANI_CANONICAL
