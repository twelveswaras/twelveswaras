// End-to-end user tests for the landing recognizer. These drive the real page in a browser
// with the recognizer API stubbed (page.route), so they test what a person actually sees, the
// wheel locking, the raaga name, the tonic, the abstention path, without a Worker, model, or mic.
const { test, expect } = require('@playwright/test');
const path = require('path');
const { stubApi } = require('./helpers');

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'clip.wav');

// top3[0].confidence drives finish(): >=0.6 confident, <0.45 abstain. The logging endpoints
// (/result, /event) are swallowed by the shared stub so nothing reaches the live Worker.
const stubIdentify = (page, top3, tonicHz = 146) => stubApi(page, { top3, tonicHz });

test('confident identify names the raaga, shows the tonic and a learn link', async ({ page }) => {
  await stubIdentify(page, [
    { raaga: 'Kalyāṇi', confidence: 0.87 },
    { raaga: 'Śankarābharaṇaṁ', confidence: 0.07 },
    { raaga: 'Tōḍi', confidence: 0.03 },
  ]);
  await page.goto('/');

  // Headless CI has no microphone, so drive the upload path: setting the hidden file input
  // fires startFile() -> a single /identify call -> apply() -> finish().
  await page.setInputFiles('#rec-file', FIXTURE);

  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');
  await expect(page.locator('#rec-status')).toHaveText('Confident');
  await expect(page.locator('#rec-sa')).toContainText('Sa · 146');
  const learn = page.locator('#r-learn');
  await expect(learn).toBeVisible();
  await expect(learn).toHaveAttribute('href', /raaga\/kalyani\.html$/);
});

test('low-confidence identify abstains and offers the teach-me funnel', async ({ page }) => {
  await stubIdentify(page, [
    { raaga: 'Sencuruṭṭi', confidence: 0.32 },
    { raaga: 'Suraṭi', confidence: 0.14 },
    { raaga: 'Kāpi', confidence: 0.09 },
  ]);
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);

  // Below the abstention threshold it must NOT present a confident raaga name or a learn link...
  await expect(page.locator('#rec-status')).toHaveText('Not sure');
  await expect(page.locator('#rec-raga')).toBeEmpty();
  await expect(page.locator('#r-learn')).toHaveCount(0);
  // ...and it reframes the contribute card as "teach me this raaga" (the vocabulary-growth funnel).
  await expect(page.locator('#rec-contrib')).toContainText('Help me learn this raaga');
});
