// A sleeping recognizer took 42.6 s to give its first answer (measured 2026-10-24), and most live
// sessions that ended with nothing gave up inside that window. These pin the four page-side fixes:
// wake it on load, say it is waking, don't throw away an answer that is on its way, and record why
// a session ended empty. A fake microphone stands in for the real one.
const { test, expect } = require('@playwright/test');

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

const TOP3 = [
  { raaga: 'Kalyāṇi', confidence: 0.9 },
  { raaga: 'Śankarābharaṇaṁ', confidence: 0.05 },
  { raaga: 'Tōḍi', confidence: 0.03 },
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// One handler owns every API call (see helpers.js for why nothing may reach the live worker).
// identify(route) decides how /identify behaves; /result bodies are collected for assertions.
async function stub(page, identify) {
  const calls = { warm: 0, identify: 0, results: [] };
  await page.route(/twelveswaras-api|\/api\//, async (route) => {
    const url = route.request().url();
    if (url.endsWith('/warm')) { calls.warm++; return route.fulfill({ status: 200, body: '{"warm":true}' }); }
    if (url.endsWith('/identify')) { calls.identify++; return identify(route); }
    if (url.endsWith('/result')) {
      calls.results.push(JSON.parse(route.request().postData() || '{}'));
      return route.fulfill({ status: 200, body: '{}' });
    }
    if (url.endsWith('/event')) return route.fulfill({ status: 200, body: '{}' });
    return route.abort();
  });
  return calls;
}

test('the page wakes the recognizer as soon as it loads, before anyone taps', async ({ page }) => {
  const calls = await stub(page, (route) => route.abort());
  await page.goto('/');
  await expect.poll(() => calls.warm, { timeout: 5_000 }).toBe(1);
  expect(calls.identify).toBe(0);
});

test('a slow first answer tells the visitor it is waking up, so they do not give up', async ({ page }) => {
  await stub(page, async (route) => { await sleep(25_000); return route.fulfill({ status: 200, body: '{}' }).catch(() => {}); });
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await expect(page.locator('#rec-lead')).toContainText(/Waking up/, { timeout: 20_000 });
});

test('Stop while the first answer is on its way waits for it instead of throwing it away', async ({ page }) => {
  const calls = await stub(page, async (route) => {
    await sleep(3_000);
    return route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify({ no_prediction: false, tonic_hz: 146, heard_seconds: 5, top3: TOP3 }) });
  });
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await expect.poll(() => calls.identify, { timeout: 10_000 }).toBe(1);   // first send is in flight
  await page.locator('#r-stop').click();
  await expect(page.locator('#rec-lead')).toContainText(/Finishing/);
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi', { timeout: 10_000 });
  await expect.poll(() => calls.results.length).toBe(1);
  expect(calls.results[0].no_prediction).toBe(0);
});

test('audio sent but no answer back is recorded as no_reply, not a blank', async ({ page }) => {
  const calls = await stub(page, async (route) => {
    await sleep(2_000);
    return route.fulfill({ status: 502, contentType: 'text/html', body: '<html>restarting</html>' });
  });
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await expect.poll(() => calls.identify, { timeout: 10_000 }).toBe(1);
  await page.locator('#r-stop').click();
  await expect.poll(() => calls.results.length, { timeout: 10_000 }).toBe(1);
  expect(calls.results[0].no_prediction).toBe(1);
  expect(calls.results[0].reason).toBe('no_reply');
});

test('stopping before any audio is sent is recorded as not_sent', async ({ page }) => {
  const calls = await stub(page, (route) => route.abort());
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.locator('#r-stop').click();                                  // well inside the 4.5 s
  await expect.poll(() => calls.results.length, { timeout: 5_000 }).toBe(1);
  expect(calls.identify).toBe(0);
  expect(calls.results[0].reason).toBe('not_sent');
});

test('an error reply clears the waking-up note instead of leaving it up for good', async ({ page }) => {
  // Found in review: the note keyed on heard_seconds, which an error reply (an undecodable clip)
  // never carries, so "Waking up" stayed on screen for the whole session.
  await stub(page, (route) => route.fulfill({ status: 400, contentType: 'application/json',
    body: JSON.stringify({ error: 'could not decode audio' }) }));
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.waitForTimeout(16_000);                                     // past FIRST_SEND + WAKE_NOTE
  await expect(page.locator('#rec-lead')).not.toContainText(/Waking up/);
});
