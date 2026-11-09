// No raaga names for the first minute of a live listen. On the 80 real-world clips a named answer
// is right 48% of the time at 30 s, 64% at 60 s and 81% at 150 s, and live visitors stopped at about
// 33 s on an early name. So the first minute shows the listening itself (Sa, the swaras, progress
// towards a minute) instead of a seconds counter and a guess. The page clock is controlled, so a
// minute passes instantly; a fake microphone stands in for the real one.
const { test, expect } = require('@playwright/test');

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

const TOP3 = [
  { raaga: 'Kalyāṇi', confidence: 0.55 },
  { raaga: 'Śankarābharaṇaṁ', confidence: 0.2 },
  { raaga: 'Tōḍi', confidence: 0.1 },
];
const ACT = [0.9, 0.1, 0.2, 0.05, 0.7, 0.3, 0.1, 0.8, 0.1, 0.2, 0.05, 0.6];

async function stub(page) {
  const results = [];
  await page.route(/twelveswaras-api|\/api\//, (route) => {
    const url = route.request().url();
    if (url.endsWith('/identify')) {
      return route.fulfill({ status: 200, contentType: 'application/json',
        body: JSON.stringify({ no_prediction: false, tonic_hz: 146.2, heard_seconds: 20, swara_activation: ACT, top3: TOP3 }) });
    }
    if (url.endsWith('/result')) { results.push(JSON.parse(route.request().postData() || '{}')); return route.fulfill({ status: 200, body: '{}' }); }
    if (url.endsWith('/warm') || url.endsWith('/event')) return route.fulfill({ status: 200, body: '{}' });
    return route.abort();
  });
  return results;
}

// Jump the page clock (timers fire once, as after a real wait), then let the answer land.
async function jump(page, ms) {
  await page.clock.fastForward(ms);
  await page.waitForTimeout(500);
  await page.clock.fastForward(100);
}

// Start a live listen and let the first answer arrive (real time for the recorder to produce audio,
// then the page clock jumps past the first send).
async function listenUntilFirstAnswer(page) {
  await page.clock.install();
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.waitForTimeout(1500);
  await page.clock.fastForward(6000);
  await page.waitForTimeout(500);
  await expect(page.locator('#rec-sa')).toContainText('146');
}

test('before a minute, an answer that has arrived is not shown as a raaga name', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 30_000);
  await expect(page.locator('#rec-top3 .rn')).toHaveCount(0);
  await expect(page.locator('#rec-raga')).toHaveText('');
  // It shows the listening instead, and says when names will come.
  await expect(page.locator('#rec-status')).toContainText(/minute/i);
});

test('after a minute the recognitions appear', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 60_000);
  await expect(page.locator('#rec-top3 .rn').first()).toHaveText('Kalyāṇi');
});

test('the orb centre shows words, never a seconds counter, before and after the minute', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 10_000);
  await expect(page.locator('#rec-orb')).toHaveAttribute('data-centre', 'Sa found');
  expect(await page.locator('#rec-orb').getAttribute('aria-label')).toMatch(/listening/i);
  await jump(page, 60_000);
  await expect(page.locator('#rec-orb')).toHaveAttribute('data-centre', 'Listening');
});

test('an answer that first arrives after the minute still switches the screen over', async ({ page }) => {
  // A cold recognizer or empty early replies: nothing to show at 60 s, then a raaga arrives.
  let answer = false;
  await page.route(/twelveswaras-api|\/api\//, (route) => {
    const url = route.request().url();
    if (url.endsWith('/identify')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(answer
        ? { no_prediction: false, tonic_hz: 146.2, heard_seconds: 70, swara_activation: ACT, top3: TOP3 }
        : { no_prediction: true, reason: 'no_windows', tonic_hz: 146.2, heard_seconds: 20, top3: [] }) });
    }
    return route.fulfill({ status: 200, body: '{}' });
  });
  await listenUntilFirstAnswer(page);
  await jump(page, 60_000);
  await expect(page.locator('#r-stop')).toHaveText('Stop now');
  answer = true;
  await jump(page, 8_000);
  await expect(page.locator('#rec-top3 .rn').first()).toHaveText('Kalyāṇi');
  await expect(page.locator('#r-stop')).toHaveText('Stop now');
  expect(await page.locator('#rec-orb').getAttribute('aria-label')).not.toMatch(/after a minute/);
});

test('stopping before a minute still gives the answer, labelled as an early guess', async ({ page }) => {
  const results = await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 20_000);
  await page.locator('#r-stop').click();
  await expect(page.locator('#rec-status')).toHaveText('Early guess');
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');
  await expect(page.locator('#rec-lead')).toContainText(/half the time/i);
  await expect.poll(() => results.length).toBe(1);
});

test('nothing locks before a minute, even on a stable, confident answer', async ({ page }) => {
  await page.route(/twelveswaras-api|\/api\//, (route) => {
    const url = route.request().url();
    if (url.endsWith('/identify')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
        no_prediction: false, tonic_hz: 146.2, heard_seconds: 20, swara_activation: ACT,
        top3: [{ raaga: 'Kalyāṇi', confidence: 0.95 }, { raaga: 'Tōḍi', confidence: 0.03 }] }) });
    }
    return route.fulfill({ status: 200, body: '{}' });
  });
  await listenUntilFirstAnswer(page);
  await jump(page, 50_000);
  await expect(page.locator('#r-stop')).toBeVisible();          // still listening at ~56 s
  await jump(page, 20_000);
  await expect(page.locator('#rec-status')).toHaveText('Confident');
});
