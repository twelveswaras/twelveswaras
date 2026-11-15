// The local MCP server (newline-delimited JSON-RPC on stdin/stdout). It is the hosted server at
// twelveswaras.com/mcp, passed through, with one addition: identify_raaga also takes a `path` to a
// recording on this machine (the hosted tool takes only a public URL), which is uploaded the way
// `twelveswaras identify` uploads it. Everything else is answered by the hosted server itself, so
// the tools, their data and their wording live in one place.

import { Failure, VERSION, client } from './api.js';
import { identifyRecording } from './identify.js';

const LOCAL = {
  path: { type: 'string', description: 'A recording on this machine (mp3, wav, m4a, ogg, webm; up to 25 MB). Use this or audio_url.' },
  from: { type: 'string', description: 'With path: start here (mm:ss), e.g. after applause or talk. Needs ffmpeg.' },
};
// The local path is for recordings only: a prompt must not be able to have this server upload any
// other file on the machine.
const AUDIO = /\.(mp3|m4a|mp4|aac|wav|ogg|oga|opus|webm|flac)$/i;
const LOCAL_NOTE = '\n\nThis is the local twelveswaras server: identify_raaga also takes `path`, a recording on this machine, instead of a public audio_url.';

/** identify_raaga as the local server describes it: the hosted tool plus `path` and `from`. */
function withPath(tool) {
  if (tool.name !== 'identify_raaga') return tool;
  const { required, ...schema } = tool.inputSchema;
  return {
    ...tool,
    description: `${tool.description} Or give \`path\`, a recording on this machine.`,
    inputSchema: { ...schema, properties: { ...schema.properties, ...LOCAL } },
  };
}

/** handleLine(line) → the reply line, or null (a notification, or a blank line). */
export function mcpServer(io) {
  const api = client(io);

  async function answer(msg) {
    const { id, method, params = {} } = msg;
    if (method === 'tools/call' && params.name === 'identify_raaga' && params.arguments?.path) {
      try {
        if (!AUDIO.test(params.arguments.path)) throw new Error('path must be an audio file: mp3, m4a, wav, ogg, webm, flac, aac or opus.');
        const { structured, text } = await identifyRecording(params.arguments, io, api);
        return { jsonrpc: '2.0', id, result: { content: [{ type: 'text', text }], structuredContent: structured } };
      } catch (e) {
        return { jsonrpc: '2.0', id, result: { content: [{ type: 'text', text: e.message }], isError: true } };
      }
    }
    const reply = await api.rpc(method, params);
    if (reply.result && method === 'initialize') {
      reply.result.serverInfo = { ...reply.result.serverInfo, version: VERSION };
      reply.result.instructions = `${reply.result.instructions || ''}${LOCAL_NOTE}`;
    }
    if (reply.result && method === 'tools/list') reply.result.tools = reply.result.tools.map(withPath);
    return { ...reply, id };
  }

  return async function handleLine(line) {
    if (!line.trim()) return null;
    let msg;
    try { msg = JSON.parse(line); } catch { return JSON.stringify({ jsonrpc: '2.0', id: null, error: { code: -32700, message: 'Parse error' } }); }
    if (!msg || msg.id === undefined) return null;          // a notification: nothing to answer
    try {
      return JSON.stringify(await answer(msg));
    } catch (e) {
      const message = e instanceof Failure ? e.message : `twelveswaras failed: ${e.message}`;
      return JSON.stringify({ jsonrpc: '2.0', id: msg.id, error: { code: -32603, message } });
    }
  };
}
