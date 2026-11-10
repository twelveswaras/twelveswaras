"""What the site tells search engines and AI assistants is current (llms.txt, JSON-LD, FAQs).

    python tests/test_site_facts.py

Answer engines quote these word for word, so a stale fact here is repeated as true.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOI = "10.5281/zenodo.24096813"


def _jsonld(page: str) -> list[dict]:
    s = (ROOT / "site" / page).read_text(encoding="utf-8")
    return [json.loads(x) for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', s, re.S)]


def _faq(page: str) -> dict[str, str]:
    faq = next(j for j in _jsonld(page) if j.get("@type") == "FAQPage")
    return {q["name"]: q["acceptedAnswer"]["text"] for q in faq["mainEntity"]}


def _llms() -> str:
    from tools import build_data

    return build_data.build_llms_txt(build_data.build_records(json.loads(build_data.GUIDE.read_text())))


def test_llms_txt_describes_both_traditions_and_how_it_listens_now():
    text = _llms()
    summary = text.split("\n\n")[1]
    assert "Carnatic" in summary and "Hindustani" in summary
    assert "30s" not in text and "short clip" not in text
    assert "a minute" in text
    assert "swara" in text.lower()                       # the chains are part of the model


def test_llms_txt_lists_every_raaga_page_of_both_traditions():
    from tools.build_data import slug

    text = _llms()
    hind = json.loads((ROOT / "raaga_guide.hindustani.json").read_text(encoding="utf-8"))
    for nm in (k for k in hind if not k.startswith("_")):
        assert f"/raaga/{slug(nm, '-hindustani')})" in text, nm


def test_llms_txt_states_licences_and_how_to_cite():
    text = _llms()
    assert "AGPL-3.0" in text and DOI in text
    assert "CC-BY-4.0" in text and "weights" in text


def test_published_llms_txt_is_the_generated_one():
    assert (ROOT / "site" / "llms.txt").read_text(encoding="utf-8") == _llms()


def test_no_page_says_the_model_is_non_commercial():
    for page in ("index.html", "about/index.html"):
        s = (ROOT / "site" / page).read_text(encoding="utf-8")
        assert not re.search(r"non-commercial licen[cs]e", s), page


def test_accuracy_is_answered_with_the_measured_numbers():
    faq = _faq("index.html")
    q = next(k for k in faq if "accurate" in k.lower())
    assert "80 real-world" in faq[q] and "71%" in faq[q] and "80%" in faq[q]


def test_every_home_faq_answer_is_also_on_the_page():
    s = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    visible = set(re.findall(r"<summary>(.*?)</summary>", s))
    assert set(_faq("index.html")) <= visible


def test_software_jsonld_carries_version_and_doi():
    app = next(j for j in _jsonld("index.html") if j.get("@type") == "SoftwareApplication")
    assert app["softwareVersion"] == "1.0.0"
    assert app["identifier"] == f"https://doi.org/{DOI}"
    assert f"https://doi.org/{DOI}" in app["sameAs"]


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
