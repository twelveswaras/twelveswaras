// Unit tests for the worker's logging surface. These cover the sanitizers that stand between an
// arbitrary POST and a D1 column, plus the /event allowlist, without a Worker runtime or a network:
// the module is imported directly and D1 is a stub that records what it was asked to insert.
//
//   node --test cloudflare/worker/test/
import test from 'node:test';
import assert from 'node:assert/strict';

import worker, { cleanReferrer, cleanId, cleanSource, cleanTradition, cleanCredit, FUNNEL_EVENTS } from '../src/index.js';

// A D1 stub shaped like the bits of the real binding the worker uses: prepare().bind().run().
// `rows` collects the bound values of every insert so a test can assert what was written.
function stubDB() {
  const rows = [];
  return {
    rows,
    prepare(sql) {
      return {
        bind(...values) {
          return {
            run: async () => { rows.push({ sql, values }); return { success: true }; },
            first: async () => null,                  // the contribute dedup lookup: never a duplicate
          };
        },
      };
    },
  };
}

function postJSON(path, body) {
  return new Request('https://twelveswaras.com' + path, {
    method: 'POST',
    headers: { 'content-type': 'application/json', Origin: 'https://twelveswaras.com' },
    body: JSON.stringify(body),
  });
}

// waitUntil has to actually be awaited, otherwise the insert races the assertion.
function stubCtx() {
  const pending = [];
  return { waitUntil: (p) => pending.push(p), settle: () => Promise.all(pending) };
}

const ENV = { ALLOW_ORIGIN: 'https://twelveswaras.com', SPACE_URL: 'https://example.invalid' };

// ---- cleanReferrer ---------------------------------------------------------------------------
// The page already sends a bare host, so this is defence-in-depth: a hand-crafted POST must not be
// able to land a full URL (path + query, potentially PII) in the log.
test('cleanReferrer keeps a bare host', () => {
  assert.equal(cleanReferrer('www.google.com'), 'www.google.com');
  assert.equal(cleanReferrer('t.co'), 't.co');
});

test('cleanReferrer reduces a full URL to its host and drops the query string', () => {
  assert.equal(cleanReferrer('https://www.google.com/search?q=leaked+secret'), 'www.google.com');
  assert.equal(cleanReferrer('http://news.ycombinator.com/item?id=1#c2'), 'news.ycombinator.com');
});

test('cleanReferrer strips a path/query smuggled in without a scheme', () => {
  assert.equal(cleanReferrer('evil.example/path?token=abc'), 'evil.example');
  assert.equal(cleanReferrer('evil.example#frag'), 'evil.example');
});

test('cleanReferrer maps empty and non-string input to null (direct visit)', () => {
  assert.equal(cleanReferrer(''), null);
  assert.equal(cleanReferrer('   '), null);
  assert.equal(cleanReferrer(undefined), null);
  assert.equal(cleanReferrer(null), null);
  assert.equal(cleanReferrer(42), null);
  assert.equal(cleanReferrer({ toString: () => 'x.com' }), null);
});

test('cleanReferrer caps length so the column cannot be used as storage', () => {
  assert.equal(cleanReferrer('a'.repeat(500)).length, 120);
});

// ---- cleanId ---------------------------------------------------------------------------------
// The funnel session id is an anonymous per-tab token. Anything that is not a short alphanumeric
// token is dropped rather than stored, so the column cannot carry a payload or a smuggled identity.
test('cleanId accepts a short alphanumeric token', () => {
  assert.equal(cleanId('k3f9a1b2c4d5e6f7'), 'k3f9a1b2c4d5e6f7');
});

test('cleanId rejects anything that is not alphanumeric', () => {
  assert.equal(cleanId('has-a-dash'), null);
  assert.equal(cleanId('user@example.com'), null);
  assert.equal(cleanId('<script>'), null);
  assert.equal(cleanId('a b'), null);
  assert.equal(cleanId(''), null);
  assert.equal(cleanId(undefined), null);
  assert.equal(cleanId(12345), null);
});

test('cleanId truncates before validating, so an over-long token is rejected not silently cut', () => {
  // 40 chars of valid alphanumeric: the first 32 are kept and still valid.
  assert.equal(cleanId('a'.repeat(40)), 'a'.repeat(32));
  // ...but padding a payload past the cap must not sneak the payload in.
  assert.equal(cleanId('a'.repeat(31) + '<script>'), null);
});

