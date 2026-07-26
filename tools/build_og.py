#!/usr/bin/env python3
"""Generate site/og.png (1200x630 social card) from a self-contained SVG.

Reproducible: the SVG is authored here and rendered with rsvg-convert, so the
card is regenerable and version-controlled (no binary editing). Palette, icon
and wordmark are lifted verbatim from site/index.html's design tokens.

Usage: python3 tools/build_og.py   (needs rsvg-convert: `brew install librsvg`)
"""
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
