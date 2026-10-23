// Notch padding. Every page sets viewport-fit=cover, so on a notched phone (installed, or in
// landscape) it may draw under the notch, rounded corners and home bar. These tests simulate a
// notch with Chromium's safe-area override and check the nav and the footer keep clear of it,
// while a screen without a notch keeps the usual 22px gutter. tests/test_site_safe_area.py
// checks the CSS on every page; this checks the real layout on one page of each kind.
const { test, expect } = require('@playwright/test');
const { stubApi } = require('./helpers');

const PAGES = ['/', '/about/', '/contribute/', '/listen/', '/raaga/', '/raaga/kalyani.html', '/404.html', '/offline/'];
const NOTCH = 47; // an iPhone's notch inset in landscape (left and right) and in portrait (top)

/** Simulate the screen's safe-area insets (CSS env(safe-area-inset-*)). */
async function setInsets(page, { top = 0, right = 0, bottom = 0, left = 0 }) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Emulation.setSafeAreaInsetsOverride', {
    insets: { top, topMax: top, right, rightMax: right, bottom, bottomMax: bottom, left, leftMax: left },
  });
}

/** The side gutter, and where the top bar's and the last row's contents actually sit. */
function edges(page) {
  return page.evaluate(() => {
    const box = (el) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      const { left, right, top } = range.getBoundingClientRect();
      return { left, right, top };
    };
    const wrap = getComputedStyle(document.querySelector('.wrap'));
    return {
      width: document.documentElement.clientWidth,
      gutter: [parseFloat(wrap.paddingLeft), parseFloat(wrap.paddingRight)],
      nav: box(document.querySelector('.top')),
      foot: box(document.querySelector('footer .wrap, .foot')),
    };
  });
}

test.beforeEach(async ({ page }) => {
  await stubApi(page); // the home page logs a view: never let it reach the live Worker
});

for (const path of PAGES) {
  test(`${path}: nav and footer clear a landscape notch`, async ({ page }) => {
    await page.setViewportSize({ width: 844, height: 390 });
    await setInsets(page, { left: NOTCH, right: NOTCH, bottom: 21 });
    await page.goto(path);
    const { width, gutter, nav, foot } = await edges(page);
    expect(gutter).toEqual([NOTCH, NOTCH]);
    for (const box of [nav, foot]) {
      expect(box.left).toBeGreaterThanOrEqual(NOTCH);
      expect(box.right).toBeLessThanOrEqual(width - NOTCH);
    }
  });
}

test('the nav clears a portrait notch at the top', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setInsets(page, { top: NOTCH, bottom: 34 });
  await page.goto('/');
  const { nav } = await edges(page);
  expect(nav.top).toBeGreaterThanOrEqual(NOTCH);
});

test('without a notch the usual 22px gutter is unchanged', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const { gutter } = await edges(page);
  expect(gutter).toEqual([22, 22]);
});
