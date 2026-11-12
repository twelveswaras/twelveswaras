"""site/data/raaga-reference.json: the public, machine-readable reference behind the raaga pages
(and the MCP server's data). One record per raaga, from the same corrected data as the pages."""
from __future__ import annotations

import json
from pathlib import Path

from tools import build_pages as B
from tests.test_raaga_seo import MOHANAM

ROOT = Path(__file__).resolve().parent.parent


def test_a_record_carries_what_the_page_states():
    r = B.reference_record("Mōhanaṁ", ["S", "R2", "G3", "P", "D2"], MOHANAM, B.TRAD["carnatic"])
    assert r["name"] == "Mōhanaṁ" and r["tradition"] == "carnatic"
    assert r["url"] == "https://twelveswaras.com/raaga/mohanam"
    assert "Mohanam" in r["also_known_as"] and "Mohanam raga" in r["also_known_as"]
    assert r["arohanam"] == "S R2 G3 P D2 S" and r["avarohanam"] == "S D2 P G3 R2 S"
    assert r["notes"] == {"scale": ["S", "R2", "G3", "P", "D2"], "used_in_phrases": []}
    assert r["scale_positions"] == [0, 2, 4, 7, 9]
    assert r["parent"] == "28 Harikambhoji" and r["kind"] == "audava (five-note)"
    assert r["songs"][:2] == ["Mohana Rama (Tyagaraja)", "Nannu Palimpa (Tyagaraja)"]
    assert r["film_songs"] == ["Paarkathey Paarkathey (Gentleman, A.R. Rahman)"]
    assert r["confused_with"] == "Shivaranjani (same scale)"


def test_the_published_file_has_all_seventy_with_licence_and_provenance():
    d = json.loads((ROOT / "site" / "data" / "raaga-reference.json").read_text())
    assert d["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert "checked against published sources" in d["provenance"]
    assert len(d["raagas"]) == 70
    trads = {r["tradition"] for r in d["raagas"]}
    assert trads == {"carnatic", "hindustani"}
    hus = next(r for r in d["raagas"] if r["name"] == "Hussēnī")
    assert hus["avarohanam"] == "S N2 D1 P M1 G2 R2 S"            # the corrections are applied
    kam = next(r for r in d["raagas"] if r["name"] == "Kāṁbhōji")
    assert kam["notes"]["used_in_phrases"] == ["N3"]


def test_agents_can_find_the_mcp_server_and_the_reference():
    llms = (ROOT / "site" / "llms.txt").read_text()
    assert "https://twelveswaras.com/mcp" in llms
    for tool in ("find_raaga", "raagas_with_notes", "list_raagas", "identify_raaga"):
        assert tool in llms
    assert "https://twelveswaras.com/data/raaga-reference.json" in llms
    card = json.loads((ROOT / "site" / ".well-known" / "mcp.json").read_text())
    assert card["remotes"][0] == {"type": "streamable-http", "url": "https://twelveswaras.com/mcp"}
    assert sorted(card["tools"]) == ["find_raaga", "identify_raaga", "list_raagas", "raagas_with_notes"]
    reg = json.loads((ROOT / "server.json").read_text())
    assert reg["remotes"][0]["url"] == "https://twelveswaras.com/mcp"
