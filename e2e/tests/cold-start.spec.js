// A sleeping recognizer took 42.6 s to give its first answer (measured 2026-10-24), and most live
// sessions that ended with nothing gave up inside that window. These pin the four page-side fixes:
// wake it on load, say it is waking, don't throw away an answer that is on its way, and record why
// a session ended empty. A fake microphone stands in for the real one.
const { test, expect } = require('@playwright/test');
const { stubApi, answer, jump, FAKE_MIC } = require('./helpers');

test.use(FAKE_MIC);

const TOP3 = [
  { raaga: 'Kalyāṇi', confidence: 0.9 },
  { raaga: 'Śankarābharaṇaṁ', confidence: 0.05 },
  { raaga: 'Tōḍi', confidence: 0.03 },
];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const stub = (page, identify) => stubApi(page, { identify });

test('the page wakes the recognizer as soon as it loads, before anyone taps', async ({ page }) => {
  const api = await stub(page, (route) => route.abort());
  await page.goto('/');
  await expect.poll(() => api.calls.warm, { timeout: 5_000 }).toBe(1);
  expect(api.calls.identify).toBe(0);
});

test('a slow first answer tells the visitor it is waking up, so they do not give up', async ({ page }) => {
  await stub(page, () => new Promise(() => {}));                         // the answer never comes
  await page.clock.install();
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.waitForTimeout(1500);                                       // the recorder has audio
  await jump(page, 16_000);                                              // past FIRST_SEND + WAKE_NOTE
  await jump(page, 100);
  await expect(page.locator('#rec-lead')).toContainText(/Waking up/);
});

test('Stop while the first answer is on its way waits for it instead of throwing it away', async ({ page }) => {
  const api = await stub(page, async (route) => {
    await sleep(3_000);
    return answer(route, { no_prediction: false, tonic_hz: 146, heard_seconds: 5, top3: TOP3 });
  });
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await expect.poll(() => api.calls.identify, { timeout: 10_000 }).toBe(1);   // first send is in flight
  await page.locator('#r-stop').click();
  await expect(page.locator('#rec-lead')).toContainText(/Finishing/);
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi', { timeout: 10_000 });
  await expect.poll(() => api.results.length).toBe(1);
  expect(api.results[0].no_prediction).toBe(0);
});

test('audio sent but no answer back is recorded as no_reply, not a blank', async ({ page }) => {
  const api = await stub(page, async (route) => {
    await sleep(2_000);
    return route.fulfill({ status: 502, contentType: 'text/html', body: '<html>restarting</html>' });
  });
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await expect.poll(() => api.calls.identify, { timeout: 10_000 }).toBe(1);
  await page.locator('#r-stop').click();
  await expect.poll(() => api.results.length, { timeout: 10_000 }).toBe(1);
  expect(api.results[0].no_prediction).toBe(1);
  expect(api.results[0].reason).toBe('no_reply');
});

test('stopping before any audio is sent is recorded as not_sent', async ({ page }) => {
  const api = await stub(page, (route) => route.abort());
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.locator('#r-stop').click();                                  // well inside the 4.5 s
  await expect.poll(() => api.results.length, { timeout: 5_000 }).toBe(1);
  expect(api.calls.identify).toBe(0);
  expect(api.results[0].reason).toBe('not_sent');
});

test('an error reply clears the waking-up note instead of leaving it up for good', async ({ page }) => {
  // Found in review: the note keyed on heard_seconds, which an error reply (an undecodable clip)
  // never carries, so "Waking up" stayed on screen for the whole session.
  await stub(page, (route) => answer(route, { error: 'could not decode audio' }, 400));
  await page.clock.install();
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.waitForTimeout(1500);
  await jump(page, 16_000);                                              // past FIRST_SEND + WAKE_NOTE
  await jump(page, 100);
  await expect(page.locator('#rec-lead')).not.toContainText(/Waking up/);
});

test('a send that hangs is abandoned after a minute, so the listen keeps sending', async ({ page }) => {
  let n = 0;
  const api = await stub(page, (route) => {
    n += 1;
    if (n === 1) return new Promise(() => {});              // the first send never answers
    return answer(route, { no_prediction: false, tonic_hz: 146, heard_seconds: 20, top3: TOP3 });
  });
  await page.clock.install();
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.waitForTimeout(1500);
  await page.clock.fastForward(6000);                       // first send goes out and hangs
  await expect.poll(() => api.calls.identify).toBe(1);
  await page.clock.fastForward(61_000);                     // past the send timeout
  await page.waitForTimeout(300);
  await page.clock.fastForward(4000);                       // the next tick sends again
  await expect.poll(() => api.calls.identify, { timeout: 5000 }).toBeGreaterThan(1);
});

test('the first audio goes out at 4.5 s, not at the next 3.5 s tick after it', async ({ page }) => {
  const api = await stub(page, (route) => answer(route, { no_prediction: false, tonic_hz: 146, heard_seconds: 4, top3: TOP3 }));
  await page.clock.install();
  await page.goto('/');
  await page.clock.pauseAt(new Date(Date.now() + 5000));    // page time now moves only when told to
  await page.locator('#rec-orb').click();
  await page.waitForTimeout(1500);                          // the recorder produces audio in real time
  await page.clock.runFor(4600);                            // timers fire at their real times, to just past 4.5 s
  await expect.poll(() => api.calls.identify, { timeout: 3000 }).toBe(1);
});
