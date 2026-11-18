// The twelveswaras command line, end to end without a network: run() takes argv and an Io, and the
// Io's fetch is a stub that plays twelveswaras.com (/mcp, /api/identify, /api/result).
//
//   cd cli && node --test
import test from 'node:test';
import assert from 'node:assert/strict';

import { run, HELP } from '../src/run.js';
import { VERSION } from '../src/api.js';

const SITE = 'https://site.test';
const RAAGAS = [
  { name: 'Kalyāṇi', tradition: 'carnatic', parent: '65 Mechakalyani', url: 'https://twelveswaras.com/raaga/kalyani' },
  { name: 'Mōhanaṁ', tradition: 'carnatic', parent: '28 Harikambhoji', url: 'https://twelveswaras.com/raaga/mohanam' },
  { name: 'Yaman kalyāṇ', tradition: 'hindustani', parent: 'Kalyan', url: 'https://twelveswaras.com/raaga/yaman-kalyan-hindustani' },
];
const RECOGNIZED = {
  no_prediction: false, tonic_hz: 146.2, heard_seconds: 75,
  top3: [{ raaga: 'Kalyāṇi', tradition: 'carnatic', confidence: 0.81 },
    { raaga: 'Yaman kalyāṇ', tradition: 'hindustani', confidence: 0.1 },
    { raaga: 'Mōhanaṁ', tradition: 'carnatic', confidence: 0.04 }],
};

/** A fake twelveswaras.com. Records every request (url, headers, body). */
function site({ identify = () => Response.json(RECOGNIZED) } = {}) {
  const calls = [];
  const fetch = async (url, init = {}) => {
    const headers = new Headers(init.headers);
    calls.push({ url, init, headers });
    if (url === `${SITE}/mcp`) {
      const { id, method, params } = JSON.parse(init.body);
      const result = (r) => Response.json({ jsonrpc: '2.0', id, result: r });
      if (method !== 'tools/call') return result({ method });
      const pool = RAAGAS.filter((r) => !params.arguments.tradition || r.tradition === params.arguments.tradition);
      if (params.name === 'list_raagas') return result({ content: [{ type: 'text', text: 'x' }], structuredContent: { count: pool.length, raagas: pool } });
      if (params.name === 'find_raaga') {
        const m = pool.filter((r) => r.name.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().startsWith(params.arguments.name.toLowerCase()))
          .map((r) => ({ ...r, arohanam: 'S R2 G3 M2 P D2 N3 S', avarohanam: 'S N3 D2 P M2 G3 R2 S', notes: { scale: ['S', 'R2'], used_in_phrases: [] }, how_to_hear: 'Bright.', songs: ['Nidhi chala sukhama'] }));
        return result({ content: [{ type: 'text', text: 'x' }], structuredContent: { query: params.arguments.name, matches: m } });
      }
      if (params.name === 'raagas_with_notes') {
        return result({ content: [{ type: 'text', text: 'x' }], structuredContent: { notes: params.arguments.notes, positions: [0, 2, 4, 7, 9], exact: [RAAGAS[1]], containing: [RAAGAS[0]] } });
      }
    }
    if (url === `${SITE}/api/identify`) return identify(init);
    if (url === `${SITE}/api/result`) return Response.json({ ok: true });
    return new Response('not found', { status: 404 });
  };
  return { fetch, calls };
}

function io(over = {}) {
  const s = over.site || site();
  const progress = [];
  return {
    calls: s.calls, progress,
    io: {
      isTTY: true, site: SITE, fetch: s.fetch,
      progress: (line) => progress.push(line),
      size: async (p) => { if (p === 'missing.m4a') { const e = new Error('ENOENT'); e.code = 'ENOENT'; throw e; } return over.size ?? 4000; },
      blob: async () => new Blob([new Uint8Array(4000)]),
      readStdin: async () => new Uint8Array(4000),
      hasFfmpeg: async () => over.ffmpeg ?? true,
      cut: async (p, secs) => { (over.cuts ||= []).push([p, secs]); return '/tmp/cut.wav'; },
      share: async (md, title) => { (over.shared ||= []).push({ md, title }); return 'https://mdshare.live/d/abc'; },
      writeFile: async (p, s2) => { (over.written ||= []).push([p, s2]); },
      ...over.io,
    },
    over,
  };
}

// --- help, usage, modes -----------------------------------------------------------------------

test('no arguments on a terminal prints help; off a terminal, or serve, hands over to the MCP server', async () => {
  const t = io();
  const r = await run([], t.io);
  assert.equal(r.code, 0);
  assert.equal(r.stdout, `${HELP}\n`);
  assert.equal((await run([], { ...t.io, isTTY: false })).serve, true);
  assert.equal((await run(['serve'], t.io)).serve, true);
});

test('--version and per-command --help', async () => {
  const t = io();
  assert.equal((await run(['--version'], t.io)).stdout, `${VERSION}\n`);
  for (const cmd of ['identify', 'raaga', 'notes', 'list']) {
    const r = await run([cmd, '--help'], t.io);
    assert.equal(r.code, 0, cmd);
    assert.match(r.stdout, new RegExp(`twelveswaras ${cmd}`), cmd);
  }
});

