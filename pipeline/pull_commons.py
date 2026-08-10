"""Pull verified commons contributions into a local training-ready corpus (PRD §13/§14).

    python -m pipeline.pull_commons              # dry run: classify + report, download nothing
    python -m pipeline.pull_commons --apply      # download eligible clips + write the manifest

This is the step that stops the contribution pile being inert. It reads contributions out
of the D1 commons (read-only — never writes to prod), classifies each into exactly one
bucket, and for the trainable ones downloads the audio from R2 into data/commons/ and
appends a line to data/commons/manifest.jsonl. `raaga_id.data.iter_commons_clips` reads
that manifest, so `python -m raaga_id.train --datasets saraga_carnatic commons` folds the
contributions into the next model.

Three buckets (a contribution lands in exactly one):
  * TRAIN        rights-attested + in the model's vocabulary + a TRUSTWORTHY label
                 (verification_status == 'verified', OR label_source == 'model_confirmed',
                 which is self-verifying: the model already agreed with the contributor).
  * VOCAB_GROWTH rights-attested but the raaga is NOT one of the model's classes. This is a
                 new-raaga request, not a training row: it can't augment a class that does
                 not exist. Held (never trained, never dropped) so it accumulates toward a
                 future class — a raaga needs enough clips before it can BE a class.
  * SKIP         not yet usable: rights not attested, in-vocab but unverified, disputed,
                 no audio, or already pulled (dedup by audio_sha256).

The manifest is the dedup ledger: re-running is idempotent and pulls only what's new.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from raaga_id.config import DATA_DIR, MODELS_DIR, canonical_raaga, fold_raaga, load_raagas

TRAIN = "train"
VOCAB_GROWTH = "vocab_growth"
SKIP = "skip"

COMMONS_DIR = DATA_DIR / "commons"
AUDIO_DIR = COMMONS_DIR / "audio"
MANIFEST = COMMONS_DIR / "manifest.jsonl"
VOCAB_GROWTH_LOG = COMMONS_DIR / "vocab_growth.jsonl"

DUAL_CLASSES = MODELS_DIR / "raaga_xgb.dual.classes.json"
D1_DATABASE = "twelveswaras"
R2_BUCKET = "twelveswaras-clips"

# The columns the corpus needs — an explicit safe projection, never SELECT * (the row also
# holds contributor-adjacent fields that have no business in a training manifest).
_COLUMNS = (
    "id, ts, r2_key, audio_sha256, raaga, tradition, label_source, model_pred, confidence, "
    "tonic_hz, instrument, is_own, license, release_public, verification_status, "
    "votes_agree, votes_disagree, split"
)


# ---- pure logic (unit-tested; no D1 / R2 / essentia) ----------------------------

def load_dual_classes(path: Path = DUAL_CLASSES) -> set[str]:
    """The model's tradition-tagged class labels, e.g. 'Tōḍi (Carnatic)'."""
    return set(json.loads(Path(path).read_text()))


def tagged(raaga: str, tradition: str, vocab: dict | None = None) -> str:
    """Canonical, tradition-tagged label matching the model's class naming."""
    canon = canonical_raaga(raaga, vocab or load_raagas())
    return f"{canon} ({tradition.strip().capitalize()})"


def in_vocab(raaga: str, tradition: str, dual_classes: set[str], vocab: dict | None = None) -> bool:
    """True iff (raaga, tradition) is one of the model's classes, matched diacritic- and
    case-insensitively but tradition-EXACT (the two Tōḍis are different classes)."""
    key = fold_raaga(canonical_raaga(raaga, vocab or load_raagas()))
    trad = tradition.strip().lower()
    for cls in dual_classes:
        name, _, tag = cls.partition(" (")
        if fold_raaga(name) == key and tag.rstrip(")").strip().lower() == trad:
            return True
    return False


def audio_ext(r2_key: str) -> str:
    """File extension carried from the R2 key ('.webm', '.mp3', ...); '' if none."""
    return Path(r2_key or "").suffix


def classify(row: dict, dual_classes: set[str], pulled: set[str],
             vocab: dict | None = None) -> tuple[str, str]:
    """Sort one contribution into (bucket, human-readable reason)."""
    vocab = vocab or load_raagas()
    sha = (row.get("audio_sha256") or "").strip()
    if not row.get("r2_key"):
        return SKIP, "no audio (missing r2_key)"
    if sha and sha in pulled:
        return SKIP, "already pulled"
    if int(row.get("is_own") or 0) != 1:
        return SKIP, "rights not attested (is_own != 1)"
    trad = (row.get("tradition") or "").strip().lower()
    if trad not in ("carnatic", "hindustani"):
        return SKIP, "no tradition"
    if not (row.get("raaga") or "").strip():
        return SKIP, "no raaga label"
    if not in_vocab(row["raaga"], trad, dual_classes, vocab):
        return VOCAB_GROWTH, f"out-of-vocab ({tagged(row['raaga'], trad, vocab)})"
    if row.get("verification_status") == "disputed":
        return SKIP, "disputed (in the expert queue)"
    if row.get("verification_status") == "verified" or row.get("label_source") == "model_confirmed":
        return TRAIN, "eligible"
    return SKIP, "unverified (needs verification votes or a model-confirmed label)"


