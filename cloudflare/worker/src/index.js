/**
 * twelveswaras API edge worker.
 *
 * The browser talks only to this worker (same-origin via a route on twelveswaras.com), so there is
 * no cross-origin iframe and no CORS pain. The worker:
 *   - forwards the audio to the headless recognizer Space (server-to-server),
 *   - logs RESULT METADATA ONLY to D1 (never the audio — privacy is the product),
 *   - optionally stores an opt-in clip to R2 for the CC-BY commons (only when the client consents),
 *   - returns the JSON to the page.
 *
 * Bindings (wrangler.toml): SPACE_URL (var), ALLOW_ORIGIN (var), DB (D1), CLIPS (R2).
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }), env, request);

    // match /identify and /health with or without the /api prefix, so the same worker serves both
    // same-origin (twelveswaras.com/api/identify) and the direct staging URL (…workers.dev/identify)
    if (request.method === 'POST' && url.pathname.endsWith('/identify')) {
      return handleIdentify(request, env, ctx);
    }
    if (request.method === 'POST' && url.pathname.endsWith('/contribute')) {
      return handleContribute(request, env, ctx);
    }
    // one row per finished session: the wheel posts the final (locked) result here when it stops
    if (request.method === 'POST' && url.pathname.endsWith('/result')) {
      return handleResult(request, env, ctx);
    }
    // one row per funnel step reached (view -> listen_start -> result), so a visit that produces
    // nothing is legible rather than invisible
    if (request.method === 'POST' && url.pathname.endsWith('/event')) {
      return handleEvent(request, env, ctx);
    }
    if (url.pathname.endsWith('/health')) {
      try {
        const r = await fetch(env.SPACE_URL + '/health');
        return cors(json(await r.json()), env, request);
      } catch {
        return cors(json({ status: 'backend unavailable' }, 502), env, request);
      }
    }
    return cors(json({ error: 'not found', path: url.pathname }, 404), env, request);
  },

  // Cron (wrangler.toml [triggers]): keep the recognizer Space warm. A sleeping HF Space costs the
  // FIRST visitor a ~34s cold start with no feedback, which is well past the point where anyone
  // waits; measured usage was ~100 visitors/day producing zero recognitions. Cheaper to pay that
  // cold start on a schedule than to charge it to whoever shows up.
  async scheduled(event, env, ctx) {
    ctx.waitUntil(keepWarm(env));
  },
};

// A warm Space answers /health in ~1s. Anything slower means it had gone to sleep and this ping
// just absorbed the cold start on a visitor's behalf. Logged either way (`wrangler tail`) so the
// cron cadence can be tuned from evidence about how fast the Space actually sleeps.
const COLD_MS = 5000;

async function keepWarm(env) {
  const t0 = Date.now();
  try {
    const r = await fetch(env.SPACE_URL + '/health');
    const ms = Date.now() - t0;
    console.log('keepwarm', { status: r.status, ms, cold: ms > COLD_MS });
  } catch (e) {
    // Never throw: an unhandled rejection here would mark the cron as failing, and a dead cron is
    // worse than a cold Space (it fails silently and the cold start comes back).
    console.error('keepwarm failed', { err: String((e && e.message) || e), ms: Date.now() - t0 });
  }
}

// Reflect the request Origin when it's one of ours (production, *.pages.dev previews, or localhost
// dev), otherwise fall back to the primary origin. This lets the wheel be tested from a local static
// server or a preview deploy without opening the API to arbitrary sites.
function allowedOrigin(origin, env) {
  const primary = env.ALLOW_ORIGIN || '*';
  if (!origin) return primary;
  let host;
  try { host = new URL(origin).hostname; } catch { return primary; }
  if (
    host === 'twelveswaras.com' || host === 'www.twelveswaras.com' ||
    host === 'localhost' || host === '127.0.0.1' || host.endsWith('.pages.dev')
  ) return origin;
  return primary;
}

function cors(resp, env, request) {
  const h = new Headers(resp.headers);
  h.set('Access-Control-Allow-Origin', allowedOrigin(request && request.headers.get('Origin'), env));
  h.set('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
  h.set('Access-Control-Allow-Headers', 'content-type');
  h.set('Vary', 'Origin');
  return new Response(resp.body, { status: resp.status, headers: h });
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { 'content-type': 'application/json' } });
}

async function handleIdentify(request, env, ctx) {
  let form;
  try {
    form = await request.formData();
  } catch {
    return cors(json({ error: 'expected multipart/form-data with an "audio" field' }, 400), env, request);
  }
  const audio = form.get('audio');
  if (!audio || typeof audio === 'string') return cors(json({ error: 'no audio' }, 400), env, request);

  // forward to the headless recognizer
  const fwd = new FormData();
  fwd.append('audio', audio, 'clip.webm');
  let data;
  try {
    const r = await fetch(env.SPACE_URL + '/identify', { method: 'POST', body: fwd });
    data = await r.json();
  } catch {
    return cors(json({ error: 'recognizer unavailable' }, 502), env, request);
  }

  if (!data || data.error) return cors(json(data || { error: 'bad response' }, 502), env, request);

  // NB: identify is NOT logged. The wheel polls /identify every few seconds while listening, so
  // logging here over-counted usage many times over. The browser posts the final locked result to
  // /result once per session instead (handleResult).
  return cors(json(data), env, request);
}

// POST /result — log ONE row per finished session (the locked result, or a no-prediction). The
// browser sends the same result-metadata shape /identify returns (top3, tonic_hz, heard_seconds,
// no_prediction). No audio, never PII.
async function handleResult(request, env, ctx) {
  let data;
  try { data = await request.json(); }
  catch { return cors(json({ error: 'expected json' }, 400), env, request); }
  if (env.DB) ctx.waitUntil(logToD1(env, data, request));
  return cors(json({ ok: true }), env, request);
}

async function logToD1(env, data, request) {
  const top = (data.top3 && data.top3[0]) || null;
  try {
    await env.DB.prepare(
      `INSERT INTO identifications (ts, top1, confidence, top3, tonic_hz, heard_s, no_prediction, country, referrer)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      new Date().toISOString(),
      top ? top.raaga : null,
      top ? top.confidence : null,
      JSON.stringify(data.top3 || []),
      data.tonic_hz ?? null,
      data.heard_seconds ?? null,
      data.no_prediction ? 1 : 0,
      (request.cf && request.cf.country) || null,
      cleanReferrer(data.referrer)
    ).run();
  } catch {
    /* logging must never break recognition */
  }
}

