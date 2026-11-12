// Sharing a result: the cheapest way twelveswaras spreads is one rasika sending a result to a
// WhatsApp group. A named raaga gets a "Share this result" button that hands the phone's share
// sheet that raaga's page and a line saying what was heard; where there is no share sheet it copies
// the same text. An abstention ("Not sure") offers no share: there is nothing worth passing on.
const { test, expect } = require('@playwright/test');
const path = require('path');
const { stubApi } = require('./helpers');

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'clip.wav');
const KALYANI = [
  { raaga: 'Kalyāṇi', confidence: 0.87, tradition: 'carnatic' },
  { raaga: 'Śankarābharaṇaṁ', confidence: 0.07, tradition: 'carnatic' },
  { raaga: 'Tōḍi', confidence: 0.03, tradition: 'carnatic' },
];

// Record what the page hands navigator.share (or the clipboard when share is absent).
async function captureShare(page, { withShare }) {
  await page.addInitScript((withShare) => {
    window.__shared = [];
    if (withShare) navigator.share = (d) => { window.__shared.push(d); return Promise.resolve(); };
    else delete Navigator.prototype.share;
    Object.defineProperty(navigator, 'clipboard', { configurable: true,
      value: { writeText: (t) => { window.__shared.push({ copied: t }); return Promise.resolve(); } } });
  }, withShare);
}

test('a confident result shares its raaga page through the share sheet', async ({ page }) => {
  await captureShare(page, { withShare: true });
  const events = await stubApi(page, { top3: KALYANI });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');

  await page.locator('#r-share').click();
  const [d] = await page.evaluate(() => window.__shared);
  expect(d.url).toBe('https://twelveswaras.com/raaga/kalyani.html');
  expect(d.text).toBe('twelveswaras heard Kalyāṇi (Carnatic). How to hear it:');
  await expect.poll(() => events.map((e) => e.event)).toContain('share');
});

test('a Hindustani best guess says so and links its own page', async ({ page }) => {
  await captureShare(page, { withShare: true });
  await stubApi(page, { top3: [
    { raaga: 'Bhūp', confidence: 0.5, tradition: 'hindustani' },
    { raaga: 'Mārvā', confidence: 0.3, tradition: 'hindustani' },
    { raaga: 'Yaman kalyāṇ', confidence: 0.1, tradition: 'hindustani' },
  ] });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-status')).toHaveText('Best guess');

  await page.locator('#r-share').click();
  const [d] = await page.evaluate(() => window.__shared);
  expect(d.url).toBe('https://twelveswaras.com/raaga/bhup-hindustani.html');
  expect(d.text).toBe('twelveswaras thinks this is Bhūp (Hindustani). How to hear it:');
});

test('without a share sheet it copies the text and link, and says so', async ({ page }) => {
  await captureShare(page, { withShare: false });
  await stubApi(page, { top3: KALYANI });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);

  const btn = page.locator('#r-share');
  await btn.click();
  const [d] = await page.evaluate(() => window.__shared);
  expect(d.copied).toBe('twelveswaras heard Kalyāṇi (Carnatic). How to hear it: https://twelveswaras.com/raaga/kalyani.html');
  await expect(btn).toHaveText('Copied');
});

test('an abstention offers no share', async ({ page }) => {
  await stubApi(page, { top3: [
    { raaga: 'Kalyāṇi', confidence: 0.3, tradition: 'carnatic' },
    { raaga: 'Tōḍi', confidence: 0.2, tradition: 'carnatic' },
    { raaga: 'Mōhanaṁ', confidence: 0.1, tradition: 'carnatic' },
  ] });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-status')).toHaveText('Not sure');
  await expect(page.locator('#r-share')).toHaveCount(0);
});
