// The MCP server at twelveswaras.com/mcp: protocol, the four tools, and the safety limits on the one
// tool that fetches (identify_raaga). No network: global fetch is replaced by a stub that serves the
// raaga reference, a recording, and the recognizer's answer.
//
//   node --test cloudflare/worker/test/
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import worker from '../src/index.js';
import { normalName, notePositions, _resetReference } from '../src/mcp.js';

const REFERENCE = readFileSync(new URL('../../../site/data/raaga-reference.json', import.meta.url), 'utf8');
const ENV = { SPACE_URL: 'https://recognizer.test', SITE_URL: 'https://site.test' };

// fetch stub: the reference file, recordings by URL, and the recognizer. Records every call.
function stubFetch({ audio = {}, recognizer = null } = {}) {
  const calls = [];
  globalThis.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    calls.push({ url, init });
    if (url === 'https://site.test/data/raaga-reference.json') return new Response(REFERENCE);
    if (url === 'https://recognizer.test/identify') {
      if (typeof recognizer === 'function') return recognizer();
      return new Response(JSON.stringify(recognizer || { no_prediction: true, top3: [] }));
    }
    if (url in audio) return audio[url]();
    return new Response('nope', { status: 404 });
  };
  return calls;
}

function ctx() {
  const pending = [];
  return { waitUntil: (p) => pending.push(p), done: () => Promise.all(pending) };
}

async function rpc(method, params, { env = ENV, c = ctx() } = {}) {
  const req = new Request('https://twelveswaras.com/mcp', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: 1, method, params }),
  });
  const res = await worker.fetch(req, env, c);
  return { res, body: await res.json(), c };
}

const call = (name, args, opts) => rpc('tools/call', { name, arguments: args }, opts);

test.beforeEach(() => _resetReference());

// --- protocol -----------------------------------------------------------------------------------

test('initialize names the server, its scope and how to credit it', async () => {
  const { body } = await rpc('initialize', { protocolVersion: '2025-06-18', clientInfo: { name: 'claude' } });
  const r = body.result;
  assert.equal(r.protocolVersion, '2025-06-18');
  assert.equal(r.serverInfo.name, 'twelveswaras');
  assert.match(r.instructions, /70 raagas/);
  assert.match(r.instructions, /CC-BY-4\.0/);
  assert.match(r.instructions, /not reviewed by a musician/);
});

test('tools/list offers the four tools, all read-only', async () => {
  const { body } = await rpc('tools/list', {});
  const names = body.result.tools.map((t) => t.name).sort();
  assert.deepEqual(names, ['find_raaga', 'identify_raaga', 'list_raagas', 'raagas_with_notes']);
  for (const t of body.result.tools) assert.equal(t.annotations.readOnlyHint, true);
});

test('a notification gets 202, an unknown method a JSON-RPC error, and CORS is open', async () => {
  const note = await worker.fetch(new Request('https://twelveswaras.com/mcp', {
    method: 'POST', body: JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' }),
  }), ENV, ctx());
  assert.equal(note.status, 202);
  const { res, body } = await rpc('nope/nope', {});
  assert.equal(body.error.code, -32601);
  assert.equal(res.headers.get('access-control-allow-origin'), '*');
});

// --- find_raaga ---------------------------------------------------------------------------------

test('names are matched however they are spelled', () => {
  assert.equal(normalName('Mōhanaṁ'), 'mohanam');
  assert.equal(normalName('mohana ragam'), 'mohana');
  assert.equal(normalName('Raag Bhoop'), 'bhoop');
});

test('find_raaga finds a raaga by a plain spelling and returns its page and scale', async () => {
  stubFetch();
  const { body } = await call('find_raaga', { name: 'mohanam raga' });
  const r = body.result.structuredContent;
  assert.equal(r.matches[0].name, 'Mōhanaṁ');
  assert.equal(r.matches[0].url, 'https://twelveswaras.com/raaga/mohanam');
  assert.equal(r.matches[0].arohanam, 'S R2 G3 P D2 S');
  assert.match(body.result.content[0].text, /Mōhanaṁ/);
});

