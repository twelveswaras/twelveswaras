"""v0 "Shazam for raagas" — mic/upload -> top-3 (PRD build-order step 7).

    python -m apps.identify        # launches the Gradio app (needs the inference env)

Runs the PCD path (essentia pitch + tonic -> pooled model), shows top-3 as confidence
bars + the estimated Sa + how long recognition took (also logged to the console).
"""
from __future__ import annotations

import time

import numpy as np

from raaga_id import pitch_extract
from raaga_id.config import LOW_CONFIDENCE, MODELS_DIR, TOP_K
from raaga_id.model import RaagaXGB

MODEL_PATH = MODELS_DIR / "raaga_xgb.json"

TITLE_HTML = """
<div style="text-align:center; line-height:1.15; margin:.2rem 0 .4rem">
  <div style="font-size:clamp(1.35rem,6.5vw,2rem); font-weight:700">🎶 twelveswaras</div>
  <div style="opacity:.6; font-size:clamp(.8rem,3.6vw,1rem)">identify the raaga</div>
</div>
"""


def _load_model() -> RaagaXGB:
    if not MODEL_PATH.exists():
        raise SystemExit(f"no model at {MODEL_PATH} — run `python -m raaga_id.train` first.")
    return RaagaXGB.load(MODEL_PATH)


def identify(audio, model: RaagaXGB):
    """audio = (sample_rate, np.ndarray) from Gradio. Returns (label_dict, info_md) for a
    gr.Label + gr.Markdown."""
    if audio is None:
        return {}, "Upload or record ~10 s+ of melody — a clear line with a drone works best."
    sr, wav = audio
    t0 = time.perf_counter()
    windows, tonic = pitch_extract.audio_to_pcd(wav, sr)
    if not windows:
        return {}, "🤔 Couldn't find a clear melody + tonic — try a longer, cleaner clip with a drone."
    preds = model.aggregate_top_k(np.vstack(windows), k=TOP_K)
    elapsed = time.perf_counter() - t0
    print(f"[identify] {preds[0].raaga} ({preds[0].confidence:.0%}) · Sa≈{tonic:.0f}Hz · {elapsed:.1f}s",
          flush=True)

    labels = {p.raaga: float(p.confidence) for p in preds}
    caveat = "  ·  🤔 low confidence" if preds[0].confidence < LOW_CONFIDENCE else ""
    info = f"**Sa ≈ {tonic:.0f} Hz**  ·  recognized in **{elapsed:.1f} s**{caveat}"
    return labels, info


def build_ui():
    import gradio as gr

    model = _load_model()
    pitch_extract.warmup()          # pay the essentia/compiam import cost once, up front

    with gr.Blocks(title="twelveswaras", theme=gr.themes.Soft()) as demo:
        gr.HTML(TITLE_HTML)
        audio = gr.Audio(sources=["microphone", "upload"], type="numpy")
        btn = gr.Button("Identify", variant="primary", size="lg")
        result = gr.Label(num_top_classes=TOP_K, label="Raaga")
        info = gr.Markdown()
        btn.click(lambda a: identify(a, model), audio, [result, info])
    return demo


if __name__ == "__main__":
    build_ui().launch()
