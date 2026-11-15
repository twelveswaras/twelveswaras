// What a recognizer answer means, in one place: the top three with each raaga's page, whether it is
// sure, and a plain note. Shared by the hosted MCP tool identify_raaga (cloudflare/worker/src/mcp.js
// imports this file) and the command line, so the two always say the same thing. No dependencies.

export const NOT_SURE = 0.45;     // the site's own abstention threshold (site/index.html ABSTAIN_CONF)

/** The recognizer's reply and the raaga list ({ name, tradition, url }) in; the answer out:
 *  { structured: { top3, tonic_hz, heard_seconds, confident, note }, text }. */
export function describeIdentification(data, raagas) {
  const page = (name, trad) => (raagas.find((x) => x.name === name && x.tradition === trad) || {}).url || null;
  const top3 = (data.top3 || []).map((t) => ({ raaga: t.raaga, tradition: t.tradition, confidence: Math.round(t.confidence * 100) / 100, url: page(t.raaga, t.tradition) }));
  const confident = !data.no_prediction && top3.length > 0 && top3[0].confidence >= NOT_SURE;
  const heard = Math.round(data.heard_seconds || 0);
  const note = !top3.length ? 'No raaga was heard: it needs a clear melody, ideally over a tanpura or drone.'
    : !confident ? 'Not sure: it may be a raaga outside the 70, or the recording needs a clearer drone. These are the closest guesses.'
    : heard < 60 ? `Heard ${heard} s; answers firm up after about a minute.` : '';
  const structured = { top3, tonic_hz: data.tonic_hz ?? null, heard_seconds: heard, confident, note };
  const text = top3.length
    ? `${confident ? 'Most likely' : 'Not sure; closest'}: ${top3.map((t) => `${t.raaga} (${t.tradition}, ${Math.round(t.confidence * 100)}%)`).join(', ')}. Tonic ${structured.tonic_hz ? `${Math.round(structured.tonic_hz)} Hz` : 'unknown'}. ${note}`.trim()
    : note;
  return { structured, text };
}
