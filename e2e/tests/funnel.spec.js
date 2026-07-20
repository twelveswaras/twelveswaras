// Funnel instrumentation tests. These assert the page reports the steps a visitor reaches, which
// is what makes "~100 visitors/day, 0 recognitions" readable: without a `view` count and a
// `listen_start` count, never-tapped-the-orb and gave-up-waiting are indistinguishable.
const { test, expect } = require('@playwright/test');
const path = require('path');
const { stubApi } = require('./helpers');

const FIXTURE = path.join(__dirname, '..', 'fixtures', 'clip.wav');
const CONFIDENT = [
  { raaga: 'Kalyāṇi', confidence: 0.87 },
  { raaga: 'Śankarābharaṇaṁ', confidence: 0.07 },
  { raaga: 'Tōḍi', confidence: 0.03 },
];

test('a page load reports the top of the funnel', async ({ page }) => {
  const events = await stubApi(page, { top3: CONFIDENT });
  await page.goto('/');

  await expect.poll(() => events.map((e) => e.event)).toEqual(['view']);
  expect(events[0].session).toMatch(/^[a-z0-9]+$/);
});

test('an upload reports listen_start then result, under one session', async ({ page }) => {
  const events = await stubApi(page, { top3: CONFIDENT });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');

  await expect.poll(() => events.map((e) => e.event)).toEqual(['view', 'listen_start', 'result']);
  // The upload path is distinguishable from a live listen, so the two funnels can be read apart.
  expect(events[1].source).toBe('file');
  expect(events[2].source).toBe('file');
  // One anonymous per-tab id ties the steps together. It is what lets us compute a drop-off rate
  // rather than three unrelated counters.
  const sessions = new Set(events.map((e) => e.session));
  expect(sessions.size).toBe(1);
});

test('an abstention still reports a result (a shown answer, not a successful one)', async ({ page }) => {
  const events = await stubApi(page, {
    top3: [
      { raaga: 'Sencuruṭṭi', confidence: 0.32 },
      { raaga: 'Suraṭi', confidence: 0.14 },
      { raaga: 'Kāpi', confidence: 0.09 },
    ],
  });
  await page.goto('/');
  await page.setInputFiles('#rec-file', FIXTURE);
  await expect(page.locator('#rec-status')).toHaveText('Not sure');

  await expect.poll(() => events.map((e) => e.event)).toEqual(['view', 'listen_start', 'result']);
});

test('the funnel id is per-tab and does not persist across a fresh session', async ({ browser }) => {
  // Privacy claim under test: the id lives in sessionStorage, so a new context (a new tab, a new
  // visit) gets a new one. It is not a cookie and cannot follow anyone between visits.
  const seen = [];
  for (let i = 0; i < 2; i++) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const events = await stubApi(page, { top3: CONFIDENT });
    await page.goto('/');
    await expect.poll(() => events.length).toBeGreaterThan(0);
    seen.push(events[0].session);
    await ctx.close();
  }
  expect(seen[0]).not.toBe(seen[1]);
});
