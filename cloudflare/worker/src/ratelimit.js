// A per-IP limit on identifying, shared by /identify and the MCP tool identify_raaga, so a scripted
// loop cannot keep the recognizer container busy for everyone. A live listen sends at most 24
// /identify calls (one every 3.5 to 7 s for up to 150 s: maybeSend in site/index.html) and an upload
// sends one, so a person running four listens back to back stays under 100 in ten minutes; a loop
// does not. Counted in D1 (one row per address, as mdshare's create limit) because a per-isolate
// counter in memory never holds across Cloudflare's edge. Fails open: if D1 cannot count (no
// binding, or the table not yet created), nobody is blocked.
// No address is kept: a row's key is a SHA-256 of the address and the secret RATE_LIMIT_SALT (so
// the 2^32 IPv4 addresses can't be tried against it), and each call first deletes the rows whose
// window has ended, so a row lasts about ten minutes after a caller's last identification.
const IDENTIFY_LIMIT = { max: 100, windowSec: 600 };

/** Seconds until this address may identify again, or 0 when it is under the limit. */
export async function identifyLimited(env, request) {
  const ip = request.headers.get('cf-connecting-ip') || 'unknown';
  const now = Date.now();
  const resetAt = now + IDENTIFY_LIMIT.windowSec * 1000;
  try {
    const key = `identify:${await sha256Hex(`${env.RATE_LIMIT_SALT || ''}:${ip}`)}`;
    await env.DB.prepare('DELETE FROM rate_limits WHERE reset_at < ?').bind(now).run();
    // one atomic upsert: a new window starts at 1, otherwise the count goes up by one
    const row = await env.DB.prepare(
      `INSERT INTO rate_limits (key, count, reset_at) VALUES (?, 1, ?)
       ON CONFLICT(key) DO UPDATE SET
         count    = CASE WHEN rate_limits.reset_at < ? THEN 1 ELSE rate_limits.count + 1 END,
         reset_at = CASE WHEN rate_limits.reset_at < ? THEN ? ELSE rate_limits.reset_at END
       RETURNING count, reset_at`
    ).bind(key, resetAt, now, now, resetAt).first();
    if (!row || row.count <= IDENTIFY_LIMIT.max) return 0;
    return Math.max(1, Math.ceil((row.reset_at - now) / 1000));
  } catch {
    return 0;
  }
}

async function sha256Hex(text) {
  const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(d)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** The plain message for a caller over the limit. */
export function tooMany(wait) {
  return `Too many recordings from this address. Try again in ${Math.ceil(wait / 60)} min.`;
}
