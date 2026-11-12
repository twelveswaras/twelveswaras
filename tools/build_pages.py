"""Generate one static page per raaga from the single source of truth.

    python -m tools.build_pages

Reads:
  raaga_guide.json                         -> authoritative swara set (drives the wheel)
  supporting-docs/raaga_reference_draft.json -> draft reference fields (arohana, jeeva,
                                              prayogas, kritis, ...), marked reviewed=false

Emits site/raaga/<slug>.html for every raaga, from ONE template, so 40 pages stay consistent
and regenerate whenever the data changes. Every page carries a visible "Draft" banner until a
musician verifies it. Reference prose is shown as-is (already de-dashed at the data layer).

The wheel lights the raaga's swaras; jeeva/nyasa notes are parsed from the (prose) reference and
emphasised where they can be resolved unambiguously against the raaga's own swara set.
Audio is a small formant-based vocal "aah" synth (no samples, no backend), warmer than a beep;
a real sung rendition with gamaka is future work (the audio commons).
"""
from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path

from tools import build_og
from tools.build_data import SEMITONE, slug

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "raaga_guide.json"
REF = ROOT / "supporting-docs" / "raaga_reference_draft.json"
OUT = ROOT / "site" / "raaga"

COUNT_LABEL = {5: "audava (five-note)", 6: "shadava (six-note)", 7: "sampurna (seven-note)"}
LETTER_WORDS = {
    "S": ["sa", "shadja", "shadjam", "shadjamam"],
    "R": ["ri", "rishabha", "rishabham"],
    "G": ["ga", "gandhara", "gandharam"],
    "M": ["ma", "madhyama", "madhyamam"],
    "P": ["pa", "panchama", "panchamam"],
    "D": ["dha", "da", "daivata", "daivatam", "dhaivata", "dhaivatham"],
    "N": ["ni", "nishada", "nishadam", "nishadham"],
}


# Per-tradition config. Carnatic values are the exact current literals, so its output stays
# byte-identical (verified by regenerating + a zero git diff). Hindustani reuses the SAME template,
# CSS and wheel, swapping the swara labels, the vadi/samvadi legend, the reference field names, and
# a "-hindustani" slug suffix (same directory, so every relative path is unchanged).
TRAD = {
    "carnatic": {
        "word": "Carnatic",
        "labels": ["S", "R1", "R2", "G2", "G3", "M1", "M2", "P", "D1", "D2", "N2", "N3"],
        "suffix": "",
        "termset": "Carnatic raagas",
        "guide": "raaga_guide.json",
        "ref": "supporting-docs/raaga_reference_draft.json",
        "legend_jeeva": "jeeva (life note)",
        "legend_nyasa": "nyasa (resting note)",
    },
    "hindustani": {
        "word": "Hindustani",
        "labels": ["S", "r", "R", "g", "G", "m", "M", "P", "d", "D", "n", "N"],
        "suffix": "-hindustani",
        "termset": "Hindustani raagas",
        "guide": "raaga_guide.hindustani.json",
        "ref": "supporting-docs/raaga_reference_hindustani.json",
        "legend_jeeva": "vadi (sonant)",
        "legend_nyasa": "samvadi (consonant)",
    },
}




def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def plain(name: str) -> str:
    """The name as people type it in a search box: no diacritics (Mōhanaṁ -> Mohanam)."""
    return "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))


# The 72 melakartas, by number, as they are commonly written (the parent scale of every Carnatic raaga).
MELAKARTAS = (
    "Kanakangi Ratnangi Ganamurti Vanaspati Manavati Tanarupi Senavati Hanumatodi Dhenuka Natakapriya Kokilapriya "
    "Rupavati Gayakapriya Vakulabharanam Mayamalavagowla Chakravakam Suryakantam Hatakambari Jhankaradhwani "
    "Natabhairavi Keeravani Kharaharapriya Gourimanohari Varunapriya Mararanjani Charukesi Sarasangi Harikambhoji "
    "Dheerasankarabharanam Naganandini Yagapriya Ragavardhini Gangeyabhushani Vagadheeswari Shulini Chalanata Salagam "
    "Jalarnavam Jhalavarali Navaneetam Pavani Raghupriya Gavambhodi Bhavapriya Shubhapantuvarali Shadvidamargini "
    "Suvarnangi Divyamani Dhavalambari Namanarayani Kamavardhini Ramapriya Gamanashrama Vishwambari Shamalangi "
    "Shanmukhapriya Simhendramadhyamam Hemavati Dharmavati Neetimati Kantamani Rishabhapriya Latangi Vachaspati "
    "Mechakalyani Chitrambari Sucharitra Jyotiswarupini Dhatuvardhani Nasikabhushani Kosalam Rasikapriya").split()


def mela(text: str):
    """The parent melakarta from the reference's free text: (number, name, the raaga is that melakarta itself), or
    None when the text gives none or says the sources disagree. The first number is the mela; the name is the
    standard one for that number, whatever spelling and notes the text carries."""
    text = text or ""
    found = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", text)
    if not found or re.match(r"\s*sources disagree", text, re.I) or not 1 <= int(found.group(1)) <= 72:
        return None
    n = int(found.group(1))
    return n, MELAKARTAS[n - 1], bool(re.search(r"\bitself\b|not a janya", text, re.I))


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def parse_positions(text: str, swaras: list[str]) -> list[int]:
    """Resolve jeeva/nyasa prose to wheel positions, only where unambiguous vs the swara set."""
    if not text:
        return []
    semis: set[int] = set()
    letters: dict[str, list[str]] = {}
    for tok in swaras:
        letters.setdefault(tok[0], []).append(tok)
    # explicit multi-char tokens the raaga actually uses (e.g. R2, G3, N2)
    for tok in swaras:
        if len(tok) >= 2 and re.search(r"\b" + re.escape(tok) + r"\b", text):
            semis.add(SEMITONE[tok])
    # standalone capital letters (e.g. "R, D, N" or the "P" in "G3, P")
    for m in re.findall(r"\b([SRGMPDN])\b", text):
        toks = letters.get(m, [])
        if len(toks) == 1:
            semis.add(SEMITONE[toks[0]])
    # lowercase word-forms (e.g. "Ga and Ni", "Rishabham")
    low = text.lower()
    for letter, toks in letters.items():
        if len(toks) != 1:
            continue
        if any(re.search(r"\b" + w + r"\b", low) for w in LETTER_WORDS[letter]):
            semis.add(SEMITONE[toks[0]])
    return sorted(semis & {SEMITONE[t] for t in swaras})


def items(s: str) -> list[str]:
    return [x.strip() for x in re.split(r";", s or "") if x.strip()]


def wikipedia_url(sources: str) -> str:
    m = re.search(r"https?://en\.wikipedia\.org/wiki/\S+", sources or "")
    return m.group(0).rstrip(".,;") if m else ""


def resolve_swaras(g_swaras: list[str], ref: dict) -> list[str]:
    """Guide swaras if present, else a DRAFT set derived from the reference arohana/avarohana
    (for the 6 raagas the expert hasn't verified yet). Enharmonic tokens outside the 12-position
    naming (G1, N1, R3, D3) are skipped, so vivadi raagas render partially until verified."""
    if g_swaras:
        return g_swaras
    text = (ref.get("arohana", "") or "") + " " + (ref.get("avarohana", "") or "")
    seen: list[str] = []
    for tok in re.findall(r"[SRGMPDN][123]?", text):
        if tok in SEMITONE and tok not in seen:
            seen.append(tok)
    return sorted(seen, key=lambda t: SEMITONE[t])


def necklace(pcs: frozenset) -> tuple:
    """Canonical form of a pitch-class set under transposition. Two raagas share a necklace iff one
    scale is the other with a different note taken as Sa, i.e. they are graha-bhedam related."""
    best = None
    for k in pcs:
        rot = tuple(sorted((x - k) % 12 for x in pcs))
        if best is None or rot < best:
            best = rot
    return best


