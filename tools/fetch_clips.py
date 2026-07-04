"""Download real-world benchmark clips from a link list and build clips.csv.

    # 1) put your links in benchmark/realworld/links.csv (see links.example.csv)
    # 2) python -m tools.fetch_clips       # downloads audio + writes clips.csv
    # 3) python -m tools.realworld_eval    # scores them through the production pipeline

Downloads AUDIO ONLY, a mid-performance section (skips the typical intro / tuning / announcement),
into the gitignored benchmark/realworld/audio/. This is private-eval measurement, per
benchmark/realworld/README.md: measure accuracy, do not redistribute. Needs yt-dlp + ffmpeg
(`pip install yt-dlp`; ffmpeg via brew/apt). A row's `start` (or a &t= in the url) overrides the
default offset; the pipeline analyses ~90 s, so we grab a bit more for margin.
"""
from __future__ import annotations

import csv
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
RW = ROOT / "benchmark" / "realworld"
AUDIO = RW / "audio"
LINKS = RW / "links.csv"
CLIPS = RW / "clips.csv"
DEFAULT_START = 30       # skip typical intros / tuning
DEFAULT_DUR = 150        # > 90 s so the pipeline's first-90s analysis lands squarely on music
FIELDS = ["file", "raga", "source", "license", "drone", "instrument", "notes"]


def slug(s: str) -> str:
    d = unicodedata.normalize("NFKD", s or "")
    d = "".join(c for c in d if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", d.lower().replace("ṁ", "m")).strip("-") or "clip"


def start_from_url(url: str, fallback: int) -> int:
    try:
        t = parse_qs(urlparse(url).query).get("t", [None])[0]
        if t:
            return int(re.sub(r"[^0-9]", "", t) or fallback)
    except Exception:  # noqa: BLE001
        pass
    return fallback


def _int(v, default):
    v = (v or "").strip()
    return int(v) if v.isdigit() else default


def main() -> None:
    if not LINKS.exists():
        raise SystemExit(f"no {LINKS.relative_to(ROOT)} — copy links.example.csv to links.csv and add rows.")
    AUDIO.mkdir(parents=True, exist_ok=True)
    rows = [r for r in csv.DictReader(open(LINKS, encoding="utf-8"))
            if (r.get("url") or "").strip()
            and not (r.get("raga") or "").lstrip().startswith("#")
            and not (r.get("url") or "").lstrip().startswith("#")]

    out, failed = [], []
    for i, r in enumerate(rows, 1):
        raga, url = (r.get("raga") or "").strip(), (r.get("url") or "").strip()
        start = _int(r.get("start"), start_from_url(url, DEFAULT_START))
        end = start + _int(r.get("dur"), DEFAULT_DUR)
        name = f"{i:02d}_{slug(raga)}"
        target = AUDIO / f"{name}.m4a"

        if target.exists():
            print(f"  [{i:02d}] {raga:18s} cached  {target.name}", flush=True)
        else:
            print(f"  [{i:02d}] {raga:18s} download {url}  ({start}-{end}s)", flush=True)
            cmd = [sys.executable, "-m", "yt_dlp", "-q", "--no-playlist", "-x", "--audio-format", "m4a",
                   "--download-sections", f"*{start}-{end}", "-o", str(AUDIO / f"{name}.%(ext)s"), url]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not target.exists():
                msg = (res.stderr or res.stdout or "unknown error").strip().splitlines()
                print(f"       !! failed: {msg[-1] if msg else 'unknown'}", flush=True)
                failed.append((raga, url))
                continue

        out.append({"file": target.name, "raga": raga, "source": url, "license": "private-eval",
                    "drone": (r.get("drone") or "").strip(), "instrument": (r.get("instrument") or "").strip(),
                    "notes": (r.get("notes") or "").strip()})

    if out:
        with open(CLIPS, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(out)
        print(f"\nwrote {CLIPS.relative_to(ROOT)} ({len(out)} clips)"
              f"{f', {len(failed)} failed' if failed else ''}. Now run:  python -m tools.realworld_eval")
    else:
        raise SystemExit("no clips downloaded — check the links and that yt-dlp works.")


if __name__ == "__main__":
    main()
