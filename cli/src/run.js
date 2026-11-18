// The twelveswaras command line. argv and an Io in, the output and an exit code out, so every
// command is tested without a process or a network; bin/twelveswaras.js wires it to the real ones.
// With no arguments off a terminal (or `serve`) it hands over to the local MCP server (stdio.js).
//
// raaga, notes and list ask the hosted MCP server's own tools (find_raaga, raagas_with_notes,
// list_raagas) rather than carrying a second copy of the raaga data and its matching rules.

import { parseArgs } from 'node:util';
import { CREDIT, Failure, VERSION, client } from './api.js';
import { UsageError, identifyRecording } from './identify.js';

export const HELP = `twelveswaras: name the raaga in a recording of Carnatic or Hindustani music, and look up 70 raagas.

Usage:
  twelveswaras identify <file|->            the raaga in a recording (mp3, m4a, wav, ogg, webm; up to 25 MB)
  twelveswaras raaga <name>                 a raaga's scale, parent, notes, songs and page
  twelveswaras notes "S R2 G3 P D2"         the raagas that use these notes
  twelveswaras list                         the 70 raagas
  twelveswaras serve                        the MCP server on stdio (also: no arguments, piped)

Options:
  --tradition carnatic|hindustani           raaga, notes, list: one tradition only
  --from mm:ss                              identify: start there, e.g. after applause (needs ffmpeg)
  --json                                    the result as JSON
  --format text|md|json                     md is a document with the CC-BY credit
  --share                                   post the markdown to mdshare and print its link
  -o <file>                                 write the result to a file
  -h, --help / -v, --version

Results go to stdout, progress and errors to stderr. Exit 0 ok, 1 failure, 2 bad usage.
Recordings are not stored. Data: ${CREDIT}.`;

const COMMAND_HELP = {
  identify: `twelveswaras identify <file|-> [--from mm:ss] [--json | --format md] [--share] [-o file]

Uploads the recording to twelveswaras.com and prints the three likeliest raagas with confidence, the
tonic (Sa) it heard, and each raaga's page. It hears the first 5 minutes; a minute or more with a
tanpura or drone works best. --from cuts 5 minutes from that point first (needs ffmpeg), for a
recording that opens with applause or talk, or one over 25 MB. "-" reads the audio from stdin.
The recording is not stored.`,
  raaga: `twelveswaras raaga <name> [--tradition carnatic|hindustani] [--json | --format md]

Looks a raaga up in any spelling (Mohanam, Mōhanaṁ, Bhoop, "kalyani ragam"): its scale, parent,
notes, how to hear it, songs, and its page.`,
  notes: `twelveswaras notes "<notes>" [--tradition carnatic|hindustani] [--json | --format md]

The raagas whose scale is exactly these notes, and those that use them and more. Carnatic labels
(S R1 R2 G2 G3 M1 M2 P D1 D2 N2 N3) or Hindustani letters (S r R g G m M P d D n N: lowercase is
komal, M is tivra).`,
  list: `twelveswaras list [--tradition carnatic|hindustani] [--json | --format md]

The 70 raagas twelveswaras knows (40 Carnatic, 30 Hindustani), with parent and page.`,
};

const OPTIONS = {
  tradition: { type: 'string' },
  from: { type: 'string' },
  json: { type: 'boolean' },
  format: { type: 'string' },
  share: { type: 'boolean' },
  output: { type: 'string', short: 'o' },
  help: { type: 'boolean', short: 'h' },
  version: { type: 'boolean', short: 'v' },
};
const FORMATS = ['text', 'md', 'json'];
const TRADITIONS = ['carnatic', 'hindustani'];

const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const pct = (c) => `${Math.round(c * 100)}%`;
const named = (r) => `${r.name} (${r.tradition})`;
const credit = `\n---\n\nFrom ${CREDIT}. The facts are checked against published sources; not yet reviewed by a musician.\n`;

/** Ask a hosted tool; its own error is a failure, its structured answer is the result. */
async function ask(api, name, args) {
  const r = await api.tool(name, args);
  if (r.isError) throw new Failure(r.content?.[0]?.text || `${name} failed.`);
  return r.structuredContent;
}

