// Renders the screenshots the install dialog shows (site/manifest.webmanifest): the home page on a
// phone and on a desktop, from the local site/. Run it after a visible change to the home page:
//
//     cd e2e && npm run screenshots      (then commit site/screenshots/*.webp)
//
// The files are served straight from disk and every other request is blocked, so the page never
// reaches the live recognizer API (on any host but twelveswaras.com it calls the workers.dev one).
const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const SITE = path.join(__dirname, '..', 'site');
const ORIGIN = 'http://twelveswaras.test';
const SHOTS = [
  { file: 'home-narrow.webp', width: 412, height: 915, scale: 2 },
  { file: 'home-wide.webp', width: 1280, height: 800, scale: 1 },
];

/** Serve site/ at ORIGIN; abort anything else. */
async function serveSite(context) {
  await context.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== ORIGIN) return route.abort();
    let file = path.join(SITE, decodeURIComponent(url.pathname));
    if (!file.startsWith(SITE)) return route.abort();
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
    return fs.existsSync(file) ? route.fulfill({ path: file }) : route.fulfill({ status: 404 });
  });
}

(async () => {
  const browser = await chromium.launch();
  for (const shot of SHOTS) {
    const context = await browser.newContext({
      viewport: { width: shot.width, height: shot.height },
      deviceScaleFactor: shot.scale,
      reducedMotion: 'reduce', // a still frame, not mid-animation
      serviceWorkers: 'block',
    });
    await serveSite(context);
    const page = await context.newPage();
    await page.goto(`${ORIGIN}/`, { waitUntil: 'load' });
    const png = (await page.screenshot()).toString('base64');
    // Playwright writes PNG or JPEG only; the browser's own encoder makes the much smaller WebP.
    const webp = await page.evaluate(async (src) => {
      const image = new Image();
      image.src = src;
      await image.decode();
      const canvas = Object.assign(document.createElement('canvas'), { width: image.width, height: image.height });
      canvas.getContext('2d').drawImage(image, 0, 0);
      return canvas.toDataURL('image/webp', 0.85).split(',')[1];
    }, `data:image/png;base64,${png}`);
    const out = Buffer.from(webp, 'base64');
    fs.writeFileSync(path.join(SITE, 'screenshots', shot.file), out);
    await context.close();
    console.log(`${shot.file} ${shot.width * shot.scale}x${shot.height * shot.scale} ${(out.length / 1000).toFixed(0)} KB`);
  }
  await browser.close();
})();
