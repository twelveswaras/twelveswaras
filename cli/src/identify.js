// Identify the raaga in a recording on this machine: the one thing the hosted MCP tool cannot do
// (it takes only a public URL). Used by `twelveswaras identify` and by the local MCP server's
// identify_raaga { path }.

import { basename } from 'node:path';
import { MAX_BYTES } from './api.js';
import { describeIdentification } from './describe.js';

/** Bad input (a missing or oversized file, no ffmpeg for --from): exit 2. */
export class UsageError extends Error {}

const ANALYSED_SECONDS = 300;     // the recognizer hears only the first 5 minutes (space/api.py)
const mb = (n) => `${(n / 1024 / 1024).toFixed(1)} MB`;

/** "2:30", "1:02:03" or "90" in seconds; null for anything else. */
export function parseTime(s) {
  if (!/^\d+(:[0-5]\d){0,2}$/.test(String(s))) return null;
  return String(s).split(':').reduce((acc, part) => acc * 60 + Number(part), 0);
}

/** The audio to upload ({ blob, name }), cut from `from` when asked. Checks the size before reading. */
async function loadAudio(path, from, io) {
  if (from !== undefined) {
    const secs = parseTime(from);
    if (secs === null) throw new UsageError(`--from takes mm:ss, h:mm:ss or seconds, not "${from}".`);
    if (path === '-') throw new UsageError('--from needs a file, not stdin.');
    if (!(await io.hasFfmpeg())) throw new UsageError('--from needs ffmpeg (https://ffmpeg.org) on your PATH to cut the recording. Install it, or cut the file yourself.');
    io.progress(`Cutting ${ANALYSED_SECONDS / 60} minutes from ${from} with ffmpeg...`);
    const cut = await io.cut(path, secs, ANALYSED_SECONDS);
    return { ...(await loadFile(cut, 'clip.wav', io)), cut };
  }
  if (path === '-') {
    const bytes = await io.readStdin(MAX_BYTES + 1);
    if (bytes.length > MAX_BYTES) throw tooLarge('stdin', bytes.length);
    return { blob: new Blob([bytes]), name: 'clip.webm' };
  }
  return loadFile(path, basename(path), io);
}

async function loadFile(path, name, io) {
  let size;
  try { size = await io.size(path); }
  catch (e) { throw new UsageError(e.code === 'ENOENT' ? `No such file: ${path}` : `Cannot read ${path}: ${e.message}`); }
  if (size > MAX_BYTES) throw tooLarge(path, size);
  return { blob: await io.blob(path), name };
}

function tooLarge(what, size) {
  return new UsageError(`${what} is ${mb(size)}; twelveswaras takes up to 25 MB and hears only the first ${ANALYSED_SECONDS / 60} minutes. `
    + 'Cut a piece with --from (e.g. --from 0:00, or later to skip applause or talk; needs ffmpeg).');
}

/** { structured, text } as the identify_raaga tool answers, and one /result row posted as source cli. */
export async function identifyRecording({ path, from }, io, api) {
  const audio = await loadAudio(path, from, io);
  try {
    io.progress(`Listening to ${audio.name} (${mb(audio.blob.size)}); this takes up to a minute...`);
    const t0 = Date.now();
    const data = await api.identify(audio.blob, audio.name);
    const { raagas } = (await api.tool('list_raagas', {})).structuredContent;
    const answer = describeIdentification(data, raagas);
    const top3 = data.top3 || [];
    await api.result({
      top3, tonic_hz: data.tonic_hz ?? null, heard_seconds: data.heard_seconds ?? null,
      elapsed_s: Math.round((Date.now() - t0) / 100) / 10, source: 'cli', reason: data.reason ?? null,
      no_prediction: top3.length ? 0 : 1, referrer: null,
    });
    return answer;
  } finally {
    if (audio.cut) await io.remove?.(audio.cut);
  }
}