// POST /event — log ONE row per funnel step a visitor reaches. /result tells us about sessions
// that finished; this tells us about the ones that did not, which is the larger number. Without it
// "100 visitors, 0 recognitions" cannot be read: we cannot separate never-tapped-the-orb from
// tapped-then-gave-up-waiting, and those need opposite fixes. No audio, no PII; `session` is an
// anonymous per-tab token that dies with the tab (see sid() in site/index.html).
const FUNNEL_EVENTS = new Set([
  'view',          // the recognizer page rendered and ran its script (so: a human, not a crawler)
  'listen_start',  // tapped the orb, or picked a file
  'mic_denied',    // asked for the microphone and was refused
  'result',        // a result was shown (a lock, an abstention, or a no-prediction)
]);

async function handleEvent(request, env, ctx) {
  let data;
  try { data = await request.json(); }
  catch { return cors(json({ error: 'expected json' }, 400), env, request); }
  // Unknown step names are dropped, not stored: the allowlist is what keeps this table a funnel
  // rather than an open write endpoint. Still a 200, because analytics must never surface to the
  // page as an error.
  if (env.DB && FUNNEL_EVENTS.has(data.event)) ctx.waitUntil(logEvent(env, data, request));
  return cors(json({ ok: true }), env, request);
}

async function logEvent(env, data, request) {
  try {
    await env.DB.prepare(
      `INSERT INTO events (ts, event, session, source, country, referrer)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(
      new Date().toISOString(),
      data.event,
      cleanId(data.session),
      cleanSource(data.source),
      (request.cf && request.cf.country) || null,
      cleanReferrer(data.referrer)
    ).run();
  } catch {
    /* logging must never break the page */
  }
}

// The anonymous per-tab funnel id. Accept a short alphanumeric token and nothing else: dropping a
// malformed id costs one row of funnel data, whereas storing whatever was posted would turn this
// column into free-form storage (and a place to smuggle an identity we promised not to keep).
function cleanId(v) {
  if (typeof v !== 'string') return null;
  const s = v.trim().slice(0, 32);
  return /^[a-z0-9]+$/i.test(s) ? s : null;
}

// Which entry point the step came through. A closed enum, so it stays a dimension we can group by.
function cleanSource(v) {
  return v === 'live' || v === 'file' ? v : null;
}

// Acquisition referrer, HOST only. The page sends document.referrer's hostname (see logResult in
// site/index.html); this is defence-in-depth so a hand-crafted POST can't smuggle a full URL with a
// path/query (potential PII) into the log. Reduce anything to its host, cap length, '' -> NULL.
function cleanReferrer(v) {
  if (typeof v !== 'string') return null;
  let s = v.trim();
  if (!s) return null;
  try { if (s.includes('://')) s = new URL(s).hostname; } catch { /* not a URL, fall through */ }
  s = s.split('/')[0].split('?')[0].split('#')[0].slice(0, 120);
  return s || null;
}

// POST /contribute — an explicit, opt-in donation to the commons. The rights gate is enforced
// HERE (server-side), not just in the UI. The clip is stored privately in R2 (to improve the model
// and for human verification); we publish the model + non-reconstructable features, not the audio,
// unless release_public=1. Row lands split='pending' and never trains until verified.
async function handleContribute(request, env, ctx) {
  let form;
  try { form = await request.formData(); }
  catch { return cors(json({ error: 'expected multipart/form-data' }, 400), env, request); }

  const audio = form.get('audio');
  const raaga = (form.get('raaga') || '').toString().trim();
  const isOwn = form.get('is_own') === 'true' || form.get('is_own') === '1';
  if (!audio || typeof audio === 'string') return cors(json({ error: 'no audio' }, 400), env, request);
  if (!isOwn) return cors(json({ error: 'rights not attested' }, 403), env, request);
  if (!raaga) return cors(json({ error: 'no raaga' }, 400), env, request);

  const bytes = await audio.arrayBuffer();
  const sha = await sha256hex(bytes);
  const mime = audio.type || 'audio/webm';
  const key = `contrib/${new Date().toISOString().slice(0, 10)}/${sha.slice(0, 20)}.${extForType(mime)}`;
  const modelPred = (form.get('model_pred') || '').toString() || null;
  const meta = {
    key, sha, raaga, model_pred: modelPred,
    confidence: numOrNull(form.get('confidence')),
    tonic_hz: numOrNull(form.get('tonic_hz')),
    instrument: (form.get('instrument') || '').toString().slice(0, 40) || null,
    release_public: (form.get('release_public') === 'true' || form.get('release_public') === '1') ? 1 : 0,
    label_source: modelPred && modelPred === raaga ? 'model_confirmed' : 'contributor_declared',
    consent_version: (form.get('consent_version') || '').toString().slice(0, 40) || null,
    country: (request.cf && request.cf.country) || null,
  };
  if (env.CLIPS) ctx.waitUntil(env.CLIPS.put(key, bytes, { httpMetadata: { contentType: mime } })
    .catch((e) => console.error('contribute: R2 put failed', { err: String((e && e.message) || e), key })));
  if (env.DB) ctx.waitUntil(insertContribution(env, meta));
  return cors(json({ ok: true, status: 'queued' }), env, request);
}

function numOrNull(v) { const n = parseFloat(v); return Number.isFinite(n) ? n : null; }

// Map an audio MIME type to a file extension, so a stored clip is named for what it actually is
// (an MP3 upload is saved .mp3, not .webm). ffmpeg reads by content, so this is just for a tidy,
// honestly-named commons dataset. Unknown types fall back to webm (the browser mic default).
function extForType(t) {
  const m = (t || '').split(';')[0].trim().toLowerCase();
  return {
    'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/opus': 'opus',
    'audio/mp4': 'm4a', 'audio/x-m4a': 'm4a', 'audio/aac': 'aac',
    'audio/mpeg': 'mp3', 'audio/mp3': 'mp3',
    'audio/wav': 'wav', 'audio/x-wav': 'wav', 'audio/wave': 'wav', 'audio/vnd.wave': 'wav',
    'audio/flac': 'flac', 'audio/x-flac': 'flac',
    'audio/3gpp': '3gp', 'audio/amr': 'amr',
  }[m] || 'webm';
}

async function sha256hex(buf) {
  const h = await crypto.subtle.digest('SHA-256', buf);
  return [...new Uint8Array(h)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function insertContribution(env, m) {
  try {
    const dup = await env.DB.prepare('SELECT 1 FROM contributions WHERE audio_sha256 = ? LIMIT 1').bind(m.sha).first();
    if (dup) return;                                         // idempotent: same clip donated twice
    await env.DB.prepare(
      `INSERT INTO contributions
         (ts, r2_key, audio_sha256, raaga, label_source, model_pred, confidence, tonic_hz,
          instrument, is_own, license, release_public, consent_version, country, split)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'CC-BY-4.0', ?, ?, ?, 'pending')`
    ).bind(
      new Date().toISOString(), m.key, m.sha, m.raaga, m.label_source, m.model_pred,
      m.confidence, m.tonic_hz, m.instrument, m.release_public, m.consent_version, m.country
    ).run();
  } catch (e) {
    // Best-effort insert (never break the contributor's UX), but do NOT swallow silently:
    // log so a failed write shows up in `wrangler tail` instead of a contribution vanishing.
    console.error('contribute: insertContribution failed',
      { err: String((e && e.message) || e), r2_key: m.key, raaga: m.raaga });
  }
}

// Test-only surface (cloudflare/worker/test/worker.test.mjs). The Workers runtime only ever reads
// the default export above; naming these as well costs nothing at runtime and lets the sanitizers
// that guard the D1 columns be unit-tested directly.
export { cleanReferrer, cleanId, cleanSource, FUNNEL_EVENTS };
