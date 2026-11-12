"""The scales checked against published sources (12 Nov 2026): corrections in raaga_corrections.json
are applied over the reference, and the wheel shows the scale's notes lit, the notes a raaga uses
only in phrases (anya swaras) outlined, and enharmonic notes by the raaga's own name."""
from __future__ import annotations

import json
from pathlib import Path

from tools import build_og as O
from tools import build_pages as B

ROOT = Path(__file__).resolve().parent.parent
CORR = json.loads((ROOT / "raaga_corrections.json").read_text())
GUIDE = json.loads((ROOT / "raaga_guide.json").read_text())
HGUIDE = json.loads((ROOT / "raaga_guide.hindustani.json").read_text())


def test_every_correction_names_its_sources_and_what_it_replaced():
    for trad in ("carnatic", "hindustani"):
        for name, fixes in CORR[trad].items():
            for f in fixes:
                assert f["sources"] and f["now"] and "was" in f and f["why"], (name, f["field"])


def test_corrections_override_the_reference_field_and_nothing_else():
    ref = {"_about": "a note, not a raaga",
           "Hussēnī": {"avarohana": "S N2 D2 P M1 G2 R2 S", "arohana": "S R2 G2 M1 P N2 D2 N2 S"}}
    out = B.corrected(ref, CORR["carnatic"])
    assert out["Hussēnī"]["avarohana"] == "S N2 D1 P M1 G2 R2 S"
    assert out["Hussēnī"]["arohana"] == "S R2 G2 M1 P N2 D2 N2 S"
    assert ref["Hussēnī"]["avarohana"] == "S N2 D2 P M1 G2 R2 S"        # the reference itself is untouched
    assert out["_about"] == "a note, not a raaga"


def test_scale_notes_are_lit_and_phrase_notes_outlined():
    # Kambhoji: the scale uses N2; N3 comes in only in the phrase S N3 P D2 S
    w = B.wheel_notes(GUIDE["Kāṁbhōji"]["swaras"], "S R2 G3 M1 P D2 S", "S N2 D2 P M1 G3 R2 S", B.TRAD["carnatic"])
    assert w["scale"] == [0, 2, 4, 5, 7, 9, 10] and w["anya"] == [11]
    # Anandabhairavi's anya swaras G3, D1, N3, whatever the parent
    w = B.wheel_notes(GUIDE["Ānandabhairavi"]["swaras"], "S G2 R2 G2 M1 P D2 P S", "S N2 D2 P M1 G2 R2 S", B.TRAD["carnatic"])
    assert w["anya"] == [4, 8, 11]


def test_enharmonic_notes_are_lit_under_the_raagas_own_name():
    w = B.wheel_notes([], "S G1 R1 G1 M2 P D1 N3 S", "S N3 D1 P M2 G1 R1 S", B.TRAD["carnatic"])   # Varali
    assert 2 in w["scale"] and w["labels"][2] == "G1"
    w = B.wheel_notes([], "S R3 G3 M1 P D3 N3 S", "S N3 P M1 R3 S", B.TRAD["carnatic"])           # Nata
    assert w["labels"][3] == "R3" and w["labels"][10] == "D3" and {3, 10} <= set(w["scale"])


def test_hindustani_notation_maps_to_positions():
    w = B.wheel_notes(HGUIDE["Yaman kalyāṇ"]["swaras"], "N. R G M P D N S'", "S' N D P M G, G m G R S", B.TRAD["hindustani"])
    assert w["scale"] == [0, 2, 4, 5, 6, 7, 9, 11] and w["anya"] == []


def test_the_research_note_sets_are_in_the_guide():
    has = lambda name, *notes: set(notes) <= set(GUIDE[name]["swaras"])
    assert has("Hussēnī", "D1") and has("Dēvagāndhāri", "N2") and has("Bilahari", "N2")
    assert has("Kāṁbhōji", "N3") and has("Kamās", "N3") and has("Sencuruṭṭi", "G2")
    assert has("Kāpi", "G3", "D1", "N3") and has("Ānandabhairavi", "G3", "D1", "N3")
    assert len(GUIDE["Sindhubhairavi"]["swaras"]) == 12
    assert "M1" in HGUIDE["Yaman kalyāṇ"]["swaras"]


def test_pages_and_cards_draw_phrase_notes_outlined():
    c = B.card("Kāṁbhōji", GUIDE["Kāṁbhōji"]["swaras"],
               {"arohana": "S R2 G3 M1 P D2 S", "avarohana": "S N2 D2 P M1 G3 R2 S"}, B.TRAD["carnatic"])
    svg = O.raaga_svg(c)
    assert svg.count('class="lit"') == 7 and svg.count('class="anya"') == 1
    page = B.build_page("Kāṁbhōji", GUIDE["Kāṁbhōji"]["swaras"],
                        {"arohana": "S R2 G3 M1 P D2 S", "avarohana": "S N2 D2 P M1 G3 R2 S"}, [])
    assert "var IN = [0,2,4,5,7,9,10], ANYA = [11]" in page
