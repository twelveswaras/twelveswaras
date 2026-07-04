"""v0 "Shazam for raagas" — mic/upload -> top-3 (PRD build-order step 7).

    python -m apps.identify        # launches the Gradio app (needs the inference env)

Runs the PCD path (essentia pitch + tonic -> pooled model), shows top-3 as confidence
bars + the estimated Sa + recognition time. Styled to the shared urbanmorph design
system (dark #0a0a0a canvas, system-ui, hairline borders) with twelveswaras' amber hue.
"""
from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from raaga_id import pitch_extract
from raaga_id.config import MODELS_DIR, TOP_K
from raaga_id.model import RaagaXGB

ASSETS = Path(__file__).resolve().parent.parent / "assets"
MODEL_PATH = MODELS_DIR / "raaga_xgb.json"

# Inline logo tile (12-bar pitch-class histogram = the twelve swaras), amber gradient.
_TILE = """
<svg width="46" height="46" viewBox="0 0 256 256" style="flex:0 0 auto">
  <defs><linearGradient id="tsl" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#f59e0b"/><stop offset="1" stop-color="#b45309"/></linearGradient></defs>
  <rect width="256" height="256" rx="56" fill="url(#tsl)"/>
  <g fill="#fff">
    <rect x="36" y="140" width="10" height="60" rx="5"/><rect x="52" y="105" width="10" height="95" rx="5"/>
    <rect x="68" y="145" width="10" height="55" rx="5"/><rect x="84" y="80" width="10" height="120" rx="5"/>
    <rect x="100" y="120" width="10" height="80" rx="5"/><rect x="116" y="95" width="10" height="105" rx="5"/>
    <rect x="132" y="64" width="10" height="136" rx="5"/><rect x="148" y="130" width="10" height="70" rx="5"/>
    <rect x="164" y="90" width="10" height="110" rx="5"/><rect x="180" y="115" width="10" height="85" rx="5"/>
    <rect x="196" y="100" width="10" height="100" rx="5"/><rect x="212" y="135" width="10" height="65" rx="5"/>
  </g></svg>
"""

TITLE_HTML = f"""
<div style="display:flex; align-items:center; justify-content:center; gap:.65rem; margin:.4rem 0 .2rem">
  {_TILE}
  <div style="text-align:left; line-height:1.05">
    <div style="font-size:clamp(1.4rem,6.5vw,2.1rem); font-weight:800; letter-spacing:-1px"><span style="color:#ededed">twelve</span><span style="color:#f59e0b">swaras</span></div>
    <div style="font-size:clamp(.72rem,3.2vw,.92rem); color:#9ca3af; letter-spacing:.2px">identify the raaga</div>
  </div>
</div>
"""

FOOTER_HTML = """
<div id="ts-footer">a non-commercial, open-source public good · Carnatic first · CC-BY data commons</div>
"""

CSS = """
.gradio-container { max-width: 640px !important; margin: 0 auto !important; }
footer { display: none !important; }
#ts-footer { text-align:center; color:#9ca3af; opacity:.7; font-size:.78rem; margin:1rem 0 .3rem; }
/* confidence bars in the brand amber */
.gradio-container .label span.text + div, .gradio-container .fill { background: #f59e0b !important; }
/* audio player: keep the seek bar from covering the 0:00 / total time read-outs */
.gradio-container .timestamps { position: relative; z-index: 3; margin-top: 4px; }
.gradio-container .timestamps time { background: #0a0a0a; padding: 0 3px; border-radius: 3px; }
"""


