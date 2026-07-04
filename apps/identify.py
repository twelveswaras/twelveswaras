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
<div id="ts-title" style="display:flex; align-items:center; justify-content:center; gap:.65rem; margin:.4rem 0 .2rem">
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
/* embed mode (loaded in the twelveswaras.com iframe via ?embed=1): hide the app's own logo,
   footer, and the drone tip (the page already carries all three) so it fits without scrolling */
body.embed #ts-title, body.embed #ts-footer, body.embed #ts-drone { display: none !important; }
body.embed .gap, body.embed .contain { gap: 10px !important; }
body.embed .gradio-container { padding-top: 2px !important; padding-bottom: 0 !important;
  overflow: hidden !important; max-width: 100% !important; }  /* fill page width; no bottom slack
  so the auto-resized frame ends right at the content (640px cap is for standalone) */
/* breathing room around the status line so Gradio's progress bar doesn't crowd the "Listening…" text */
#ts-status { margin-top: 10px !important; }
#ts-status p { padding-top: 6px !important; }
/* frame is sized to content -> the iframe itself never scrolls; the page does. Kills Gradio's
   always-on scrollbar track. (overflow only — no height changes, which would blank the app.) */
html:has(body.embed), body.embed { overflow: hidden !important; }
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
    state, note = confidence_state(preds)   # calibrated top-2 -> "confident" / "close" / "unsure"
    info = (f"**Sa ≈ {tonic:.0f} Hz**  ·  heard **0:00–{_mmss(heard)}**  ·  "
            f"recognized in **{elapsed:.1f} s**  ·  {note}")

    from raaga_id import learn
    from raaga_id.features import pcd_to_swaras
    top = preds[0].raaga
    user_profile = pcd_to_swaras(display_pcd)   # human-readable swaras from the PCD, not the TDMS surface
    learn_md = learn.summary_md(top, user_profile)
    # On a close call, lead the learner panel with how to tell the top two apart (D29 Explorer).
    if state == "close":
        cmp = learn.comparison_md(preds[0].raaga, preds[1].raaga)
        if cmp:
            learn_md = cmp + "\n\n---\n\n" + learn_md
    yield labels, info, _learn_plot(top, user_profile), learn_md


# When the recognizer is loaded inside the twelveswaras.com page (i.e. in an iframe), hide its
# own logo/footer/drone-tip so it reads as part of the page. Injected in <head> so it always
# runs; detects embedding by iframe (window.self !== window.top) — no query-param dependency —
# and hides elements DIRECTLY by id, re-applying on a few timers because Gradio renders its
# components asynchronously after first paint. Standalone (hf.space direct) keeps full branding.
EMBED_HEAD = """
<script>
(function () {
  function embedded() { try { return window.self !== window.top; } catch (e) { return true; } }
  function hideChrome() {
    if (!embedded()) return;
    document.body.classList.add('embed');
    // The frame is sized to content, so the recognizer never needs to scroll itself — the PAGE
    // scrolls. Hide the iframe's own overflow so Gradio's always-on scrollbar track disappears.
    // (Only overflow — no height/min-height changes, which would collapse the layout.)
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
    ['ts-title', 'ts-drone', 'ts-footer'].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) { el.style.display = 'none'; }
    });
  }
  // Tell the parent page our content height so it can grow the iframe to fit — the PAGE scrolls,
  // the frame never gets its own scrollbar. Fires on load, timers, window resize, and (via
  // ResizeObserver) whenever the content changes — a result appears, the accordion opens, etc.
  var lastH = 0;
  function reportHeight() {
    if (!embedded()) return;
    // Gradio stretches every CONTAINER to fill the viewport (= the frame height), so measuring any
    // of them loops the auto-resize to infinity ("grows like a worm"). The #ts-end sentinel is a
    // plain marker that flows right after the last component, so its bottom is the TRUE content
    // height and can't stretch. absolute = rect.bottom + scrollY. +10px breathing room.
    var end = document.getElementById('ts-end');
    if (!end) return;
    var h = Math.ceil(end.getBoundingClientRect().bottom + window.scrollY) + 10;
    if (h > 0 && h !== lastH) {
      lastH = h;
      try { window.parent.postMessage({ twelveswaras_height: h }, '*'); } catch (er) {}
    }
  }
  function hideDeadMic() {
    // Gradio's audio device <select> shows a misleading "No microphone found" before mic permission
    // is granted, even though recording works fine on the default device. Hide that control while it
    // shows the dead label, and restore ONLY the ones we hid once a real device name appears.
    var L = 'No microphone found';
    document.querySelectorAll('select, button').forEach(function (el) {
      var t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
      if (t === L) { el.style.display = 'none'; el.dataset.tsDeadmic = '1'; }
      else if (el.dataset.tsDeadmic === '1') { el.style.display = ''; delete el.dataset.tsDeadmic; }
    });
  }
  function tick() { hideChrome(); hideDeadMic(); reportHeight(); }
  if (document.readyState !== 'loading') tick();
  document.addEventListener('DOMContentLoaded', tick);
  [150, 400, 900, 1800].forEach(function (t) { setTimeout(tick, t); });
  window.addEventListener('resize', reportHeight);
  // Gradio's body is pinned to 100vh, so opening the accordion / getting a result overflows it
  // WITHOUT changing its size — ResizeObserver never fires. So poll the sentinel (deduped, cheap).
  setInterval(tick, 300);
})();
</script>
"""


