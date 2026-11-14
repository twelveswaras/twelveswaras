// twelveswaras' MCP server at twelveswaras.com/mcp: a stateless JSON-RPC 2.0 endpoint over
// Streamable HTTP (MCP 2025-06-18), the same shape as mugilu's. Four read-only tools: look a raaga up,
// find raagas by their notes, list them, and identify the raaga in a recording.
//
// The raaga facts come from site/data/raaga-reference.json, which tools/build_pages.py writes from
// the same corrected data as the raaga pages, so the server and the pages can never disagree.

import { askRecognizer } from './recognizer.js';

const PROTOCOL_VERSION = '2025-06-18';
const SUPPORTED_VERSIONS = ['2025-06-18', '2025-03-26', '2024-11-05'];
const SERVER_INFO = { name: 'twelveswaras', version: '1', title: 'twelveswaras: identify and learn raagas' };

export const INSTRUCTIONS = `twelveswaras: an open-source "Shazam for raagas" for Indian classical music. It knows 70 raagas (40 Carnatic, 30 Hindustani): their scales (arohanam/avarohanam, aroh/avroh), parent melakarta or thaat, the notes each uses (and the notes it uses only in phrases, its anya swaras), key notes, well-known songs, and the raagas each is confused with. It can also name the raaga in a recording.

Tools: find_raaga to look a raaga up by any spelling (Mohanam, Mōhanaṁ, Bhoop, "kalyani ragam"); raagas_with_notes to find raagas by their notes (Carnatic S R2 G3 P D2, or Hindustani S R G P D with komal r g d n and tivra M); list_raagas for the full list; identify_raaga to name the raaga in a recording at a public URL.

Limits: the facts were checked against published sources (Wikipedia, karnatik.com, ragasurabhi, darbar.org, tanarang) but are not reviewed by a musician. identify_raaga needs about a minute or more of music, ideally with a tanpura or drone; on real recordings its top answer is right about 71% of the time and the right raaga is in its top three about 80% of the time. It only knows the 70 raagas; for any other it names the closest. When it is not sure, say so. Recordings are not stored.

Attribution: credit "twelveswaras (twelveswaras.com), CC-BY-4.0" and link the raaga's page (each answer carries its url).`;

const READ_ONLY = { readOnlyHint: true, idempotentHint: true, openWorldHint: false };
const TRADITION = { type: 'string', enum: ['carnatic', 'hindustani'], description: 'Limit to one tradition.' };

export const TOOLS = [
  {
    name: 'find_raaga',
    title: 'Find a raaga',
    description: 'Look up a raaga by name, in any spelling (with or without diacritics, "raga"/"ragam"/"raag"). Returns its scale, parent, notes, key notes, songs, what it is confused with, and its page.',
    inputSchema: { type: 'object', properties: { name: { type: 'string', description: 'The raaga, e.g. "Mohanam", "Bhoop", "kalyani ragam".' }, tradition: TRADITION }, required: ['name'] },
    annotations: READ_ONLY,
  },
  {
    name: 'raagas_with_notes',
    title: 'Raagas with these notes',
    description: 'Find the raagas that use a set of notes: those whose scale is exactly these notes, and those whose notes include them. Carnatic labels (S R1 R2 G2 G3 M1 M2 P D1 D2 N2 N3) or Hindustani letters (S r R g G m M P d D n N: lowercase komal, M tivra).',
    inputSchema: { type: 'object', properties: { notes: { type: 'string', description: 'e.g. "S R2 G3 P D2" or "S R G P D".' }, tradition: TRADITION }, required: ['notes'] },
    annotations: READ_ONLY,
  },
  {
    name: 'list_raagas',
    title: 'List the raagas',
    description: 'The 70 raagas twelveswaras knows (40 Carnatic, 30 Hindustani), with their parent and page.',
    inputSchema: { type: 'object', properties: { tradition: TRADITION } },
    annotations: READ_ONLY,
  },
  {
    name: 'identify_raaga',
    title: 'Identify the raaga in a recording',
    description: 'Name the raaga in a recording of Carnatic or Hindustani music at a public http(s) URL (mp3, wav, m4a, ogg, webm; up to 25 MB). Returns the top three with confidence, the tonic (Sa) it heard, and each raaga\'s page. Best with a minute or more and a drone. The recording is not stored.',
    inputSchema: { type: 'object', properties: { audio_url: { type: 'string', description: 'A public link to the audio file.' } }, required: ['audio_url'] },
    annotations: { ...READ_ONLY, openWorldHint: true, idempotentHint: false },
  },
];

