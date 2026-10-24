// The identify -> contribute journey. These assert both contribute paths report their steps under
// the visit's one anonymous session id, which is what turns "how many contributions" into "where
// do people drop off between hearing an answer and sending a recording".
const { test, expect } = require('@playwright/test');
const path = require('path');
const { stubApi } = require('./helpers');

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'clip.wav');
const CONFIDENT = [
  { raaga: 'Kalyāṇi', confidence: 0.87 },
  { raaga: 'Śankarābharaṇaṁ', confidence: 0.07 },
  { raaga: 'Tōḍi', confidence: 0.03 },
];
const names = (events) => events.map((e) => e.event);

test('correcting a result reports correct_open then correct_sent, in the same session', async ({ page }) => {
  const events = await stubApi(page, { top3: CONFIDENT });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');

  await page.locator('#cc-open').click();
  await expect.poll(() => names(events)).toEqual(['view', 'listen_start', 'result', 'correct_open']);
  await page.locator('#cc-own').check();
  await page.locator('#cc-send').click();
  await expect(page.locator('.cc-done')).toBeVisible();

  await expect.poll(() => names(events)).toEqual(['view', 'listen_start', 'result', 'correct_open', 'correct_sent']);
  expect(new Set(events.map((e) => e.session)).size).toBe(1);
});

test('closing the correction card is not counted as opening it again', async ({ page }) => {
  const events = await stubApi(page, { top3: CONFIDENT });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');
  await page.locator('#cc-open').click();   // open
  await page.locator('#cc-open').click();   // "Never mind"
  await page.locator('#cc-open').click();   // open again
  await expect.poll(() => names(events).filter((n) => n === 'correct_open').length).toBe(2);
});

test('a failed send is not counted as sent', async ({ page }) => {
  const events = await stubApi(page, { top3: CONFIDENT });
  await page.route(/\/contribute$/, (route) => route.fulfill({ status: 500, body: '{"error":"x"}' }));
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await page.locator('#cc-open').click();
  await page.locator('#cc-own').check();
  await page.locator('#cc-send').click();
  await expect(page.locator('#cc-err')).toBeVisible();
  expect(names(events)).not.toContain('correct_sent');
});

test('the contribute page reports its view under the session that identified first', async ({ page }) => {
  const events = await stubApi(page, { top3: CONFIDENT });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');
  await page.goto('/contribute/');           // same tab, as following the "Contribute" link

  await expect.poll(() => names(events)).toEqual(['view', 'listen_start', 'result', 'contribute_view']);
  expect(new Set(events.map((e) => e.session)).size).toBe(1);
});

test('contributing from the contribute page reports contribute_sent', async ({ page }) => {
  const events = await stubApi(page, { top3: CONFIDENT });
  await page.goto('/contribute/');
  await page.setInputFiles('#cx-file', FIXTURE);
  await page.locator('#cx-raaga').selectOption('Kalyāṇi');
  await page.locator('#cx-own').check();
  await page.locator('#cx-send').click();

  await expect.poll(() => names(events)).toEqual(['contribute_view', 'contribute_sent']);
  expect(events.contributions).toBe(1);
  expect(events[0].session).toMatch(/^[a-z0-9]+$/);
});
