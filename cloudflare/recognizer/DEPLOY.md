# Recognizer on Cloudflare Containers: deploy

Moves the recognizer off the (now unreliable, sleeping) Hugging Face free Space onto a Cloudflare
Container, on the Workers Paid plan already in use. The gateway worker (`twelveswaras-api`) keeps
doing everything else (CORS, D1 logging, R2, /result, /event, /contribute); only its `SPACE_URL`
changes to point here.

## Prerequisites

- **Docker Desktop running** - `wrangler deploy` builds the container image locally and pushes it.
- **Node 22** for wrangler 4 (system node is 16). Use the mise node:
  `export PATH="$HOME/.local/share/mise/installs/node/22.22.0/bin:$PATH"`
- Cloudflare auth: `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` (already in repo `.env`).

## Step 1: build the app bundle (CARNATIC first)

```
cd cloudflare/recognizer
./assemble.sh            # carnatic model (default): pure reliability cutover, IDENTICAL predictions
npm install
```

The first cutover deliberately ships the **same Carnatic model**, so the only thing that changes is
where it runs. That de-risks the Container path before adding Hindustani.

## Step 2: deploy the container worker

```
export PATH="$HOME/.local/share/mise/installs/node/22.22.0/bin:$PATH"
export CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=...     # from .env
npx --yes wrangler@4 deploy
```

Wrangler builds `./Dockerfile` (context = `./app`), pushes the image, and creates the
`twelveswaras-recognizer` worker + `Recognizer` container class. Note the printed
`https://twelveswaras-recognizer.<subdomain>.workers.dev` URL.

## Step 3: verify the container serves recognition

```
curl -s https://twelveswaras-recognizer.<subdomain>.workers.dev/health      # {"status":"ok","raagas":40,...}
```

First call cold-starts the container (a few seconds, vs HF's ~30s); subsequent calls are warm.

## Step 4: cut the gateway worker over (one line)

In `cloudflare/worker/wrangler.toml`, change:

```
SPACE_URL = "https://twelveswaras-recognizer.<subdomain>.workers.dev"
```

Then redeploy the gateway worker:

```
cd ../worker && npx --yes wrangler@4 deploy
```

Now `twelveswaras.com/api/identify` is served by the Container. **Rollback** = set `SPACE_URL` back
to `https://twelveswaras-recognizer-api.hf.space` and redeploy. Instant.

## Later: the Hindustani launch (dual model)

Do NOT ship the dual model until the site frontend guards a Hindustani result (a
`raaga/<slug>.html` learn link that does not exist yet would 404). Once that frontend change is
live:

```
cd cloudflare/recognizer
./assemble.sh dual      # 70-class calibrated dual model (Carnatic + Hindustani)
npx --yes wrangler@4 deploy
```

No gateway change needed - same URL, new model. `/health` will then report
`{"raagas":70,"traditions":{"carnatic":40,"hindustani":30}}`.

## Notes

- Instance size is `standard-1` (4 GiB) in `wrangler.toml`; bump to `standard-2` if warm inference
  is slow. Container usage is billed against the Workers Paid monthly allowance (25 GiB-hours etc.).
- `./app` is gitignored (it contains the model). `assemble.sh`, the Dockerfile, worker, and this
  doc are tracked.
- The container config keys (`[[containers]]`, `instance_type`) are validated by `wrangler deploy`;
  if a key name has changed in your wrangler version, `wrangler deploy` will say so.