// ---- cleanSource -----------------------------------------------------------------------------
test('cleanSource is a closed enum (live, file, cli) and nulls everything else', () => {
  assert.equal(cleanSource('live'), 'live');
  assert.equal(cleanSource('file'), 'file');
  assert.equal(cleanSource('cli'), 'cli');            // the twelveswaras command line (cli/)
  assert.equal(cleanSource('CLI'), null);
  assert.equal(cleanSource('other'), null);
  assert.equal(cleanSource(''), null);
  assert.equal(cleanSource(undefined), null);
});

// ---- cleanTradition --------------------------------------------------------------------------
test('cleanTradition is a two-value enum, everything else NULL', () => {
  assert.equal(cleanTradition('carnatic'), 'carnatic');
  assert.equal(cleanTradition('hindustani'), 'hindustani');
  assert.equal(cleanTradition('western'), null);
  assert.equal(cleanTradition(''), null);
  assert.equal(cleanTradition(undefined), null);
});

// ---- cleanCredit -----------------------------------------------------------------------------
// The one contribution column that stores free text (an optional public display credit). It must
// keep a normal name/handle intact, collapse to a single line, cap length, and map empty -> NULL.
test('cleanCredit keeps a normal name or handle', () => {
  assert.equal(cleanCredit('Skanda (Shaale)'), 'Skanda (Shaale)');
  assert.equal(cleanCredit('@some_handle'), '@some_handle');
});

test('cleanCredit trims and collapses internal whitespace to one line', () => {
  assert.equal(cleanCredit('  Ravi   Kumar  '), 'Ravi Kumar');
  assert.equal(cleanCredit('line one\nline two\tx'), 'line one line two x');
});

test('cleanCredit maps empty and non-string input to null (anonymous, the default)', () => {
  assert.equal(cleanCredit(''), null);
  assert.equal(cleanCredit('   '), null);
  assert.equal(cleanCredit(undefined), null);
  assert.equal(cleanCredit(null), null);
  assert.equal(cleanCredit(42), null);
});

test('cleanCredit caps length so the column cannot be used as storage', () => {
  assert.equal(cleanCredit('a'.repeat(300)).length, 80);
});

// ---- POST /event -----------------------------------------------------------------------------
test('POST /event logs an allowlisted funnel step', async () => {
  const db = stubDB();
  const ctx = stubCtx();
  const res = await worker.fetch(
    postJSON('/api/event', { event: 'listen_start', session: 'abc123', source: 'live', referrer: 'www.google.com' }),
    { ...ENV, DB: db }, ctx);
  await ctx.settle();

  assert.equal(res.status, 200);
  assert.equal(db.rows.length, 1);
  const [ts, event, session, source, country, referrer] = db.rows[0].values;
  assert.match(ts, /^\d{4}-\d{2}-\d{2}T/);
  assert.equal(event, 'listen_start');
  assert.equal(session, 'abc123');
  assert.equal(source, 'live');
  assert.equal(country, null);              // no request.cf outside the Workers runtime
  assert.equal(referrer, 'www.google.com');
});

test('POST /event drops an event name that is not on the allowlist', async () => {
  const db = stubDB();
  const ctx = stubCtx();
  const res = await worker.fetch(
    postJSON('/api/event', { event: 'arbitrary_junk', session: 'abc123' }), { ...ENV, DB: db }, ctx);
  await ctx.settle();

  assert.equal(res.status, 200);            // never look like an error to the page
  assert.equal(db.rows.length, 0);          // ...but nothing is written
});

test('POST /event sanitizes a hostile payload rather than rejecting it', async () => {
  const db = stubDB();
  const ctx = stubCtx();
  await worker.fetch(
    postJSON('/api/event', {
      event: 'view',
      session: 'not a valid id',
      source: 'sneaky',
      referrer: 'https://evil.example/path?token=abc',
    }), { ...ENV, DB: db }, ctx);
  await ctx.settle();

  const [, event, session, source, , referrer] = db.rows[0].values;
  assert.equal(event, 'view');
  assert.equal(session, null);
  assert.equal(source, null);
  assert.equal(referrer, 'evil.example');
});

