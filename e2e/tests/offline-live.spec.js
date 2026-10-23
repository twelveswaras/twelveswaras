// Live listening when the connection drops: it stops and says why, instead of
// "listening" forever with no answer. A fake microphone stands in for the real one.
const { test, expect } = require('@playwright/test');

test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['microphone'],
});

test('stops and says so when the connection drops, instead of listening silently forever', async ({ page }) => {
  await page.route(/twelveswaras-api|\/api\//, (route) =>
    route.request().url().endsWith('/identify') ? route.abort('internetdisconnected') : route.fulfill({ status: 200, body: '{}' }),
  );
  await page.goto('/');
  await page.locator('#rec-orb').click(); // tap to identify
  await expect(page.locator('.rerr')).toHaveText(/No connection\. Identifying a raaga needs the internet/, { timeout: 20_000 });
  await expect(page.locator('#rec-status')).toHaveText('Identify a raaga');
});