// --- the commands: each returns { data, text(), md() } -----------------------------------------------

async function identify(pos, v, io, api) {
  if (pos.length !== 1) throw new UsageError('identify takes one recording: twelveswaras identify <file|->');
  const file = pos[0] === '-' ? 'the recording' : pos[0].split(/[\\/]/).pop();
  const { structured: d } = await identifyRecording({ path: pos[0], from: v.from }, io, api);
  const lead = !d.top3.length ? '' : d.confident ? `Most likely: ${d.top3[0].raaga}` : 'Not sure; the closest guesses:';
  const tonic = `Tonic (Sa): ${d.tonic_hz ? `${Math.round(d.tonic_hz)} Hz` : 'not found'}. Heard ${d.heard_seconds} s.`;
  return {
    data: d,
    title: `The raaga in ${file}`,
    text: () => [lead, ...d.top3.map((t) => `  ${pct(t.confidence).padStart(4)}  ${named({ name: t.raaga, tradition: t.tradition }).padEnd(28)} ${t.url || ''}`),
      tonic, d.note].filter(Boolean).join('\n'),
    md: () => [`# The raaga in ${file}`, '', lead && `**${lead}**`, '',
      ...(d.top3.length ? ['| | Raaga | Tradition | Confidence |', '|---|---|---|---|',
        ...d.top3.map((t, i) => `| ${i + 1} | ${t.url ? `[${t.raaga}](${t.url})` : t.raaga} | ${cap(t.tradition || '')} | ${pct(t.confidence)} |`), ''] : []),
      tonic, '', d.note,
      `\n---\n\nIdentified by [twelveswaras](https://twelveswaras.com), CC-BY-4.0. On real recordings its top answer is right about 71% of the time, and the right raaga is in its top three about 80% of the time.\n`,
    ].filter((l) => l !== false && l !== null && l !== undefined).join('\n').replace(/\n{3,}/g, '\n\n'),
  };
}

function scaleLines(r) {
  const [up, down] = r.tradition === 'hindustani' ? ['Aroh', 'Avroh'] : ['Arohanam', 'Avarohanam'];
  const phrases = r.notes?.used_in_phrases?.length ? ` (in phrases: ${r.notes.used_in_phrases.join(' ')})` : '';
  return [[up, r.arohanam], [down, r.avarohanam], ['Notes', r.notes?.scale && r.notes.scale.join(' ') + phrases],
    ['How to hear', r.how_to_hear], ['Songs', r.songs?.length && r.songs.join('; ')], ['Confused with', r.confused_with]]
    .filter(([, val]) => val);
}

async function raaga(pos, v, io, api) {
  if (pos.length !== 1) throw new UsageError('raaga takes one name: twelveswaras raaga <name> (quote a name with spaces)');
  const d = await ask(api, 'find_raaga', { name: pos[0], ...(v.tradition && { tradition: v.tradition }) });
  if (!d.matches.length) throw new Failure(`"${pos[0]}" is not among the 70 raagas twelveswaras knows. twelveswaras list gives them all.`);
  return {
    data: d,
    title: d.matches.map((r) => r.name).join(', '),
    text: () => d.matches.map((r) => [`${named(r)}, parent ${r.parent}`,
      ...scaleLines(r).map(([k, val]) => `  ${k.padEnd(14)}${val}`), `  ${r.url}`].join('\n')).join('\n\n'),
    md: () => d.matches.map((r) => [`# ${r.name}`, '', `${cap(r.tradition)} raaga, parent ${r.parent}. [Its page](${r.url}).`, '',
      ...scaleLines(r).map(([k, val]) => `- **${k}:** ${val}`)].join('\n')).join('\n\n') + `\n${credit}`,
  };
}

