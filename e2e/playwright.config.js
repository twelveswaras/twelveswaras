// Playwright E2E config for the twelveswaras site. Serves the static site/ over a plain
// Python http.server (no build step) and drives it in headless Chromium. The recognizer API
// is stubbed per-test with page.route(), so these tests are fully offline and deterministic:
// no Worker, no Hugging Face Space, no model, no network.
const { defineConfig, devices } = require('@playwright/test');

const PORT = 8099;

module.exports = defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
  },
  webServer: {
    command: `python3 -m http.server ${PORT} --directory ../site`,
    url: `http://localhost:${PORT}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