def is_symmetric(ref: dict) -> bool:
    """Graha bhedam relates SCALES, not every janya that reuses a parent's notes. Only a symmetric
    linear scale qualifies: a krama-sampurna melakarta, or an audava/shadava janya with the same
    notes ascending and descending. Vakra, bhashanga, and audava-sampurna (asymmetric) janyas are
    excluded, otherwise every janya of a diatonic mela would falsely group with all the others."""
    jt = (ref.get("janya_type", "") or "").lower()
    if "vakra" in jt or "bhashanga" in jt:
        return False
    if "melakarta" in jt or "it is itself" in jt or "it is the melakarta" in jt:
        return True
    return "audava-audava" in jt or "shadava-shadava" in jt or "sampurna-sampurna" in jt


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__TITLE__</title>
<meta name="description" content="__DESC__">
<link rel="canonical" href="https://twelveswaras.com/raaga/__SLUG__">
<meta name="theme-color" content="#0b0a08">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<meta property="og:type" content="article">
<meta property="og:title" content="__TITLE__">
<meta property="og:description" content="__DESC__">
<meta property="og:image" content="https://twelveswaras.com/raaga/og/__SLUG__.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="__OGALT__">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="__TITLE__">
<meta name="twitter:image" content="https://twelveswaras.com/raaga/og/__SLUG__.png">
__JSONLD__
<link rel="stylesheet" href="/nav.css">
<style>
  :root{
    --ink:#0b0a08; --raise:#16130f; --raise-2:#1c1811; --line:#2a241c; --line-2:#39301f;
    --paper:#f2ece2; --muted:#a89e8e; --faint:#8b8173;
    --amber:#f59e0b; --amber-lo:#d97706; --amber-hi:#fbbf24;
    --jade:#5aa87f; --jade-hi:#74c69d;   /* secondary accent: resting notes, the learning section */
    --sans:"SF Pro Display",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,monospace;
    --measure:64ch;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
  @media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
  body{margin:0;background:var(--ink);color:var(--paper);font-family:var(--sans);
    line-height:1.62;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  a{color:var(--amber-hi);text-decoration:none} a:hover{color:#fff}
  :focus-visible{outline:2px solid var(--amber);outline-offset:3px;border-radius:4px}
  .wrap{width:100%;max-width:780px;margin:0 auto;padding:0 max(22px,env(safe-area-inset-right)) 0 max(22px,env(safe-area-inset-left))}
  .crumb{font-family:var(--mono);font-size:.74rem;letter-spacing:.04em;color:var(--faint);padding:20px 0 0}
  .crumb a{color:var(--muted);text-decoration:underline;text-underline-offset:2px} .crumb a:hover{color:var(--paper)}
  .hero{padding:14px 0 8px}
  .eyebrow{font-family:var(--mono);font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;
    color:var(--amber);margin:0 0 12px}
  .title{font-size:clamp(2.4rem,10vw,4rem);font-weight:800;letter-spacing:-.03em;line-height:1.02;margin:0}
  .thesis{color:var(--paper);font-size:clamp(1.02rem,3.4vw,1.18rem);max-width:52ch;margin:14px 0 0;text-wrap:balance}
  .mood{font-family:var(--mono);font-size:.76rem;letter-spacing:.06em;color:var(--amber-hi);margin:12px 0 0}
  .struct{color:var(--muted);font-size:.98rem;max-width:46ch;margin:8px 0 0}
  .wheelwrap{display:flex;flex-direction:column;align-items:center;margin:30px 0 6px}
  .wheel{width:min(360px,86vw);height:auto;display:block}
  .wheel text{font-family:var(--mono);font-size:12px;fill:var(--faint)}
  .wheel text.on{fill:var(--paper)}
  .wheel text.jeeva{fill:var(--amber-hi);font-weight:700}
  .legend{display:flex;flex-wrap:wrap;gap:16px;justify-content:center;margin-top:12px;
    font-family:var(--mono);font-size:.72rem;letter-spacing:.02em;color:var(--muted)}
  .legend span{display:inline-flex;align-items:center;gap:.5rem}
  .legend i{width:14px;height:14px;border-radius:50%;display:inline-block}
  .lg-on{background:var(--amber)}
  .lg-jeeva{background:var(--amber-hi);box-shadow:0 0 0 3px rgba(251,191,36,.22)}
  .lg-nyasa{background:transparent;border:2px solid var(--jade-hi)}
  .lg-anya{background:transparent;border:2px solid var(--amber)}
  .wheel text.anya{fill:var(--muted)}
  .wheel .node{cursor:pointer}
  .play{display:flex;align-items:center;gap:14px;margin-top:16px;flex-wrap:wrap;justify-content:center}
  .play button{display:inline-flex;align-items:center;gap:.5rem;background:var(--raise-2);
    border:1px solid var(--line-2);color:var(--paper);font-family:var(--mono);font-size:.8rem;
    letter-spacing:.02em;padding:.6rem 1rem;border-radius:999px;cursor:pointer;
    transition:border-color .12s ease,background .12s ease}
  .play button:hover{border-color:var(--amber);background:var(--raise)}
  .play button[aria-pressed="true"]{border-color:var(--amber);color:var(--amber-hi)}
  .play .hint{font-family:var(--mono);font-size:.72rem;color:var(--faint)}
  .scale{display:grid;grid-template-columns:1fr;gap:10px;margin:26px 0 0}
  @media(min-width:520px){.scale{grid-template-columns:1fr 1fr}}
  .scale .cell{background:var(--raise);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
  .scale .k{font-family:var(--mono);font-size:.72rem;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin:0 0 6px}
  .scale .v{font-family:var(--mono);font-size:1.06rem;letter-spacing:.05em;color:var(--paper);margin:0}
  .scale .v.pending{color:var(--faint);letter-spacing:0}
  .scale .note{font-size:.8rem;line-height:1.5;color:var(--faint);margin:8px 0 0}
  section{padding:36px 0;border-top:1px solid var(--line)}
  h2{font-size:clamp(1.2rem,4.5vw,1.5rem);font-weight:800;letter-spacing:-.02em;margin:0 0 1rem;text-wrap:balance}
  p{color:var(--muted);max-width:var(--measure)}
  .hear dl{margin:0;display:grid;gap:18px}
  .hear dt{font-family:var(--mono);font-size:.7rem;letter-spacing:.14em;text-transform:uppercase;color:var(--jade-hi);margin:0 0 5px}
  .hear dd{margin:0;color:var(--paper)}
  .cards{display:grid;gap:10px;margin-top:4px}
  .card{background:var(--raise);border:1px solid var(--line);border-radius:12px;padding:13px 16px;color:var(--paper);font-size:.98rem}
  ul.listen{list-style:none;padding:0;margin:6px 0 0;display:grid;gap:10px}
  ul.listen li{display:flex;gap:.7rem;align-items:baseline;color:var(--paper)}
  ul.listen li::before{content:"\\25b8";color:var(--amber);flex:0 0 auto}
  .facts{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 0}
  .chip{font-family:var(--mono);font-size:.74rem;letter-spacing:.03em;color:var(--muted);
    background:var(--raise);border:1px solid var(--line);border-radius:999px;padding:.42rem .8rem}
  .chip b{color:var(--amber);font-weight:600}
  .cta-row{margin:34px 0 6px}
  .cta{display:inline-flex;align-items:center;gap:.55rem;background:var(--amber);color:#1a1205;
    font-weight:700;font-size:1rem;padding:.8rem 1.5rem;border-radius:11px;border:0;
    transition:transform .12s ease,background .12s ease}
  .cta:hover{background:var(--amber-hi);color:#1a1205;transform:translateY(-1px)}
  .draftbar{font-family:var(--mono);font-size:.72rem;color:var(--faint);border:1px dashed var(--line-2);
    border-radius:10px;padding:12px 14px;margin:14px 0 0;line-height:1.5}
  footer{border-top:1px solid var(--line);padding:30px 0 max(46px,env(safe-area-inset-bottom));text-align:center}
  footer .tagline{font-family:var(--mono);font-size:.74rem;letter-spacing:.04em;color:var(--faint);
    max-width:48ch;margin:0 auto;text-wrap:balance}
  footer .links{margin-top:.7rem;font-size:.9rem;display:flex;gap:18px;justify-content:center;flex-wrap:wrap}
  /* Printable reference card: drop the dark theme + interactive wheel; keep the raaga's notes,
     so the reference works on paper, not only on a screen. */
  @media print {
    *{background:transparent !important;box-shadow:none !important;text-shadow:none !important;color:#1a1a1a !important}
    body{background:#fff !important}
    .top,.crumb,.wheelwrap,.play,.cta-row,footer .links{display:none !important}
    a{text-decoration:none}
    .scale span,.struct span,.cell{border:1px solid #bbb !important}
    .draftbar{border-color:#999 !important} footer{border-color:#ccc !important}
  }
</style>
</head>
<body>
<div class="wrap">
  <nav class="top">
    <a class="brand" href="../" aria-label="twelveswaras home">
      <svg viewBox="0 0 256 256" aria-hidden="true">
        <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#fbbf24"/><stop offset="1" stop-color="#b45309"/></linearGradient></defs>
        <rect width="256" height="256" rx="60" fill="url(#g)"/>
        <g fill="#fff">
          <rect x="40" y="140" width="12" height="60" rx="6"/><rect x="60" y="104" width="12" height="96" rx="6"/>
          <rect x="80" y="150" width="12" height="50" rx="6"/><rect x="100" y="76" width="12" height="124" rx="6"/>
          <rect x="120" y="118" width="12" height="82" rx="6"/><rect x="140" y="92" width="12" height="108" rx="6"/>
          <rect x="160" y="60" width="12" height="140" rx="6"/><rect x="180" y="128" width="12" height="72" rx="6"/>
          <rect x="200" y="100" width="12" height="100" rx="6"/></g>
      </svg>
      <span><span class="a">twelve</span><span class="b">swaras</span></span>
    </a>
    <span class="nav">
      <a href="./">raagas</a>
      <span class="sep" aria-hidden="true">·</span>
      <a href="../listen/">train your ear</a>
      <span class="sep" aria-hidden="true">·</span>
      <a href="../contribute/">contribute</a>
      <span class="sep" aria-hidden="true">·</span>
      <a href="../about/">about</a>
    </span>
  </nav>
<main>
  <p class="crumb"><a href="../">home</a> / <a href="./">raagas</a> / __CRUMB__</p>

  <header class="hero">
    <p class="eyebrow">__EYEBROW__</p>
    <h1 class="title">__NAME__</h1>
    <p class="thesis">__THESIS__</p>__MOOD____STRUCT__

    <div class="wheelwrap">
      <svg class="wheel" viewBox="0 0 300 300" role="img" aria-label="__WHEEL_ALT__">
        <g id="wheel"></g>
      </svg>
      <div class="legend">
        <span><i class="lg-on"></i> in the raaga</span>
        <span><i class="lg-jeeva"></i> __LEGEND_JEEVA__</span>
        <span><i class="lg-nyasa"></i> __LEGEND_NYASA__</span>__ANYA_LEGEND__
      </div>
      <div class="play">
        <button id="playScale" type="button" aria-pressed="false">▶ play the scale</button>
        <span class="hint">or tap any lit note to hear it</span>
      </div>
    </div>

    <div class="scale">
      <div class="cell"><p class="k">__ARO_LABEL__</p>__AROHANA__</div>
      <div class="cell"><p class="k">__AVA_LABEL__</p>__AVAROHANA__</div>
    </div>
  </header>
__HEAR____CONFUSE____LISTEN____COUSINS__
  <div class="cta-row"><a class="cta" href="../">Identify a raaga →</a></div>
  <p class="draftbar">◐ Draft: the reference facts on this page are compiled from public sources and are pending review by a musician. Corrections welcome via GitHub.</p>
</main>
</div>

<footer>
  <div class="wrap">
    <p class="tagline">a non-commercial, open-source public good, Carnatic and Hindustani, CC-BY data commons</p>
    <div class="links"><a href="../listen/">train your ear</a><a href="https://github.com/twelveswaras">github</a><a href="https://github.com/twelveswaras/twelveswaras/blob/main/PDGI.md">a digital commons</a></div>
  </div>
</footer>

<script>
(function () {
  var LABELS = __LABELS__;
  var IN = __IN__, ANYA = __ANYA__, JEEVA = __JEEVA__, NYASA = __NYASA__;
  var cx=150, cy=150, rNode=104, rLabel=132, nodes={};
  var g = document.getElementById('wheel'), NS='http://www.w3.org/2000/svg';
  function el(t,a){ var e=document.createElementNS(NS,t); for(var k in a) e.setAttribute(k,a[k]); return e; }
  function pt(i,r){ var a=(-90+i*30)*Math.PI/180; return [cx+r*Math.cos(a), cy+r*Math.sin(a)]; }
  g.appendChild(el('circle',{cx:cx,cy:cy,r:rNode,fill:'none',stroke:'#2a241c','stroke-width':1}));
  if (IN.length>1){
    var poly = IN.map(function(i){ var p=pt(i,rNode); return p[0].toFixed(1)+','+p[1].toFixed(1); }).join(' ');
    g.appendChild(el('polygon',{points:poly,fill:'rgba(245,158,11,.09)',stroke:'#d97706','stroke-width':1.5,'stroke-linejoin':'round'}));
  }
  function has(arr,i){ return arr.indexOf(i)>=0; }
  for (var i=0;i<12;i++){
    var p=pt(i,rNode), lp=pt(i,rLabel), on=has(IN,i), an=!on&&has(ANYA,i), je=has(JEEVA,i), ny=has(NYASA,i);
    if (ny) g.appendChild(el('circle',{cx:p[0],cy:p[1],r:9,fill:'none',stroke:'#74c69d','stroke-width':2}));
    if (je) g.appendChild(el('circle',{cx:p[0],cy:p[1],r:11,fill:'rgba(251,191,36,.20)'}));
    // a note used only in phrases (anya swara): an outlined node, playable but not part of the scale
    var node=an ? el('circle',{cx:p[0],cy:p[1],r:5,fill:'#0b0a08',stroke:'#f59e0b','stroke-width':1.6})
                : el('circle',{cx:p[0],cy:p[1],r:on?5:3,fill:on?(je?'#fbbf24':'#f59e0b'):'#39301f'});
    if (on||an){ node.setAttribute('class','node'); nodes[i]=node;
             node.addEventListener('click',(function(s){return function(){ voice(s); pulse(nodes[s]); };})(i)); }
    g.appendChild(node);
    var t=el('text',{x:lp[0],y:lp[1],'text-anchor':'middle','dominant-baseline':'middle'});
    t.setAttribute('class', je?'jeeva':(on?'on':(an?'anya':''))); t.textContent=LABELS[i]; g.appendChild(t);
  }

  // A spiccato violin note (Freesound #373854 by sgossner, CC0) tuned near Sa and pitch-shifted
  // per swara. Falls back to a formant-synth voice if the sample can't load or Web Audio is absent.
  var SA_HZ = 174.61, SAMPLE_HZ = 261.2, ctx = null, aaBuf = null;
  // Decode the sample eagerly (offline context, no user gesture needed) so it is ready before the
  // first playback. Otherwise "play the scale" schedules its notes before the async decode finishes
  // and every note falls back to the synth voice.
  try { fetch('../swara-violin.mp3').then(function(r){ return r.arrayBuffer(); }).then(function(b){
      var OAC=window.OfflineAudioContext||window.webkitOfflineAudioContext;
      (OAC?new OAC(1,1,44100):audio()).decodeAudioData(b.slice(0)).then(function(buf){ aaBuf=buf; }).catch(function(){});
    }).catch(function(){}); } catch(e){}
  function audio(){
    if(!ctx){ var AC=window.AudioContext||window.webkitAudioContext; ctx=AC?new AC():null; }
    return ctx;
  }
  function voice(semi, when, dur){
    var ac=audio(); if(!ac) return;
    var t0=(when==null?ac.currentTime:when), d=dur||0.62, f0=SA_HZ*Math.pow(2,semi/12);
    if(aaBuf){                                                  // sampled voice, pitch-shifted to f0
      var s=ac.createBufferSource(); s.buffer=aaBuf; s.playbackRate.value=f0/SAMPLE_HZ;
      var g=ac.createGain();
      g.gain.setValueAtTime(0.0001,t0);
      g.gain.exponentialRampToValueAtTime(0.85,t0+0.04);
      g.gain.setValueAtTime(0.85,t0+Math.max(0.06,d-0.16));
      g.gain.exponentialRampToValueAtTime(0.0001,t0+d);
      s.connect(g).connect(ac.destination); s.start(t0); s.stop(t0+d+0.05); return;
    }
    var src=ac.createOscillator(); src.type='sawtooth'; src.frequency.value=f0;   // synth fallback
    var vib=ac.createOscillator(); vib.frequency.value=5.4;
    var vibg=ac.createGain(); vibg.gain.value=f0*0.011; vib.connect(vibg).connect(src.frequency);
    var out=ac.createGain();
    out.gain.setValueAtTime(0.0001,t0);
    out.gain.exponentialRampToValueAtTime(0.5,t0+0.06);
    out.gain.exponentialRampToValueAtTime(0.0001,t0+d);
    [[720,1.0,80],[1150,0.55,90],[2600,0.22,120]].forEach(function(f){
      var bp=ac.createBiquadFilter(); bp.type='bandpass'; bp.frequency.value=f[0]; bp.Q.value=f[0]/f[2];
      var gg=ac.createGain(); gg.gain.value=f[1]; src.connect(bp).connect(gg).connect(out);
    });
    var lp=ac.createBiquadFilter(); lp.type='lowpass'; lp.frequency.value=3200;
    out.connect(lp).connect(ac.destination);
    src.start(t0); src.stop(t0+d+0.05); vib.start(t0); vib.stop(t0+d+0.05);
  }
  function pulse(n){ if(!n) return; var r0=+n.getAttribute('r'); n.setAttribute('r',r0+3); setTimeout(function(){ n.setAttribute('r',r0); },180); }

  var ASC = IN.slice().sort(function(a,b){return a-b;}).concat([12]);
  var SCALE = ASC.concat(ASC.slice(0,-1).reverse());
  var btn=document.getElementById('playScale'), playing=false;
  btn.addEventListener('click',function(){
    var ac=audio(); if(!ac||IN.length<1) return;
    if (ac.state==='suspended') ac.resume();
    if (playing) return; playing=true; btn.setAttribute('aria-pressed','true');
    var step=0.46, t=ac.currentTime+0.05;
    SCALE.forEach(function(semi,k){
      voice(semi, t+k*step, step*0.95);
      var idx=semi%12;
      if (nodes[idx]) setTimeout(function(){ pulse(nodes[idx]); }, (t+k*step-ac.currentTime)*1000);
    });
    setTimeout(function(){ playing=false; btn.setAttribute('aria-pressed','false'); }, (SCALE.length*step+0.2)*1000);
  });
})();
</script>
</body>
</html>
"""


def hear_section(ref: dict, trad: dict = TRAD["carnatic"]) -> str:
    if trad["word"] == "Hindustani":
        rows = [
            ("Vadi / sonant", ref.get("vadi", "")),
            ("Samvadi / consonant", ref.get("samvadi", "")),
            ("Signature phrase / pakad", ref.get("pakad", "")),
            ("Thaat", ref.get("thaat", "")),
            ("Time / samay", ref.get("samay", "")),
        ]
    else:
        rows = [
            ("Life notes / jeeva", ref.get("jeeva_swaras", "")),
            ("Resting notes / nyasa", ref.get("nyasa_swaras", "")),
            ("Signature phrases / prayoga", ref.get("prayogas", "")),
            ("Ornament / gamaka", ref.get("gamakas", "")),
        ]
    rows = [(k, v) for k, v in rows if v]
    if not rows:
        return ""
    dl = "\n".join(
        f"      <div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in rows
    )
    return ('\n  <section class="hear">\n    <h2>How to hear it</h2>\n    <dl>\n'
            + dl + "\n    </dl>\n  </section>")


def confuse_section(ref: dict) -> str:
    its = items(ref.get("confusing_with", ""))
    if not its:
        return ""
    cards = "\n".join(f'      <div class="card">{esc(x)}</div>' for x in its)
    return ('\n  <section>\n    <h2>Easy to confuse with</h2>\n    <div class="cards">\n'
            + cards + "\n    </div>\n  </section>")


def listen_section(ref: dict, known_as: str = "") -> str:
    kritis = items(ref.get("kritis", ""))
    films = items(ref.get("film_songs", ""))
    if not kritis and not films:
        return ""
    lis = "".join(f"      <li>{esc(x)}</li>\n" for x in kritis)
    lis += "".join(f'      <li>{esc(x)} <small style="color:var(--faint);font-family:var(--mono);font-size:.72rem">film</small></li>\n' for x in films)
    # the heading says what people search for: "<raaga> songs", "<raaga> kritis"
    kinds = " and ".join(k for k, have in (("kritis", kritis), ("film songs", films)) if have)
    heading = f"Songs in {known_as}: {kinds}" if known_as else "Listen for it"
    return (f'\n  <section>\n    <h2>{esc(heading)}</h2>\n    <ul class="listen">\n'
            + lis + "    </ul>\n  </section>")


def cousins_section(cousins: list[str]) -> str:
    if not cousins:
        return ""
    cards = "\n".join(
        f'      <a class="card" href="{slug(c)}.html">{esc(c)}</a>' for c in cousins)
    return ('\n  <section>\n    <h2>Modal cousins</h2>\n'
            '    <p style="margin:0 0 12px">The same set of notes heard with a different note as Sa'
            ' (graha bhedam). These raagas share this scale-shape.</p>\n'
            '    <div class="cards">\n' + cards + "\n    </div>\n  </section>")


def search_words(name: str, ref: dict, label: str, hin: bool, aro: str, ava: str):
    """The page's title, description, alternate names and FAQ, in the words people search with: the name without
    diacritics, "raga"/"ragam" (Carnatic) or "raag" (Hindustani), arohanam and avarohanam (aroh and avroh), the parent
    melakarta or thaat, and the songs. Only facts the reference has; a missing one leaves no empty sentence."""
    p = plain(name)
    also = f" ({name})" if p != name else ""
    kritis, films = items(ref.get("kritis", "")), items(ref.get("film_songs", ""))
    songs = " ".join(x for x in (f"Kritis: {'; '.join(kritis)}." if kritis else "",
                                 f"Film songs: {'; '.join(films)}." if films else "") if x)
    faq = []
    if hin:
        thaat, jati, pakad, samay = (ref.get(k, "") for k in ("thaat", "jati", "pakad", "samay"))
        title = f"Raag {p} (Hindustani): aroh, avroh and pakad · twelveswaras"
        head = ", ".join(x for x in (f"{thaat} thaat" if thaat else "", jati) if x) or "a Hindustani raaga"
        desc = " ".join(x for x in (
            f"Raag {p}{also}: {head}.",
            f"Aroh {aro}, avroh {ava}." if aro and ava else "",
            f"Pakad {pakad}." if pakad else "",
            f"Vadi {ref['vadi']}, samvadi {ref['samvadi']}." if ref.get("vadi") and ref.get("samvadi") else "",
            "How to hear it, and raagas it is confused with.") if x)
        names = [p, f"Raag {p}", f"Rag {p}"]
        if aro and ava:
            faq.append((f"What is the aroh and avroh of raag {p}?", f"Aroh: {aro}. Avroh: {ava}."))
        if thaat:
            faq.append((f"Which thaat is raag {p} in?", f"{thaat} thaat."))
        if pakad:
            faq.append((f"What is the pakad of raag {p}?", f"{pakad}."))
        if samay:
            faq.append((f"When is raag {p} sung?", f"{'' if samay.lower().startswith('the ') else 'The '}{samay}."))
    else:
        m = mela(ref.get("parent_mela", ""))
        kriti_names = [re.split(r" [–—-] | \(|, ", k)[0] for k in kritis[:3]]   # the song, not its composer
        title = f"{p} raga: arohanam, avarohanam and songs · twelveswaras"
        kind = f"{article(label)} {label}" if label else "a"
        if m and m[2]:
            head = f"{kind} raaga, melakarta {m[0]}"
        elif m:
            head = f"{kind} janya of melakarta {m[0]}, {m[1]}"
        else:
            head = f"{kind} Carnatic raaga"
        desc = " ".join(x for x in (
            f"{p}{also} raga: {head}.",
            f"Arohanam {aro}, avarohanam {ava}." if aro and ava else "",
            f"Kritis: {', '.join(kriti_names)}." if kritis else "",
            "How to hear it, and raagas it is confused with.") if x)
        names = [p, f"{p} raga", f"{p} ragam"]
        if aro and ava:
            faq.append((f"What is the arohanam and avarohanam of {p}?", f"Arohanam: {aro}. Avarohanam: {ava}."))
        if m and m[2]:
            faq.append((f"Is {p} a melakarta raga?", f"Yes: melakarta {m[0]}."))
        elif m:
            faq.append((f"What is the parent melakarta of {p}?", f"{p} is a janya of melakarta {m[0]}, {m[1]}."))
    if songs:
        faq.append((f"Which songs are in {'raag ' + p if hin else p + ' raga'}?", songs))
    return title, desc, names, faq


def heading(n: int, ref: dict, hin: bool) -> tuple[str, str]:
    """The note-count label ("audava (five-note)") for a raaga using `n` notes, and the eyebrow over
    the name, shared by the page and its share card. More than seven: bhashanga (notes from outside
    the parent)."""
    label = COUNT_LABEL.get(n, "bhashanga" if n > 7 else "")
    if hin:
        thaat = ref.get("thaat", "")
        return label, "Hindustani raaga" + (f" · {thaat.split()[0]} thaat" if thaat else "")
    return label, (label.split()[0].capitalize() + " Carnatic raaga") if label else "Carnatic raaga"


# A swara as the references write it: S, R2, komal r, a dotted lower N. or an upper S'.
_TOK = r"(?:[.][SRGMPDNsrgmpdn]|[SRGMPDNsrgmpdn][1-3]?['’.]?)"
_RUN = re.compile(rf"(?<![A-Za-z]){_TOK}(?:[ ,;]+{_TOK})+(?![A-Za-z0-9])")


def notation(text):
    """The scale's swaras without the notes about it: the references sometimes follow (or lead) the
    notation with sources and variants, which a card has no room for. The first run of three or more
    swaras; the whole text when it is all notation."""
    for m in _RUN.finditer(text):
        run = m.group(0).rstrip(" ,;.")
        if len(run.split()) >= 3:
            return run
    return text.strip()


CORRECTIONS = ROOT / "raaga_corrections.json"


def corrected(ref: dict, fixes: dict) -> dict:
    """The reference with the sourced corrections (raaga_corrections.json) applied; the reference
    itself is not changed."""
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in ref.items()}
    for name, items in fixes.items():
        for f in items:
            out.setdefault(name, {})[f["field"]] = f["now"]
    return out


# Wheel positions of the notes as the scales write them. Carnatic enharmonics (G1 at R2's pitch, R3 at
# G2's, D3 at N2's, N1 at D2's) are lit under their own name; Hindustani uses komal lowercase and
# tivra M.
ENHARMONIC = {"G1": 2, "R3": 3, "D3": 10, "N1": 9}
HINDUSTANI_POS = dict(zip("SrRgGmMPdDnN", range(12)))


def notation_notes(text: str, hin: bool) -> dict[int, str]:
    """{wheel position: the name the scale uses} for every swara in the notation."""
    if hin:
        return {HINDUSTANI_POS[t]: t for t in re.findall(r"[SrRgGmMPdDnN]", text)}
    out = {}
    for t in re.findall(r"[SRGMPDN][123]?", text):
        pos = SEMITONE.get(t, ENHARMONIC.get(t))
        if pos is not None:
            out[pos] = t
    return out


def wheel_notes(swaras: list[str], aro: str, ava: str, trad: dict) -> dict:
    """What the wheel shows. `scale`: the notes of the arohanam/avarohanam, lit and played.
    `anya`: notes the raaga's full note set has (raaga_guide) that the scale lines don't, i.e. the
    notes it uses only in phrases, drawn outlined. `labels`: the tradition's twelve, with a raaga's
    own enharmonic names (Varali's G1, Nata's R3 and D3) where its scale uses them."""
    hin = trad["word"] == "Hindustani"
    named = notation_notes(f"{aro} {ava}", hin)
    full = {SEMITONE[s] for s in swaras if s in SEMITONE}
    scale_pos = sorted(named) if named else sorted(full)
    labels = list(trad["labels"])
    if not hin:
        for pos, name in named.items():
            if name in ENHARMONIC:
                labels[pos] = name
    return {"scale": scale_pos, "anya": sorted(full - set(scale_pos)), "labels": labels}


def scale_fields(ref: dict, hin: bool) -> tuple[str, str]:
    """The reference's scale fields as written: notation, sometimes with research notes around it."""
    return (ref.get("aroha", ""), ref.get("avaroha", "")) if hin else (ref.get("arohana", ""), ref.get("avarohana", ""))


def scale(ref: dict, hin: bool) -> tuple[str, str]:
    """Just the notation, for every place that states the scale (page, description, FAQ, card)."""
    return tuple(notation(f) for f in scale_fields(ref, hin))


def scale_html(field: str) -> str:
    """The scale cell: the notation, and the reference's own note below it when it has one, so the
    variants and sources stay visible (the source is shown, not rewritten)."""
    if not field:
        return '<p class="v pending">pending review</p>'
    shown = notation(field)
    note = f'<p class="note">Variants and sources: {esc(field)}</p>' if shown != field.strip() else ""
    return f'<p class="v">{esc(shown)}</p>{note}'


def card(name: str, swaras: list[str], ref: dict, trad: dict = TRAD["carnatic"]) -> dict:
    """What the raaga's share image shows (rendered by tools/build_og.py)."""
    hin = trad["word"] == "Hindustani"
    aro, ava = scale(ref, hin)
    w = wheel_notes(swaras, aro, ava, trad)
    return {"slug": slug(name, trad["suffix"]), "name": name,
            "eyebrow": heading(len(w["scale"]) + len(w["anya"]), ref, hin)[1],
            "count": len(w["scale"]) + len(w["anya"]),
            "labels": w["labels"], "semis": w["scale"], "anya": w["anya"],
            "aro": aro, "ava": ava,
            "aro_label": "aroh · ascending" if hin else "arohanam · ascending",
            "ava_label": "avroh · descending" if hin else "avarohanam · descending"}


def reference_record(name: str, swaras: list[str], ref: dict, trad: dict = TRAD["carnatic"]) -> dict:
    """One raaga in site/data/raaga-reference.json: what its page states, as data (CC-BY). The MCP
    server answers from this file."""
    hin = trad["word"] == "Hindustani"
    c = card(name, swaras, ref, trad)
    label = heading(c["count"], ref, hin)[0]
    _, _, names, _ = search_words(name, ref, label, hin, c["aro"], c["ava"])
    rec = {
        "name": name, "tradition": trad["word"].lower(), "url": f"https://twelveswaras.com/raaga/{c['slug']}",
        "also_known_as": names, "kind": label,
        "parent": ref.get("thaat" if hin else "parent_mela", ""),
        "arohanam": c["aro"], "avarohanam": c["ava"],
        "notes": {"scale": [c["labels"][i] for i in c["semis"]],
                  "used_in_phrases": [c["labels"][i] for i in c["anya"]]},
        "scale_positions": c["semis"], "phrase_positions": c["anya"],
        "how_to_hear": ref.get("tell", ""),
        "confused_with": ref.get("confusing_with", ""),
    }
    if hin:
        rec.update({"vadi": ref.get("vadi", ""), "samvadi": ref.get("samvadi", ""),
                    "pakad": ref.get("pakad", ""), "time": ref.get("samay", "")})
    else:
        rec.update({"jeeva_swaras": ref.get("jeeva_swaras", ""), "nyasa_swaras": ref.get("nyasa_swaras", ""),
                    "songs": items(ref.get("kritis", "")), "film_songs": items(ref.get("film_songs", ""))})
    return rec


def build_page(name: str, swaras: list[str], ref: dict, cousins: list[str],
               trad: dict = TRAD["carnatic"]) -> str:
    hin = trad["word"] == "Hindustani"
    word = trad["word"]
    # The wheel highlights the "life" and "resting" notes; for Hindustani those are the vadi and
    # samvadi (the raaga's most and second-most important notes), which map cleanly onto the same
    # jeeva/nyasa highlight slots.
    jeeva = parse_positions(ref.get("vadi" if hin else "jeeva_swaras", ""), swaras)
    nyasa = parse_positions(ref.get("samvadi" if hin else "nyasa_swaras", ""), swaras)
    c = card(name, swaras, ref, trad)
    label, eyebrow = heading(c["count"], ref, hin)
    if hin:
        thaat = ref.get("thaat", "")
        thesis = (f"{name} is a raaga in the Hindustani tradition"
                  + (f" ({thaat.split()[0]} thaat)." if thaat else "."))
    else:
        thesis = (f"{name} is a {label} raaga in the Carnatic tradition."
                  if label else f"{name} is a Carnatic raaga (note-set pending expert review).")
    # a verified beginner "tell" becomes the hero line; the structural sentence drops below it
    tell = ref.get("tell", "")
    rasa = ref.get("rasa", "")
    thesis_text = tell or thesis
    mood_html = f'\n    <p class="mood">{esc(rasa)}</p>' if rasa else ""
    struct_html = f'\n    <p class="struct">{esc(thesis)}</p>' if tell else ""

    aro, ava = scale(ref, hin)
    title, desc, names, faq = search_words(name, ref, label, hin, aro, ava)
    known = plain(name)
    if known != name:
        struct_html += f'\n    <p class="struct">Also written {esc(known)}.</p>'
    aro_field, ava_field = scale_fields(ref, hin)
    aro_html, ava_html = scale_html(aro_field), scale_html(ava_field)

    src = ref.get("sources", "")
    sameas = wikipedia_url("; ".join(src) if isinstance(src, list) else src)
    jsonld = {
        "@context": "https://schema.org", "@type": "DefinedTerm", "name": name,
        "inDefinedTermSet": {"@type": "DefinedTermSet", "name": trad["termset"],
                             "url": "https://twelveswaras.com/raaga/"},
        "alternateName": names,
        "description": desc, "url": f"https://twelveswaras.com/raaga/{slug(name, trad['suffix'])}",
        # Machine-readable rights that travel with the data, so an agent reading a single raaga
        # page (not just /data/raagas.json) gets the licence + the exact attribution string.
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "creditText": "twelveswaras (twelveswaras.com), CC-BY-4.0",
        "isAccessibleForFree": True,
        "usageInfo": "https://twelveswaras.com/about/#faq",
    }
    if sameas:
        jsonld["sameAs"] = sameas
    jsonld_html = ('<script type="application/ld+json">\n'
                   + json.dumps(jsonld, ensure_ascii=False, indent=2) + "\n</script>")
    if faq:   # the questions people ask, answered from the reference (AI answers and search features read these)
        faq_ld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        jsonld_html += ('\n<script type="application/ld+json">\n'
                        + json.dumps(faq_ld, ensure_ascii=False, indent=2).replace("</", "<\\/") + "\n</script>")

    page = TEMPLATE
    repl = {
        "__TITLE__": esc(title),
        "__DESC__": esc(desc), "__SLUG__": slug(name, trad["suffix"]), "__JSONLD__": jsonld_html,
        "__TRADWORD__": word, "__LABELS__": json.dumps(c["labels"], ensure_ascii=False, separators=(",", ":")),
        "__LEGEND_JEEVA__": esc(trad["legend_jeeva"]), "__LEGEND_NYASA__": esc(trad["legend_nyasa"]),
        "__CRUMB__": esc(name), "__EYEBROW__": esc(eyebrow), "__NAME__": esc(name),
        "__THESIS__": esc(thesis_text),
        "__MOOD__": mood_html, "__STRUCT__": struct_html,
        "__OGALT__": esc(f"{name}, a {word} raaga: {' '.join(swaras)} on the swara wheel, "
                         "with its ascending and descending scale."),
        "__WHEEL_ALT__": esc(f"Swara wheel for {name}: {' '.join(swaras)}."),
        "__AROHANA__": aro_html, "__AVAROHANA__": ava_html,
        "__HEAR__": hear_section(ref, trad), "__CONFUSE__": confuse_section(ref),
        "__LISTEN__": listen_section(ref, known),
        "__ARO_LABEL__": c["aro_label"], "__AVA_LABEL__": c["ava_label"],
        "__COUSINS__": cousins_section(cousins),
        "__IN__": json.dumps(c["semis"], separators=(",", ":")),
        "__ANYA__": json.dumps(c["anya"], separators=(",", ":")),
        "__ANYA_LEGEND__": ('\n        <span><i class="lg-anya"></i> used in phrases</span>' if c["anya"] else ""),
        "__JEEVA__": json.dumps(jeeva), "__NYASA__": json.dumps(nyasa),
    }
    for k, v in repl.items():
        page = page.replace(k, v)
    return page


# Parent-mēḷa families: allied raagas sit together (janyas of the same melakarta share a scale
# and differ mainly in gamaka). Curated from the research; a few placements are debated (marked).
# The janaka (mēḷa) raaga, when it's in our 40, is the one whose name matches the family.
FAMILIES = [
    (8, "Hanumatōḍi", ["Tōḍi", "Dhanyāsi", "Sindhubhairavi"]),
    (15, "Māyāmāḷavagauḷa", ["Māyāmāḷavagauḷa", "Gauḷa", "Sāvēri"]),
    (20, "Naṭabhairavi", ["Bhairavi"]),
    (22, "Kharaharapriya", ["Karaharapriya", "Hussēnī", "Śrī", "Śrīranjani", "Madhyamāvati",
                            "Kānaḍa", "Kāpi", "Mukhāri", "Rītigauḷa", "Ānandabhairavi"]),
    (28, "Harikāmbhōji", ["Harikāmbhōji", "Mōhanaṁ", "Kāṁbhōji", "Kēdāragauḷa", "Suraṭi",
                          "Sahānā", "Nāṭakurinji", "Sencuruṭṭi", "Kamās", "Yadukula kāṁbōji"]),
    (29, "Śankarābharaṇaṁ", ["Śankarābharaṇaṁ", "Bilahari", "Bēgaḍa", "Dēvagāndhāri", "Aṭāna",
                             "Sāma", "Behāg"]),
    (36, "Chalanāṭa", ["Nāṭa"]),
    (39, "Jhālavarāḷi", ["Varāḷi"]),
    (51, "Kāmavardani", ["Kāmavardani"]),
    (53, "Gamanaśrama", ["Pūrvīkaḷyāṇi"]),
    (56, "Ṣanmukhapriya", ["Ṣanmukhapriya"]),
    (65, "Mēchakalyāṇi", ["Kalyāṇi"]),
]
# parent-mēḷa still genuinely split across sources (Behāg→29 and Sindhubhairavi→8 were resolved;
# Sāma has no clean majority between 28 and 29). See supporting-docs/contested-facts.md.
CONTESTED = {"Sāma"}


def swara_chips(swaras: list[str], labels: list[str] | None = None) -> str:
    if not swaras:
        return '<span class="empty">notes pending review</span>'
    # labels=None keeps the raw position tokens (Carnatic labels == tokens, byte-identical output);
    # Hindustani passes its own label set, mapping each position token to its Hindustani name.
    if labels is None:
        return "".join(f"<span>{esc(s)}</span>" for s in swaras)
    return "".join(f"<span>{esc(labels[SEMITONE[s]])}</span>" for s in swaras if s in SEMITONE)


def build_index(guide: dict, ref: dict, hguide: dict | None = None, href: dict | None = None) -> str:
    from collections import defaultdict
    covered = [nm for _, _, members in FAMILIES for nm in members]
    missing = [k for k in guide if k not in covered]
    extra = [nm for nm in covered if nm not in guide]
    if missing:
        print("  !! index: guide raagas not placed in a family:", missing)
    if extra:
        print("  !! index: family members not in guide:", extra)

    sections = []
    for mela, mela_name, members in FAMILIES:
        cards = []
        for nm in members:
            g = guide.get(nm, {})
            swaras = g.get("swaras") or []
            janaka = (nm == mela_name) or (slug(nm) == slug(mela_name))
            tags = ""
            if janaka:
                tags += '<span class="tag mela">mēḷa</span>'
            if nm in CONTESTED:
                tags += '<span class="tag q" title="parent mēḷa is debated across sources">mēḷa?</span>'
            cards.append(
                f'      <a class="card" href="{slug(nm)}.html">'
                f'<div class="cn"><span class="name">{esc(nm)}</span>{tags}</div>'
                f'<div class="chips">{swara_chips(swaras)}</div></a>')
        sections.append(
            f'  <section class="fam">\n'
            f'    <h2><span class="ml">mēḷa {mela}</span> {esc(mela_name)}'
            f' <span class="ct">{len(members)}</span></h2>\n'
            f'    <div class="grid">\n' + "\n".join(cards) + "\n    </div>\n  </section>")

    # Hindustani, grouped by thaat (the Hindustani analog of the melakarta family view). Cards link
    # to the -hindustani pages; chips render in Hindustani notation. Each h2 self-labels as
    # Hindustani so the two traditions read apart at a glance.
    if hguide:
        hlabels = TRAD["hindustani"]["labels"]
        THAATS = ["Kalyan", "Bilawal", "Khamaj", "Kafi", "Asavari", "Bhairavi", "Bhairav",
                  "Todi", "Purvi", "Marwa"]
        hnames = [k for k in hguide if not k.startswith("_")]
        by_thaat: dict = defaultdict(list)
        for nm in hnames:
            th = ((href or {}).get(nm, {}).get("thaat", "") or "").split()[0] or "Other"
            th = {"Poorvi": "Purvi", "Bilaval": "Bilawal"}.get(th, th)
            by_thaat[th].append(nm)
        for th in THAATS + [t for t in by_thaat if t not in THAATS]:
            members = sorted(by_thaat.get(th, []))
            if not members:
                continue
            cards = [
                f'      <a class="card" href="{slug(nm, "-hindustani")}.html">'
                f'<div class="cn"><span class="name">{esc(nm)}</span></div>'
                f'<div class="chips">{swara_chips(hguide[nm].get("swaras") or [], hlabels)}</div></a>'
                for nm in members]
            sections.append(
                f'  <section class="fam">\n'
                f'    <h2><span class="ml">Hindustani</span> {esc(th)} thaat'
                f' <span class="ct">{len(members)}</span></h2>\n'
                f'    <div class="grid">\n' + "\n".join(cards) + "\n    </div>\n  </section>")

    body = "\n".join(sections)
    return INDEX_TEMPLATE.replace("__SECTIONS__", body)


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>The raagas: 40 Carnatic + 30 Hindustani · twelveswaras</title>
<meta name="description" content="Browse the raagas twelveswaras recognises: 40 Carnatic grouped by parent melakarta and 30 Hindustani (preview) grouped by thaat, so allied raagas sit together. Each has its own page: swaras and how to hear it.">
<link rel="canonical" href="https://twelveswaras.com/raaga/">
<meta name="theme-color" content="#0b0a08">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<meta property="og:title" content="The raagas: 40 Carnatic + 30 Hindustani · twelveswaras">
<meta property="og:description" content="Browse the raagas twelveswaras recognises: 40 Carnatic grouped by melakarta and 30 Hindustani (preview) grouped by thaat.">
<meta property="og:image" content="https://twelveswaras.com/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://twelveswaras.com/og.png">
<link rel="stylesheet" href="/nav.css">
<style>
  :root{
    --ink:#0b0a08; --raise:#16130f; --raise-2:#1c1811; --line:#2a241c; --line-2:#39301f;
    --paper:#f2ece2; --muted:#a89e8e; --faint:#8b8173;
    --amber:#f59e0b; --amber-lo:#d97706; --amber-hi:#fbbf24;
    --jade:#5aa87f; --jade-hi:#74c69d;   /* secondary accent: resting notes, the learning section */
    --sans:"SF Pro Display",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
    --mono:ui-monospace,"SF Mono","JetBrains Mono","Cascadia Code",Menlo,monospace;
  }
  *{box-sizing:border-box}
  html{-webkit-text-size-adjust:100%}
  body{margin:0;background:var(--ink);color:var(--paper);font-family:var(--sans);
    line-height:1.6;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
  a{color:var(--amber-hi);text-decoration:none} a:hover{color:#fff}
  :focus-visible{outline:2px solid var(--amber);outline-offset:3px;border-radius:6px}
  .wrap{width:100%;max-width:860px;margin:0 auto;padding:0 max(22px,env(safe-area-inset-right)) 0 max(22px,env(safe-area-inset-left))}
  header.hero{padding:26px 0 6px}
  .eyebrow{font-family:var(--mono);font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;color:var(--amber);margin:0 0 10px}
  h1{font-size:clamp(1.9rem,7vw,2.8rem);font-weight:800;letter-spacing:-.03em;margin:0;text-wrap:balance}
  .sub{color:var(--muted);max-width:56ch;margin:12px 0 0;font-size:1.02rem;text-wrap:balance}
  .fam{padding:26px 0 8px;border-top:1px solid var(--line);margin-top:26px}
  .fam:first-of-type{border-top:0;margin-top:14px}
  .fam h2{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;
    font-size:clamp(1.15rem,4vw,1.4rem);font-weight:800;letter-spacing:-.02em;margin:0 0 6px}
  .fam h2 .ml{font-family:var(--mono);font-size:.72rem;font-weight:600;letter-spacing:.08em;
    text-transform:uppercase;color:var(--amber);background:var(--raise);border:1px solid var(--line-2);
    border-radius:999px;padding:.3rem .7rem;align-self:center}
  .fam h2 .ct{font-family:var(--mono);font-size:.74rem;font-weight:500;color:var(--faint)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:12px}
  .card{display:block;background:var(--raise);border:1px solid var(--line);border-radius:12px;
    padding:13px 15px;transition:border-color .12s ease,transform .12s ease}
  .card:hover{border-color:var(--amber);transform:translateY(-1px)}
  .card .cn{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .card .name{font-size:1.08rem;font-weight:700;letter-spacing:-.01em;color:var(--paper)}
  .card .tag{font-family:var(--mono);font-size:.68rem;letter-spacing:.06em;text-transform:uppercase;
    border-radius:5px;padding:.1rem .34rem}
  .card .tag.mela{color:var(--amber-hi);border:1px solid var(--line-2)}
  .card .tag.q{color:var(--faint);border:1px dashed var(--line-2)}
  .card .chips{display:flex;gap:4px;flex-wrap:wrap;margin-top:9px}
  .card .chips span{font-family:var(--mono);font-size:.7rem;color:var(--muted);
    border:1px solid var(--line-2);border-radius:5px;padding:.12rem .34rem}
  .card .chips span.empty{color:var(--faint);border-style:dashed}
  .foot{font-family:var(--mono);font-size:.72rem;color:var(--faint);text-align:center;
    border-top:1px solid var(--line);margin-top:34px;padding:22px 0 max(40px,env(safe-area-inset-bottom));line-height:1.7}
  .foot a{color:var(--muted)} .foot a:hover{color:var(--paper)}
</style>
</head>
<body>
<div class="wrap">
  <nav class="top">
    <a class="brand" href="../" aria-label="twelveswaras home">
      <svg viewBox="0 0 256 256" aria-hidden="true">
        <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#fbbf24"/><stop offset="1" stop-color="#b45309"/></linearGradient></defs>
        <rect width="256" height="256" rx="60" fill="url(#g)"/>
        <g fill="#fff">
          <rect x="40" y="140" width="12" height="60" rx="6"/><rect x="60" y="104" width="12" height="96" rx="6"/>
          <rect x="80" y="150" width="12" height="50" rx="6"/><rect x="100" y="76" width="12" height="124" rx="6"/>
          <rect x="120" y="118" width="12" height="82" rx="6"/><rect x="140" y="92" width="12" height="108" rx="6"/>
          <rect x="160" y="60" width="12" height="140" rx="6"/><rect x="180" y="128" width="12" height="72" rx="6"/>
          <rect x="200" y="100" width="12" height="100" rx="6"/></g>
      </svg>
      <span><span class="a">twelve</span><span class="b">swaras</span></span>
    </a>
    <span class="nav">
      <a class="here" href="./" aria-current="page">raagas</a>
      <span class="sep" aria-hidden="true">·</span>
      <a href="../listen/">train your ear</a>
      <span class="sep" aria-hidden="true">·</span>
      <a href="../contribute/">contribute</a>
      <span class="sep" aria-hidden="true">·</span>
      <a href="../about/">about</a>
    </span>
  </nav>
<main>

  <header class="hero">
    <p class="eyebrow">The raagas</p>
    <h1>The raagas: Carnatic and Hindustani</h1>
    <p class="sub">40 Carnatic raagas grouped by parent melakarta, and 30 Hindustani raagas (preview, draft) grouped by thaat, so allied raagas sit side by side. Tap any one for its swaras and how to hear it.</p>
  </header>

__SECTIONS__

  <p class="foot">
    Grouped from our draft reference; a few parent-mēḷa placements (marked mēḷa?) are debated and pending a musician's review. ·
    <a href="../">identify a raaga →</a> · <a href="../listen/">train your ear →</a> · <a href="https://github.com/twelveswaras">github →</a> · <a href="https://github.com/twelveswaras/twelveswaras/blob/main/PDGI.md">a digital commons →</a>
  </p>
</main>
</div>
</body>
</html>
"""


def main() -> None:
    guide = json.loads(GUIDE.read_text())
    fixes = json.loads(CORRECTIONS.read_text())
    ref = corrected(json.loads(REF.read_text()), fixes["carnatic"])
    OUT.mkdir(parents=True, exist_ok=True)

    # resolve each raaga's note-set once, then group by necklace for graha-bhedam (modal cousins)
    resolved = {nm: resolve_swaras(g.get("swaras") or [], ref.get(nm, {})) for nm, g in guide.items()}
    from collections import defaultdict
    # graha bhedam relates scales, so compare the scale's notes, not notes used only in phrases
    scale_pcs = {nm: frozenset(wheel_notes(sw, *scale(ref.get(nm, {}), False), TRAD["carnatic"])["scale"])
                 for nm, sw in resolved.items()}

    def qualifies(nm):
        return len(scale_pcs[nm]) >= 4 and is_symmetric(ref.get(nm, {}))

    groups: dict = defaultdict(list)
    for nm in resolved:
        if qualifies(nm):
            groups[necklace(scale_pcs[nm])].append(nm)
    cousins_of = {}
    for nm in resolved:
        grp = groups.get(necklace(scale_pcs[nm]), []) if qualifies(nm) else []
        cousins_of[nm] = [c for c in grp if c != nm]

    # Hindustani data (also feeds the index below): same template/CSS/wheel, tradition-aware labels
    # + reference fields, written with a -hindustani slug suffix into the same dir (so relative paths
    # match the Carnatic pages). Graha-bhedam (modal cousins) is a Carnatic construct, so empty here.
    htrad = TRAD["hindustani"]
    hguide = json.loads((ROOT / htrad["guide"]).read_text())
    href = corrected(json.loads((ROOT / htrad["ref"]).read_text()), fixes["hindustani"])
    hnames = [k for k in hguide if not k.startswith("_")]

    cards, records = [], []
    n = 0
    for nm, g in guide.items():
        cards.append(card(nm, resolved[nm], ref.get(nm, {})))
        records.append(reference_record(nm, resolved[nm], ref.get(nm, {})))
        page = build_page(nm, resolved[nm], ref.get(nm, {}), cousins_of[nm])
        (OUT / f"{slug(nm)}.html").write_text(page)
        n += 1
    hn = 0
    for nm in hnames:
        cards.append(card(nm, hguide[nm].get("swaras") or [], href.get(nm, {}), htrad))
        records.append(reference_record(nm, hguide[nm].get("swaras") or [], href.get(nm, {}), htrad))
        page = build_page(nm, hguide[nm].get("swaras") or [], href.get(nm, {}), [], trad=htrad)
        (OUT / f"{slug(nm, htrad['suffix'])}.html").write_text(page)
        hn += 1
    (OUT / "index.html").write_text(build_index(guide, ref, hguide, href))

    # sitemap.xml — landing, ear-trainer, raaga index, every raaga (clean URLs, as Pages serves them)
    base = "https://twelveswaras.com"
    urls = [f"{base}/", f"{base}/about/", f"{base}/contribute/", f"{base}/listen/", f"{base}/raaga/"]
    urls += [f"{base}/raaga/{slug(nm)}" for nm in guide]
    urls += [f"{base}/raaga/{slug(nm, htrad['suffix'])}" for nm in hnames]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
               + "</urlset>\n")
    (ROOT / "site" / "sitemap.xml").write_text(sitemap)

    reference = {
        "project": "twelveswaras", "homepage": "https://twelveswaras.com",
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "twelveswaras (twelveswaras.com), CC-BY-4.0",
        "provenance": ("The facts on the twelveswaras raaga pages: scales, parents and note sets checked against "
                       "published sources (corrections and their sources in raaga_corrections.json); not reviewed "
                       "by a musician. Positions count semitones from Sa (0-11)."),
        "count": len(records), "raagas": records,
    }
    (ROOT / "site" / "data" / "raaga-reference.json").write_text(
        json.dumps(reference, ensure_ascii=False, indent=1) + "\n")
    drawn = build_og.write_raaga_cards(cards)
    print(f"share cards: {drawn} drawn, {len(cards) - drawn} unchanged")
    linked = sum(1 for v in cousins_of.values() if v)
    print(f"wrote {n} Carnatic + {hn} Hindustani raaga pages + grouped index to "
          f"{OUT.relative_to(ROOT)}/ ({linked} have graha-bhedam cousins)")


if __name__ == "__main__":
    main()