test('POST /event with a malformed body is a 400 and writes nothing', async () => {
  const db = stubDB();
  const ctx = stubCtx();
  const req = new Request('https://twelveswaras.com/api/event', {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: 'not json',
  });
  const res = await worker.fetch(req, { ...ENV, DB: db }, ctx);
  await ctx.settle();

  assert.equal(res.status, 400);
  assert.equal(db.rows.length, 0);
});

test('the funnel allowlist is exactly the steps the pages can reach', () => {
  assert.deepEqual([...FUNNEL_EVENTS].sort(), [
    'contribute_sent', 'contribute_view', 'correct_open', 'correct_sent',
    'listen_start', 'mic_blocked', 'mic_busy', 'mic_denied', 'mic_missing', 'mic_unsupported',
    'result', 'share', 'view',
  ]);
});

// ---- POST /result telemetry columns ------------------------------------------------------------
// heard_s used to receive the BROWSER's wall-clock, which for an upload is processing time, not
// audio duration. Conflating the two made our biggest failure mode (~46% of sessions end with no
// prediction) unreadable, so the server's analysed seconds, the browser elapsed, the source and the
// failure reason are now separate columns.
test('POST /result records source, elapsed_s and the no-prediction reason', async () => {
  const db = stubDB();
  const ctx = stubCtx();
  const res = await worker.fetch(
    postJSON('/api/result', {
      top3: [], no_prediction: 1, tonic_hz: null,
      heard_seconds: 42.5, elapsed_s: 118.2, source: 'live', reason: 'tonic_failed',
    }), { ...ENV, DB: db }, ctx);
  await ctx.settle();

  assert.equal(res.status, 200);
  assert.equal(db.rows.length, 1);
  const v = db.rows[0].values;
  assert.equal(v[5], 42.5);            // heard_s  = the SERVER's analysed seconds
  assert.equal(v[6], 1);               // no_prediction
  assert.equal(v[9], 'live');          // source
  assert.equal(v[10], 118.2);          // elapsed_s = browser wall-clock, kept separate
  assert.equal(v[11], 'tonic_failed'); // reason
});

test('POST /result rejects an unknown source or reason rather than storing it', async () => {
  const db = stubDB();
  const ctx = stubCtx();
  await worker.fetch(
    postJSON('/api/result', {
      top3: [], no_prediction: 1,
      source: '../../etc/passwd', reason: 'DROP TABLE', elapsed_s: 'not-a-number',
    }), { ...ENV, DB: db }, ctx);
  await ctx.settle();

  const v = db.rows[0].values;
  assert.equal(v[9], null);            // source  outside the allowlist -> NULL
  assert.equal(v[10], null);           // elapsed_s non-numeric        -> NULL
  assert.equal(v[11], null);           // reason  outside the allowlist -> NULL
});

