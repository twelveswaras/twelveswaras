---
title: twelveswaras recognizer API
emoji: 🎧
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

# twelveswaras recognizer API (headless)

The decoupled inference backend. No UI: it exposes JSON only. The user-facing wheel lives
first-party on twelveswaras.com (Cloudflare Pages) and calls this through a Cloudflare Worker.

- `GET /health` -> `{ "status": "ok", "raagas": 40 }`
- `POST /identify` (multipart `audio`) -> `{ top3, tonic_hz, heard_seconds, no_prediction, swara_activation[12] }`

This Space is a **Docker** SDK space (not Gradio). It builds `space/Dockerfile`, which runs
`uvicorn api:app` on port 7860. To deploy, assemble the build (raaga_id/, models/, api.py,
Dockerfile, requirements-api.txt) and push to a Space whose README has the front-matter above.
See `cloudflare/DEPLOY.md`.
