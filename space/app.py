"""Hugging Face Space entry point. The Space bundles the raaga_id package, apps/,
assets/, raagas.json, schema.py, and models/ alongside this file (see space/assemble.sh).
Gradio auto-launches the `demo` object; the __main__ guard covers local runs.
"""
from apps.identify import build_ui

demo = build_ui()

if __name__ == "__main__":
    demo.launch()
