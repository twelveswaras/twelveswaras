"""The site's raaga pickers match the model vocabulary (raagas.json, raagas.hindustani.json).

    python tests/test_site_vocab.py

The recognizer page and the contribute page each carry the full raaga lists inline (no extra
request). Adding a raaga means editing both; this catches the copy that was forgotten.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["site/index.html", "site/contribute/index.html"]


def _lists(page):
    s = (ROOT / page).read_text(encoding="utf-8")
    return {name: json.loads(re.search(rf"var {name}=(\[[^\]]*\])", s).group(1))
            for name in ("RAAGAS", "HINDUSTANI_RAAGAS")}


def test_every_page_lists_exactly_the_model_vocabulary():
    carnatic = sorted(json.loads((ROOT / "raagas.json").read_text(encoding="utf-8"))["canonical"])
    hindustani = sorted(json.loads((ROOT / "raagas.hindustani.json").read_text(encoding="utf-8"))["canonical"])
    for page in PAGES:
        got = _lists(page)
        assert sorted(got["RAAGAS"]) == carnatic, f"{page}: Carnatic list differs from raagas.json"
        assert sorted(got["HINDUSTANI_RAAGAS"]) == hindustani, f"{page}: Hindustani list differs"


if __name__ == "__main__":
    test_every_page_lists_exactly_the_model_vocabulary()
    print("ok")
