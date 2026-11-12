#!/usr/bin/env python3
"""Generate site/og.png (1200x630 social card) from a self-contained SVG.

Reproducible: the SVG is authored here and rendered with rsvg-convert, so the
card is regenerable and version-controlled (no binary editing). Palette, icon
and wordmark are lifted verbatim from site/index.html's design tokens.

Usage: python3 tools/build_og.py   (needs rsvg-convert: `brew install librsvg`)
"""
import hashlib
import html
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "og.png"
W, H = 1200, 630
CX = W // 2

# tokens (from site/index.html)
INK = "#0b0a08"
PAPER = "#f2ece2"
MUTED = "#a89e8e"
FAINT = "#8b8173"
AMBER = "#f59e0b"
AMBER_HI = "#fbbf24"
AMBER_LO = "#d97706"
JADE_HI = "#74c69d"
LINE2 = "#39301f"
SANS = "SF Pro Display, Helvetica Neue, Helvetica, Arial, sans-serif"
MONO = "SF Mono, Menlo, ui-monospace, monospace"

# the equalizer icon reused verbatim from favicon.svg (0..64 coord space)
BARS = [
    (12, 34, 4, 18), (20, 24, 4, 28), (28, 18, 4, 34),
    (36, 28, 4, 24), (44, 22, 4, 30), (52, 32, 4, 20),
]
ICON = 150
ICON_X = CX - ICON // 2
ICON_Y = 118


def pill_width(text):
    # width scales roughly with text length at the mono size (dot + padding + glyphs)
    return 34 + int(len(text) * 12.3)


def pill(x, text, dot):
    w = pill_width(text)
    return f'''
  <g>
    <rect x="{x:.0f}" y="546" width="{w}" height="42" rx="21" fill="#ffffff08" stroke="{LINE2}"/>
    <circle cx="{x+22:.0f}" cy="567" r="5" fill="{dot}"/>
    <text x="{x+38:.0f}" y="573" font-family="{MONO}" font-size="20" letter-spacing="0.02em"
          fill="{PAPER}" opacity="0.92">{text}</text>
  </g>'''


def build_svg():
    bars = "".join(
        f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="2"/>'
        for bx, by, bw, bh in BARS
    )
    # two pills, centered as a group with a 20px gap between them
    w1, w2, gap = pill_width("Carnatic"), pill_width("Hindustani"), 20
    x1 = CX - (w1 + gap + w2) / 2
    p1 = pill(x1, "Carnatic", AMBER)
    p2 = pill(x1 + w1 + gap, "Hindustani", JADE_HI)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="ic" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{AMBER_HI}"/>
      <stop offset="0.5" stop-color="{AMBER}"/>
      <stop offset="1" stop-color="#b5650a"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.32" r="0.55">
      <stop offset="0" stop-color="{AMBER}" stop-opacity="0.10"/>
      <stop offset="1" stop-color="{AMBER}" stop-opacity="0"/>
    </radialGradient>
  </defs>

  <rect width="{W}" height="{H}" fill="{INK}"/>
  <rect width="{W}" height="{H}" fill="url(#glow)"/>

  <svg x="{ICON_X}" y="{ICON_Y}" width="{ICON}" height="{ICON}" viewBox="0 0 64 64">
    <rect width="64" height="64" rx="14" fill="url(#ic)"/>
    <g fill="#ffffff">{bars}</g>
  </svg>

  <text x="{CX}" y="440" text-anchor="middle" font-family="{SANS}" font-weight="800"
        font-size="98" letter-spacing="-0.02em"><tspan fill="{PAPER}">twelve</tspan><tspan fill="{AMBER}">swaras</tspan></text>

  <text x="{CX}" y="500" text-anchor="middle" font-family="{SANS}" font-size="31"
        fill="{MUTED}">identify the raaga <tspan fill="{FAINT}">&#183;</tspan> a Shazam for raagas</text>
{p1}{p2}
</svg>
'''


# ---- one card per raaga page ------------------------------------------------------------------
# The raaga's name, its scale and the swara wheel with its notes lit: what a shared raaga page
# (and so a shared result) shows in WhatsApp, X or LinkedIn.
RAAGA_OUT = ROOT / "site" / "raaga" / "og"
RAAGA_SUMS = ROOT / "tools" / "og-raaga.sha256.json"   # skip cards whose SVG has not changed
WHEEL_X, WHEEL_Y, WHEEL_R = 905, 300, 190


def fit(text, width, start, per_char):
    """The largest font size (up to `start`) at which `text` fits `width`, estimated per glyph."""
    return min(start, int(width / (per_char * max(len(text), 1))))


def wheel(labels, semis):
    lit = set(semis)
    out = []
    for i, lab in enumerate(labels):
        a = math.radians(-90 + i * 30)
        c, s_ = math.cos(a), math.sin(a)
        on = i in lit
        x1, y1 = WHEEL_X + 108 * c, WHEEL_Y + 108 * s_
        x2, y2 = WHEEL_X + 172 * c, WHEEL_Y + 172 * s_
        lx, ly = WHEEL_X + 214 * c, WHEEL_Y + 214 * s_ + 8
        out.append(
            f'<line class="{"lit" if on else "off"}" x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{AMBER if on else LINE2}" stroke-width="{14 if on else 6}" stroke-linecap="round"/>'
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" font-family="{MONO}" font-size="24" '
            f'fill="{PAPER if on else FAINT}">{html.escape(lab)}</text>')
    return "\n  ".join(out)


def raaga_svg(card):
    e = html.escape
    name_size = fit(card["name"], 560, 112, 0.58)
    scale = [(card["aro_label"], card["aro"]), (card["ava_label"], card["ava"])]
    lines = ""
    for i, (label, notes) in enumerate(scale):
        y = 360 + i * 92
        lines += (f'\n  <text x="90" y="{y}" font-family="{MONO}" font-size="19" fill="{FAINT}">{e(label)}</text>'
                  f'\n  <text x="90" y="{y + 40}" font-family="{MONO}" font-size="{fit(notes or "pending review", 620, 32, 0.62)}" '
                  f'fill="{PAPER}">{e(notes or "pending review")}</text>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <radialGradient id="glow" cx="0.75" cy="0.48" r="0.5">
      <stop offset="0" stop-color="{AMBER}" stop-opacity="0.12"/>
      <stop offset="1" stop-color="{AMBER}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="{INK}"/>
  <rect width="{W}" height="{H}" fill="url(#glow)"/>
  <text x="90" y="138" font-family="{SANS}" font-size="28" fill="{MUTED}">{e(card["eyebrow"])}</text>
  <text class="name" x="90" y="250" font-family="{SANS}" font-weight="800" font-size="{name_size}"
        letter-spacing="-0.02em" fill="{PAPER}">{e(card["name"])}</text>{lines}
  <text x="90" y="578" font-family="{SANS}" font-weight="800" font-size="38" letter-spacing="-0.02em"><tspan fill="{PAPER}">twelve</tspan><tspan fill="{AMBER}">swaras</tspan></text>
  <text x="348" y="578" font-family="{SANS}" font-size="24" fill="{FAINT}">how to hear it</text>
  <circle cx="{WHEEL_X}" cy="{WHEEL_Y}" r="86" fill="none" stroke="{LINE2}" stroke-width="2"/>
  {wheel(card["labels"], card["semis"])}
</svg>
'''


