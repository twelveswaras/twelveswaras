// Use by mode (web, api, cli, mcp) and MCP calls by AI client product, counted without keeping
// anything about the caller: the User-Agent and clientInfo.name are read to pick a mode or a product
// from a fixed set and then dropped.
//
//   node --test cloudflare/worker/test/
import test from 'node:test';
import assert from 'node:assert/strict';

import { callerMode, isBot, mcpClient, MCP_CLIENTS } from '../src/usage.js';

const req = (headers = {}) => new Request('https://twelveswaras.com/api/identify', { method: 'POST', headers });

test('callerMode: the site (its own origins) is web', () => {
  for (const origin of ['https://twelveswaras.com', 'https://www.twelveswaras.com', 'https://abc.twelveswaras-site.pages.dev',
                        'http://localhost:8000', 'http://127.0.0.1:5500']) {
    assert.equal(callerMode(req({ Origin: origin })), 'web', origin);
  }
  assert.equal(callerMode(req({ 'sec-fetch-site': 'same-origin' })), 'web');
});

test('callerMode: the twelveswaras command line is cli', () => {
  assert.equal(callerMode(req({ 'user-agent': 'twelveswaras-cli/0.3.0' })), 'cli');
});

test('callerMode: anything else that is not a bot is api', () => {
  assert.equal(callerMode(req({ 'user-agent': 'curl/8.4.0' })), 'api');
  assert.equal(callerMode(req({ 'user-agent': 'python-requests/2.31' })), 'api');
  assert.equal(callerMode(req({})), 'api');
  assert.equal(callerMode(req({ Origin: 'https://evil.example', 'user-agent': 'Mozilla/5.0' })), 'api');
});

test('callerMode: bots are not counted (null)', () => {
  for (const ua of ['Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)', 'GPTBot/1.1',
                    'Mozilla/5.0 (compatible; bingbot/2.0)', 'AhrefsBot/7.0', 'UptimeRobot/2.0', 'HeadlessChrome/120',
                    'facebookexternalhit/1.1 crawler', 'Baiduspider']) {
    assert.equal(callerMode(req({ 'user-agent': ua })), null, ua);
  }
});

test('isBot does not catch real agents or the command line', () => {
  for (const ua of ['claude-code/2.0', 'Claude-User', 'openai-mcp/1.0', 'ChatGPT-User/1.0', 'twelveswaras-cli/0.3.0',
                    'node', 'curl/8.4.0', '', null]) {
    assert.equal(isBot(ua), false, String(ua));
  }
});

test('mcpClient maps clientInfo.name to a small fixed set', () => {
  const cases = {
    'claude-ai': 'claude-ai', 'Claude Desktop': 'claude-ai', 'claude-code': 'claude-code', 'Claude Code': 'claude-code',
    'cursor-vscode': 'cursor', Cursor: 'cursor', 'openai-mcp': 'chatgpt', ChatGPT: 'chatgpt',
    'Visual Studio Code': 'vscode', 'Visual Studio Code - Insiders': 'vscode', 'github-copilot': 'vscode',
    windsurf: 'windsurf', 'Codeium Windsurf': 'windsurf', 'codex-mcp-client': 'codex', 'gemini-cli-mcp-client': 'gemini',
    Cline: 'cline', 'mcp-inspector': 'inspector',
    'my-own-agent': 'other', '': 'other',
  };
  for (const [name, want] of Object.entries(cases)) assert.equal(mcpClient(name), want, name);
  for (const v of [undefined, null, 42, {}, ['claude']]) assert.equal(mcpClient(v), 'other', String(v));
});

test('mcpClient never returns the raw string: every answer is in the fixed set', () => {
  for (const name of ['claude-ai', 'x'.repeat(500), 'Robert"); DROP TABLE events;--', 'Someone\'s laptop']) {
    assert.ok(MCP_CLIENTS.includes(mcpClient(name)), name);
  }
});
