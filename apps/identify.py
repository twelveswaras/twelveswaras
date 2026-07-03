"""v0 "Shazam for raagas" — mic/upload -> top-3 (PRD build-order step 7).

    python -m apps.identify        # launches the Gradio app

Loads the trained floor model and shows top-3 + confidence (D6). When the best
confidence is low, it surfaces an explicit "not sure" line instead of pretending.
"""
from __future__ import annotations

import numpy as np

from raaga_id import pitch_extract
from raaga_id.config import LOW_CONFIDENCE, MODELS_DIR, TOP_K
from raaga_id.model import RaagaXGB

MODEL_PATH = MODELS_DIR / "raaga_xgb.json"


def _load_model() -> RaagaXGB:
    if not MODEL_PATH.exists():
        raise SystemExit(f"no model at {MODEL_PATH} — run `python -m raaga_id.train` first.")
    return RaagaXGB.load(MODEL_PATH)


def identify(audio, model: RaagaXGB) -> str:
    """audio = (sample_rate, np.ndarray) from Gradio. Runs the PCD path: extract
    predominant-melody pitch + tonic, then classify (needs the numpy<2 inference env)."""
    if audio is None:
        return "Give me ~10 seconds of melody (a clip with a clear line + drone works best)."
    sr, wav = audio
    windows, tonic = pitch_extract.audio_to_pcd(wav, sr)
    if not windows:
        return "🤔 Not sure — couldn't find a clear melody + tonic. Try a longer, cleaner clip with a drone."
    preds = model.aggregate_top_k(np.vstack(windows), k=TOP_K)
    if preds[0].confidence < LOW_CONFIDENCE:
        return "🤔 Not sure — not enough clear melody. Try a longer, cleaner clip."
    lines = "\n".join(f"{p.raaga}: {p.confidence:.0%}" for p in preds)
    return f"{lines}\n\n(Sa ≈ {tonic:.0f} Hz)"


def build_ui():
    import gradio as gr

    model = _load_model()
    with gr.Blocks(title="twelveswaras") as demo:
        gr.Markdown("## 🎶 twelveswaras — identify the raaga")
        audio = gr.Audio(sources=["microphone", "upload"], type="numpy")
        out = gr.Textbox(label="Top-3")
        gr.Button("Identify").click(lambda a: identify(a, model), audio, out)
    return demo


if __name__ == "__main__":
    build_ui().launch()