// ---- POST /identify failures -------------------------------------------------------------------
// A failed recognition used to be one opaque 502 "recognizer unavailable", whatever happened. Each
// failure now records WHY (one events row, no audio, no session) and a clip the recognizer rejects
// keeps its own status, so a bad clip never reads as a server error.
function identifyRequest(filename = 'clip.webm', ip = null) {
  const fd = new FormData();
  fd.append('audio', new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm' }), filename);
  const headers = { Origin: 'https://twelveswaras.com' };
  if (ip) headers['cf-connecting-ip'] = ip;
  return new Request('https://twelveswaras.com/api/identify', { method: 'POST', body: fd, headers });
}
async function identifyWith(fakeFetch, request = identifyRequest()) {
  const realFetch = globalThis.fetch, realError = console.error;
  const logged = [];
  globalThis.fetch = fakeFetch;
  console.error = (...a) => logged.push(a.join(' '));
  try {
    const DB = stubDB(), ctx = stubCtx();
    const res = await worker.fetch(request, { ...ENV, DB }, ctx);
    await ctx.settle();
    return { res, body: await res.json(), rows: DB.rows, logged };
  } finally {
    globalThis.fetch = realFetch; console.error = realError;
  }
}
const failureRow = (rows) => rows.find((r) => r.sql.includes('INSERT INTO events'));

test('identify: recognizer unreachable → 502, recorded as unreachable', async () => {
  const { res, rows, logged } = await identifyWith(async () => { throw new TypeError('Network connection lost'); });
  assert.equal(res.status, 502);
  const row = failureRow(rows);
  assert.equal(row.values[1], 'identify_failed');
  assert.equal(row.values[3], 'unreachable');
  assert.match(logged.join('\n'), /unreachable.*Network connection lost/);
});

test('identify: a reply that is not JSON (container restarting) → 502, recorded with its status', async () => {
  const { res, rows, logged } = await identifyWith(async () => new Response('Container is not running', { status: 503 }));
  assert.equal(res.status, 502);
  assert.equal(failureRow(rows).values[3], 'bad_reply:503');
  assert.match(logged.join('\n'), /bad_reply:503.*Container is not running/);
});

// The recognizer's container sometimes drops a request mid-way ("Container suddenly disconnected,
// try again": 3 of 135 calls on 13 Nov 2026, each fine seconds later). That answer is plain text, so
// it is told apart from the recognizer's own JSON errors; such a reply, or no reply, is tried once more.
function scripted(...replies) {
  const calls = [];
  const fake = async (url, init) => {
    calls.push({ url, audio: init.body.get('audio') });
    const next = replies[Math.min(calls.length - 1, replies.length - 1)];
    return typeof next === 'function' ? next() : next.clone();
  };
  return { fake, calls };
}

test('identify: a dropped container connection is tried once more, and its answer returned', async () => {
  const { fake, calls } = scripted(new Response('Container suddenly disconnected, try again', { status: 500 }),
    Response.json({ top3: [{ raaga: 'Saveri', confidence: 0.8 }], tonic_hz: 140 }));
  const { res, body, rows, logged } = await identifyWith(fake);
  assert.equal(res.status, 200);
  assert.equal(body.top3[0].raaga, 'Saveri');
  assert.equal(calls.length, 2);
  assert.equal((await calls[1].audio.arrayBuffer()).byteLength, 3, 'the second try carries the same clip');
  assert.equal(failureRow(rows), undefined, 'a recovered call is not a failure');
  assert.equal(logged.length, 0);
});

test('identify: an unreachable recognizer is tried once more too', async () => {
  const { fake, calls } = scripted(() => { throw new TypeError('Network connection lost'); }, Response.json({ top3: [], tonic_hz: 140 }));
  const { res } = await identifyWith(fake);
  assert.equal(res.status, 200);
  assert.equal(calls.length, 2);
});

test('identify: only once more: a second failure is a 502, recorded once', async () => {
  const { fake, calls } = scripted(new Response('Container suddenly disconnected, try again', { status: 500 }));
  const { res, rows } = await identifyWith(fake);
  assert.equal(res.status, 502);
  assert.equal(calls.length, 2);
  assert.equal(rows.filter((r) => r.sql.includes('INSERT INTO events')).length, 1);
  assert.equal(failureRow(rows).values[3], 'bad_reply:500');
});

test("identify: the recognizer's own answers are not retried: a rejected clip, or its JSON error", async () => {
  for (const reply of [Response.json({ error: 'could not decode audio' }, { status: 400 }), Response.json({ error: 'model crashed' }, { status: 500 })]) {
    const { fake, calls } = scripted(reply);
    await identifyWith(fake);
    assert.equal(calls.length, 1);
  }
});

test('identify: a clip the recognizer cannot decode keeps its 400, recorded as rejected', async () => {
  const { res, body, rows } = await identifyWith(async () =>
    Response.json({ error: 'could not decode audio', detail: 'x' }, { status: 400 }));
  assert.equal(res.status, 400);
  assert.equal(body.error, 'could not decode audio');
  assert.equal(failureRow(rows).values[3], 'rejected:400');
});

test('identify: a recognizer error reply is a 502, recorded with its status', async () => {
  const { res, rows } = await identifyWith(async () => Response.json({ error: 'model crashed' }, { status: 500 }));
  assert.equal(res.status, 502);
  assert.equal(failureRow(rows).values[3], 'error:500');
});

test('identify: a normal answer records nothing (identify is not logged)', async () => {
  const { res, rows } = await identifyWith(async () => Response.json({ top3: [], tonic_hz: 140 }));
  assert.equal(res.status, 200);
  // the rate limiter's own housekeeping (rate_limits) is not a record of the identification
  assert.equal(rows.filter((r) => !/rate_limits/.test(r.sql)).length, 0);
});

// ---- use by mode: the API ----------------------------------------------------------------------
// The site's own calls (and the command line's) are counted once per finished listen through
// /result, so /identify itself is not logged for them: the page polls it every few seconds. A caller
// that is neither the site nor the command line (a script, another app) never posts /result, so a
// successful identify from one is counted here as api:identify, with nothing about the caller.
function apiIdentify(headers) {
  const fd = new FormData();
  fd.append('audio', new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm' }), 'clip.webm');
  return new Request('https://twelveswaras.com/api/identify', { method: 'POST', body: fd, headers });
}
const OK = async () => Response.json({ top3: [], tonic_hz: 140 });

test('identify from an API caller is counted as api:identify, mode api, nothing about the caller', async () => {
  const { res, rows } = await identifyWith(OK, apiIdentify({ 'user-agent': 'python-requests/2.31', 'cf-connecting-ip': '203.0.113.9' }));
  assert.equal(res.status, 200);
  assert.equal(rows.length, 1);
  const [ts, event, session, source, country, referrer] = rows[0].values;
  assert.match(ts, /^\d{4}-\d\d-\d\dT/);
  assert.deepEqual([event, source, session, country, referrer], ['api:identify', 'api', null, null, null]);
  assert.ok(!JSON.stringify(rows).includes('203.0.113.9') && !JSON.stringify(rows).includes('python'));
});

test('identify from the command line or a bot is not counted here', async () => {
  for (const ua of ['twelveswaras-cli/0.3.0', 'Mozilla/5.0 (compatible; Googlebot/2.1)']) {
    const { res, rows } = await identifyWith(OK, apiIdentify({ 'user-agent': ua }));
    assert.equal(res.status, 200);
    assert.equal(rows.length, 0, ua);
  }
});

test('a failed identify from an API caller is recorded as the failure only, not as use', async () => {
  const { res, rows } = await identifyWith(async () => Response.json({ error: 'model crashed' }, { status: 500 }),
    apiIdentify({ 'user-agent': 'curl/8.4.0' }));
  assert.equal(res.status, 502);
  assert.deepEqual(rows.map((r) => r.values[1]), ['identify_failed']);
});

test('a contribution from an API caller is counted as api:contribute', async () => {
  const fd = new FormData();
  fd.append('audio', new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/webm' }), 'clip.webm');
  fd.append('raaga', 'Mohanam');
  fd.append('is_own', 'true');
  const DB = stubDB(), ctx = stubCtx();
  const res = await worker.fetch(new Request('https://twelveswaras.com/api/contribute', { method: 'POST', body: fd,
    headers: { 'user-agent': 'curl/8.4.0' } }), { ...ENV, DB }, ctx);
  await ctx.settle();
  assert.equal(res.status, 200);
  const use = DB.rows.filter((r) => r.sql.includes('INSERT INTO events')).map((r) => [r.values[1], r.values[3]]);
  assert.deepEqual(use, [['api:contribute', 'api']]);
});

test('identify: recording a failure never breaks the reply (D1 down)', async () => {
  const realFetch = globalThis.fetch, realError = console.error;
  globalThis.fetch = async () => { throw new TypeError('down'); };
  console.error = () => {};
  try {
    const DB = { prepare() { throw new Error('D1 unavailable'); } }, ctx = stubCtx();
    const res = await worker.fetch(identifyRequest(), { ...ENV, DB }, ctx);
    await ctx.settle();
    assert.equal(res.status, 502);
  } finally { globalThis.fetch = realFetch; console.error = realError; }
});

// ---- Workers Logs --------------------------------------------------------------------------------
// Neither worker kept logs, so a failure could only be read live with `wrangler tail`. Both keep
// them now (Workers Logs), which is where identifyFailed's detail lands.
test('both workers keep Workers Logs', async () => {
  const { readFile } = await import('node:fs/promises');
  for (const f of ['../wrangler.toml', '../../recognizer/wrangler.toml']) {
    const toml = await readFile(new URL(f, import.meta.url), 'utf8');
    assert.match(toml, /^\[observability\]\s*\nenabled = true/m, f);
  }
});

// ---- GET /warm: wake the recognizer before the visitor taps ------------------------------------
// A sleeping recognizer took 42.6 s to give its first answer (measured 2026-10-24), and 163 live
// sessions gave up inside that window with nothing. The page pings /warm on load so the wake-up
// happens while the visitor is reading, not while they hold their phone up.
test('GET /api/warm forwards to the recognizer /warm and logs nothing', async () => {
  const db = stubDB();
  const seen = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (u) => { seen.push(String(u)); return new Response('{"warm":true}', { status: 200 }); };
  try {
    const res = await worker.fetch(new Request('https://twelveswaras.com/api/warm'),
      { ...ENV, DB: db, SPACE_URL: 'https://space.invalid' }, stubCtx());
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { warm: true });
  } finally {
    globalThis.fetch = realFetch;
  }
  assert.deepEqual(seen, ['https://space.invalid/warm']);
  assert.equal(db.rows.length, 0, 'a warm-up ping is not usage and must not be logged');
});

test('GET /api/warm degrades quietly when the recognizer is unreachable', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('down'); };
  try {
    const res = await worker.fetch(new Request('https://twelveswaras.com/api/warm'), ENV, stubCtx());
    assert.equal(res.status, 503);
    assert.deepEqual(await res.json(), { warm: false });
  } finally {
    globalThis.fetch = realFetch;
  }
});

