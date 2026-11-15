// The local MCP server (no arguments, or `serve`): the hosted tools, proxied, with one addition:
// identify_raaga also takes a `path` to a recording on this machine, which the hosted tool cannot.
import test from 'node:test';
import assert from 'node:assert/strict';

import { mcpServer } from '../src/stdio.js';
import { VERSION } from '../src/api.js';

const SITE = 'https://site.test';
const HOSTED_TOOLS = [
  { name: 'find_raaga', inputSchema: { type: 'object', properties: { name: { type: 'string' } }, required: ['name'] } },
  { name: 'identify_raaga', description: 'Name the raaga in a recording at a public http(s) URL.',
    inputSchema: { type: 'object', properties: { audio_url: { type: 'string' } }, required: ['audio_url'] } },
];

function hosted() {
  const calls = [];
  const fetch = async (url, init = {}) => {
    calls.push({ url, init });
    if (url === `${SITE}/mcp`) {
      const msg = JSON.parse(init.body);
      const reply = (result) => Response.json({ jsonrpc: '2.0', id: msg.id, result });
      if (msg.method === 'initialize') return reply({ protocolVersion: '2025-06-18', capabilities: { tools: {} }, serverInfo: { name: 'twelveswaras', version: '1' }, instructions: 'identify_raaga to name the raaga in a recording at a public URL.' });
      if (msg.method === 'tools/list') return reply({ tools: HOSTED_TOOLS });
      if (msg.method === 'tools/call' && msg.params.name === 'list_raagas') return reply({ content: [], structuredContent: { raagas: [{ name: 'Kalyāṇi', tradition: 'carnatic', url: 'https://twelveswaras.com/raaga/kalyani' }] } });
      return reply({ content: [{ type: 'text', text: `hosted ${msg.params.name}` }], structuredContent: { echoed: msg.params } });
    }
    if (url === `${SITE}/api/identify`) return Response.json({ no_prediction: false, tonic_hz: 140, heard_seconds: 80, top3: [{ raaga: 'Kalyāṇi', tradition: 'carnatic', confidence: 0.9 }] });
    if (url === `${SITE}/api/result`) return Response.json({ ok: true });
    return new Response('nope', { status: 404 });
  };
  return { fetch, calls };
}

function server(over = {}) {
  const h = hosted();
  const io = {
    site: SITE, fetch: h.fetch, progress: () => {},
    size: async () => over.size ?? 4000, blob: async () => new Blob([new Uint8Array(10)]),
    hasFfmpeg: async () => true, cut: async () => '/tmp/cut.wav',
  };
  return { line: mcpServer(io), calls: h.calls };
}
const send = async (line, msg) => JSON.parse(await line(JSON.stringify({ jsonrpc: '2.0', id: 7, ...msg })));

test('initialize answers as the local twelveswaras server and says identify_raaga takes a local path', async () => {
  const { line } = server();
  const r = (await send(line, { method: 'initialize', params: { protocolVersion: '2025-06-18' } })).result;
  assert.equal(r.serverInfo.name, 'twelveswaras');
  assert.equal(r.serverInfo.version, VERSION);
  assert.match(r.instructions, /path/);
});

test('tools/list is the hosted list, with identify_raaga also taking a local path', async () => {
  const { line } = server();
  const { tools } = (await send(line, { method: 'tools/list' })).result;
  assert.deepEqual(tools.map((t) => t.name), ['find_raaga', 'identify_raaga']);
  const id = tools.find((t) => t.name === 'identify_raaga');
  assert.ok(id.inputSchema.properties.path);
  assert.ok(id.inputSchema.properties.audio_url);
  assert.ok(id.inputSchema.properties.from);
  assert.equal(id.inputSchema.required, undefined, 'either audio_url or path');
  assert.match(id.description, /path/);
  assert.deepEqual(HOSTED_TOOLS[1].inputSchema.required, ['audio_url'], 'the hosted list is not mutated');
});

test('identify_raaga with a path uploads the local file, never asks the hosted tool', async () => {
  const { line, calls } = server();
  const r = (await send(line, { method: 'tools/call', params: { name: 'identify_raaga', arguments: { path: '/music/concert.m4a' } } })).result;
  assert.equal(r.structuredContent.top3[0].url, 'https://twelveswaras.com/raaga/kalyani');
  assert.match(r.content[0].text, /Most likely/);
  assert.ok(calls.some((c) => c.url === `${SITE}/api/identify`));
  assert.ok(!calls.some((c) => c.url === `${SITE}/mcp` && JSON.parse(c.init.body).params?.name === 'identify_raaga'));
});

test('identify_raaga with a path that cannot be used is a tool error, not a protocol fault', async () => {
  const { line } = server({ size: 40 * 1024 * 1024 });
  const r = await send(line, { method: 'tools/call', params: { name: 'identify_raaga', arguments: { path: '/music/concert.m4a' } } });
  assert.equal(r.result.isError, true);
  assert.match(r.result.content[0].text, /25 MB/);
});

test('every other call goes to the hosted server unchanged', async () => {
  const { line } = server();
  const r = (await send(line, { method: 'tools/call', params: { name: 'identify_raaga', arguments: { audio_url: 'https://example.org/a.mp3' } } })).result;
  assert.equal(r.content[0].text, 'hosted identify_raaga');
  const f = (await send(line, { method: 'tools/call', params: { name: 'find_raaga', arguments: { name: 'kalyani' } } })).result;
  assert.deepEqual(f.structuredContent.echoed, { name: 'find_raaga', arguments: { name: 'kalyani' } });
});

test('a notification gets no reply; a line that is not JSON is a parse error', async () => {
  const { line } = server();
  assert.equal(await line(JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' })), null);
  assert.equal(await line('   '), null);
  assert.equal(JSON.parse(await line('{nope')).error.code, -32700);
});

test('the hosted server being unreachable is a JSON-RPC error with the reason, not a crash', async () => {
  const line = mcpServer({ site: SITE, fetch: async () => { throw new TypeError('fetch failed'); }, progress: () => {} });
  const r = await send(line, { method: 'tools/list' });
  assert.match(r.error.message, /could not reach/i);
});

// An agent can be talked into anything; the local path is for recordings only, so a prompt cannot
// have this server upload ~/.ssh/id_rsa or a spreadsheet.
test('identify_raaga with a path takes only an audio file', async () => {
  const { line, calls } = server();
  for (const path of ['/home/me/.ssh/id_rsa', '/home/me/notes.txt', '/home/me/clip']) {
    const r = await send(line, { method: 'tools/call', params: { name: 'identify_raaga', arguments: { path } } });
    assert.equal(r.result.isError, true, path);
    assert.match(r.result.content[0].text, /audio file/);
  }
  assert.equal(calls.length, 0);
});
