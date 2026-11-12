// Contributions must be at least a minute long: short clips rarely give a usable Sa, so they
// teach the recognizer little. The page asks for 1 to 3 minutes, will not take a shorter upload,
// and a recording can only be kept once it passes the minute.
const { test, expect } = require('@playwright/test');
const { stubApi, FAKE_MIC, wav } = require('./helpers');

test.use(FAKE_MIC);                       // a microphone for the recording tests; harmless for uploads

test('the page asks for one to three minutes', async ({ page }) => {
  await stubApi(page);
  await page.goto('/contribute/');
  await expect(page.locator('#cx')).toContainText('1 to 3 minutes');
});

test('an upload shorter than a minute is refused with its length', async ({ page }) => {
  await stubApi(page);
  await page.goto('/contribute/');
  await page.setInputFiles('#cx-file', wav(30));
  await expect(page.locator('#cx .err')).toContainText('30 s');
  await expect(page.locator('#cx .err')).toContainText('at least a minute');
  await expect(page.locator('#cx-raaga')).toHaveCount(0);
});

test('an upload of a minute or more goes on to the review', async ({ page }) => {
  await stubApi(page);
  await page.goto('/contribute/');
  await page.setInputFiles('#cx-file', wav(61));
  await expect(page.locator('#cx-raaga')).toBeVisible();
});

test.describe('recording', () => {
  test('before a minute the only way out is Cancel, which keeps nothing', async ({ page }) => {
    await page.clock.install();
    await stubApi(page);
    await page.goto('/contribute/');
    await page.locator('#cx-rec').click();
    await expect(page.locator('#cx-timer')).toBeVisible();   // the microphone has started
    await page.clock.fastForward(30_000);
    await expect(page.locator('#cx-stop')).toHaveText('Cancel');
    await expect(page.locator('.rec-live')).toContainText('keep going to 1:00');
    await page.locator('#cx-stop').click();
    await expect(page.locator('#cx-rec')).toBeVisible();
    await expect(page.locator('#cx-raaga')).toHaveCount(0);
  });

  test('after a minute it can be kept, and it stops on its own at three', async ({ page }) => {
    await page.clock.install();
    await stubApi(page);
    await page.goto('/contribute/');
    await page.locator('#cx-rec').click();
    await expect(page.locator('#cx-timer')).toBeVisible();   // the microphone has started
    await page.clock.fastForward(61_000);
    await expect(page.locator('#cx-stop')).toHaveText('Done, review it');
    await page.clock.fastForward(120_000);
    await expect(page.locator('#cx-raaga')).toBeVisible();
  });
});
