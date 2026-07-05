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

    if (request.method === 'OPTIONS') return cors(new Response(null, { status: 204 }), env);

    // match /identify and /health with or without the /api prefix, so the same worker serves both
    // same-origin (twelveswaras.com/api/identify) and the direct staging URL (…workers.dev/identify)
    if (request.method === 'POST' && url.pathname.endsWith('/identify')) {
      return handleIdentify(request, env, ctx);
    }
    if (url.pathname.endsWith('/health')) {
      try {
        const r = await fetch(env.SPACE_URL + '/health');
        return cors(json(await r.json()), env);
      } catch {
        return cors(json({ status: 'backend unavailable' }, 502), env);
      }
    }
    return cors(json({ error: 'not found', path: url.pathname }, 404), env);
  },
};

function cors(resp, env) {
  const h = new Headers(resp.headers);
  h.set('Access-Control-Allow-Origin', env.ALLOW_ORIGIN || '*');
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
    return cors(json({ error: 'expected multipart/form-data with an "audio" field' }, 400), env);
  }
  const audio = form.get('audio');
  if (!audio || typeof audio === 'string') return cors(json({ error: 'no audio' }, 400), env);

  // forward to the headless recognizer
  const fwd = new FormData();
  fwd.append('audio', audio, 'clip.webm');
  let data;
  try {
    const r = await fetch(env.SPACE_URL + '/identify', { method: 'POST', body: fwd });
    data = await r.json();
  } catch {
    return cors(json({ error: 'recognizer unavailable' }, 502), env);
  }

  if (!data || data.error) return cors(json(data || { error: 'bad response' }, 502), env);

  // result-metadata logging (no audio) — never block the response on it
  if (env.DB) ctx.waitUntil(logToD1(env, data, request));

  // opt-in contribution to the CC-BY commons: ONLY when the client explicitly consented
  if (env.CLIPS && form.get('contribute') === 'yes' && data.top3 && data.top3[0]) {
    ctx.waitUntil(storeContribution(env, audio, data));
  }

  return cors(json(data), env);
}

async function logToD1(env, data, request) {
  const top = (data.top3 && data.top3[0]) || null;
  try {
    await env.DB.prepare(
      `INSERT INTO identifications (ts, top1, confidence, top3, tonic_hz, heard_s, no_prediction, country)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
    ).bind(
      new Date().toISOString(),
      top ? top.raaga : null,
      top ? top.confidence : null,
      JSON.stringify(data.top3 || []),
      data.tonic_hz ?? null,
      data.heard_seconds ?? null,
      data.no_prediction ? 1 : 0,
      (request.cf && request.cf.country) || null
    ).run();
  } catch {
    /* logging must never break recognition */
  }
}

async function storeContribution(env, audio, data) {
  try {
    const key = `contrib/${new Date().toISOString().slice(0, 10)}/${crypto.randomUUID()}.webm`;
    await env.CLIPS.put(key, await audio.arrayBuffer(), {
      httpMetadata: { contentType: audio.type || 'audio/webm' },
    });
    if (env.DB) {
      await env.DB.prepare(
        `INSERT INTO contributions (ts, r2_key, declared_raaga, confidence) VALUES (?, ?, ?, ?)`
      ).bind(new Date().toISOString(), key, data.top3[0].raaga, data.top3[0].confidence).run();
    }
  } catch {
    /* contribution is best-effort */
  }
}