// --- the reference --------------------------------------------------------------------------------

const REFERENCE_TTL_MS = 60 * 60 * 1000;
let reference = { at: 0, data: null };
export function _resetReference() { reference = { at: 0, data: null }; }

async function loadReference(env) {
  if (reference.data && Date.now() - reference.at < REFERENCE_TTL_MS) return reference.data;
  const r = await fetch(`${env.SITE_URL || 'https://twelveswaras.com'}/data/raaga-reference.json`);
  if (!r.ok) throw new Error(`reference ${r.status}`);
  reference = { at: Date.now(), data: await r.json() };
  return reference.data;
}

/** A raaga name as people type it: no diacritics, lower case, without "raga"/"ragam"/"raag". */
export function normalName(s) {
  return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    .replace(/[^a-z0-9 ]+/g, ' ')
    .split(/\s+/).filter((w) => w && !['raga', 'ragam', 'raag', 'raaga', 'rag', 'raagam'].includes(w))
    .join(' ');
}

/** normalName, folded over the usual romanisation variants: Bhoop/Bhup, Kalyaani/Kalyani,
 *  Shankarabharanam/Sankarabharanam, Kamboji/Kambhoji, w/v. */
function looseName(s) {
  return normalName(s).replace(/aa/g, 'a').replace(/ee/g, 'i').replace(/oo/g, 'u')
    .replace(/sh/g, 's').replace(/w/g, 'v').replace(/([kgcjtdpb])h/g, '$1');
}

const CARNATIC = { S: 0, R1: 1, R2: 2, G1: 2, R3: 3, G2: 3, G3: 4, M1: 5, M2: 6, P: 7, D1: 8, D2: 9, N1: 9, D3: 10, N2: 10, N3: 11 };
const HINDUSTANI = { S: 0, r: 1, R: 2, g: 3, G: 4, m: 5, M: 6, P: 7, d: 8, D: 9, n: 10, N: 11 };