def build_ui():
    import gradio as gr

    model = _load_model()
    pitch_extract.warmup()          # pay the essentia/compiam import cost once, up front

    with gr.Blocks(title="twelveswaras", theme=_theme(), css=CSS, head=EMBED_HEAD) as demo:
        gr.HTML(TITLE_HTML)
        # buttons=["download"] drops Gradio's built-in "share": it re-uploads the raw clip to HF's
        # MIME-restricted uploader (rejects m4a/aac/flac/…) and shares the *input*, not the result
        # — confusing + flaky. A real "share this raga" is an Explorer feature (D29). Keep download.
        audio = gr.Audio(sources=["microphone", "upload"], type="numpy", autoplay=True,
                         label="Upload or record ~15–30 s", buttons=["download"])
        gr.Markdown("🎚️ **For best accuracy, include a tanpura / shruti-box drone.** A live "
                    "concert always has one — the tonic (Sa) is found from it, so solo voice "
                    "without a drone is unreliable.", elem_id="ts-drone")
        result = gr.Label(num_top_classes=TOP_K, label="Raaga")
        info = gr.Markdown("_Recognition runs automatically when you upload or finish recording._",
                           elem_id="ts-status")
        with gr.Accordion("🎓 How to hear this raaga", open=False):
            learn_plot = gr.Plot(label="Typical shape from recordings (gold) vs your clip (grey)")
            learn_md = gr.Markdown()
        gr.HTML(FOOTER_HTML)
        # Sentinel at the very end of the content. Gradio stretches every CONTAINER to fill the
        # viewport (so measuring any of them loops the auto-resize), but this plain marker just
        # flows after the last component — its position IS the true content height.
        gr.HTML('<div id="ts-end" style="height:1px"></div>')

        outs = [result, info, learn_plot, learn_md]

        def on_audio(a):        # generator fn so Gradio streams "listening…" then the result
            yield from identify(a, model)

        # No button: auto-identify when a file is uploaded or a recording stops.
        # show_progress="hidden": the generator already yields a "🎧 Listening…" status, so Gradio's
        # per-output progress spinners are redundant AND duplicate on mobile — each of the 4 outputs
        # renders its own "N.Ns" eta, and on a narrow layout one floats over the caption text.
        audio.upload(on_audio, audio, outs, show_progress="hidden")
        audio.stop_recording(on_audio, audio, outs, show_progress="hidden")

        # Clearing the audio (Gradio's ✕) must also reset the result/Sa/panels below — otherwise
        # the previous clip's raaga lingers under an empty input.
        def clear_panels():
            return {}, "_Recognition runs automatically when you upload or finish recording._", None, ""
        audio.clear(clear_panels, None, outs)
    return demo


if __name__ == "__main__":
    favicon = ASSETS / "favicon.svg"
    build_ui().launch(favicon_path=str(favicon) if favicon.exists() else None)
