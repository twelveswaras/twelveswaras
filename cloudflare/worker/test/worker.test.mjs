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
          return { run: async () => { rows.push({ sql, values }); return { success: true }; } };
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
test('cleanSource is a two-value enum and nulls everything else', () => {
  assert.equal(cleanSource('live'), 'live');
  assert.equal(cleanSource('file'), 'file');
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

test('the funnel allowlist is exactly the steps the page can reach', () => {
  assert.deepEqual([...FUNNEL_EVENTS].sort(), ['listen_start', 'mic_denied', 'result', 'view']);
});

// ---- scheduled (keep-warm) -------------------------------------------------------------------
test('the cron pings the Space so a visitor never pays the cold start', async () => {
  const seen = [];
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (u) => { seen.push(String(u)); return new Response('{}', { status: 200 }); };
  try {
    const ctx = stubCtx();
    await worker.scheduled({ cron: '*/5 * * * *' }, { ...ENV, SPACE_URL: 'https://space.invalid' }, ctx);
    await ctx.settle();
  } finally {
    globalThis.fetch = realFetch;
  }
  assert.deepEqual(seen, ['https://space.invalid/health']);
});

test('a failing keep-warm ping never throws (a dead cron is worse than a cold Space)', async () => {
  const realFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('space is down'); };
  try {
    const ctx = stubCtx();
    await worker.scheduled({ cron: '*/5 * * * *' }, ENV, ctx);
    await ctx.settle();                     // must resolve, not reject
  } finally {
    globalThis.fetch = realFetch;
  }
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