test('bad usage exits 2 with the reason on stderr and nothing on stdout', async () => {
  const t = io();
  for (const argv of [['nope'], ['raaga'], ['notes'], ['identify'], ['list', '--tradition', 'western'], ['list', '--bogus'], ['list', '--format', 'pdf']]) {
    const r = await run(argv, t.io);
    assert.equal(r.code, 2, argv.join(' '));
    assert.equal(r.stdout, '');
    assert.ok(r.stderr.length > 0);
  }
});

// --- raaga, notes, list: the hosted MCP tools ----------------------------------------------------

test('list calls the hosted list_raagas tool with the CLI User-Agent and prints one raaga per line', async () => {
  const t = io();
  const r = await run(['list', '--tradition', 'carnatic'], t.io);
  assert.equal(r.code, 0);
  const lines = r.stdout.trim().split('\n');
  assert.equal(lines.length, 2);
  assert.match(lines[0], /Kalyāṇi.*carnatic.*https:\/\/twelveswaras\.com\/raaga\/kalyani/);
  const call = t.calls[0];
  assert.equal(call.url, `${SITE}/mcp`);
  assert.deepEqual(JSON.parse(call.init.body).params, { name: 'list_raagas', arguments: { tradition: 'carnatic' } });
  assert.equal(call.headers.get('user-agent'), `twelveswaras-cli/${VERSION}`);
});

test('--json prints the tool\'s structured result', async () => {
  const r = await run(['list', '--json'], io().io);
  assert.equal(JSON.parse(r.stdout).count, 3);
});

test('raaga prints its scale and page; an unknown raaga exits 1', async () => {
  const t = io();
  const r = await run(['raaga', 'kalyani'], t.io);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /Kalyāṇi \(carnatic\)/);
  assert.match(r.stdout, /S R2 G3 M2 P D2 N3 S/);
  assert.match(r.stdout, /https:\/\/twelveswaras\.com\/raaga\/kalyani/);
  const miss = await run(['raaga', 'darbari kanada'], t.io);
  assert.equal(miss.code, 1);
  assert.match(miss.stderr, /not among the 70 raagas/);
});

test('notes lists the exact and the containing raagas', async () => {
  const r = await run(['notes', 'S R2 G3 P D2'], io().io);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /Exactly these notes:\s+Mōhanaṁ/);
  assert.match(r.stdout, /These and more:\s+Kalyāṇi/);
});

test('--format md carries the CC-BY credit', async () => {
  for (const argv of [['list', '--format', 'md'], ['raaga', 'kalyani', '--format', 'md'], ['notes', 'S R2 G3 P D2', '--format', 'md']]) {
    const r = await run(argv, io().io);
    assert.match(r.stdout, /CC-BY-4\.0/, argv.join(' '));
    // The site's, llms.txt's and README's wording for the reference facts.
    assert.match(r.stdout, /checked against published sources; not yet reviewed by a musician\./, argv.join(' '));
    assert.match(r.stdout, /^# /, argv.join(' '));
  }
});

test('the site being down is exit 1 with a plain message', async () => {
  const t = io({ site: { calls: [], fetch: async () => { throw new TypeError('fetch failed'); } } });
  const r = await run(['list'], t.io);
  assert.equal(r.code, 1);
  assert.match(r.stderr, /could not reach https:\/\/site\.test/i);
});

// --- identify -----------------------------------------------------------------------------------

test('identify uploads the file as multipart audio, prints the top three, and posts one /result row as cli', async () => {
  const t = io();
  const r = await run(['identify', 'recordings/concert.m4a'], t.io);
  assert.equal(r.code, 0, r.stderr);
  assert.match(r.stdout, /Most likely: Kalyāṇi/);
  assert.match(r.stdout, /81%.*Kalyāṇi.*https:\/\/twelveswaras\.com\/raaga\/kalyani/);
  assert.match(r.stdout, /Tonic \(Sa\): 146 Hz/);
  const up = t.calls.find((c) => c.url === `${SITE}/api/identify`);
  assert.equal(up.init.method, 'POST');
  assert.equal(up.init.body.get('audio').name, 'concert.m4a', 'the name only, never the path');
  assert.equal(up.headers.get('user-agent'), `twelveswaras-cli/${VERSION}`);
  const posted = t.calls.filter((c) => c.url === `${SITE}/api/result`);
  assert.equal(posted.length, 1);
  const row = JSON.parse(posted[0].init.body);
  assert.equal(row.source, 'cli');
  assert.equal(row.no_prediction, 0);
  assert.deepEqual(row.top3, RECOGNIZED.top3);
  assert.equal(row.tonic_hz, 146.2);
  assert.equal(row.heard_seconds, 75);
  assert.equal(typeof row.elapsed_s, 'number');
});

test('identify --json is the same shape as the identify_raaga tool', async () => {
  const r = await run(['identify', 'a.mp3', '--json'], io().io);
  const out = JSON.parse(r.stdout);
  assert.deepEqual(Object.keys(out).sort(), ['confident', 'heard_seconds', 'note', 'tonic_hz', 'top3']);
  assert.equal(out.top3[0].url, 'https://twelveswaras.com/raaga/kalyani');
});

test('identify refuses a file over 25 MB before uploading anything', async () => {
  const t = io({ size: 30 * 1024 * 1024 });
  const r = await run(['identify', 'concert.m4a'], t.io);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /25 MB/);
  assert.match(r.stderr, /--from/);
  assert.equal(t.calls.length, 0);
});

