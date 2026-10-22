// "Install app" button. Chromium installs through `beforeinstallprompt`, which a headless test
// cannot make the browser fire for real, so the tests dispatch a synthetic one carrying a stub
// prompt(). iPhone Safari has no install API: the button opens a "Share -> Add to Home Screen"
// guide instead. The pure platform checks are unit-tested in the page against fake navigators.
const { test, expect } = require('@playwright/test');
const { stubApi } = require('./helpers');

const IPHONE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1';
const PAGES = ['/', '/about/'];

// Dispatch the event Chromium fires when the site meets its install criteria.
function firePrompt(page, outcome = 'accepted') {
  return page.evaluate((outcome) => {
    window.__prompted = 0;
    const e = new Event('beforeinstallprompt', { cancelable: true });
    e.prompt = () => { window.__prompted += 1; };
    e.userChoice = Promise.resolve({ outcome });
    window.dispatchEvent(e);
    return e.defaultPrevented;
  }, outcome);
}

test.beforeEach(async ({ page }) => {
  await stubApi(page); // never let the home page's funnel events reach the live Worker
});

test.describe('platform checks (pure logic)', () => {
  test('isIosSafari tells iOS Safari from other browsers', async ({ page }) => {
    await page.goto('/');
    const got = await page.evaluate(async (iphone) => {
      const { isIosSafari } = await import('/install-button.js');
      const mac = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15';
      return {
        iphone: isIosSafari({ userAgent: iphone }),
        ipadAsMac: isIosSafari({ userAgent: mac, maxTouchPoints: 5 }),
        desktopMac: isIosSafari({ userAgent: mac, maxTouchPoints: 0 }),
        chromeOnIos: isIosSafari({ userAgent: iphone.replace('Version/18.0', 'CriOS/130.0') }),
        android: isIosSafari({ userAgent: 'Mozilla/5.0 (Linux; Android 14) Chrome/130.0 Mobile Safari/537.36' }),
      };
    }, IPHONE_UA);
    expect(got).toEqual({ iphone: true, ipadAsMac: true, desktopMac: false, chromeOnIos: false, android: false });
  });

  test('isStandalone reads display-mode and the iOS navigator flag', async ({ page }) => {
    await page.goto('/');
    const got = await page.evaluate(async () => {
      const { isStandalone } = await import('/install-button.js');
      const win = (mq, standalone) => ({ matchMedia: () => ({ matches: mq }), navigator: { standalone } });
      return [isStandalone(win(true)), isStandalone(win(false, true)), isStandalone(win(false))];
    });
    expect(got).toEqual([true, true, false]);
  });
});

for (const path of PAGES) {
  test.describe(`install button on ${path}`, () => {
    test('stays hidden where the browser offers no install', async ({ page }) => {
      await page.goto(path);
      await expect(page.locator('#install-app')).toBeAttached();
      await expect(page.locator('#install-app')).toBeHidden();
    });

    test('appears on beforeinstallprompt and prompts on tap', async ({ page }) => {
      await page.goto(path);
      const button = page.locator('#install-app');
      await expect.poll(() => firePrompt(page)).toBe(true); // module mounted and kept the event
      await expect(button).toBeVisible();
      await button.click();
      await expect.poll(() => page.evaluate(() => window.__prompted)).toBe(1);
      await expect(button).toBeHidden(); // accepted -> nothing left to install
    });
  });
}

test('a dismissed prompt leaves the button for a later try', async ({ page }) => {
  await page.goto('/');
  await expect.poll(() => firePrompt(page, 'dismissed')).toBe(true);
  await page.locator('#install-app').click();
  await expect.poll(() => page.evaluate(() => window.__prompted)).toBe(1);
  await expect(page.locator('#install-app')).toBeVisible();
});

test.describe('iPhone Safari', () => {
  test.use({ userAgent: IPHONE_UA, viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test('shows the button and opens the Add to Home Screen guide', async ({ page }) => {
    await page.goto('/');
    const button = page.locator('#install-app');
    await expect(button).toBeVisible();
    await button.click();
    const guide = page.getByRole('dialog', { name: 'Add twelveswaras to your Home Screen' });
    await expect(guide).toBeVisible();
    await expect(guide).toContainText('Add to Home Screen');
    await guide.getByRole('button', { name: 'OK' }).click();
    await expect(page.locator('dialog.install-guide')).toHaveCount(0);
  });
});

test.describe('already installed', () => {
  test.use({ userAgent: IPHONE_UA });

  test('stays hidden when running standalone', async ({ page }) => {
    await page.addInitScript(() => { Object.defineProperty(navigator, 'standalone', { value: true }); });
    await page.goto('/');
    await expect(page.locator('#install-app')).toBeAttached();
    await expect.poll(() => firePrompt(page)).toBe(false); // not even listening
    await expect(page.locator('#install-app')).toBeHidden();
  });
});

test('the manifest is installable with split icon purposes', async ({ page, request }) => {
  await page.goto('/');
  const cdp = await page.context().newCDPSession(page);
  const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors');
  expect(installabilityErrors).toEqual([]);

  const manifest = await (await request.get('/manifest.webmanifest')).json();
  for (const icon of manifest.icons) {
    expect(['any', 'maskable']).toContain(icon.purpose);
    expect((await request.get(`/${icon.src}`)).status(), icon.src).toBe(200);
  }
});
