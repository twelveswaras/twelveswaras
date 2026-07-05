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

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "raaga_guide.json"
REF = ROOT / "supporting-docs" / "raaga_reference_draft.json"
OUT = ROOT / "site" / "raaga"

SWARA12 = ["S", "R1", "R2", "G2", "G3", "M1", "M2", "P", "D1", "D2", "N2", "N3"]
SEMITONE = {s: i for i, s in enumerate(SWARA12)}
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


def slug(name: str) -> str:
    d = unicodedata.normalize("NFKD", name)
    d = "".join(c for c in d if not unicodedata.combining(c))
    return d.lower().replace("ṁ", "m").replace(" ", "-")


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


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


def pcset(swaras: list[str]) -> frozenset:
    return frozenset(SEMITONE[s] for s in swaras if s in SEMITONE)


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
<meta property="og:title" content="__NAME__: a Carnatic raaga · twelveswaras">
<meta property="og:description" content="__DESC__">
<meta property="og:image" content="https://twelveswaras.com/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="__NAME__: a Carnatic raaga">
<meta name="twitter:image" content="https://twelveswaras.com/og.png">
__JSONLD__
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
  .wrap{width:100%;max-width:780px;margin:0 auto;padding:0 22px}
  .top{display:flex;align-items:center;justify-content:space-between;padding:18px 0 0}
  .brand{display:inline-flex;align-items:center;gap:.5rem;font-weight:800;letter-spacing:-.4px;font-size:1.02rem}
  .brand .a{color:var(--paper)} .brand .b{color:var(--amber)}
  .brand svg{width:26px;height:26px;flex:0 0 auto}
  .top .gh{font-family:var(--mono);font-size:.76rem;letter-spacing:.02em;color:var(--muted)}
  .top .gh:hover{color:var(--paper)}
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
  footer{border-top:1px solid var(--line);padding:30px 0 46px;text-align:center}
  footer .tagline{font-family:var(--mono);font-size:.74rem;letter-spacing:.04em;color:var(--faint);
    max-width:48ch;margin:0 auto;text-wrap:balance}
  footer .links{margin-top:.7rem;font-size:.9rem;display:flex;gap:18px;justify-content:center;flex-wrap:wrap}
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
    <a class="gh" href="./">all raagas</a>
  </nav>
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
        <span><i class="lg-jeeva"></i> jeeva (life note)</span>
        <span><i class="lg-nyasa"></i> nyasa (resting note)</span>
      </div>
      <div class="play">
        <button id="playScale" type="button" aria-pressed="false">▶ play the scale</button>
        <span class="hint">or tap any lit note to hear it</span>
      </div>
    </div>

    <div class="scale">
      <div class="cell"><p class="k">arohana / ascending</p>__AROHANA__</div>
      <div class="cell"><p class="k">avarohana / descending</p>__AVAROHANA__</div>
    </div>
  </header>
__HEAR____CONFUSE____LISTEN____COUSINS__
  <div class="cta-row"><a class="cta" href="../">Identify a raaga →</a></div>
  <p class="draftbar">◐ Draft: the reference facts on this page are compiled from public sources and are pending review by a musician. Corrections welcome via GitHub.</p>
</div>

<footer>
  <div class="wrap">
    <p class="tagline">a non-commercial, open-source public good, Carnatic first, CC-BY data commons</p>
    <div class="links"><a href="../listen/">train your ear</a><a href="https://github.com/twelveswaras">github.com/twelveswaras</a></div>
  </div>
</footer>