test('find_raaga tolerates the usual romanisations (oo/u, aa/a, sh/s, w/v)', async () => {
  stubFetch();
  for (const [typed, name] of [['Bhoop', 'Bhūp'], ['Shankarabharanam', 'Śankarābharaṇaṁ'],
                               ['kalyaani', 'Kalyāṇi'], ['Raag Yaman Kalyan', 'Yaman kalyāṇ']]) {
    const m = (await call('find_raaga', { name: typed })).body.result.structuredContent.matches;
    assert.ok(m.some((r) => r.name === name), `${typed} -> ${m.map((r) => r.name)}`);
  }
});

test('find_raaga can narrow by tradition (Todi exists in both)', async () => {
  stubFetch();
  const both = (await call('find_raaga', { name: 'todi' })).body.result.structuredContent.matches;
  assert.deepEqual([...new Set(both.map((m) => m.tradition))].sort(), ['carnatic', 'hindustani']);
  const h = (await call('find_raaga', { name: 'todi', tradition: 'hindustani' })).body.result.structuredContent.matches;
  assert.ok(h.length >= 1 && h.every((m) => m.tradition === 'hindustani'));
});

test('find_raaga says plainly when a raaga is not among the 70', async () => {
  stubFetch();
  const { body } = await call('find_raaga', { name: 'Hindolam' });
  assert.equal(body.result.structuredContent.matches.length, 0);
  assert.match(body.result.content[0].text, /not among the 70/);
});

// --- raagas_with_notes --------------------------------------------------------------------------

test('notes parse in Carnatic labels or Hindustani letters', () => {
  assert.deepEqual(notePositions('S R2 G3 P D2'), [0, 2, 4, 7, 9]);
  assert.deepEqual(notePositions('S R G P D', 'hindustani'), [0, 2, 4, 7, 9]);
  assert.deepEqual(notePositions('S r g m P d n', 'hindustani'), [0, 1, 3, 5, 7, 8, 10]);
});

test('raagas_with_notes finds the raagas with exactly that scale, across traditions', async () => {
  stubFetch();
  const { body } = await call('raagas_with_notes', { notes: 'S R2 G3 P D2' });
  const exact = body.result.structuredContent.exact.map((r) => r.name);
  assert.ok(exact.includes('Mōhanaṁ'));
  assert.ok(exact.includes('Bhūp'));                      // Mohanam's Hindustani counterpart
});

test('raagas_with_notes rejects notes it cannot read', async () => {
  stubFetch();
  const { body } = await call('raagas_with_notes', { notes: 'banana' });
  assert.equal(body.result.isError, true);
});

// --- list_raagas --------------------------------------------------------------------------------

test('list_raagas lists all 70, or one tradition', async () => {
  stubFetch();
  assert.equal((await call('list_raagas', {})).body.result.structuredContent.raagas.length, 70);
  assert.equal((await call('list_raagas', { tradition: 'carnatic' })).body.result.structuredContent.raagas.length, 40);
});

// --- identify_raaga -----------------------------------------------------------------------------

const RECOGNIZED = {
  no_prediction: false, tonic_hz: 146.2, heard_seconds: 75,
  top3: [{ raaga: 'Kalyāṇi', tradition: 'carnatic', confidence: 0.81 },
         { raaga: 'Yaman kalyāṇ', tradition: 'hindustani', confidence: 0.1 },
         { raaga: 'Śankarābharaṇaṁ', tradition: 'carnatic', confidence: 0.04 }],
};

test('identify_raaga fetches the recording, asks the recognizer, and links each answer', async () => {
  const calls = stubFetch({
    audio: { 'https://example.org/clip.mp3': () => new Response(new Uint8Array(4000), { headers: { 'content-type': 'audio/mpeg' } }) },
    recognizer: RECOGNIZED,
  });
  const c = ctx();
  const env = { ...ENV, DB: logDB() };
  const { body } = await call('identify_raaga', { audio_url: 'https://example.org/clip.mp3' }, { env, c });
  const r = body.result.structuredContent;
  assert.equal(r.top3[0].raaga, 'Kalyāṇi');
  assert.equal(r.top3[0].url, 'https://twelveswaras.com/raaga/kalyani');
  assert.equal(r.top3[1].url, 'https://twelveswaras.com/raaga/yaman-kalyan-hindustani');
  assert.equal(r.confident, true);
  assert.ok(calls.some((x) => x.url === 'https://recognizer.test/identify' && x.init.method === 'POST'));
  await c.done();
  assert.deepEqual(env.DB.rows.map((v) => [v[1], v[3]]), [['mcp:identify_raaga', 'mcp']]);
});

