"""Bulk-import a licensed folder of recordings into the PRIVATE commons (Shaale; D9, §12).

    python -m pipeline.import_shaale scan   data/shaale                       # emit a manifest to fill
    python -m pipeline.import_shaale import data/shaale -m data/shaale/manifest.csv            # dry run
    python -m pipeline.import_shaale import data/shaale -m data/shaale/manifest.csv --apply --verified

Skanda (Shaale) shared student recordings for training but did not want to upload them one by
one through the web form. Shaale owns the rights and grants TRAIN-ONLY use with attribution to
"Shaale": the model may learn from them, the audio is NEVER published, and they are NOT part of
the public CC-BY dataset. This tool writes each clip into the SAME private store the web form
uses (audio -> R2, one D1 `contributions` row) so they flow through the existing
verify -> pull_commons -> train path, but with the correct rights baked in:

    is_own=1, release_public=0, license='Shaale-train-only', credit='Shaale', label_source='expert'.

RIGHTS NOTE: because these are licensed train-only, any future public-audio or clean-CC-BY-model
export MUST exclude license='Shaale-train-only'. release_public=0 already keeps them out of the
public dataset; the licence tag is belt-and-braces.

Labels: `scan` walks the folder and writes a manifest.csv skeleton (one row per audio file, the
raaga/tradition columns blank) for a human to fill; `import` reads that manifest. Idempotent: a
clip already present (by audio_sha256) is skipped, so re-running only adds what is new. Dry-run
by default; --apply uploads to R2 and inserts the rows. A row lands verified only with --verified
(trusting Shaale as the label source); without it the rows are 'unverified' and pull_commons will
hold them until they are verified.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import tempfile
from datetime import date as _date
from pathlib import Path

# Reuse the Cloudflare plumbing (token from .env, wrangler runner), so this stays a thin, honest
# mirror of what the worker's /contribute insert already does (raw raaga label in; pull_commons
# canonicalises downstream, identically for form and imported rows).
from pipeline.pull_commons import D1_DATABASE, R2_BUCKET, _wrangler
from raaga_id.config import DATA_DIR

# Fixed rights for every Shaale clip (see module docstring). These are the ONLY values that
# differ from a web-form contribution, and they are what keep the audio private + attributed.
LICENSE = "Shaale-train-only"
CREDIT = "Shaale"
CONSENT_VERSION = "shaale-2026-09-12"
LABEL_SOURCE = "expert"                       # teacher-provided label, not a model/contributor guess

DEFAULT_DIR = DATA_DIR / "shaale"             # gitignored (under data/), where the folder is downloaded

AUDIO_EXTS = {".wav", ".wave", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".webm", ".aif", ".aiff"}
_MIME = {
    ".wav": "audio/wav", ".wave": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
    ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".opus": "audio/opus",
    ".webm": "audio/webm", ".aif": "audio/aiff", ".aiff": "audio/aiff",
}
MANIFEST_FIELDS = ["file", "raaga", "tradition", "instrument"]

# The contributions columns this tool writes, in a fixed order. Matches the worker's insert
# except license/release_public/credit/label_source, which carry the Shaale train-only rights.
INSERT_COLUMNS = [
    "ts", "r2_key", "audio_sha256", "raaga", "tradition", "label_source", "instrument",
    "is_own", "license", "release_public", "consent_version", "credit", "verification_status", "split",
]


# ---- pure logic (unit-tested; no R2 / D1 / filesystem) --------------------------

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ext_of(name) -> str:
    """Lower-cased file extension including the dot ('.mp3'), '' if none."""
    return Path(str(name)).suffix.lower()


def is_audio(name) -> bool:
    return ext_of(name) in AUDIO_EXTS


def mime_for(ext: str) -> str:
    return _MIME.get(ext.lower(), "application/octet-stream")


def r2_key(sha: str, ext: str, day: str) -> str:
    """The private R2 key, shaped exactly like the worker's: contrib/<date>/<sha20><ext>."""
    return f"contrib/{day}/{sha[:20]}{ext}"


