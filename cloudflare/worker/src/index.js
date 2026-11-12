/**
 * twelveswaras API edge worker.
 *
 * The browser talks only to this worker (same-origin via a route on twelveswaras.com), so there is
 * no cross-origin iframe and no CORS pain. The worker:
 *   - forwards the audio to the recognizer container (server-to-server),
 *   - logs RESULT METADATA ONLY to D1 (never the audio — privacy is the product),
 *   - optionally stores an opt-in clip to R2 for the CC-BY commons (only when the client consents),
 *   - returns the JSON to the page.
 *
 * Bindings (wrangler.toml): SPACE_URL (var, the recognizer's URL), ALLOW_ORIGIN (var), DB (D1),
 * CLIPS (R2).
 */

import { handleMcp } from './mcp.js';

export default {
  async fetch(request, env, ctx) {
    // the MCP server answers any origin (agents and their inspectors), so it sets its own CORS
    if (new URL(request.url).pathname.endsWith('/mcp')) {
      return handleMcp(request, env, ctx, (event) => insertEvent(env, {
        event, session: null, source: 'mcp', country: country(request), referrer: null }));
    }
    return cors(await route(request, env, ctx), env, request);
  },
};

async function route(request, env, ctx) {
  const url = new URL(request.url);

  if (request.method === 'OPTIONS') return new Response(null, { status: 204 });

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
    return proxyRecognizerGet('/health', { status: 'backend unavailable' }, 502, env);
  }
  // The page pings this on load. A sleeping recognizer took 42.6 s to give its first answer, and
  // most visitors gave up inside that window; waking it while they read the page moves that wait
  // off their critical path. Deliberately not logged: it is not usage.
  if (url.pathname.endsWith('/warm')) {
    return proxyRecognizerGet('/warm', { warm: false }, 503, env);
  }
  return json({ error: 'not found', path: url.pathname }, 404);
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

const country = (request) => (request.cf && request.cf.country) || null;
const errText = (e) => String((e && e.message) || e);
const isTrue = (v) => v === 'true' || v === '1';
// A free-text form field, bounded: at most n characters, '' -> NULL.
const field = (form, name, n) => (form.get(name) || '').toString().trim().slice(0, n) || null;
async function jsonBody(request) {
  try { return await request.json(); } catch { return undefined; }
}

// One row in the events table. Best effort: analytics must never break a reply.
async function insertEvent(env, row) {
  try {
    await env.DB.prepare(
      `INSERT INTO events (ts, event, session, source, country, referrer) VALUES (?, ?, ?, ?, ?, ?)`
    ).bind(new Date().toISOString(), row.event, row.session, row.source, row.country, row.referrer).run();
  } catch { /* D1 unavailable */ }
}

// A failed recognition: why, in Workers Logs (with the detail) and as one events row (the reason
// only, with country; no audio, no session) so the ops dashboard can count failures by reason.
// Best effort: recording it must never change the reply.
function identifyFailed(env, ctx, request, reason, detail) {
  console.error(`identify failed: ${reason}: ${String(detail).slice(0, 200)}`);
  try {
    ctx.waitUntil(insertEvent(env, { event: 'identify_failed', session: null, source: reason.slice(0, 40),
      country: country(request), referrer: null }));
  } catch { /* no DB binding: the log line above still has it */ }
}

// GET a recognizer endpoint and relay its JSON, or a fixed fallback if it is unreachable.
async function proxyRecognizerGet(path, fallback, fallbackStatus, env) {
  try {
    const r = await fetch(env.SPACE_URL + path);
    return json(await r.json());
  } catch {
    return json(fallback, fallbackStatus);
  }
}

