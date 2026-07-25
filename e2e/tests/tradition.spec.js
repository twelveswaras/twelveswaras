// Tradition-awareness on the result. The API tags each prediction with its tradition; a
// Hindustani result must be labeled and must NOT offer a "how to hear" link (those pages exist
// only for the Carnatic 40 today, so the link would 404). Carnatic results are unchanged, which
// the confident test in identify.spec.js covers (it asserts the learn link IS present).
const { test, expect } = require('@playwright/test');
const path = require('path');
const { stubApi } = require('./helpers');

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'clip.wav');

test('a Hindustani result is labeled and omits the (nonexistent) learn page', async ({ page }) => {
  await stubApi(page, {
    top3: [
      { raaga: 'Bhūp', confidence: 0.9, tradition: 'hindustani' },
      { raaga: 'Mārvā', confidence: 0.05, tradition: 'hindustani' },
      { raaga: 'Yaman kalyāṇ', confidence: 0.03, tradition: 'hindustani' },
    ],
  });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);

  await expect(page.locator('#rec-raga')).toHaveText('Bhūp');
  await expect(page.locator('#rec-status')).toHaveText('Confident');
  // labeled as Hindustani so the traditions are never conflated
  await expect(page.locator('#rec-lead')).toContainText('Hindustani');
  // no learn link -> no 404 (the Carnatic pages don't cover Hindustani yet)
  await expect(page.locator('#r-learn')).toHaveCount(0);
});