/** Wheel positions (semitones from Sa) of the notes written, or null if any token is not a note. */
export function notePositions(text, tradition) {
  const tokens = String(text).trim().split(/[\s,]+/).filter(Boolean).map((t) => t.replace(/['.’]/g, ''));
  if (!tokens.length) return null;
  const carnatic = tradition !== 'hindustani' && tokens.some((t) => /^[RGMDN][123]$/.test(t));
  const map = carnatic ? CARNATIC : HINDUSTANI;
  const pos = new Set();
  for (const t of tokens) {
    const p = map[t];
    if (p === undefined) return null;
    pos.add(p);
  }
  return [...pos].sort((a, b) => a - b);
}

// --- the tools ------------------------------------------------------------------------------------

const brief = (r) => ({ name: r.name, tradition: r.tradition, parent: r.parent, url: r.url });

async function findRaaga(args, env) {
  const want = looseName(args.name || '');
  if (!want) return fail('Give a raaga name.');
  const { raagas } = await loadReference(env);
  const pool = raagas.filter((r) => !args.tradition || r.tradition === args.tradition);
  const names = (r) => [r.name, ...(r.also_known_as || [])].map(looseName);
  let matches = pool.filter((r) => names(r).includes(want));
  if (!matches.length) matches = pool.filter((r) => names(r).some((n) => n.includes(want) || want.includes(n)));
  if (!matches.length) {
    return done({ query: args.name, matches: [] },
      `"${args.name}" is not among the 70 raagas twelveswaras knows. list_raagas gives the full list.`);
  }
  const text = matches.map((r) => `${r.name} (${r.tradition}, ${r.parent}): ${r.arohanam || 'scale pending'} / ${r.avarohanam || ''}. ${r.url}`).join('\n');
  return done({ query: args.name, matches }, text);
}

async function raagasWithNotes(args, env) {
  const want = notePositions(args.notes || '', args.tradition);
  if (!want) return fail('Could not read those notes. Use Carnatic labels (S R2 G3 P D2) or Hindustani letters (S R G P D).');
  const { raagas } = await loadReference(env);
  const pool = raagas.filter((r) => !args.tradition || r.tradition === args.tradition);
  const key = (a) => a.join(',');
  const exact = pool.filter((r) => key(r.scale_positions) === key(want)).map(brief);
  const containing = pool.filter((r) => {
    const all = new Set([...r.scale_positions, ...(r.phrase_positions || [])]);
    return key(r.scale_positions) !== key(want) && want.every((p) => all.has(p));
  }).map(brief);
  const text = `Exactly these notes: ${exact.map((r) => `${r.name} (${r.tradition})`).join(', ') || 'none'}.\n`
    + `Using these notes and more: ${containing.map((r) => `${r.name} (${r.tradition})`).join(', ') || 'none'}.`;
  return done({ notes: args.notes, positions: want, exact, containing }, text);
}

async function listRaagas(args, env) {
  const { raagas } = await loadReference(env);
  const list = raagas.filter((r) => !args.tradition || r.tradition === args.tradition).map(brief);
  return done({ count: list.length, raagas: list }, list.map((r) => `${r.name} (${r.tradition})`).join(', '));
}

const MAX_AUDIO = 25 * 1024 * 1024;
const NOT_SURE = 0.45;     // the site's own abstention threshold (site/index.html ABSTAIN_CONF)

/** A public http(s) URL, not a loopback, private or link-local address. */
function publicUrl(raw) {
  let u;
  try { u = new URL(raw); } catch { return null; }
  if (u.protocol !== 'https:' && u.protocol !== 'http:') return null;
  const h = u.hostname.replace(/^\[|\]$/g, '').toLowerCase();
  if (h === 'localhost' || h.endsWith('.localhost') || h.endsWith('.internal') || h === '::1' || h === '0.0.0.0') return null;
  const m = h.match(/^(\d+)\.(\d+)\.\d+\.\d+$/);
  if (m) {
    const [a, b] = [+m[1], +m[2]];
    if (a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)) return null;
  }
  if (/^(fc|fd|fe80)/.test(h)) return null;
  return u;
}

/** Fetch a public URL, following up to five redirects by hand so every hop passes publicUrl. */
async function fetchPublic(u) {
  const signal = AbortSignal.timeout(30_000);
  for (let hop = 0; hop <= 5; hop++) {
    const res = await fetch(u.toString(), { redirect: 'manual', signal });
    const next = res.status >= 300 && res.status < 400 && res.headers.get('location');
    if (!next) return res;
    u = publicUrl(new URL(next, u).toString());
    if (!u) return null;
  }
  return null;
}

async function readCapped(res) {
  const len = Number(res.headers.get('content-length') || 0);
  if (len > MAX_AUDIO) return null;
  const reader = res.body.getReader();
  const parts = [];
  let size = 0;
  for (;;) {
    const { done: end, value } = await reader.read();
    if (end) break;
    size += value.byteLength;
    if (size > MAX_AUDIO) { reader.cancel(); return null; }
    parts.push(value);
  }
  return new Blob(parts, { type: res.headers.get('content-type') || 'application/octet-stream' });
}

async function identifyRaaga(args, env) {
  const u = publicUrl(args.audio_url || '');
  if (!u) return fail('Give a public http(s) link to the recording.');
  let res;
  try { res = await fetchPublic(u); }
  catch { return fail('Could not download the recording from that link.'); }
  if (!res) return fail('That link redirects somewhere that is not a public web address.');
  if (!res.ok) return fail(`The link answered ${res.status}; it needs to serve the audio file itself.`);
  const audio = await readCapped(res);
  if (!audio) return fail('The recording is too large: up to 25 MB (a few minutes is plenty).');

  const reply = await askRecognizer(env.SPACE_URL, audio, u.pathname.split('/').pop() || 'clip');
  if (reply.reason) return fail('The recognizer is unavailable right now. Try again in a minute.');
  const { data } = reply;
  if (!data || data.error) return fail(`The recognizer could not use this recording${data && data.error ? `: ${data.error}` : ''}.`);

  const { raagas } = await loadReference(env);
  const page = (name, trad) => (raagas.find((x) => x.name === name && x.tradition === trad) || {}).url || null;
  const top3 = (data.top3 || []).map((t) => ({ raaga: t.raaga, tradition: t.tradition, confidence: Math.round(t.confidence * 100) / 100, url: page(t.raaga, t.tradition) }));
  const confident = !data.no_prediction && top3.length > 0 && top3[0].confidence >= NOT_SURE;
  const heard = Math.round(data.heard_seconds || 0);
  const note = !top3.length ? 'No raaga was heard: it needs a clear melody, ideally over a tanpura or drone.'
    : !confident ? 'Not sure: it may be a raaga outside the 70, or the recording needs a clearer drone. These are the closest guesses.'
    : heard < 60 ? `Heard ${heard} s; answers firm up after about a minute.` : '';
  const out = { top3, tonic_hz: data.tonic_hz ?? null, heard_seconds: heard, confident, note };
  const text = top3.length
    ? `${confident ? 'Most likely' : 'Not sure; closest'}: ${top3.map((t) => `${t.raaga} (${t.tradition}, ${Math.round(t.confidence * 100)}%)`).join(', ')}. Tonic ${out.tonic_hz ? `${Math.round(out.tonic_hz)} Hz` : 'unknown'}. ${note}`.trim()
    : note;
  return done(out, text);
}

const HANDLERS = { find_raaga: findRaaga, raagas_with_notes: raagasWithNotes, list_raagas: listRaagas, identify_raaga: identifyRaaga };

function done(structuredContent, text) { return { content: [{ type: 'text', text }], structuredContent }; }
function fail(text) { return { content: [{ type: 'text', text }], isError: true }; }

// --- the protocol ---------------------------------------------------------------------------------

const CORS = {
  'access-control-allow-origin': '*',
  'access-control-allow-methods': 'POST, OPTIONS',
  'access-control-allow-headers': 'content-type, mcp-session-id, mcp-protocol-version, authorization',
};

function rpc(body) {
  return new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...CORS } });
}
const ok = (id, result) => rpc({ jsonrpc: '2.0', id, result });
const err = (id, code, message) => rpc({ jsonrpc: '2.0', id, error: { code, message } });