async function handleIdentify(request, env, ctx) {
  let form;
  try {
    form = await request.formData();
  } catch {
    return json({ error: 'expected multipart/form-data with an "audio" field' }, 400);
  }
  const audio = form.get('audio');
  if (!audio || typeof audio === 'string') return json({ error: 'no audio' }, 400);

  // forward to the headless recognizer
  const fwd = new FormData();
  fwd.append('audio', audio, 'clip.webm');
  let r;
  try {
    r = await fetch(env.SPACE_URL + '/identify', { method: 'POST', body: fwd });
  } catch (e) {
    identifyFailed(env, ctx, request, 'unreachable', errText(e));
    return json({ error: 'recognizer unavailable' }, 502);
  }
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); }
  catch {
    // e.g. the container restarting answers with a plain-text error page
    identifyFailed(env, ctx, request, `bad_reply:${r.status}`, text);
    return json({ error: 'recognizer unavailable' }, 502);
  }

  if (!data || data.error) {
    // A clip the recognizer rejects (400 "could not decode audio") is the clip's problem, not a
    // server error: keep its status. Anything else from the recognizer is a 502.
    const rejected = r.status >= 400 && r.status < 500;
    identifyFailed(env, ctx, request, `${rejected ? 'rejected' : 'error'}:${r.status}`, (data && data.error) || 'empty reply');
    return json(data || { error: 'bad response' }, rejected ? r.status : 502);
  }

  // NB: identify is NOT logged. The wheel polls /identify every few seconds while listening, so
  // logging here over-counted usage many times over. The browser posts the final locked result to
  // /result once per session instead (handleResult).
  return json(data);
}

// POST /result — log ONE row per finished session (the locked result, or a no-prediction). The
// browser sends the same result-metadata shape /identify returns (top3, tonic_hz, heard_seconds,
// no_prediction). No audio, never PII.
async function handleResult(request, env, ctx) {
  const data = await jsonBody(request);
  if (data === undefined) return json({ error: 'expected json' }, 400);
  if (env.DB) ctx.waitUntil(logToD1(env, data, request));
  return json({ ok: true });
}

// A closed set, so a malformed/hostile body cannot write arbitrary strings into the column.
// too_short / tonic_failed / no_windows come from the recognizer. not_sent / no_reply come from the
// page: the session ended before any audio was sent, or audio was sent and no answer came back.
const RESULT_REASONS = new Set(['too_short', 'tonic_failed', 'no_windows', 'not_sent', 'no_reply']);
const NAME_MAX = 80;   // a raaga name is never this long; the cap keeps the columns from being storage

// The posted top-3, reduced to what it is: at most 3 {raaga, tradition, confidence}, bounded. The
// tradition is kept because a name like Tōḍī or Śrī exists in both traditions.
function cleanTop3(v) {
  if (!Array.isArray(v)) return [];
  return v.slice(0, 3).filter((e) => e && typeof e.raaga === 'string')
    .map((e) => ({ raaga: e.raaga.slice(0, NAME_MAX), tradition: cleanTradition(e.tradition),
      confidence: numOrNull(e.confidence) }));
}