def render(svg, out):
    tmp = out.with_suffix(".svg")
    tmp.write_text(svg, encoding="utf-8")
    try:
        subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(out), str(tmp)], check=True)
    except FileNotFoundError:
        sys.exit("rsvg-convert not found. Install with: brew install librsvg")
    finally:
        tmp.unlink(missing_ok=True)
    shrink(out)


def shrink(png):
    """A 256-colour palette: the same card at under half the bytes (the dark gradient is what
    makes the full-colour PNG heavy). Skipped where Pillow is missing; the full PNG still works."""
    try:
        from PIL import Image
    except ImportError:
        return
    im = Image.open(png).convert("RGB")
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                dither=Image.Dither.FLOYDSTEINBERG).save(png, "PNG", optimize=True)


def write_raaga_cards(cards):
    """Render each raaga's card, skipping any whose SVG is unchanged and whose PNG exists, so a
    rebuild with nothing new rewrites nothing. Returns how many were rendered."""
    RAAGA_OUT.mkdir(parents=True, exist_ok=True)
    sums = json.loads(RAAGA_SUMS.read_text()) if RAAGA_SUMS.exists() else {}
    done = 0
    for card in cards:
        svg = raaga_svg(card)
        digest = hashlib.sha256(svg.encode()).hexdigest()
        out = RAAGA_OUT / f"{card['slug']}.png"
        if sums.get(card["slug"]) == digest and out.exists():
            continue
        render(svg, out)
        sums[card["slug"]] = digest
        done += 1
    keep = {c["slug"] for c in cards}
    RAAGA_SUMS.write_text(json.dumps({k: v for k, v in sorted(sums.items()) if k in keep}, indent=1) + "\n")
    return done


def main():
    svg = build_svg()
    svg_path = ROOT / "tools" / "og.svg"
    svg_path.write_text(svg, encoding="utf-8")
    try:
        subprocess.run(
            ["rsvg-convert", "-w", str(W), "-h", str(H), "-o", str(OUT), str(svg_path)],
            check=True,
        )
    except FileNotFoundError:
        sys.exit("rsvg-convert not found. Install with: brew install librsvg")
    print(f"wrote {OUT.relative_to(ROOT)} ({W}x{H}) and {svg_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
