// Layout rules every page keeps, from the 2026-11-10 UI/UX audit: a <main> landmark, no sideways
// scroll on a 320 px phone, and tap targets of at least 44 px for the links people use on phones.
const { test, expect } = require('@playwright/test');
const { stubApi } = require('./helpers');

const PAGES = ['/', '/about/', '/contribute/', '/listen/', '/raaga/', '/raaga/kalyani.html'];

for (const path of PAGES) {
  test(`${path} has a main landmark and no sideways scroll at 320 px`, async ({ page }) => {
    await stubApi(page);
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto(path);
    await expect(page.locator('main')).toHaveCount(1);
    const over = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    expect(over).toBeLessThanOrEqual(0);
    // the navigation fits on one line, so no link is left alone on a second row
    const rows = await page.locator('.top .nav a').evaluateAll((as) => new Set(as.map((a) => Math.round(a.getBoundingClientRect().top))).size);
    expect(rows).toBe(1);
  });

  test(`${path} navigation links are at least 44 px tall`, async ({ page }) => {
    await stubApi(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    const heights = await page.locator('.top .nav a').evaluateAll((as) => as.map((a) => a.getBoundingClientRect().height));
    expect(heights.length).toBeGreaterThan(0);
    for (const h of heights) expect(h).toBeGreaterThanOrEqual(44);
  });
}

test('the idle recognizer gives one clear instruction and a full-size upload button', async ({ page }) => {
  await stubApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('#rec-lead')).toHaveText('Tap the mic, then hold your phone near the music for a minute.');
  await expect(page.locator('#rec-controls .rhint')).toHaveCount(0);
  const up = page.locator('#r-up');
  await expect(up).toHaveText(/Upload a recording/);
  expect((await up.boundingBox()).height).toBeGreaterThanOrEqual(44);
});
