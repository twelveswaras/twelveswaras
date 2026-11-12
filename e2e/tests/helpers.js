// Shared Worker stubs for the browser tests.
//
// IMPORTANT: on localhost the page's API base resolves to the LIVE workers.dev Worker (see the
// API constant in site/index.html), so an un-stubbed call from a test would write junk straight
// into production D1. One handler therefore owns every request to the API and dispatches by path,
// and anything it does not recognise is ABORTED rather than allowed through. If a new endpoint is
// added to the page, these tests fail loudly instead of quietly logging from CI.
const ACT = [0.9, 0.1, 0.2, 0.05, 0.7, 0.3, 0.1, 0.8, 0.1, 0.2, 0.05, 0.6];

// A fake microphone that grants permission without a prompt: `test.use(FAKE_MIC)`.
const FAKE_MIC = {
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
};

/** Fulfil a route with a JSON body. */
function answer(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

/**
 * Own every API call for the page. /identify answers with the chosen top-3, unless `identify`
 * (a route handler) says otherwise; the logging endpoints are swallowed and recorded.
 * Returns the array that /event bodies are pushed into, so a test can assert the funnel, with:
 *   .results        /result bodies
 *   .calls          { warm, identify } counts
 *   .contributions  accepted /contribute posts
 * Call this BEFORE page.goto(): the `view` event and the /warm ping fire as the page initialises.
 */
async function stubApi(page, { top3 = [], tonicHz = 146, identify = null } = {}) {
  const events = [];
  events.results = [];
  events.calls = { warm: 0, identify: 0 };
  events.contributions = 0;
  await page.route(/twelveswaras-api|\/api\//, (route) => {
    const url = route.request().url();
    if (url.endsWith('/identify')) {
      events.calls.identify += 1;
      if (identify) return identify(route);
      return answer(route, { tonic_hz: tonicHz, swara_activation: ACT, top3 });
    }
    if (url.endsWith('/warm')) { events.calls.warm += 1; return route.fulfill({ status: 200, body: '{"warm":true}' }); }
    if (url.endsWith('/result')) {
      try { events.results.push(JSON.parse(route.request().postData() || '{}')); } catch { /* ignore */ }
      return route.fulfill({ status: 200, body: '{}' });
    }
    if (url.endsWith('/contribute')) {
      events.contributions += 1;
      return answer(route, { ok: true });
    }
    if (url.endsWith('/event')) {
      try { events.push(JSON.parse(route.request().postData() || '{}')); } catch { /* ignore */ }
      return route.fulfill({ status: 200, body: '{}' });
    }
    return route.abort();
  });
  return events;
}

/** Jump the page clock (each due timer fires once, as after a real wait), then let replies land. */
async function jump(page, ms) {
  await page.clock.fastForward(ms);
  await page.waitForTimeout(500);
  await page.clock.fastForward(100);
}

/** A silent mono 16-bit WAV of the given length, small enough to upload quickly (8 kHz). */
function wav(seconds) {
  const sr = 8000, n = Math.round(seconds * sr), b = Buffer.alloc(44 + n * 2);
  b.write('RIFF', 0); b.writeUInt32LE(36 + n * 2, 4); b.write('WAVE', 8); b.write('fmt ', 12);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(sr, 24);
  b.writeUInt32LE(sr * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34);
  b.write('data', 36); b.writeUInt32LE(n * 2, 40);
  return { name: `clip-${seconds}s.wav`, mimeType: 'audio/wav', buffer: b };
}

module.exports = { stubApi, answer, jump, ACT, FAKE_MIC, wav };
