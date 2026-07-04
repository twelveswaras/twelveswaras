"""Aggregate, privacy-preserving usage logging.

Logs the RESULT of each identification (predicted raaga + confidence + tonic + whether a
prediction was made) to a private Hugging Face Dataset. It NEVER logs the audio, an IP, or any
user identifier — just anonymous per-identification result metadata, so we can see how much the
app is used and what it's recognising in the wild (the passive real-world signal).

Robustness:
- Disabled unless HF_TOKEN is set (a write token, as a Space secret). Without it the app runs
  exactly as before, just without logging.
- Every call is wrapped so a logging failure can NEVER break recognition.
- Uses huggingface_hub.CommitScheduler: appends locally, flushes to the dataset every few minutes
  (one commit per identification would be far too many).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DATASET = "twelveswaras/usage-logs"
LOG_DIR = Path("usage_logs")
LOG_FILE = LOG_DIR / "identifications.jsonl"

_scheduler = None
_tried = False


def _scheduler_or_none():
    global _scheduler, _tried
    if _scheduler is not None or _tried:
        return _scheduler
    _tried = True
    if not os.environ.get("HF_TOKEN"):
        return None                       # logging off; app still works
    try:
        from huggingface_hub import CommitScheduler
        LOG_DIR.mkdir(exist_ok=True)
        _scheduler = CommitScheduler(repo_id=DATASET, repo_type="dataset", private=True,
                                     folder_path=str(LOG_DIR), path_in_repo="data", every=5)
    except Exception:                     # noqa: BLE001  (bad token / no access -> stay disabled)
        _scheduler = None
    return _scheduler


def record(*, top1=None, confidence=None, top3=None, tonic_hz=None,
           heard_seconds=None, no_prediction=False, elapsed_s=None) -> None:
    """Append one identification's RESULT metadata. No audio, no PII. Never raises."""
    try:
        sch = _scheduler_or_none()
        if sch is None:
            return
        from datetime import datetime, timezone
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "top1": top1,
            "confidence": round(float(confidence), 3) if confidence is not None else None,
            "top3": top3,
            "tonic_hz": round(float(tonic_hz)) if tonic_hz else None,
            "heard_s": round(float(heard_seconds), 1) if heard_seconds is not None else None,
            "no_prediction": bool(no_prediction),
            "elapsed_s": round(float(elapsed_s), 2) if elapsed_s is not None else None,
        }
        with sch.lock:
            with open(LOG_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:                     # noqa: BLE001  (logging must never break recognition)
        pass
