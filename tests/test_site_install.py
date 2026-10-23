"""Installable-app contract for the static site: the web app manifest and the "Install app" button.

The manifest's icons must declare `any` and `maskable` as SEPARATE entries. A combined
`"purpose": "any maskable"` makes one image serve both uses, so it is either cropped (as maskable,
when it has no safe-zone padding) or shrunk inside a coloured plate (as any, when it does).
Every page that links the manifest also offers the install button. The manifest's screenshots
(a phone and a desktop view, rendered by e2e/screenshots.js) give Chrome its richer install dialog. Structural assertions over the
source, like test_commons; the button's behaviour is covered in e2e/tests/install.spec.js.

    python -m pytest tests/test_site_install.py
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


def _manifest() -> dict:
    return json.loads((SITE / "manifest.webmanifest").read_text(encoding="utf-8"))


def _png_size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a PNG"
    return struct.unpack(">II", head[16:24])


def _pages_linking_manifest() -> list[Path]:
    return [p for p in SITE.rglob("*.html") if 'rel="manifest"' in p.read_text(encoding="utf-8")]


def test_manifest_has_id_and_lang():
    m = _manifest()
    assert m["id"] == "/"
    assert m["lang"] == "en"


def test_icon_purposes_are_split():
    for icon in _manifest()["icons"]:
        assert icon.get("purpose", "any") in {"any", "maskable"}, icon


def test_any_icons_cover_192_and_512():
    sizes = {i["sizes"] for i in _manifest()["icons"] if i.get("purpose", "any") == "any"}
    assert {"192x192", "512x512"} <= sizes


def test_dedicated_maskable_512_png():
    maskable = [i for i in _manifest()["icons"] if i.get("purpose") == "maskable"]
    assert len(maskable) == 1
    icon = maskable[0]
    assert icon["type"] == "image/png" and icon["sizes"] == "512x512"
    assert "maskable" in icon["src"]  # its own file, not the rounded `any` art reused


def test_every_icon_exists_at_its_declared_size():
    for icon in _manifest()["icons"]:
        path = SITE / icon["src"]
        assert path.is_file(), icon["src"]
        if icon["type"] == "image/png":
            w, h = _png_size(path)
            assert f"{w}x{h}" == icon["sizes"], icon["src"]


def test_pages_with_a_manifest_offer_the_install_button():
    pages = _pages_linking_manifest()
    assert {p.relative_to(SITE).as_posix() for p in pages} >= {"index.html", "about/index.html"}
    for page in pages:
        html = page.read_text(encoding="utf-8")
        # hidden by default: only the script reveals it, on a platform that can install
        assert re.search(r'<button[^>]*id="install-app"[^>]*\bhidden\b', html), page
        assert re.search(r'<link rel="stylesheet" href="(\.\./)*install-button\.css">', html), page
        assert re.search(r"import \{ mountInstallButton \} from '(\./|\.\./)+install-button\.js'", html), page


def test_manifest_description_names_both_traditions():
    """The install dialog shows this: it must match the site, which identifies Carnatic and Hindustani raagas."""
    description = _manifest()["description"]
    assert "Carnatic" in description and "Hindustani" in description


def _webp_size(path: Path) -> tuple[int, int]:
    """Pixel size from a WebP header: lossy (VP8), lossless (VP8L) or extended (VP8X)."""
    head = path.read_bytes()[:30]
    assert head[:4] == b"RIFF" and head[8:12] == b"WEBP", f"{path.name} is not a WebP"
    chunk = head[12:16]
    if chunk == b"VP8 ":
        assert head[23:26] == b"\x9d\x01\x2a", f"{path.name}: bad VP8 start code"
        w, h = struct.unpack("<HH", head[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    assert chunk == b"VP8X", f"{path.name}: unknown WebP chunk {chunk!r}"
    return int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1


def _screenshots() -> dict[str, dict]:
    return {s["form_factor"]: s for s in _manifest().get("screenshots", [])}


def test_manifest_has_a_narrow_and_a_wide_screenshot():
    """Without them, Android and desktop Chrome show a plain install dialog instead of the richer one."""
    shots = _screenshots()
    assert set(shots) == {"narrow", "wide"}
    for shot in shots.values():
        assert shot["type"] == "image/webp"
        assert shot["label"].strip()


def test_screenshots_exist_at_their_declared_size_within_chrome_limits():
    sizes = {}
    for form, shot in _screenshots().items():
        path = SITE / shot["src"]
        assert path.is_file(), shot["src"]
        assert path.stat().st_size < 300_000, f"{shot['src']} is too heavy for an install dialog"
        w, h = _webp_size(path)
        assert f"{w}x{h}" == shot["sizes"], shot["src"]
        assert 320 <= min(w, h) and max(w, h) <= 3840, shot["src"]
        assert max(w, h) <= 2.3 * min(w, h), shot["src"]
        sizes[form] = (w, h)
    assert sizes["narrow"][1] > sizes["narrow"][0]  # portrait
    assert sizes["wide"][0] > sizes["wide"][1]  # landscape


def test_screenshots_are_not_precached():
    """Only the install dialog fetches them: the worker must not download them for every visitor."""
    sw = (SITE / "sw.js").read_text(encoding="utf-8")
    for shot in _screenshots().values():
        assert Path(shot["src"]).name not in sw