// The page now says why a session ended without any reply: it never sent audio (stopped before
// the first send), or it sent and no answer came back in time. Both were NULL before, which hid
// 221 of 262 failures in the first month of this telemetry.
test('POST /result accepts the page-side reasons not_sent and no_reply', async () => {
  for (const reason of ['not_sent', 'no_reply']) {
    const db = stubDB();
    const ctx = stubCtx();
    await worker.fetch(postJSON('/api/result', { top3: [], no_prediction: 1, source: 'live', reason }),
      { ...ENV, DB: db }, ctx);
    await ctx.settle();
    assert.equal(db.rows[0].values[11], reason);
  }
});

// ---- hostile input: nothing unbounded reaches D1 or R2 ---------------------------------------
test('POST /result stores at most 3 bounded {raaga, confidence} entries and numbers only', async () => {
  const db = stubDB();
  const ctx = stubCtx();
  const huge = 'x'.repeat(5000);
  const top3 = Array.from({ length: 10 }, (_, i) => ({ raaga: huge, confidence: i ? 0.1 : 'high', extra: huge }));
  await worker.fetch(postJSON('/api/result', { top3, tonic_hz: 'abc', heard_seconds: { a: 1 } }), { ...ENV, DB: db }, ctx);
  await ctx.settle();
  const v = db.rows[0].values;
  assert.equal(v[1].length, 80);                         // top1, capped
  assert.equal(v[2], null);                              // a non-numeric confidence is not stored
  const stored = JSON.parse(v[3]);
  assert.equal(stored.length, 3);
  assert.deepEqual(Object.keys(stored[0]).sort(), ['confidence', 'raaga', 'tradition']);
  assert.ok(stored.every((e) => e.raaga.length <= 80));
  assert.equal(v[4], null);                              // tonic_hz 'abc'
  assert.equal(v[5], null);                              // heard_seconds object
});

