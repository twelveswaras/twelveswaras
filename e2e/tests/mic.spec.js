// When the microphone fails, the page says WHY and offers a way forward. Before, every failure (a
// blocked permission, a browser that cannot record, no microphone, one busy in another app) got one
// message and a "Try again" that fails again at once after a block: one session tapped it 11 times
// in 67 s. Each cause is also logged, so we learn which ones visitors actually hit.
const { test, expect } = require('@playwright/test');
const { stubApi } = require('./helpers');

// Make getUserMedia fail the way a real browser does for each cause, before the page loads.
async function failMic(page, name) {
  await page.addInitScript((errName) => {
    if (errName === 'norecorder') { delete window.MediaRecorder; return; }
    if (errName === 'unsupported') {
      Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true });
      return;
    }
    navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('mic', errName));
  }, name);
}

const CASES = [
  { err: 'NotAllowedError', cause: 'mic_blocked', says: /not allowed/i },
  { err: 'NotFoundError', cause: 'mic_missing', says: /No microphone was found/i },
  { err: 'NotReadableError', cause: 'mic_busy', says: /another app/i },
  { err: 'unsupported', cause: 'mic_unsupported', says: /can't record audio/i },
  { err: 'norecorder', cause: 'mic_unsupported', says: /can't record audio/i },
];

for (const c of CASES) {
  test(`${c.err}: says why, offers upload first, and logs ${c.cause}`, async ({ page }) => {
    const events = await stubApi(page);
    await failMic(page, c.err);
    await page.goto('/');
    await page.locator('#rec-orb').click();

    await expect(page.locator('#rec-lead')).toContainText(c.says);
    // no listen is running, so no empty notes row between the message and the way forward
    await expect(page.locator('#rec-pills')).toBeHidden();
    // Upload is the main way forward; retrying a failed microphone is the secondary choice.
    const buttons = page.locator('#rec-controls button');
    await expect(buttons.first()).toHaveText(/Upload a recording/);
    await expect(page.locator('#r-again')).toBeVisible();
    // The old event still fires (funnel continuity), plus one naming the cause.
    await expect.poll(() => events.map((e) => e.event)).toContain(c.cause);
    await expect.poll(() => events.map((e) => e.event)).toContain('mic_denied');
  });
}

test('the main button after a microphone failure opens the file picker', async ({ page }) => {
  await stubApi(page);
  await failMic(page, 'NotAllowedError');
  await page.goto('/');
  await page.locator('#rec-orb').click();
  const chooser = page.waitForEvent('filechooser');
  await page.locator('#rec-controls button').first().click();
  await chooser;
});

test('a blocked microphone explains how to allow it', async ({ page }) => {
  await stubApi(page);
  await failMic(page, 'NotAllowedError');
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await expect(page.locator('#rec-lead')).toContainText(/Allow/);
});
