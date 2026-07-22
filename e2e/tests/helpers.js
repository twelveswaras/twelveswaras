// Shared Worker stubs for the browser tests.
//
// IMPORTANT: on localhost the page's API base resolves to the LIVE workers.dev Worker (see the
// API constant in site/index.html), so an un-stubbed call from a test would write junk straight
// into production D1. One handler therefore owns every request to the API and dispatches by path,
// and anything it does not recognise is ABORTED rather than allowed through. If a new endpoint is
// added to the page, these tests fail loudly instead of quietly logging from CI.
const ACT = [0.9, 0.1, 0.2, 0.05, 0.7, 0.3, 0.1, 0.8, 0.1, 0.2, 0.05, 0.6];

/**
 * Stub /identify with a chosen top-3 and swallow the two logging endpoints.
 * Returns the array that /event bodies are pushed into, so a test can assert the funnel.
 * Call this BEFORE page.goto(): the `view` event fires as the page initialises.
 */
async function stubApi(page, { top3 = [], tonicHz = 146 } = {}) {
  const events = [];
  await page.route(/twelveswaras-api|\/api\//, (route) => {
    const url = route.request().url();
    if (url.endsWith('/identify')) {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ tonic_hz: tonicHz, swara_activation: ACT, top3 }),
      });
    }
    if (url.endsWith('/result')) return route.fulfill({ status: 200, body: '{}' });
    if (url.endsWith('/event')) {
      try { events.push(JSON.parse(route.request().postData() || '{}')); } catch { /* ignore */ }
      return route.fulfill({ status: 200, body: '{}' });
    }
    return route.abort();
  });
  return events;
}

module.exports = { stubApi, ACT };