def manifest_entry(row: dict, vocab: dict | None = None) -> dict:
    """The training-ready record for one pulled clip: canonical label + provenance."""
    vocab = vocab or load_raagas()
    sha = (row.get("audio_sha256") or "").strip()
    stem = sha or str(row.get("id"))
    return {
        "id": row.get("id"),
        "raaga": canonical_raaga(row["raaga"], vocab),
        "tradition": (row.get("tradition") or "").strip().lower(),
        "audio_sha256": sha,
        "r2_key": row.get("r2_key"),
        "audio_path": f"audio/{stem}{audio_ext(row.get('r2_key'))}",
        "tonic_hz": row.get("tonic_hz"),
        "instrument": row.get("instrument"),
        "license": row.get("license"),
        "release_public": row.get("release_public"),
        "label_source": row.get("label_source"),
        "verification_status": row.get("verification_status"),
        "source": "commons",
    }


def load_manifest(path: Path = MANIFEST) -> list[dict]:
    """Parse the JSONL manifest (empty list if it doesn't exist yet)."""
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append_manifest(path: Path, entry: dict) -> None:
    """Append one entry as a JSONL line, creating the file/dir if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def pulled_shas(manifest_rows: list[dict]) -> set[str]:
    """The audio_sha256 of every already-pulled clip (the dedup key)."""
    return {r["audio_sha256"] for r in manifest_rows if r.get("audio_sha256")}


def summarize(classified: list[tuple[dict, str, str]]) -> dict:
    """Per-bucket counts for the run report."""
    counts = {TRAIN: 0, VOCAB_GROWTH: 0, SKIP: 0}
    for _, bucket, _ in classified:
        counts[bucket] = counts.get(bucket, 0) + 1
    counts["total"] = len(classified)
    return counts


# ---- side effects (D1 read-only, R2 download; smoke-tested, not unit-tested) -----

def _cf_token() -> str:
    """The valid Cloudflare token from .env — the shell-exported one may be stale."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("CLOUDFLARE_API_TOKEN="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return os.environ.get("CLOUDFLARE_API_TOKEN", "")


def _wrangler(args: list[str]) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLOUDFLARE_API_TOKEN": _cf_token()}
    return subprocess.run(["npx", "wrangler", *args], env=env, capture_output=True, text=True)


def d1_rows() -> list[dict]:
    """Every contribution, read-only, as plain dicts (explicit safe columns)."""
    cp = _wrangler([
        "d1", "execute", D1_DATABASE, "--remote", "--json",
        "--command", f"SELECT {_COLUMNS} FROM contributions ORDER BY id",
    ])
    if cp.returncode != 0:
        raise SystemExit(f"D1 query failed:\n{cp.stderr or cp.stdout}")
    payload = json.loads(cp.stdout)
    return payload[0]["results"] if payload else []


def r2_download(r2_key: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cp = _wrangler(["r2", "object", "get", f"{R2_BUCKET}/{r2_key}", "--file", str(dest), "--remote"])
    if cp.returncode != 0:
        raise SystemExit(f"R2 download failed for {r2_key}:\n{cp.stderr or cp.stdout}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pull verified commons contributions into training.")
    ap.add_argument("--apply", action="store_true",
                    help="download eligible clips + write the manifest (default: dry-run report)")
    args = ap.parse_args()

    vocab = load_raagas()
    dual = load_dual_classes()
    pulled = pulled_shas(load_manifest())

    rows = d1_rows()
    classified = [(r, *classify(r, dual, pulled, vocab)) for r in rows]
    counts = summarize(classified)

    print(f"{counts['total']} contribution(s): "
          f"{counts[TRAIN]} trainable, {counts[VOCAB_GROWTH]} vocab-growth, {counts[SKIP]} skipped\n")

    for bucket, header in ((TRAIN, "TRAINABLE"), (VOCAB_GROWTH, "VOCAB-GROWTH (new-raaga)"), (SKIP, "SKIPPED")):
        group = [(r, why) for r, b, why in classified if b == bucket]
        if not group:
            continue
        print(f"  {header}:")
        for r, why in group:
            print(f"    #{r['id']:<3} {(r.get('raaga') or '?'):22} {(r.get('tradition') or '?'):11} — {why}")
        print()

    if not args.apply:
        print("dry run — pass --apply to download the trainable clips + write the manifest.")
        return

    n_pulled = 0
    for r, bucket, _ in classified:
        if bucket == VOCAB_GROWTH:
            append_manifest(VOCAB_GROWTH_LOG, manifest_entry(r, vocab))
        elif bucket == TRAIN:
            entry = manifest_entry(r, vocab)
            r2_download(r["r2_key"], COMMONS_DIR / entry["audio_path"])
            append_manifest(MANIFEST, entry)
            n_pulled += 1
    print(f"pulled {n_pulled} clip(s) into {COMMONS_DIR}\n"
          f"next: python -m raaga_id.train --datasets saraga_carnatic commons")


if __name__ == "__main__":
    main()