function contribute(fields, bytes = 1000) {
  const fd = new FormData();
  fd.append('audio', new Blob([new Uint8Array(bytes)], { type: 'audio/webm' }), 'clip.webm');
  for (const [k, v] of Object.entries(fields)) fd.append(k, v);
  return new Request('https://twelveswaras.com/api/contribute', { method: 'POST', body: fd, headers: { Origin: 'https://twelveswaras.com' } });
}

function stubR2() {
  const keys = [];
  return { keys, put: async (k) => { keys.push(k); } };
}

test('POST /contribute without the rights attestation is a 403 and stores nothing', async () => {
  const db = stubDB(); const r2 = stubR2(); const ctx = stubCtx();
  const res = await worker.fetch(contribute({ raaga: 'Kalyāṇi' }), { ...ENV, DB: db, CLIPS: r2 }, ctx);
  await ctx.settle();
  assert.equal(res.status, 403);
  assert.equal(db.rows.length + r2.keys.length, 0);
});

test('POST /contribute stores a bounded row and the clip', async () => {
  const db = stubDB(); const r2 = stubR2(); const ctx = stubCtx();
  const long = 'K'.repeat(500);
  const res = await worker.fetch(contribute({ raaga: long, model_pred: long, is_own: 'true' }), { ...ENV, DB: db, CLIPS: r2 }, ctx);
  await ctx.settle();
  assert.equal(res.status, 200);
  assert.equal(r2.keys.length, 1);
  const v = db.rows[0].values;
  assert.equal(v[3].length, 80);                         // raaga
  assert.equal(v[5].length, 80);                         // model_pred
});

