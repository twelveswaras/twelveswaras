"""Each raaga page has its own share image: the raaga's name, its scale and a swara wheel with its
notes lit. A shared result (the Share button) links a raaga page, so this card is what people see
in WhatsApp, X or LinkedIn."""
from __future__ import annotations

import re
from pathlib import Path

from tools import build_og as O
from tools import build_pages as B
from tests.test_raaga_seo import MOHANAM, page

ROOT = Path(__file__).resolve().parent.parent


def mohanam_card():
    return B.card("Mōhanaṁ", ["S", "R2", "G3", "P", "D2"], MOHANAM, B.TRAD["carnatic"])


def test_a_page_points_its_share_image_at_its_own_card():
    h = page("Mōhanaṁ", MOHANAM)
    assert '<meta property="og:image" content="https://twelveswaras.com/raaga/og/mohanam.png">' in h
    assert '<meta name="twitter:image" content="https://twelveswaras.com/raaga/og/mohanam.png">' in h
    assert re.search(r'<meta property="og:image:alt" content="Mōhanaṁ, a Carnatic raaga: [^"]+">', h)


def test_the_card_carries_name_scale_and_the_lit_swaras():
    c = mohanam_card()
    assert c["slug"] == "mohanam" and c["semis"] == [0, 2, 4, 7, 9]
    svg = O.raaga_svg(c)
    assert "Mōhanaṁ" in svg and "Audava Carnatic raaga" in svg
    assert "S R2 G3 P D2 S" in svg and "S D2 P G3 R2 S" in svg
    assert svg.count('class="lit"') == 5          # one lit spoke per swara in the raaga
    assert svg.count('class="off"') == 7
    assert "twelve" in svg and "swaras" in svg


def test_hindustani_cards_use_their_own_labels_and_slug():
    c = B.card("Bhūp", ["S", "R", "G", "P", "D"], {"thaat": "Kalyan thaat", "aroha": "S R G P D S'",
                                                    "avaroha": "S' D P G R S"}, B.TRAD["hindustani"])
    assert c["slug"] == "bhup-hindustani"
    svg = O.raaga_svg(c)
    assert "Hindustani raaga · Kalyan thaat" in svg and ">d<" in svg   # komal dha label on the wheel


def test_text_is_escaped_and_long_names_shrink_to_fit():
    long = dict(mohanam_card(), name="Śankarābharaṇaṁ & co")
    svg = O.raaga_svg(long)
    assert "&amp; co" in svg
    size = lambda s: int(re.search(r'class="name"[^>]*font-size="(\d+)"', s).group(1))
    assert size(svg) < size(O.raaga_svg(mohanam_card()))


def test_every_raaga_page_has_its_card_committed_at_1200x630():
    pages = [p for p in (ROOT / "site" / "raaga").glob("*.html") if p.name != "index.html"]
    assert len(pages) == 70
    for p in pages:
        png = ROOT / "site" / "raaga" / "og" / (p.stem + ".png")
        assert png.exists(), png.name
        b = png.read_bytes()
        assert (int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")) == (1200, 630)
        assert len(b) < 80_000, f"{png.name} is {len(b)} bytes"   # shared over phone data


def test_the_card_shows_the_notation_not_the_notes_about_it():
    n = B.notation
    assert n("S R2 G3 P D2 S") == "S R2 G3 P D2 S"
    assert n("S R1 G2 M1 P D1 N2 S (most-cited straight form). Bhashanga flexibility") == "S R1 G2 M1 P D1 N2 S"
    assert n("Vakra. Wikipedia/shivkumar: S N3 P M1 R3 S (dropping G3 and D3).") == "S N3 P M1 R3 S"
    assert n("S N3 D1 P M2 G1 R1 S. The G1 R1 gandhara-janta occurs") == "S N3 D1 P M2 G1 R1 S"
    assert n("r' N D M G r S; N. D. r S") == "r' N D M G r S; N. D. r S"
    assert n("S' N D P, m P D P M, m G R S") == "S' N D P, m P D P M, m G R S"
    assert n("") == ""
