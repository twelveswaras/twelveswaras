// Use by mode, and MCP calls by AI client product, with nothing about the caller kept. The
// User-Agent, Origin and MCP clientInfo.name are READ here to pick one value from a closed set, and
// only that value is written (as an events row: ts, event, source; no session, country or referrer).
//
// Modes: web (the site), cli (the twelveswaras command line), api (any other caller), mcp (the MCP
// server; decided in index.js). Bots are not counted.

/** One of the site's own hosts: production, Pages previews, or local development. */
export function isSiteHost(host) {
  return host === 'twelveswaras.com' || host === 'www.twelveswaras.com' ||
    host === 'localhost' || host === '127.0.0.1' || host.endsWith('.pages.dev');
}

const CLI_UA = /^twelveswaras-cli\//;
// Crawlers, link previews, uptime checks and headless browsers. Read, never stored.
const BOT_UA = /bot\b|crawl|spider|slurp|headless|uptime|monitor/i;

export const isCli = (ua) => CLI_UA.test(ua || '');
export const isBot = (ua) => BOT_UA.test(ua || '');

/** 'web' | 'cli' | 'api' for an /api request, or null for a bot (not counted). */
export function callerMode(request) {
  const ua = request.headers.get('user-agent');
  if (isBot(ua)) return null;
  if (isCli(ua)) return 'cli';
  const origin = request.headers.get('origin');
  let host = '';
  try { host = origin ? new URL(origin).hostname : ''; } catch { /* not a URL: not the site */ }
  if (isSiteHost(host) || request.headers.get('sec-fetch-site') === 'same-origin') return 'web';
  return 'api';
}

// The AI client products an MCP session is counted under, tested in order (claude-code before
// claude-ai, cursor-vscode is Cursor, not VS Code). Anything else is 'other'.
const CLIENT_RULES = [
  ['claude-code', /claude[ -]?code/],
  ['claude-ai', /claude/],
  ['cursor', /cursor/],
  ['windsurf', /windsurf|codeium/],
  ['vscode', /visual studio code|vscode|copilot/],
  ['chatgpt', /chatgpt|openai/],
  ['codex', /codex/],
  ['gemini', /gemini/],
  ['cline', /\bcline\b/],
  ['inspector', /inspector/],
];
export const MCP_CLIENTS = [...CLIENT_RULES.map(([name]) => name), 'other'];

/** initialize's params.clientInfo.name, reduced to one of MCP_CLIENTS. The raw name is dropped. */
export function mcpClient(name) {
  if (typeof name !== 'string') return 'other';
  const n = name.toLowerCase().slice(0, 100);
  const hit = CLIENT_RULES.find(([, re]) => re.test(n));
  return hit ? hit[0] : 'other';
}