def _theme():
    import gradio as gr

    return gr.themes.Base(
        primary_hue=gr.themes.colors.amber,
        secondary_hue=gr.themes.colors.amber,
        neutral_hue=gr.themes.colors.neutral,
        font=["system-ui", "ui-sans-serif", "-apple-system", "Segoe UI", "sans-serif"],
        font_mono=["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
    ).set(
        body_background_fill="#0b0a08",   # match the twelveswaras.com page ground (no seam)
        body_text_color="#ededed",
        body_text_color_subdued="#9ca3af",
        background_fill_primary="#15151a",
        background_fill_secondary="#1a1a1f",
        block_background_fill="#15151a",
        block_border_color="#262626",
        block_border_width="1px",
        block_radius="12px",
        block_label_background_fill="#1a1a1f",
        block_label_text_color="#fbbf24",
        border_color_primary="#262626",
        input_background_fill="#1a1a1f",
        button_primary_background_fill="#d97706",
        button_primary_background_fill_hover="#b45309",
        button_primary_text_color="#ffffff",
        button_primary_border_color="#d97706",
    )


def _load_model() -> RaagaXGB:
    if not MODEL_PATH.exists():
        raise SystemExit(f"no model at {MODEL_PATH} — run `python -m raaga_id.train` first.")
    return RaagaXGB.load(MODEL_PATH)


def _learn_plot(raaga, user_profile):
    """A dark/amber bar chart of which of the seven swaras the raaga rests on vs the user's
    clip — the 'how to hear this raaga' visual, in the notes a beginner knows."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from raaga_id import learn
    from raaga_id.features import to_swaras7

    names, user7 = to_swaras7(user_profile)
    x = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(6, 2.4))
    fig.patch.set_facecolor("#0a0a0a")
    ax.set_facecolor("#0a0a0a")
    ref = learn.reference_profile(raaga)
    if ref is not None:
        ax.bar(x - 0.2, to_swaras7(ref)[1], width=0.4, color="#f59e0b", label=raaga)
    ax.bar(x + 0.2, user7, width=0.4, color="#6b7280", label="your clip")
    ax.set_xticks(x)
    ax.set_xticklabels(names, color="#ededed", fontsize=9)
    ax.tick_params(axis="x", length=0)
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.legend(facecolor="#15151a", edgecolor="#262626", labelcolor="#ededed", fontsize=8, loc="upper right")
    fig.tight_layout()
    return fig


def _mmss(seconds: float) -> str:
    """Whole-second duration as m:ss (e.g. 90 -> '1:30'), for the 'heard 0:00-…' label."""
    s = int(round(seconds))
    return f"{s // 60}:{s % 60:02d}"


def identify(audio, model: RaagaXGB):
    """audio = (sample_rate, np.ndarray) from Gradio. A GENERATOR: it yields a "listening"
    state first (so the app is visibly working before it answers — D24), then the final
    (labels, info, plot, learn_md). The info line names the segment it actually heard."""
    if audio is None:
        yield {}, "Upload or record ~10 s+ of melody — a clear line with a drone works best.", None, ""
        return
    # Show that we're listening BEFORE the ~3.5 s of pitch+tonic extraction, and clear any
    # previous result, so the answer never appears to precede the analysis.
    yield {}, "🎧 **Listening…** finding the tonic (Sa) and tracing the swaras.", None, ""

    sr, wav = audio
    t0 = time.perf_counter()
    windows, tonic, heard, display_pcd = pitch_extract.audio_to_features(wav, sr)
    if not windows:
        yield {}, "🤔 Couldn't find a clear melody + tonic — try a longer, cleaner clip with a drone.", None, ""
        return
    X = np.vstack(windows)
    preds = model.aggregate_top_k(X, k=TOP_K)
    elapsed = time.perf_counter() - t0
    print(f"[identify] {preds[0].raaga} ({preds[0].confidence:.0%}) · Sa≈{tonic:.0f}Hz · "
          f"heard {_mmss(heard)} · {elapsed:.1f}s", flush=True)

    from raaga_id.calibrate import confidence_state
    labels = {p.raaga: float(p.confidence) for p in preds}
    _, note = confidence_state(preds)     # calibrated top-2 -> "✓ confident" / "close call" / "not sure"
    info = (f"**Sa ≈ {tonic:.0f} Hz**  ·  heard **0:00–{_mmss(heard)}**  ·  "
            f"recognized in **{elapsed:.1f} s**  ·  {note}")

    from raaga_id import learn
    from raaga_id.features import pcd_to_swaras
    top = preds[0].raaga
    user_profile = pcd_to_swaras(display_pcd)   # human-readable swaras from the PCD, not the TDMS surface
    yield labels, info, _learn_plot(top, user_profile), learn.summary_md(top, user_profile)


def is_embedded(query_params) -> bool:
    """True when the app is loaded inside the twelveswaras.com page iframe (src has ?embed=1).
    In that case the app hides its own logo + footer so it reads as part of the page, not a
    separate site."""
    try:
        return str(query_params.get("embed", "")) == "1"
    except AttributeError:
        return False


def build_ui():
    import gradio as gr

    model = _load_model()
    pitch_extract.warmup()          # pay the essentia/compiam import cost once, up front

    with gr.Blocks(title="twelveswaras", theme=_theme(), css=CSS) as demo:
        title = gr.HTML(TITLE_HTML)
        # buttons=["download"] drops Gradio's built-in "share": it re-uploads the raw clip to HF's
        # MIME-restricted uploader (rejects m4a/aac/flac/…) and shares the *input*, not the result
        # — confusing + flaky. A real "share this raga" is an Explorer feature (D29). Keep download.
        audio = gr.Audio(sources=["microphone", "upload"], type="numpy",
                         label="Upload or record ~15–30 s", buttons=["download"])
        gr.Markdown("🎚️ **For best accuracy, include a tanpura / shruti-box drone.** A live "
                    "concert always has one — the tonic (Sa) is found from it, so solo voice "
                    "without a drone is unreliable.")
        result = gr.Label(num_top_classes=TOP_K, label="Raaga")
        info = gr.Markdown("_Recognition runs automatically when you upload or finish recording._")
        with gr.Accordion("🎓 How to hear this raaga", open=False):
            learn_plot = gr.Plot(label="Typical shape from recordings (gold) vs your clip (grey)")
            learn_md = gr.Markdown()
        footer = gr.HTML(FOOTER_HTML)

        outs = [result, info, learn_plot, learn_md]

        def on_audio(a):        # generator fn so Gradio streams "listening…" then the result
            yield from identify(a, model)

        # No button: auto-identify when a file is uploaded or a recording stops.
        audio.upload(on_audio, audio, outs)
        audio.stop_recording(on_audio, audio, outs)

        def _on_load(request: gr.Request):
            hide = not is_embedded(request.query_params)  # keep logo/footer only when standalone
            return gr.update(visible=hide), gr.update(visible=hide)
        demo.load(_on_load, None, [title, footer])
    return demo


if __name__ == "__main__":
    favicon = ASSETS / "favicon.svg"
    build_ui().launch(favicon_path=str(favicon) if favicon.exists() else None)