test('identify a file that is not there exits 2', async () => {
  const r = await run(['identify', 'missing.m4a'], io().io);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /no such file/i);
});

test('identify --from cuts with ffmpeg and uploads the cut', async () => {
  const t = io({ size: 60 * 1024 * 1024 });     // a whole concert: the cut is what is uploaded
  t.io.size = async (p) => (p === '/tmp/cut.wav' ? 13 * 1024 * 1024 : 60 * 1024 * 1024);
  const r = await run(['identify', 'concert.m4a', '--from', '2:30'], t.io);
  assert.equal(r.code, 0, r.stderr);
  assert.deepEqual(t.over.cuts, [['concert.m4a', 150]]);
  assert.equal(t.calls.find((c) => c.url.endsWith('/api/identify')).init.body.get('audio').name, 'clip.wav');
});

test('identify --from without ffmpeg exits 2 saying ffmpeg is needed', async () => {
  const t = io({ ffmpeg: false });
  const r = await run(['identify', 'concert.m4a', '--from', '1:00'], t.io);
  assert.equal(r.code, 2);
  assert.match(r.stderr, /ffmpeg/);
  assert.equal(t.calls.length, 0);
});

test('identify --from takes mm:ss, h:mm:ss or seconds, and nothing else', async () => {
  for (const [from, secs] of [['2:30', 150], ['1:02:03', 3723], ['90', 90]]) {
    const t = io();
    await run(['identify', 'c.m4a', '--from', from], t.io);
    assert.deepEqual(t.over.cuts, [['c.m4a', secs]], from);
  }
  assert.equal((await run(['identify', 'c.m4a', '--from', '2:75'], io().io)).code, 2);
  assert.equal((await run(['identify', 'c.m4a', '--from', 'soon'], io().io)).code, 2);
});

test('identify reads stdin with -', async () => {
  const t = io();
  const r = await run(['identify', '-'], t.io);
  assert.equal(r.code, 0, r.stderr);
  assert.equal(t.calls.find((c) => c.url.endsWith('/api/identify')).init.body.get('audio').name, 'clip.webm');
});

test('identify: over the rate limit is exit 1 with the site\'s message; nothing is posted to /result', async () => {
  const t = io({ site: site({ identify: () => Response.json({ error: 'Too many recordings from this address. Try again in 4 min.' }, { status: 429, headers: { 'Retry-After': '240' } }) }) });
  const r = await run(['identify', 'a.m4a'], t.io);
  assert.equal(r.code, 1);
  assert.match(r.stderr, /Too many recordings/);
  assert.equal(t.calls.filter((c) => c.url.endsWith('/api/result')).length, 0);
});

test('identify: a recording with no raaga heard says why, and still posts its /result row with the reason', async () => {
  const t = io({ site: site({ identify: () => Response.json({ no_prediction: true, reason: 'too_short', top3: [], tonic_hz: null, heard_seconds: 3 }) }) });
  const r = await run(['identify', 'a.m4a'], t.io);
  assert.equal(r.code, 0);
  assert.match(r.stdout, /No raaga was heard/);
  const row = JSON.parse(t.calls.find((c) => c.url.endsWith('/api/result')).init.body);
  assert.equal(row.no_prediction, 1);
  assert.equal(row.reason, 'too_short');
});

test('identify --format md is a document with a linked table and the credit', async () => {
  const r = await run(['identify', 'concert.m4a', '--format', 'md'], io().io);
  assert.match(r.stdout, /^# The raaga in concert\.m4a/);
  assert.match(r.stdout, /\| 1 \| \[Kalyāṇi\]\(https:\/\/twelveswaras\.com\/raaga\/kalyani\) \| Carnatic \| 81% \|/);
  assert.match(r.stdout, /CC-BY-4\.0/);
});

// --- output: -o and --share ------------------------------------------------------------------------

test('-o writes the result to a file instead of stdout', async () => {
  const t = io();
  const r = await run(['list', '-o', 'raagas.txt'], t.io);
  assert.equal(r.stdout, '');
  assert.equal(t.over.written[0][0], 'raagas.txt');
  assert.match(t.over.written[0][1], /Kalyāṇi/);
});

test('--share hands the markdown to mdshare and prints the link', async () => {
  const t = io();
  const r = await run(['identify', 'concert.m4a', '--share'], t.io);
  assert.equal(r.code, 0, r.stderr);
  assert.equal(r.stdout, 'https://mdshare.live/d/abc\n');
  assert.match(t.over.shared[0].md, /^# The raaga in concert\.m4a/);
  assert.equal(t.over.shared[0].title, 'The raaga in concert.m4a');
});
