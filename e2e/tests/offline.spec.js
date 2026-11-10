// What a person sees when there is no connection. Identifying a raaga needs the network,
// so the site says so in plain words, instead of a browser error page, a silent "listening"
// that never answers, or a message that blames their recording.
const { test, expect } = require('@playwright/test');
const path = require('path');
const { stubApi, FAKE_MIC } = require('./helpers');

test.use(FAKE_MIC);

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'clip.wav');
const NO_NET = /No connection\. Identifying a raaga needs the internet/;

/** The API as if the network were down: /identify fails like a dropped connection. */
const apiOffline = (page) => stubApi(page, { identify: (route) => route.abort('internetdisconnected') });

test('opening the site with no connection shows its own offline page, not the browser error', async ({ page, context }) => {
  await stubApi(page);
  await page.goto('/');
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) await new Promise((r) => navigator.serviceWorker.addEventListener('controllerchange', r, { once: true }));
  });
  await context.setOffline(true);
  const res = await page.goto('/contribute/');
  expect(res.status()).toBe(503);
  await expect(page.locator('h1')).toContainText(/offline/i);
  await expect(page.locator('body')).toContainText('needs a connection');
  // Back online, "Try again" loads the page that was asked for.
  await context.setOffline(false);
  await page.getByRole('link', { name: 'Try again' }).click();
  await expect(page).toHaveURL(/\/contribute\/$/);
  await expect(page.locator('h1')).not.toContainText(/offline/i);
});

test('an upload with the connection gone says so, and does not blame the recording', async ({ page }) => {
  await apiOffline(page);
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('.rerr')).toHaveText(NO_NET);
  await expect(page.locator('.rerr')).not.toContainText('could not be analysed');
});

test('already offline: says so straight away, without asking for the microphone or uploading', async ({ page, context }) => {
  const api = await stubApi(page);
  await page.goto('/');
  await context.setOffline(true);
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('.rerr')).toHaveText(NO_NET);
  expect(api.calls.identify).toBe(0);
});

test('live listening stops and says so when the connection drops, instead of listening forever', async ({ page }) => {
  await apiOffline(page);
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await expect(page.locator('.rerr')).toHaveText(NO_NET, { timeout: 20_000 });
  await expect(page.locator('#rec-status')).toHaveText('Identify a raaga');
});
