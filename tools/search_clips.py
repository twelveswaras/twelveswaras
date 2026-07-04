"""Auto-fill links.csv by searching YouTube for each raaga's suggested kriti (yt-dlp ytsearch).

    python -m tools.search_clips        # fill empty-url rows in benchmark/realworld/links.csv

For every row with a blank url, searches YouTube for "<kriti hint> <raaga> carnatic", picks the
top plausible rendition (>= 3 min, skipping lessons/notation/karaoke), and fills the url. Writes
the found video's TITLE + duration into notes so you can sanity-check before downloading, and
detects the instrument from the title where it can. Private-eval only (measure, don't redistribute).
Needs yt-dlp. Re-runnable: rows that already have a url are left alone.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

LINKS = Path(__file__).resolve().parent.parent / "benchmark" / "realworld" / "links.csv"
FIELDS = ["raga", "url", "drone", "instrument", "start", "notes"]
BAD = re.compile(r"lesson|tutorial|notation|how to|learn|class\b|lyrics|karaoke|sruti|shruti box", re.I)
INSTR = {"veena": "veena", "vina": "veena", "violin": "violin", "flute": "flute", "venu": "flute",
         "nadaswaram": "nadaswaram", "nagaswaram": "nadaswaram", "mandolin": "mandolin",
         "saxophone": "saxophone", "instrumental": "instrumental"}


def ascii_(s: str) -> str:
    d = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in d if not unicodedata.combining(c)).replace("ṁ", "m")


def search(query: str, n: int = 6):
    cmd = [sys.executable, "-m", "yt_dlp", f"ytsearch{n}:{query}", "--flat-playlist",
           "--no-warnings", "--print", "%(id)s\t%(duration)s\t%(title)s"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        return []
    cands = []
    for line in res.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            try:
                dur = int(float(parts[1]))
            except (ValueError, TypeError):
                dur = 0
            cands.append((parts[0], dur, "\t".join(parts[2:])))
    return cands


def pick(cands):
    good = [c for c in cands if c[1] >= 180 and not BAD.search(c[2])]
    if good:
        return good[0]
    ok = [c for c in cands if c[1] >= 180]
    return ok[0] if ok else (cands[0] if cands else None)


def main() -> None:
    rows = list(csv.DictReader(open(LINKS, encoding="utf-8")))
    filled = 0
    for r in rows:
        raga = (r.get("raga") or "").strip()
        if not raga or raga.startswith("#") or (r.get("url") or "").strip():
            continue
        inst_pref = (r.get("instrument") or "").strip().lower()
        if inst_pref:                                   # instrumental row: search the raaga on that instrument
            query = f"{ascii_(raga)} {inst_pref} carnatic".strip()
        else:                                           # vocal row: search the suggested kriti
            hint = re.sub(r"^try:\s*", "", (r.get("notes") or "")).split(",")[0].strip()
            query = f"{ascii_(hint)} {ascii_(raga)} carnatic".strip()
        chosen = pick(search(query))
        if not chosen:
            print(f"  {raga:18s} NO RESULT  ({query})", flush=True)
            continue
        vid, dur, title = chosen
        r["url"] = f"https://youtu.be/{vid}"
        r["notes"] = f"{title}  ({dur // 60}:{dur % 60:02d})"
        detected = next((v for k, v in INSTR.items() if k in title.lower()), "")
        r["instrument"] = inst_pref or detected or "vocal"
        filled += 1
        print(f"  {raga:18s} -> {title[:58]}  ({dur // 60}:{dur % 60:02d})"
              f"{'  ['+r['instrument']+']' if r['instrument'] else ''}", flush=True)

    with open(LINKS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"\nfilled {filled} rows in {LINKS.name}. Review the titles, then:"
          f"\n  python -m tools.fetch_clips && python -m tools.realworld_eval", flush=True)


if __name__ == "__main__":
    main()