test('POST /contribute rejects audio larger than the site allows (413), storing nothing', async () => {
  const db = stubDB(); const r2 = stubR2(); const ctx = stubCtx();
  const res = await worker.fetch(contribute({ raaga: 'Kalyāṇi', is_own: 'true' }, 27 * 1024 * 1024), { ...ENV, DB: db, CLIPS: r2 }, ctx);
  await ctx.settle();
  assert.equal(res.status, 413);
  assert.equal(db.rows.length + r2.keys.length, 0);
});

test('every kind of reply carries the CORS header', async () => {
  const ctx = stubCtx();
  const replies = [
    await worker.fetch(new Request('https://twelveswaras.com/api/nope', { headers: { Origin: 'https://twelveswaras.com' } }), ENV, ctx),
    await worker.fetch(contribute({ raaga: 'x' }), { ...ENV, DB: stubDB(), CLIPS: stubR2() }, ctx),
    await worker.fetch(postJSON('/api/event', { event: 'view' }), { ...ENV, DB: stubDB() }, ctx),
    await worker.fetch(new Request('https://twelveswaras.com/api/result', { method: 'OPTIONS', headers: { Origin: 'https://twelveswaras.com' } }), ENV, ctx),
  ];
  await ctx.settle();
  for (const r of replies) assert.equal(r.headers.get('Access-Control-Allow-Origin'), 'https://twelveswaras.com');
});

test('POST /result keeps each prediction\'s tradition (Tōḍī exists in both)', async () => {
  const db = stubDB(); const ctx = stubCtx();
  const top3 = [{ raaga: 'Tōḍī', tradition: 'hindustani', confidence: 0.6 },
                { raaga: 'Tōḍi', tradition: 'carnatic', confidence: 0.3 },
                { raaga: 'Śrī', tradition: 'martian', confidence: 0.1 }];
  await worker.fetch(postJSON('/api/result', { top3 }), { ...ENV, DB: db }, ctx);
  await ctx.settle();
  const stored = JSON.parse(db.rows[0].values[3]);
  assert.deepEqual(stored.map((e) => e.tradition), ['hindustani', 'carnatic', null]);
});

// ---- /identify: the upload's own format ---------------------------------------------------------
// Every upload used to reach the recognizer as clip.webm, whatever it was. The recognizer reads only
// the name's extension (space/api.py: the temp file's suffix), so an m4a or mp3 is decoded as one
// when its extension is passed on. Only the extension: the rest of a name is the visitor's, and a
// path in it (../../x.mp3) must never reach the recognizer.
test('identify: passes the upload\'s extension on, never the rest of its name', async () => {
  const cases = [['concert.m4a', 'clip.m4a'], ['Song Name.MP3', 'clip.mp3'], ['../../etc/x.wav', 'clip.wav'],
    ['clip.webm', 'clip.webm'], ['no-extension', 'clip.webm'], ['x.m4a;rm -rf', 'clip.webm'], ['x.verylongext', 'clip.webm']];
  for (const [sent, want] of cases) {
    const { fake, calls } = scripted(Response.json({ top3: [], tonic_hz: 140 }));
    await identifyWith(fake, identifyRequest(sent));
    assert.equal(calls[0].audio.name, want, sent);
  }
});

// ---- /identify: a per-IP limit -------------------------------------------------------------------
// /identify had no limit and no key, so a scripted loop could keep the recognizer container busy
// for everyone. A live listen in the browser sends at most 24 /identify calls (one every 3.5 to 7 s
// for up to 150 s, site/index.html maybeSend), so four back-to-back listens in ten minutes stay
// under 100; a loop does not. The counter is in D1 (one row per IP), as mdshare's create limit, so
// it holds across Cloudflare's isolates.
function rateDB() {
  const counts = new Map();
  return {
    counts,
    prepare(sql) {
      return { bind: (...v) => ({
        first: async () => {
          if (!sql.includes('rate_limits')) return null;
          const [key, resetAt] = v;
          const e = counts.get(key) || { count: 0, reset_at: resetAt };
          e.count += 1;
          counts.set(key, e);
          return { count: e.count, reset_at: e.reset_at };
        },
        run: async () => ({ success: true }),
      }) };
    },
  };
}

