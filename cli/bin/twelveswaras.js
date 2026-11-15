#!/usr/bin/env node
// The `twelveswaras` bin: wires run() (src/run.js) to the process, or serves MCP on stdio.

import { execFile, spawn } from 'node:child_process';
import * as fs from 'node:fs';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { createInterface } from 'node:readline';
import { Failure, SITE } from '../src/api.js';
import { run } from '../src/run.js';
import { mcpServer } from '../src/stdio.js';

const io = {
  isTTY: Boolean(process.stdin.isTTY),
  fetch: globalThis.fetch,
  site: process.env.TWELVESWARAS_URL || SITE,
  progress: (line) => process.stderr.write(`${line}\n`),

  async size(path) {
    const s = await stat(path);
    if (!s.isFile()) throw new Error('not a file');
    return s.size;
  },
  // openAsBlob (Node 19.8+) streams the file into the upload; Node 18 reads it (already size-checked)
  blob: async (path) => (fs.openAsBlob ? fs.openAsBlob(path) : new Blob([await readFile(path)])),

  /** stdin, but never more than `cap` bytes held. */
  async readStdin(cap) {
    const chunks = [];
    let size = 0;
    for await (const c of process.stdin) {
      chunks.push(c);
      size += c.length;
      if (size >= cap) break;
    }
    return new Uint8Array(Buffer.concat(chunks));
  },

  hasFfmpeg: () => new Promise((ok) => execFile('ffmpeg', ['-version'], (e) => ok(!e))),

  /** `seconds` of the recording from `from`, as a mono WAV in a new temp directory. */
  async cut(path, from, seconds) {
    const out = join(await mkdtemp(join(tmpdir(), 'twelveswaras-')), 'clip.wav');
    await new Promise((ok, fail) => execFile('ffmpeg',
      ['-hide_banner', '-loglevel', 'error', '-nostdin', '-ss', String(from), '-i', path, '-t', String(seconds), '-vn', '-ac', '1', '-ar', '22050', out],
      (e, _o, stderr) => (e ? fail(new Failure(`ffmpeg could not cut ${path}: ${String(stderr).trim().split('\n').pop()}`)) : ok())));
    return out;
  },
  remove: (path) => rm(dirname(path), { recursive: true, force: true }),

  /** The markdown, posted with mdshare's own command line (its key stays in its own store); the link. */
  share: (md, title) => new Promise((ok, fail) => {
    const child = spawn('npx', ['-y', 'mdshare-mcp', 'upload', '-', '--title', title], { stdio: ['pipe', 'pipe', 'inherit'] });
    let link = '';
    child.stdout.on('data', (d) => { link += d; });
    child.on('error', (e) => fail(new Failure(`Could not run npx mdshare-mcp: ${e.message}`)));
    child.on('close', (code) => (code === 0 && link.trim()
      ? ok(link.trim().split('\n').pop())
      : fail(new Failure('mdshare-mcp upload failed; the result was not shared.'))));
    child.stdin.end(md);
  }),
  writeFile: (path, text) => writeFile(path, text),
};

function serve() {
  const handleLine = mcpServer(io);
  const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
  rl.on('line', async (line) => {
    const reply = await handleLine(line);
    if (reply) process.stdout.write(`${reply}\n`);
  });
}

const r = await run(process.argv.slice(2), io);
if (r.serve) serve();
else {
  if (r.stdout) process.stdout.write(r.stdout);
  if (r.stderr) process.stderr.write(r.stderr);
  process.exitCode = r.code;
}
