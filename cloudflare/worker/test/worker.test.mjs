// Unit tests for the worker's logging surface. These cover the sanitizers that stand between an
// arbitrary POST and a D1 column, plus the /event allowlist, without a Worker runtime or a network:
// the module is imported directly and D1 is a stub that records what it was asked to insert.
//
//   node --test cloudflare/worker/test/
import test from 'node:test';
import assert from 'node:assert/strict';

import worker, { cleanReferrer, cleanId, cleanSource, FUNNEL_EVENTS } from '../src/index.js';

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