// The recognizer's container sometimes drops a request ("Container suddenly disconnected, try
// again", plain text): the tool tries once more, as the site does (recognizer.js).
test('identify_raaga tries once more when the recognizer drops the request', async () => {
  let n = 0;
  stubFetch({
    audio: { 'https://example.org/a.wav': () => new Response(new Uint8Array(100)) },
    recognizer: () => (++n === 1 ? new Response('Container suddenly disconnected, try again', { status: 500 }) : Response.json(RECOGNIZED)),
  });
  const r = (await call('identify_raaga', { audio_url: 'https://example.org/a.wav' })).body.result;
  assert.equal(n, 2);
  assert.equal(r.structuredContent.top3[0].raaga, 'Kalyāṇi');
});

test('identify_raaga says the recognizer is unavailable when the second try fails too', async () => {
  stubFetch({
    audio: { 'https://example.org/a.wav': () => new Response(new Uint8Array(100)) },
    recognizer: () => new Response('Container suddenly disconnected, try again', { status: 500 }),
  });
  const r = (await call('identify_raaga', { audio_url: 'https://example.org/a.wav' })).body.result;
  assert.equal(r.isError, true);
  assert.match(r.content[0].text, /recognizer is unavailable/i);
});

test('a low-confidence answer is reported as not sure', async () => {
  stubFetch({
    audio: { 'https://example.org/a.wav': () => new Response(new Uint8Array(100)) },
    recognizer: { ...RECOGNIZED, top3: [{ ...RECOGNIZED.top3[0], confidence: 0.3 }] },
  });
  const r = (await call('identify_raaga', { audio_url: 'https://example.org/a.wav' })).body.result.structuredContent;
  assert.equal(r.confident, false);
  assert.match(r.note, /not sure/i);
});

test('identify_raaga only fetches public http(s) URLs and refuses oversized recordings', async () => {
  stubFetch({
    audio: { 'https://example.org/huge.wav': () => new Response('x', { headers: { 'content-length': String(40e6) } }) },
  });
  for (const bad of ['file:///etc/passwd', 'ftp://example.org/a.mp3', 'http://localhost/a.mp3',
                     'http://127.0.0.1/a.mp3', 'http://10.0.0.5/a.mp3', 'http://169.254.169.254/latest', 'not a url']) {
    const { body } = await call('identify_raaga', { audio_url: bad });
    assert.equal(body.result.isError, true, bad);
  }
  const { body } = await call('identify_raaga', { audio_url: 'https://example.org/huge.wav' });
  assert.equal(body.result.isError, true);
  assert.match(body.result.content[0].text, /too large/);
});

test('a redirect is followed only to another public URL', async () => {
  stubFetch({
    audio: {
      'https://example.org/sneaky.mp3': () => new Response(null, { status: 302, headers: { location: 'http://127.0.0.1/a.mp3' } }),
      'https://example.org/moved.mp3': () => new Response(null, { status: 301, headers: { location: '/real.mp3' } }),
      'https://example.org/real.mp3': () => new Response(new Uint8Array(100)),
    },
    recognizer: RECOGNIZED,
  });
  const bad = await call('identify_raaga', { audio_url: 'https://example.org/sneaky.mp3' });
  assert.equal(bad.body.result.isError, true);
  const good = await call('identify_raaga', { audio_url: 'https://example.org/moved.mp3' });
  assert.equal(good.body.result.structuredContent.top3[0].raaga, 'Kalyāṇi');
});

test('the recognizer being down is a tool error, not a protocol fault', async () => {
  globalThis.fetch = async (u) => {
    const url = typeof u === 'string' ? u : u.url;
    if (url.endsWith('/identify')) throw new Error('down');
    if (url.endsWith('.json')) return new Response(REFERENCE);
    return new Response(new Uint8Array(100));
  };
  const { body } = await call('identify_raaga', { audio_url: 'https://example.org/a.mp3' });
  assert.equal(body.result.isError, true);
});

function logDB() {
  const rows = [];
  return { rows, prepare: () => ({ bind: (...v) => ({ run: async () => { rows.push(v); } }) }) };
}