async function logToD1(env, data, request) {
  const top3 = cleanTop3(data.top3);
  const top = top3[0] || null;
  try {
    await env.DB.prepare(
      `INSERT INTO identifications (ts, top1, confidence, top3, tonic_hz, heard_s, no_prediction, country, referrer, source, elapsed_s, reason)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      new Date().toISOString(),
      top ? top.raaga : null,
      top ? top.confidence : null,
      JSON.stringify(top3),
      numOrNull(data.tonic_hz),
      numOrNull(data.heard_seconds),
      data.no_prediction ? 1 : 0,
      country(request),
      cleanReferrer(data.referrer),
      // heard_s is now the SERVER's analysed seconds; elapsed_s keeps the browser wall-clock
      // separately so the two are never conflated again, and `source` tells them apart (an
      // upload's elapsed is processing time, not audio duration). `reason` says why a
      // no-prediction happened, which was previously unrecorded and unknowable.
      cleanSource(data.source),
      typeof data.elapsed_s === 'number' ? data.elapsed_s : null,
      RESULT_REASONS.has(data.reason) ? data.reason : null
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
  'mic_denied',    // asked for the microphone and was refused (any cause; one of the four below follows)
  'mic_blocked',   //   the browser or the visitor blocked it; a retry cannot fix this
  'mic_missing',   //   no microphone on the device
  'mic_busy',      //   another app holds it
  'mic_unsupported', // the browser cannot record at all (often a browser built into another app)
  'result',        // a result was shown (a lock, an abstention, or a no-prediction)
  'share',         // shared a named result (share sheet or copied link)
  'correct_open',  // opened "Wrong? Correct it" / "Know this raaga?" under a result
  'correct_sent',  // a correction or confirmation from a result was accepted
  'contribute_view', // the contribute page rendered (site/contribute/)
  'contribute_sent', // a recording from the contribute page was accepted
]);

async function handleEvent(request, env, ctx) {
  const data = await jsonBody(request);
  if (data === undefined) return json({ error: 'expected json' }, 400);
  // Unknown step names are dropped, not stored: the allowlist is what keeps this table a funnel
  // rather than an open write endpoint. Still a 200, because analytics must never surface to the
  // page as an error.
  if (env.DB && data && FUNNEL_EVENTS.has(data.event)) {
    ctx.waitUntil(insertEvent(env, { event: data.event, session: cleanId(data.session),
      source: cleanSource(data.source), country: country(request), referrer: cleanReferrer(data.referrer) }));
  }
  return json({ ok: true });
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

// A contribution's musical tradition. Closed enum; anything else (incl. an "Another raaga" pick
// with no group) stores NULL rather than free text.
function cleanTradition(v) {
  return v === 'carnatic' || v === 'hindustani' ? v : null;
}

// A contributor's optional PUBLIC credit (name or handle), shown in CONTRIBUTORS.md and, for a
// CC-BY-released clip, alongside it in the commons dataset. Free text by nature, so this is the one
// contribution column we deliberately store as typed, but bounded: control chars and newlines
// collapse to a single space (a credit is one line, never a place to smuggle markup or a payload),
// length is capped, and empty -> NULL, which is the default (anonymous). Never an email: we ask for
// a display name only, and do not validate/keep anything that looks like contact info here.
function cleanCredit(v) {
  if (typeof v !== 'string') return null;
  const s = v.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 80);
  return s || null;
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
const MAX_AUDIO_BYTES = 26 * 1024 * 1024;   // the contribute page accepts files up to 25 MB

async function handleContribute(request, env, ctx) {
  let form;
  try { form = await request.formData(); }
  catch { return json({ error: 'expected multipart/form-data' }, 400); }

  const audio = form.get('audio');
  const raaga = field(form, 'raaga', NAME_MAX);
  if (!audio || typeof audio === 'string') return json({ error: 'no audio' }, 400);
  if (!isTrue(form.get('is_own'))) return json({ error: 'rights not attested' }, 403);
  if (!raaga) return json({ error: 'no raaga' }, 400);
  if (audio.size > MAX_AUDIO_BYTES) return json({ error: 'audio too large' }, 413);

  const bytes = await audio.arrayBuffer();
  const sha = await sha256hex(bytes);
  const mime = audio.type || 'audio/webm';
  const key = `contrib/${new Date().toISOString().slice(0, 10)}/${sha.slice(0, 20)}.${extForType(mime)}`;
  const modelPred = field(form, 'model_pred', NAME_MAX);
  const meta = {
    key, sha, raaga, model_pred: modelPred,
    confidence: numOrNull(form.get('confidence')),
    tonic_hz: numOrNull(form.get('tonic_hz')),
    instrument: field(form, 'instrument', 40),
    release_public: isTrue(form.get('release_public')) ? 1 : 0,
    label_source: modelPred && modelPred === raaga ? 'model_confirmed' : 'contributor_declared',
    consent_version: field(form, 'consent_version', 40),
    country: country(request),
    tradition: cleanTradition(form.get('tradition')),
    credit: cleanCredit(form.get('credit')),
  };
  if (env.CLIPS) ctx.waitUntil(env.CLIPS.put(key, bytes, { httpMetadata: { contentType: mime } })
    .catch((e) => console.error('contribute: R2 put failed', { err: errText(e), key })));
  if (env.DB) ctx.waitUntil(insertContribution(env, meta));
  return json({ ok: true, status: 'queued' });
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
          instrument, is_own, license, release_public, consent_version, country, tradition, credit, split)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'CC-BY-4.0', ?, ?, ?, ?, ?, 'pending')`
    ).bind(
      new Date().toISOString(), m.key, m.sha, m.raaga, m.label_source, m.model_pred,
      m.confidence, m.tonic_hz, m.instrument, m.release_public, m.consent_version, m.country, m.tradition, m.credit
    ).run();
  } catch (e) {
    // Best-effort insert (never break the contributor's UX), but do NOT swallow silently:
    // log so a failed write shows up in `wrangler tail` instead of a contribution vanishing.
    console.error('contribute: insertContribution failed',
      { err: errText(e), r2_key: m.key, raaga: m.raaga });
  }
}

// Test-only surface (cloudflare/worker/test/worker.test.mjs). The Workers runtime only ever reads
// the default export above; naming these as well costs nothing at runtime and lets the sanitizers
// that guard the D1 columns be unit-tested directly.
export { cleanReferrer, cleanId, cleanSource, cleanTradition, cleanCredit, FUNNEL_EVENTS };