test('identify: the 101st call from one IP inside ten minutes is a 429 with Retry-After, and never reaches the recognizer', async () => {
  const DB = rateDB();
  const realFetch = globalThis.fetch;
  let recognizerCalls = 0;
  globalThis.fetch = async () => { recognizerCalls++; return Response.json({ top3: [], tonic_hz: 140 }); };
  try {
    for (let i = 0; i < 100; i++) {
      const r = await worker.fetch(identifyRequest('clip.webm', '203.0.113.7'), { ...ENV, DB }, stubCtx());
      assert.equal(r.status, 200, `call ${i + 1}`);
    }
    const res = await worker.fetch(identifyRequest('clip.webm', '203.0.113.7'), { ...ENV, DB }, stubCtx());
    assert.equal(res.status, 429);
    const retry = Number(res.headers.get('Retry-After'));
    assert.ok(retry > 0 && retry <= 600, `Retry-After ${retry}`);
    assert.match((await res.json()).error, /too many/i);
    assert.equal(res.headers.get('Access-Control-Allow-Origin'), 'https://twelveswaras.com');
    assert.equal(recognizerCalls, 100);
    // another address is not affected
    const other = await worker.fetch(identifyRequest('clip.webm', '198.51.100.1'), { ...ENV, DB }, stubCtx());
    assert.equal(other.status, 200);
  } finally { globalThis.fetch = realFetch; }
});

test('identify: the limit fails open when D1 cannot count (a missing table never blocks a listen)', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ top3: [], tonic_hz: 140 });
  try {
    const DB = { prepare() { return { bind: () => ({ first: async () => { throw new Error('no such table: rate_limits'); }, run: async () => ({}) }) }; } };
    const res = await worker.fetch(identifyRequest('clip.webm', '203.0.113.7'), { ...ENV, DB }, stubCtx());
    assert.equal(res.status, 200);
  } finally { globalThis.fetch = realFetch; }
});

test('identify: the limit never stores an address: the key is a salted hash, and expired rows are deleted', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => Response.json({ top3: [], tonic_hz: 140 });
  try {
    const deletes = [];
    const DB = rateDB();
    const prepare = DB.prepare.bind(DB);
    DB.prepare = (sql) => /^\s*DELETE FROM rate_limits/.test(sql)
      ? { bind: (...v) => ({ run: async () => { deletes.push(v); return { success: true }; } }) }
      : prepare(sql);
    const before = Date.now();
    await worker.fetch(identifyRequest('clip.webm', '203.0.113.7'), { ...ENV, DB, RATE_LIMIT_SALT: 'salt-a' }, stubCtx());
    const [key] = [...DB.counts.keys()];
    assert.doesNotMatch(key, /203\.0\.113\.7/);
    assert.match(key, /^identify:[0-9a-f]{64}$/);
    // windows that have ended are removed on the same call, so no row outlives its ten minutes for long
    assert.equal(deletes.length, 1);
    assert.ok(deletes[0][0] >= before && deletes[0][0] <= Date.now());
    // the salt is secret: the same address under another salt is another key (no lookup table can undo it)
    const DB2 = rateDB();
    await worker.fetch(identifyRequest('clip.webm', '203.0.113.7'), { ...ENV, DB: DB2, RATE_LIMIT_SALT: 'salt-b' }, stubCtx());
    assert.notEqual([...DB2.counts.keys()][0], key);
  } finally { globalThis.fetch = realFetch; }
});

test('the D1 schema has the rate_limits table the /identify limit counts in', async () => {
  const { readFile } = await import('node:fs/promises');
  const sql = await readFile(new URL('../../schema.sql', import.meta.url), 'utf8');
  assert.match(sql, /CREATE TABLE IF NOT EXISTS rate_limits \(/);
});

test('POST /result records a command-line identification as source cli', async () => {
  const db = stubDB(); const ctx = stubCtx();
  await worker.fetch(postJSON('/api/result', { top3: [{ raaga: 'Kalyāṇi', tradition: 'carnatic', confidence: 0.7 }], source: 'cli' }), { ...ENV, DB: db }, ctx);
  await ctx.settle();
  assert.equal(db.rows[0].values[9], 'cli');
});