/** POST one JSON-RPC request, get one JSON response. `log(event)` records a tool call for usage. */
export async function handleMcp(request, env, ctx, log) {
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: CORS });
  if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405, headers: { allow: 'POST, OPTIONS', ...CORS } });
  let msg;
  try { msg = await request.json(); } catch { return err(null, -32700, 'Parse error'); }
  if (Array.isArray(msg)) return err(null, -32600, 'Batched requests are not supported');
  if (!msg || msg.jsonrpc !== '2.0' || typeof msg.method !== 'string') return err(msg?.id ?? null, -32600, 'Invalid Request');
  const { id, method, params = {} } = msg;
  if (id === undefined) return new Response(null, { status: 202, headers: CORS });

  switch (method) {
    case 'initialize': {
      const v = SUPPORTED_VERSIONS.includes(params.protocolVersion) ? params.protocolVersion : PROTOCOL_VERSION;
      return ok(id, { protocolVersion: v, capabilities: { tools: {} }, serverInfo: SERVER_INFO, instructions: INSTRUCTIONS });
    }
    case 'ping': return ok(id, {});
    case 'tools/list': return ok(id, { tools: TOOLS });
    case 'tools/call': {
      const handler = HANDLERS[params.name];
      if (!handler) return err(id, -32602, `Unknown tool: ${params.name}`);
      if (log) ctx.waitUntil(log(`mcp:${params.name}`));
      try { return ok(id, await handler(params.arguments || {}, env)); }
      catch { return ok(id, fail(`The ${params.name} tool failed; twelveswaras may be briefly unavailable. Try again shortly.`)); }
    }
    default: return err(id, -32601, `Method not found: ${method}`);
  }
}
