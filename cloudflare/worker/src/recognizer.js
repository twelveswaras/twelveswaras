// Asking the headless recognizer (SPACE_URL/identify), for the site's /api/identify and the MCP
// server's identify_raaga.
//
// No reply, or a reply that is not JSON, means the container dropped the request: Cloudflare
// answers "Container suddenly disconnected, try again" while it restarts or moves the instance
// (3 of 135 calls on 13 Nov 2026, each fine seconds later). That is tried once more, with the same
// audio. The recognizer's own answers, JSON errors and rejected clips, are returned as they are.

const errText = (e) => String((e && e.message) || e);

/** { r, data } with the recognizer's JSON answer, or { reason, detail } when there was none twice. */
export async function askRecognizer(spaceUrl, audio, filename) {
  const once = async () => {
    const form = new FormData();
    form.append('audio', audio, filename);
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
