# Deploy the recognizer to a Hugging Face Space

The recognizer is a Gradio app that needs a Python backend (essentia + compiam + numpy<2
+ the model) — so it runs on **Hugging Face Spaces**, not a static host. A Space is a
fresh Linux env, so the numpy<2 constraint is no problem.

## One-time (you — needs your HF account)

```bash
pip install -U "huggingface_hub[cli]"
huggingface-cli login                     # paste a write token from hf.co/settings/tokens
```

Create the Space at **huggingface.co/new-space**:
- Owner: **twelveswaras** (the org) · Name: **twelveswaras**
- SDK: **Gradio** · Hardware: **CPU basic (free)** is enough (~3.5 s/recognition)

## Assemble + push (me or you)

```bash
bash space/assemble.sh                     # builds ./space_build with the model bundled
cd space_build
git init && git add -A && git commit -m "twelveswaras recognizer"
git remote add origin https://huggingface.co/spaces/twelveswaras/twelveswaras
git push -u origin main
```

The Space builds from `requirements.txt` (+ `packages.txt` for ffmpeg) and runs `app.py`.
First build takes a few minutes (compiling deps). Then it's live at
`https://twelveswaras-twelveswaras.hf.space`.

## Notes
- The model (`models/raaga_xgb.json`, ~few MB) is bundled into the Space. To keep the
  Space lean later, host the model on the HF Hub and download at startup instead.
- Mic works on the Space (HTTPS) given the browser/OS mic permissions.
- `space_build/` is gitignored in this repo — it's a throwaway staging dir.
