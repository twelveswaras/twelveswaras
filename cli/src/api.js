// twelveswaras.com, from the command line: the hosted MCP server (/mcp) for the raaga facts, and the
// site's own /api/identify and /api/result for a recording. One client, used by both the command
// line (run.js) and the local MCP server (stdio.js); every request carries the User-Agent
// twelveswaras-cli/<version>, so the site can tell this use from the browser's and an agent's.

import { readFileSync } from 'node:fs';

export const VERSION = JSON.parse(readFileSync(new URL('../package.json', import.meta.url), 'utf8')).version;
export const SITE = 'https://twelveswaras.com';
export const MAX_BYTES = 25 * 1024 * 1024;        // /identify's limit, and the hosted identify_raaga's
export const CREDIT = 'twelveswaras (twelveswaras.com), CC-BY-4.0';

/** A failure that is not the user's fault (network, the site): exit 1. */
export class Failure extends Error {}

const TIMEOUT_MS = 30_000;
const IDENTIFY_TIMEOUT_MS = 180_000;             // a cold recognizer and five minutes of audio

/** The client. io: { fetch, site }. */
export function client(io) {
  const site = io.site || SITE;
  const headers = { 'user-agent': `twelveswaras-cli/${VERSION}` };
  let id = 0;

  async function request(path, init, ms = TIMEOUT_MS) {
    try {
      return await io.fetch(`${site}${path}`, { ...init, headers: { ...headers, ...init.headers }, signal: AbortSignal.timeout(ms) });
    } catch (e) {
      throw new Failure(`Could not reach ${site} (${e.name === 'TimeoutError' ? 'timed out' : e.message}).`);
    }
  }

  async function jsonOf(res) {
    try { return await res.json(); } catch { throw new Failure(`${site} answered ${res.status} with something that is not JSON.`); }
  }

  /** One JSON-RPC call to the hosted MCP server: the whole response ({ result } or { error }). */
  async function rpc(method, params) {
    const res = await request('/mcp', {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream' },
      body: JSON.stringify({ jsonrpc: '2.0', id: ++id, method, params }),
    });
    return jsonOf(res);
  }

  /** A hosted tool's result ({ content, structuredContent, isError }). */
  async function tool(name, args) {
    const msg = await rpc('tools/call', { name, arguments: args });
    if (msg.error) throw new Failure(msg.error.message);
    return msg.result;
  }

  /** The recognizer's answer for a recording (a Blob), as the site's page gets it. */
  async function identify(audio, name) {
    const form = new FormData();
    form.append('audio', audio, name);
    const res = await request('/api/identify', { method: 'POST', body: form }, IDENTIFY_TIMEOUT_MS);
    const data = await jsonOf(res);
    if (!res.ok || data.error) throw new Failure(data.error || `${site} answered ${res.status}.`);
    return data;
  }

  /** One /result row, as the page posts when a listen ends, so the site counts this identification
   *  once. Best effort: counting must never fail an answer. */
  async function result(row) {
    try {
      await request('/api/result', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(row) });
    } catch { /* not counted, still answered */ }
  }

  return { rpc, tool, identify, result };
}
