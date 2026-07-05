"""Headless inference API for the twelveswaras recognizer (the decoupled backend).

The recognizer used to be a Gradio app that rendered its own UI. In the decoupled architecture
the UI lives first-party on the site (Cloudflare Pages) and this is a pure JSON API. No UI, no
branding: the front end renders everything.

    POST /identify   multipart: audio=<file>   ->
      {
        "no_prediction": false,
        "tonic_hz": 147.0,
        "heard_seconds": 42.3,
        "top3": [{"raaga": "Kalyāṇi", "confidence": 0.91}, ...],
        "swara_activation": [12 floats]   # tonic-normalized pitch-class mass, folded to the 12
                                          # swara positions (Sa first) — drives the wheel glow
      }
    GET /health  ->  {"status": "ok", "raagas": 40}

Runs the EXACT production pipeline (essentia predominant pitch + compiam tonic -> windowed TDMS
-> XGBoost). Serves on port 7860 for a Hugging Face Docker Space, but is a plain FastAPI app
runnable anywhere. Requires the numpy<2 inference stack (see requirements-api.txt).
"""
from __future__ import annotations

import io
import os

import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from raaga_id import pitch_extract
from raaga_id.config import MODELS_DIR, TOP_K
from raaga_id.model import RaagaXGB

MODEL_PATH = os.environ.get("MODEL_PATH", str(MODELS_DIR / "raaga_xgb.json"))
SWARAS = 12

app = FastAPI(title="twelveswaras recognizer API", docs_url="/docs", redoc_url=None)
# CORS is permissive here because the public entry point is the Cloudflare Worker (same-origin to
# the browser); direct browser calls are allowed too for local dev.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"],
)

_model = None


def model() -> RaagaXGB:
    global _model
    if _model is None:
        _model = RaagaXGB.load(MODEL_PATH)
        pitch_extract.warmup()          # pay the essentia/compiam import cost once, at first call
    return _model


def fold_swaras(pcd) -> list[float]:
    """Fold the tonic-normalized pitch-class distribution (PCD_BINS bins over the octave) into the
    12 swara positions, Sa first. This is the real data the wheel lights up with."""
    if pcd is None:
        return [0.0] * SWARAS
    a = np.asarray(pcd, dtype=float)
    if a.size < SWARAS or a.sum() <= 0:
        return [0.0] * SWARAS
    per = a.size // SWARAS
    out = [float(a[i * per:(i + 1) * per].sum()) for i in range(SWARAS)]
    s = sum(out) or 1.0
    return [round(v / s, 4) for v in out]


@app.get("/health")
def health():
    return {"status": "ok", "raagas": len(model().classes)}


@app.post("/identify")
async def identify(audio: UploadFile = File(...), contribute: str = Form("no")):
    import librosa

    m = model()
    raw = await audio.read()
    try:
        y, sr = librosa.load(io.BytesIO(raw), sr=None, mono=True)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": "could not decode audio", "detail": str(e)[:200]}, status_code=400)

    windows, tonic, heard, pcd = pitch_extract.audio_to_features(y, sr)
    if not windows:
        return {
            "no_prediction": True,
            "tonic_hz": round(float(tonic), 1) if tonic else None,
            "heard_seconds": round(float(heard or 0), 1),
            "top3": [],
            "swara_activation": fold_swaras(pcd),
        }

    preds = m.aggregate_top_k(np.vstack(windows), k=TOP_K)
    return {
        "no_prediction": False,
        "tonic_hz": round(float(tonic), 1),
        "heard_seconds": round(float(heard), 1),
        "top3": [{"raaga": p.raaga, "confidence": round(float(p.confidence), 4)} for p in preds],
        "swara_activation": fold_swaras(pcd),
    }