async function notes(pos, v, io, api) {
  if (pos.length !== 1) throw new UsageError('notes takes the notes as one quoted argument: twelveswaras notes "S R2 G3 P D2"');
  const d = await ask(api, 'raagas_with_notes', { notes: pos[0], ...(v.tradition && { tradition: v.tradition }) });
  const line = (rs) => rs.map(named).join(', ') || 'none';
  const links = (rs) => rs.map((r) => `- [${r.name}](${r.url}) (${r.tradition}, parent ${r.parent})`).join('\n') || 'None.';
  return {
    data: d,
    title: `Raagas with ${pos[0]}`,
    text: () => `Exactly these notes:  ${line(d.exact)}\nThese and more:       ${line(d.containing)}`,
    md: () => `# Raagas with ${pos[0]}\n\n## Exactly these notes\n\n${links(d.exact)}\n\n## These notes and more\n\n${links(d.containing)}\n${credit}`,
  };
}

async function list(pos, v, io, api) {
  if (pos.length) throw new UsageError('list takes no arguments, only --tradition');
  const d = await ask(api, 'list_raagas', v.tradition ? { tradition: v.tradition } : {});
  const w = Math.max(...d.raagas.map((r) => r.name.length));
  return {
    data: d,
    title: v.tradition ? `The ${cap(v.tradition)} raagas twelveswaras knows` : 'The raagas twelveswaras knows',
    text: () => d.raagas.map((r) => `${r.name.padEnd(w)}  ${r.tradition.padEnd(10)}  ${r.url}`).join('\n'),
    md: () => `# ${v.tradition ? `The ${cap(v.tradition)} raagas` : 'The raagas'} twelveswaras knows\n\n| Raaga | Tradition | Parent |\n|---|---|---|\n`
      + d.raagas.map((r) => `| [${r.name}](${r.url}) | ${cap(r.tradition)} | ${r.parent} |`).join('\n') + `\n${credit}`,
  };
}

const COMMANDS = { identify, raaga, notes, list };

// --- the whole run --------------------------------------------------------------------------------

const out = (stdout, code = 0) => ({ code, stdout, stderr: '' });
const err = (stderr, code) => ({ code, stdout: '', stderr: `${stderr}\n` });

/** { code, stdout, stderr } for argv, or { serve: true } to run the MCP server. */
export async function run(argv, io) {
  if (!argv.length) return io.isTTY ? out(`${HELP}\n`) : { code: 0, stdout: '', stderr: '', serve: true };
  let parsed;
  try { parsed = parseArgs({ args: argv, options: OPTIONS, allowPositionals: true, strict: true }); }
  catch (e) { return err(`${e.message}\n\nRun twelveswaras --help for the commands.`, 2); }
  const { values: v, positionals: [cmd, ...pos] } = parsed;

  if (v.version) return out(`${VERSION}\n`);
  if (cmd === 'serve') return { code: 0, stdout: '', stderr: '', serve: true };
  if (!cmd || cmd === 'help') return out(`${HELP}\n`);
  if (!COMMANDS[cmd]) return err(`Unknown command: ${cmd}. Run twelveswaras --help for the commands.`, 2);
  if (v.help) return out(`${COMMAND_HELP[cmd]}\n`);
  if (v.tradition && !TRADITIONS.includes(v.tradition)) return err(`--tradition is carnatic or hindustani, not "${v.tradition}".`, 2);
  if (v.format && !FORMATS.includes(v.format)) return err(`--format is text, md or json, not "${v.format}".`, 2);
  const format = v.share ? 'md' : v.json ? 'json' : v.format || 'text';

  try {
    const r = await COMMANDS[cmd](pos, v, io, client(io));
    const body = format === 'json' ? `${JSON.stringify(r.data, null, 2)}\n` : `${r[format]().trimEnd()}\n`;
    if (v.share) return out(`${await io.share(body, r.title)}\n`);
    if (v.output) {
      await io.writeFile(v.output, body);
      io.progress(`Wrote ${v.output}`);
      return out('');
    }
    return out(body);
  } catch (e) {
    if (e instanceof UsageError) return err(e.message, 2);
    if (e instanceof Failure) return err(e.message, 1);
    return err(`twelveswaras failed: ${e.message}`, 1);
  }
}
