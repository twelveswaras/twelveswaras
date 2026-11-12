"""Raaga pages say what people search: the name as they type it ("Mohanam raga", "raag Yaman"), arohanam and
avarohanam (aroh and avroh), the parent melakarta or thaat, and the songs; in the title, the description, the
headings and schema.org (alternate names and an FAQ), while the page keeps the name's own spelling.

    python -m pytest tests/test_raaga_seo.py
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from tools import build_pages as B

MOHANAM = {
    "parent_mela": "28 Harikambhoji", "janya_type": "audava-audava (5 notes in both arohana and avarohana)",
    "arohana": "S R2 G3 P D2 S", "avarohana": "S D2 P G3 R2 S", "jeeva_swaras": "R2, G3, D2", "nyasa_swaras": "G3, P",
    "kritis": "Mohana Rama (Tyagaraja); Nannu Palimpa (Tyagaraja); Kapali (Papanasam Sivan)",
    "film_songs": "Paarkathey Paarkathey (Gentleman, A.R. Rahman)", "confusing_with": "Shivaranjani (same scale)",
    "sources": "https://en.wikipedia.org/wiki/Mohanam", "tell": "Bright and sunny.", "rasa": "joyful",
}
YAMAN = {"thaat": "Kalyan", "jati": "sampurna (7)", "aroha": "N. R G M P D N S'", "avaroha": "S' N D P M G R S",
         "pakad": "N. R G, R G, P M G R, S", "vadi": "Ga", "samvadi": "Ni", "samay": "first prahar of the night (early evening)",
         "tell": "Tivra Ma throughout.", "confusing_with": "Bhoop", "sources": ["https://en.wikipedia.org/wiki/Yaman"]}


def page(name, ref, trad="carnatic", swaras=("S", "R2", "G3", "P", "D2")):
    return B.build_page(name, list(swaras), ref, [], B.TRAD[trad])


def ld(html):
    return [json.loads(m) for m in re.findall(r'<script type="application/ld\+json">\n(.*?)\n</script>', html, re.S)]


def test_plain_spelling():
    assert B.plain("Mōhanaṁ") == "Mohanam"
    assert B.plain("Kēdāragauḷa") == "Kedaragaula"
    assert B.plain("Yaman kalyāṇ") == "Yaman kalyan"
    assert B.plain("Behāg") == "Behag"


def test_a_carnatic_title_and_description_say_what_people_search():
    h = page("Mōhanaṁ", MOHANAM)
    title = re.search(r"<title>(.*?)</title>", h).group(1)
    assert title == "Mohanam raga: arohanam, avarohanam and songs · twelveswaras"
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert desc.startswith("Mohanam (Mōhanaṁ) raga: an audava (five-note) janya of melakarta 28, Harikambhoji. "
                           "Arohanam S R2 G3 P D2 S, avarohanam S D2 P G3 R2 S.")
    assert "Mohana Rama" in desc and "a audava" not in desc
    assert f'<meta property="og:title" content="{title}">' in h
    assert '<h1 class="title">Mōhanaṁ</h1>' in h                       # the page keeps the name's own spelling
    assert "Also written Mohanam" in h
    assert "arohanam" in h and "avarohanam" in h
    assert re.search(r"<h2>Songs in Mohanam: kritis and film songs</h2>", h)


def test_carnatic_schema_alternate_names_and_faq():
    term, faq = ld(page("Mōhanaṁ", MOHANAM))
    assert term["@type"] == "DefinedTerm" and term["name"] == "Mōhanaṁ"
    assert term["alternateName"] == ["Mohanam", "Mohanam raga", "Mohanam ragam"]
    qa = {q["name"]: q["acceptedAnswer"]["text"] for q in faq["mainEntity"]}
    assert qa["What is the arohanam and avarohanam of Mohanam?"] == "Arohanam: S R2 G3 P D2 S. Avarohanam: S D2 P G3 R2 S."
    assert qa["What is the parent melakarta of Mohanam?"] == "Mohanam is a janya of melakarta 28, Harikambhoji."
    assert "Mohana Rama (Tyagaraja)" in qa["Which songs are in Mohanam raga?"]


def test_a_hindustani_page_says_raag_aroh_avroh_pakad_thaat_and_time():
    h = page("Yaman kalyāṇ", YAMAN, "hindustani", ("S", "R2", "G3", "M2", "P", "D2", "N3"))
    title = re.search(r"<title>(.*?)</title>", h).group(1)
    assert title == "Raag Yaman kalyan (Hindustani): aroh, avroh and pakad · twelveswaras"
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert desc.startswith("Raag Yaman kalyan (Yaman kalyāṇ): Kalyan thaat, sampurna (7). Aroh N. R G M P D N S&#x27;, "
                           "avroh S&#x27; N D P M G R S. Pakad N. R G, R G, P M G R, S.")
    term, faq = ld(h)
    assert term["alternateName"] == ["Yaman kalyan", "Raag Yaman kalyan", "Rag Yaman kalyan"]
    qa = {q["name"]: q["acceptedAnswer"]["text"] for q in faq["mainEntity"]}
    assert qa["What is the aroh and avroh of raag Yaman kalyan?"] == "Aroh: N. R G M P D N S'. Avroh: S' N D P M G R S."
    assert qa["Which thaat is raag Yaman kalyan in?"] == "Kalyan thaat."
    assert qa["When is raag Yaman kalyan sung?"] == "The first prahar of the night (early evening)."


def test_missing_facts_leave_no_empty_sentence_or_question():
    h = page("Abhōgi", {"tell": "Sweet."})
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert "Arohanam ," not in desc and "None" not in desc and desc.startswith("Abhogi (Abhōgi) raga:")
    assert len(ld(h)) == 1                                                # no FAQ without answers


def test_the_built_pages_carry_it():
    from pathlib import Path
    s = (Path(B.ROOT) / "site" / "raaga" / "mohanam.html").read_text(encoding="utf-8")
    assert "<title>Mohanam raga: arohanam, avarohanam and songs · twelveswaras</title>" in s


def test_the_parent_mela_is_read_from_its_free_text_and_said_one_way():
    m = B.mela
    assert m("28 Harikambhoji") == (28, "Harikambhoji", False)
    assert m("Janya of 15th melakarta Mayamalavagowla") == (15, "Mayamalavagowla", False)
    assert m("Kharaharapriya (22nd melakarta)") == (22, "Kharaharapriya", False)
    assert m("29 Dheera Shankarabharanam (sources place Behag under Shankarabharanam, NOT Harikambhoji)") == (29, "Dheerasankarabharanam", False)
    assert m("22nd melakarta (Kharaharapriya), it is itself the 22nd melakarta, not a janya") == (22, "Kharaharapriya", True)
    assert m("8th melakarta (Hanumatodi is itself the janaka/melakarta raga)") == (8, "Hanumatodi", True)
    assert m("Sources disagree: ragasurabhi and karnatik classify it as janya of 28th mela Harikambhoji; some 29th") is None
    assert m("") is None


def test_a_melakarta_raaga_says_so_and_composers_stay_out_of_the_description():
    ref = dict(MOHANAM, parent_mela="22nd melakarta (Kharaharapriya), it is itself the 22nd melakarta, not a janya",
               arohana="S R2 G2 M1 P D2 N2 S", avarohana="S N2 D2 P M1 G2 R2 S",
               kritis="Marivere Gati – Syama Sastri; Chakkani Raja (Tyagaraja); Mitri Bhagyame, Tyagaraja")
    h = page("Karaharapriya", ref, swaras=("S", "R2", "G2", "M1", "P", "D2", "N2"))
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert desc.startswith("Karaharapriya raga: a sampurna (seven-note) raaga, melakarta 22. ")
    assert "Kritis: Marivere Gati, Chakkani Raja, Mitri Bhagyame." in desc
    qa = {q["name"]: q["acceptedAnswer"]["text"] for q in ld(h)[1]["mainEntity"]}
    assert qa["Is Karaharapriya a melakarta raga?"] == "Yes: melakarta 22."


# --- the homepage answers the searches for what the app does -------------------------------------

def _home():
    return (Path(__file__).resolve().parent.parent / "site" / "index.html").read_text()


def test_homepage_title_and_description_lead_with_raga_identifier():
    h = _home()
    title = re.search(r"<title>(.*?)</title>", h).group(1)
    assert title.startswith("Raga identifier: find the raga of a song")
    assert "twelveswaras" in title
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert desc.startswith("Raga identifier for Carnatic and Hindustani music")
    assert re.search(r'<meta property="og:title" content="Raga identifier[^"]*"', h)


def test_homepage_app_schema_names_what_people_search():
    app = next(x for x in ld(_home()) if x["@type"] == "SoftwareApplication")
    for name in ["Raga identifier", "Raag identifier", "Raga finder", "Shazam for raagas"]:
        assert name in app["alternateName"]


def test_homepage_faq_answers_which_raga_is_this_song_visibly_and_in_schema():
    h = _home()
    faq = next(x for x in ld(h) if x["@type"] == "FAQPage")
    qs = [q["name"] for q in faq["mainEntity"]]
    for q in ["Which raga is this song?", "Can I find the raga of a film song?"]:
        assert q in qs, q
        assert f"<summary>{q}</summary>" in h, q   # schema mirrors the visible FAQ
    # every schema question is shown on the page
    for q in qs:
        assert f"<summary>{q}</summary>" in h, q


# --- a scale field that carries research notes: notation where the scale goes, notes kept below ----

NOTED = dict(MOHANAM,
             arohana="S R2 G3 P D2 S (most-cited form). Some sources add a vakra turn: S R2 G3 R2 P D2 S",
             avarohana="Vakra. Wikipedia: S D2 P G3 R2 S (karnatik agrees).")


def test_the_scale_shows_notation_and_keeps_the_research_note_below_it():
    h = page("Mōhanaṁ", NOTED)
    assert '<p class="v">S R2 G3 P D2 S</p>' in h
    assert '<p class="v">S D2 P G3 R2 S</p>' in h
    assert '<p class="note">Variants and sources: S R2 G3 P D2 S (most-cited form). Some sources add' in h
    assert '<p class="note">Variants and sources: Vakra. Wikipedia:' in h


def test_description_and_faq_carry_only_the_notation():
    h = page("Mōhanaṁ", NOTED)
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert "Arohanam S R2 G3 P D2 S, avarohanam S D2 P G3 R2 S." in desc
    assert "most-cited" not in desc and "Wikipedia" not in desc
    qa = {q["name"]: q["acceptedAnswer"]["text"] for q in ld(h)[1]["mainEntity"]}
    assert qa["What is the arohanam and avarohanam of Mohanam?"] == "Arohanam: S R2 G3 P D2 S. Avarohanam: S D2 P G3 R2 S."


def test_a_clean_scale_has_no_note():
    assert '<p class="note">' not in page("Mōhanaṁ", MOHANAM)
