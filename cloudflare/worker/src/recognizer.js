// Asking the headless recognizer (SPACE_URL/identify), for the site's /api/identify and the MCP
// server's identify_raaga.
//
// No reply, or a reply that is not JSON, means the container dropped the request: Cloudflare
// answers "Container suddenly disconnected, try again" while it restarts or moves the instance
// (3 of 135 calls on 13 Nov 2026, each fine seconds later). That is tried once more, with the same
// audio. The recognizer's own answers, JSON errors and rejected clips, are returned as they are.

const errText = (e) => String((e && e.message) || e);

/** The name the recognizer sees: clip.<the upload's extension>, or clip.webm. The recognizer reads
 *  only the extension (space/api.py decodes through a temp file with that suffix), so an m4a or mp3
 *  is decoded as one. Nothing else of a visitor's file name, or a path in it, is passed on. */
export function audioName(name) {
  const ext = /\.([a-z0-9]{1,5})$/i.exec(typeof name === 'string' ? name : '');
  return ext ? `clip.${ext[1].toLowerCase()}` : 'clip.webm';
}

/** { r, data } with the recognizer's JSON answer, or { reason, detail } when there was none twice. */
export async function askRecognizer(spaceUrl, audio, filename) {
  const once = async () => {
    const form = new FormData();
    form.append('audio', audio, audioName(filename));
    let r;
    try {
      r = await fetch(spaceUrl + '/identify', { method: 'POST', body: form });
    } catch (e) {
      return { reason: 'unreachable', detail: errText(e) };
    }
    const text = await r.text();
    try { return { r, data: JSON.parse(text) }; }
    catch { return { reason: `bad_reply:${r.status}`, detail: text }; }
  };
  const first = await once();
  return first.reason ? once() : first;
}
