"""v1 contribution loop — predict -> confirm/correct -> writeback (PRD §18.3, §13).

Anonymous by default (D12): no login, dedup via audio_sha256, optional handle for
attribution only. Rights gate (§12): nothing is saved unless the contributor
affirms it's their own performance / they have the right to share it.

Writes {id}.flac + {id}.json into incoming/ of the dataset repo; the consolidate
cron promotes verified clips into shards (pipeline/consolidate.py).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import uuid

# Neutral org (D19). The Space holds an HF write token scoped to this dataset repo.
DATASET_REPO = "twelveswaras/twelveswaras-commons"
CONSENT_VERSION = "2026-07-01-v1"


def utcnow() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def pseudonym(handle: str) -> str:
    # Optional, never PII (D12). Random per-clip id if no handle given.
    return "u_" + hashlib.sha256(handle.encode()).hexdigest()[:8]


def submit(audio, chosen_raaga, is_own, license_, handle, instrument, form, ctx) -> str:
    if not is_own:
        return "❌ Not saved — you must confirm this is your own performance / you may share it."

    import soundfile as sf
    from huggingface_hub import CommitOperationAdd, HfApi

    api = HfApi(token=os.environ["HF_WRITE_TOKEN"])  # Space secret, scoped to the dataset repo
    sr, wav = audio
    buf = io.BytesIO()
    sf.write(buf, wav, sr, format="FLAC")
    raw = buf.getvalue()
    rid = uuid.uuid4().hex[:8]
    meta = {
        "id": rid,
        "audio_file": f"{rid}.flac",
        "audio_sha256": hashlib.sha256(raw).hexdigest(),
        "raaga": chosen_raaga,
        "tradition": "carnatic",
        "contributor_id": pseudonym(handle or rid),
        "is_own_performance": True,
        "license": license_,
        "consent_version": CONSENT_VERSION,
        "created_at": utcnow(),
        "label_source": "model_confirmed" if chosen_raaga == ctx.get("pred") else "contributor_declared",
        "model_prediction": ctx.get("pred"),
        "model_confidence": float(ctx.get("conf", 0.0)),
        "verification_status": "unverified",
        "split": "pending",
        "votes_agree": 0,
        "votes_disagree": 0,
        "instrument": instrument,
        "form": form,
    }
    api.create_commit(
        repo_id=DATASET_REPO,
        repo_type="dataset",
        commit_message=f"contrib {rid} ({chosen_raaga})",
        operations=[
            CommitOperationAdd(f"incoming/{rid}.flac", raw),
            CommitOperationAdd(f"incoming/{rid}.json", json.dumps(meta, ensure_ascii=False).encode()),
        ],
    )
    return f"✅ Saved as {chosen_raaga} — thank you! It enters the verification queue."


# TODO(v1): assemble the Gradio Blocks UI (predict button + confirm/correct form).
# The identify half already lives in apps/identify.py; this file owns the writeback.