def _clean(s, cap: int) -> str:
    return (str(s) if s is not None else "").strip()[:cap]


def sql_lit(v) -> str:
    """A SQL literal for the D1 --file path: NULL, a bare number, or a single-quote-escaped string."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def record(entry: dict, sha: str, ext: str, day: str, ts: str, *, verified: bool) -> dict:
    """The full `contributions` row for one clip: the raaga label as given + the Shaale rights.

    The raaga is stored as provided (cleaned), exactly like a web-form contribution; pull_commons
    canonicalises + folds it at pull time, so form and imported rows are treated identically."""
    return {
        "ts": ts,
        "r2_key": r2_key(sha, ext, day),
        "audio_sha256": sha,
        "raaga": _clean(entry.get("raaga"), 80),
        "tradition": _clean(entry.get("tradition"), 20).lower(),
        "label_source": LABEL_SOURCE,
        "instrument": _clean(entry.get("instrument"), 40) or None,
        "is_own": 1,
        "license": LICENSE,
        "release_public": 0,
        "consent_version": CONSENT_VERSION,
        "credit": CREDIT,
        "verification_status": "verified" if verified else "unverified",
        "split": "pending",
    }


def insert_sql(row: dict) -> str:
    cols = ", ".join(INSERT_COLUMNS)
    vals = ", ".join(sql_lit(row[c]) for c in INSERT_COLUMNS)
    return f"INSERT INTO contributions ({cols}) VALUES ({vals});"


def classify_entry(entry: dict, sha: str, existing: set[str]) -> tuple[str, str]:
    """(action, reason): 'import' or 'skip'. Pure — the file read (sha) happens in the runner."""
    if not _clean(entry.get("raaga"), 80):
        return "skip", "no raaga label"
    if _clean(entry.get("tradition"), 20).lower() not in ("carnatic", "hindustani"):
        return "skip", "no/invalid tradition (need carnatic|hindustani)"
    if sha in existing:
        return "skip", "already imported (duplicate audio_sha256)"
    return "import", "ok"


def parse_manifest(path: Path) -> list[dict]:
    """Read the label manifest (CSV with a header: file,raaga,tradition,instrument)."""
    with Path(path).open(newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def scan_rows(folder: Path) -> list[dict]:
    """A manifest skeleton for every audio file under `folder` (raaga/tradition blank to fill)."""
    folder = Path(folder)
    rows = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and is_audio(p.name):
            rows.append({"file": str(p.relative_to(folder)), "raaga": "", "tradition": "", "instrument": ""})
    return rows


def write_manifest(path: Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in MANIFEST_FIELDS})


# ---- side effects (D1 read + write, R2 upload; smoke-tested, not unit-tested) ----

def existing_shas() -> set[str]:
    """Every audio_sha256 already in the commons — the cross-run dedup key."""
    import json
    cp = _wrangler(["d1", "execute", D1_DATABASE, "--remote", "--json",
                    "--command", "SELECT audio_sha256 FROM contributions WHERE audio_sha256 IS NOT NULL"])
    if cp.returncode != 0:
        raise SystemExit(f"D1 query failed:\n{cp.stderr or cp.stdout}")
    payload = json.loads(cp.stdout)
    return {r["audio_sha256"] for r in (payload[0]["results"] if payload else []) if r.get("audio_sha256")}


def r2_upload(key: str, path: Path, mime: str) -> None:
    cp = _wrangler(["r2", "object", "put", f"{R2_BUCKET}/{key}",
                    "--file", str(path), "--content-type", mime, "--remote"])
    if cp.returncode != 0:
        raise SystemExit(f"R2 upload failed for {path}:\n{cp.stderr or cp.stdout}")


def d1_apply(sql_text: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False, encoding="utf-8") as fh:
        fh.write(sql_text)
        sql_path = fh.name
    cp = _wrangler(["d1", "execute", D1_DATABASE, "--remote", "--file", sql_path])
    Path(sql_path).unlink(missing_ok=True)
    if cp.returncode != 0:
        raise SystemExit(f"D1 insert failed:\n{cp.stderr or cp.stdout}")


def _plan(folder: Path, entries: list[dict], existing: set[str], *, verified: bool):
    """Read each file, sha it, and classify. Returns (rows_to_insert, uploads, report)."""
    day = _date.today().isoformat()
    seen: set[str] = set()
    rows, uploads, report = [], [], []
    for e in entries:
        rel = _clean(e.get("file"), 500)
        src = folder / rel
        if not rel or not src.exists():
            report.append((rel or "?", "skip", "file not found"))
            continue
        sha = sha256_hex(src.read_bytes())
        action, reason = classify_entry(e, sha, existing | seen)
        report.append((rel, action, reason))
        if action == "import":
            seen.add(sha)
            ext = ext_of(src.name)
            row = record(e, sha, ext, day, day + "T00:00:00Z", verified=verified)
            rows.append(row)
            uploads.append((row["r2_key"], src, mime_for(ext)))
    return rows, uploads, report


def main() -> None:
    ap = argparse.ArgumentParser(description="Bulk-import a Shaale-licensed (train-only) folder into the commons.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("scan", help="write a manifest.csv skeleton (one row per audio file) to fill in")
    sc.add_argument("folder", nargs="?", default=str(DEFAULT_DIR))
    sc.add_argument("-o", "--out", default=None, help="manifest path (default: <folder>/manifest.csv)")

    im = sub.add_parser("import", help="import the folder using a filled-in manifest")
    im.add_argument("folder", nargs="?", default=str(DEFAULT_DIR))
    im.add_argument("-m", "--manifest", default=None, help="manifest CSV (default: <folder>/manifest.csv)")
    im.add_argument("--apply", action="store_true", help="upload to R2 + insert rows (default: dry-run)")
    im.add_argument("--verified", action="store_true",
                    help="mark rows verified (trust Shaale as the label source); else they wait in the queue")
    args = ap.parse_args()

    folder = Path(args.folder)

    if args.cmd == "scan":
        rows = scan_rows(folder)
        out = Path(args.out) if args.out else folder / "manifest.csv"
        write_manifest(out, rows)
        print(f"{len(rows)} audio file(s) -> {out}\n"
              f"fill in the raaga (and tradition: carnatic|hindustani) columns, then:\n"
              f"  python -m pipeline.import_shaale import {folder} -m {out}")
        return

    manifest = Path(args.manifest) if args.manifest else folder / "manifest.csv"
    if not manifest.exists():
        raise SystemExit(f"no manifest at {manifest} — run `scan` first, then fill it in.")
    entries = parse_manifest(manifest)
    existing = existing_shas()
    rows, uploads, report = _plan(folder, entries, existing, verified=args.verified)

    n_import = sum(1 for _, a, _ in report if a == "import")
    n_skip = len(report) - n_import
    print(f"{len(report)} file(s): {n_import} to import, {n_skip} skipped "
          f"(verification={'verified' if args.verified else 'unverified'})\n")
    for rel, action, reason in report:
        print(f"  {action:7} {rel:40} {reason}")
    print()

    if not args.apply:
        print("dry run — pass --apply to upload the audio to R2 and insert the rows.")
        if not args.verified:
            print("note: without --verified these land 'unverified' and pull_commons will hold them.")
        return

    for key, src, mime in uploads:
        r2_upload(key, src, mime)
    if rows:
        d1_apply("\n".join(insert_sql(r) for r in rows) + "\n")
    print(f"imported {len(rows)} clip(s): audio -> R2 ({R2_BUCKET}, private), rows -> D1 "
          f"(license={LICENSE}, credit={CREDIT})\n"
          f"next: python -m pipeline.pull_commons   (then --apply to pull the trainable ones)")


if __name__ == "__main__":
    main()