<script>
(function () {
  var LABELS = ["S","R1","R2","G2","G3","M1","M2","P","D1","D2","N2","N3"];
  var IN = __IN__, JEEVA = __JEEVA__, NYASA = __NYASA__;
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
    var p=pt(i,rNode), lp=pt(i,rLabel), on=has(IN,i), je=has(JEEVA,i), ny=has(NYASA,i);
    if (ny) g.appendChild(el('circle',{cx:p[0],cy:p[1],r:9,fill:'none',stroke:'#74c69d','stroke-width':2}));
    if (je) g.appendChild(el('circle',{cx:p[0],cy:p[1],r:11,fill:'rgba(251,191,36,.20)'}));
    var node=el('circle',{cx:p[0],cy:p[1],r:on?5:3,fill:on?(je?'#fbbf24':'#f59e0b'):'#39301f'});
    if (on){ node.setAttribute('class','node'); nodes[i]=node;
             node.addEventListener('click',(function(s){return function(){ voice(s); pulse(nodes[s]); };})(i)); }
    g.appendChild(node);
    var t=el('text',{x:lp[0],y:lp[1],'text-anchor':'middle','dominant-baseline':'middle'});
    t.setAttribute('class', je?'jeeva':(on?'on':'')); t.textContent=LABELS[i]; g.appendChild(t);
  }

  // formant-based vocal "aah" synth: a glottal-ish sawtooth through vowel formant filters +
  // vibrato. Warmer than a beep; a real sung rendition with gamaka is future work.
  var SA_HZ = 174.61, ctx = null;                             // Sa ~ F3, a vocal register
  function audio(){ if(!ctx){ var AC=window.AudioContext||window.webkitAudioContext; ctx=AC?new AC():null; } return ctx; }
  function voice(semi, when, dur){
    var ac=audio(); if(!ac) return;
    var t0=(when==null?ac.currentTime:when), d=dur||0.62, f0=SA_HZ*Math.pow(2,semi/12);
    var src=ac.createOscillator(); src.type='sawtooth'; src.frequency.value=f0;
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


def hear_section(ref: dict) -> str:
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


def listen_section(ref: dict) -> str:
    kritis = items(ref.get("kritis", ""))
    films = items(ref.get("film_songs", ""))
    if not kritis and not films:
        return ""
    lis = "".join(f"      <li>{esc(x)}</li>\n" for x in kritis)
    lis += "".join(f'      <li>{esc(x)} <small style="color:var(--faint);font-family:var(--mono);font-size:.72rem">film</small></li>\n' for x in films)
    return ('\n  <section>\n    <h2>Listen for it</h2>\n    <ul class="listen">\n'
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


def build_page(name: str, swaras: list[str], ref: dict, cousins: list[str]) -> str:
    semis = [SEMITONE[s] for s in swaras if s in SEMITONE]
    jeeva = parse_positions(ref.get("jeeva_swaras", ""), swaras)
    nyasa = parse_positions(ref.get("nyasa_swaras", ""), swaras)
    n = len(swaras)
    label = COUNT_LABEL.get(n, "bhashanga" if n > 7 else "")
    eyebrow = (label.split()[0].capitalize() + " Carnatic raaga") if label else "Carnatic raaga"
    thesis = (f"{name} is a {label} raaga in the Carnatic tradition."
              if label else f"{name} is a Carnatic raaga (note-set pending expert review).")
    # a verified beginner "tell" becomes the hero line; the structural sentence drops below it
    tell = ref.get("tell", "")
    rasa = ref.get("rasa", "")
    thesis_text = tell or thesis
    mood_html = f'\n    <p class="mood">{esc(rasa)}</p>' if rasa else ""
    struct_html = f'\n    <p class="struct">{esc(thesis)}</p>' if tell else ""
    desc = (f"{name}: a {label} Carnatic raaga. Its swaras, how to hear it, allied raagas, and "
            f"kritis to listen for." if label
            else f"{name}: a Carnatic raaga. How to hear it, allied raagas, and kritis.")

    aro = ref.get("arohana", "")
    ava = ref.get("avarohana", "")
    aro_html = f'<p class="v">{esc(aro)}</p>' if aro else '<p class="v pending">pending review</p>'
    ava_html = f'<p class="v">{esc(ava)}</p>' if ava else '<p class="v pending">pending review</p>'

    sameas = wikipedia_url(ref.get("sources", ""))
    jsonld = {
        "@context": "https://schema.org", "@type": "DefinedTerm", "name": name,
        "inDefinedTermSet": {"@type": "DefinedTermSet", "name": "Carnatic raagas",
                             "url": "https://twelveswaras.com/raaga/"},
        "description": desc, "url": f"https://twelveswaras.com/raaga/{slug(name)}",
    }
    if sameas:
        jsonld["sameAs"] = sameas
    jsonld_html = ('<script type="application/ld+json">\n'
                   + json.dumps(jsonld, ensure_ascii=False, indent=2) + "\n</script>")

    page = TEMPLATE
    repl = {
        "__TITLE__": f"{name}: a Carnatic raaga, and how to hear it · twelveswaras",
        "__DESC__": desc, "__SLUG__": slug(name), "__JSONLD__": jsonld_html,
        "__CRUMB__": esc(name), "__EYEBROW__": esc(eyebrow), "__NAME__": esc(name),
        "__THESIS__": esc(thesis_text),
        "__MOOD__": mood_html, "__STRUCT__": struct_html,
        "__WHEEL_ALT__": esc(f"Swara wheel for {name}: {' '.join(swaras)}."),
        "__AROHANA__": aro_html, "__AVAROHANA__": ava_html,
        "__HEAR__": hear_section(ref), "__CONFUSE__": confuse_section(ref),
        "__LISTEN__": listen_section(ref), "__COUSINS__": cousins_section(cousins),
        "__IN__": json.dumps(semis), "__JEEVA__": json.dumps(jeeva), "__NYASA__": json.dumps(nyasa),
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


def swara_chips(swaras: list[str]) -> str:
    if not swaras:
        return '<span class="empty">notes pending review</span>'
    return "".join(f"<span>{esc(s)}</span>" for s in swaras)


def build_index(guide: dict, ref: dict) -> str:
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

    body = "\n".join(sections)
    return INDEX_TEMPLATE.replace("__SECTIONS__", body)


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>The raagas: all 40, by mēḷa family · twelveswaras</title>
<meta name="description" content="Browse the 40 Carnatic raagas twelveswaras recognises, grouped by parent melakarta so allied raagas sit together. Each has a page: swaras, how to hear it, and kritis.">
<link rel="canonical" href="https://twelveswaras.com/raaga/">
<meta name="theme-color" content="#0b0a08">
<link rel="icon" href="../favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="../apple-touch-icon.png">
<meta property="og:title" content="The raagas: all 40, by mēḷa family · twelveswaras">
<meta property="og:description" content="Browse the 40 Carnatic raagas twelveswaras recognises, grouped by parent melakarta.">
<meta property="og:image" content="https://twelveswaras.com/og.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://twelveswaras.com/og.png">
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
  .wrap{width:100%;max-width:860px;margin:0 auto;padding:0 22px}
  .top{display:flex;align-items:center;justify-content:space-between;padding:18px 0 0}
  .brand{display:inline-flex;align-items:center;gap:.5rem;font-weight:800;letter-spacing:-.4px;font-size:1.02rem}
  .brand .a{color:var(--paper)} .brand .b{color:var(--amber)}
  .brand svg{width:26px;height:26px;flex:0 0 auto}
  .top .gh{font-family:var(--mono);font-size:.76rem;color:var(--muted)}
  .top .gh:hover{color:var(--paper)}
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
    border-top:1px solid var(--line);margin-top:34px;padding:22px 0 40px;line-height:1.7}
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
    <a class="gh" href="../listen/">train your ear ↗</a>
  </nav>

  <header class="hero">
    <p class="eyebrow">The raagas</p>
    <h1>All 40, by mēḷa family</h1>
    <p class="sub">Grouped by parent melakarta, so the allied raagas you'd most likely confuse sit side by side. Tap any one to see its swaras, how to hear it, and kritis to listen for.</p>
  </header>

__SECTIONS__

  <p class="foot">
    Grouped from our draft reference; a few parent-mēḷa placements (marked mēḷa?) are debated and pending a musician's review. ·
    <a href="../">identify a raaga →</a> · <a href="../listen/">train your ear →</a>
  </p>
</div>
</body>
</html>
"""


def main() -> None:
    guide = json.loads(GUIDE.read_text())
    ref = json.loads(REF.read_text())
    OUT.mkdir(parents=True, exist_ok=True)

    # resolve each raaga's note-set once, then group by necklace for graha-bhedam (modal cousins)
    resolved = {nm: resolve_swaras(g.get("swaras") or [], ref.get(nm, {})) for nm, g in guide.items()}
    from collections import defaultdict
    def qualifies(nm, sw):
        return len(pcset(sw)) >= 4 and is_symmetric(ref.get(nm, {}))

    groups: dict = defaultdict(list)
    for nm, sw in resolved.items():
        if qualifies(nm, sw):
            groups[necklace(pcset(sw))].append(nm)
    cousins_of = {}
    for nm, sw in resolved.items():
        grp = groups.get(necklace(pcset(sw)), []) if qualifies(nm, sw) else []
        cousins_of[nm] = [c for c in grp if c != nm]

    n = 0
    for nm, g in guide.items():
        page = build_page(nm, resolved[nm], ref.get(nm, {}), cousins_of[nm])
        (OUT / f"{slug(nm)}.html").write_text(page)
        n += 1
    (OUT / "index.html").write_text(build_index(guide, ref))

    # sitemap.xml — landing, ear-trainer, raaga index, every raaga (clean URLs, as Pages serves them)
    base = "https://twelveswaras.com"
    urls = [f"{base}/", f"{base}/listen", f"{base}/raaga/"]
    urls += [f"{base}/raaga/{slug(nm)}" for nm in guide]
    sitemap = ('<?xml version="1.0" encoding="UTF-8"?>\n'
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
               + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls)
               + "</urlset>\n")
    (ROOT / "site" / "sitemap.xml").write_text(sitemap)

    linked = sum(1 for v in cousins_of.values() if v)
    print(f"wrote {n} raaga pages + grouped index to {OUT.relative_to(ROOT)}/ "
          f"({linked} have graha-bhedam cousins)")


if __name__ == "__main__":
    main()
