// Tradition-awareness on the result. The API tags each prediction with its tradition; a Hindustani
// result must be labeled and must link to its own -hindustani raaga page (kept distinct from the
// Carnatic pages so the two Todi/Sri never collide). Carnatic results are unchanged, which the
// confident test in identify.spec.js covers (it asserts the plain learn link IS present).
const { test, expect } = require('@playwright/test');
const path = require('path');
const { stubApi } = require('./helpers');

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'clip.wav');

test('a Hindustani result is labeled and links to its -hindustani raaga page', async ({ page }) => {
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
  // learn link points at the distinct Hindustani page (not the Carnatic slug)
  await expect(page.locator('#r-learn')).toHaveAttribute('href', 'raaga/bhup-hindustani.html');
});
