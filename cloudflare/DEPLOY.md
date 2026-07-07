# Deploying the decoupled recognizer (Cloudflare + HF Docker Space)

Architecture: **first-party wheel (Cloudflare Pages) -> Cloudflare Worker (/api/*) -> headless
recognizer (HF Docker Space)**, with **D1** for result logging and **R2** for the opt-in CC-BY
clip commons. The browser only ever talks to the Worker, same-origin, so there is no cross-origin
iframe, no CORS pain, and no third-party chrome or logo.

```
 browser (twelveswaras.com/app)
    |  POST /api/identify  (multipart audio, same-origin)
    v
 Cloudflare Worker  --server->  HF Docker Space  POST /identify  (essentia+compiam+XGBoost)
    |  \--> D1 (result metadata)   \--> R2 (opt-in clip)
    v
 JSON { top3, tonic_hz, swara_activation, ... }  ->  wheel renders it
```

Everything below needs YOUR accounts (Cloudflare + Hugging Face). The code is all in this repo.

## 1. Headless recognizer on a HF Docker Space

```bash
bash space/assemble.sh                 # stages raaga_id/, apps/, models/, schema.py, etc. into space_build/
cp space/api.py space/Dockerfile space/requirements-api.txt space_build/
cp space/README-api.md space_build/README.md    # Docker SDK front-matter (sdk: docker, app_port: 7860)
cd space_build
git init && git add -A && git commit -m "headless recognizer API"
git remote add origin https://huggingface.co/spaces/twelveswaras/recognizer-api
git push -u origin main
```

Create the Space at huggingface.co/new-space as **Docker** SDK first (or let the README front-matter
set it). First build takes a few minutes (essentia compiles). Verify:

```bash
curl https://twelveswaras-recognizer-api.hf.space/health      # {"status":"ok","raagas":40}
curl -F audio=@some-clip.m4a https://twelveswaras-recognizer-api.hf.space/identify
```

## 2. Cloudflare: D1, R2, Worker

```bash
npm i -g wrangler && wrangler login

# D1 (result logs)
wrangler d1 create twelveswaras
#   -> copy the database_id into cloudflare/worker/wrangler.toml
wrangler d1 execute twelveswaras --remote --file cloudflare/schema.sql

# R2 (opt-in commons clips)
wrangler r2 bucket create twelveswaras-clips

# point the worker at the Space, then deploy
#   edit wrangler.toml: SPACE_URL = "https://twelveswaras-recognizer-api.hf.space"
cd cloudflare/worker
wrangler deploy
```

The `[[routes]]` block binds the Worker to `twelveswaras.com/api/*` (needs the zone on Cloudflare).
Until DNS is on Cloudflare you can test against the `*.workers.dev` URL by loading the front end with
`?api=https://twelveswaras-api.<acct>.workers.dev`.

## 3. Cloudflare Pages (the wheel front end)

```bash
# publish site/ as a Pages project (dashboard: Pages -> create -> direct upload,
# or `wrangler pages deploy site --project-name twelveswaras-app`)
```

The front end calls `/api/identify` same-origin, so serve it under the same zone as the Worker route
(e.g. twelveswaras.com/app, or app.twelveswaras.com with a matching `[[routes]]` pattern). No API URL
is hard-coded; `?api=` only overrides for local/dev.

## 4. DNS / custom domain

Move the `twelveswaras.com` zone to Cloudflare (or add `app.twelveswaras.com`). Once the zone is on
Cloudflare, the Worker route `twelveswaras.com/api/*` and the Pages project resolve same-origin. This
also replaces the GitHub-Pages hosting for the app surface (the static marketing site can stay on
Pages too, or move under the same zone).

## 5. Retire the Gradio Space (optional, later)

Once the wheel is live and calling the API, the old Gradio Space (`twelveswaras/twelveswaras`) and the
iframe embed can be removed. The `apps/usage_log.py` HF-Dataset logger is superseded by D1.

## Notes
- **Privacy is preserved:** on identify, audio is forwarded, analysed, and dropped; only the final
  result metadata is logged (via `POST /result`, one row per session, never the audio). A clip is
  stored to R2 **only** through the explicit `POST /contribute` endpoint, which is opt-in and
  rights-gated (`is_own` must be attested) and keeps the clip private unless `release_public` is set.
- **Costs:** Worker + Pages + D1 + R2 all have generous free tiers; the HF Docker Space on CPU-basic is
  free. The heavy dependency is essentia in the Space image.
- **Rate limiting:** a Cloudflare WAF rate-limiting rule (Security -> WAF -> Rate limiting rules)
  protects `/api/identify`: **50 requests / 10s per IP per data center, block for 10s**. On the Free
  plan this is the one allowed WAF rule, and the period is fixed at 10s and counting is per-colo
  (characteristics must include `cf.colo.id`). The limit is generous on purpose: a real listen sends
  only ~3 identify polls per 10s, so shared concert/CGNAT IPs are safe, while a hammering loop is
  cut off. The Workers-native rate-limit binding does NOT enforce on the Free plan (verified), so do
  not rely on it here. `/api/contribute` is not rate-limited (Free allows one rule; it is lower risk
  behind the rights gate + sha256 dedup).
