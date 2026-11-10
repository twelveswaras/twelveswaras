// No raaga names for the first minute of a live listen. On the 80 real-world clips a named answer
// is right 48% of the time at 30 s, 64% at 60 s and 81% at 150 s, and live visitors stopped at about
// 33 s on an early name. So the first minute shows the listening itself (Sa, the swaras, progress
// towards a minute) instead of a seconds counter and a guess. The page clock is controlled, so a
// minute passes instantly; a fake microphone stands in for the real one.
const { test, expect } = require('@playwright/test');
const { stubApi, answer, jump, ACT, FAKE_MIC } = require('./helpers');

test.use(FAKE_MIC);

const TOP3 = [
  { raaga: 'Kalyāṇi', confidence: 0.55 },
  { raaga: 'Śankarābharaṇaṁ', confidence: 0.2 },
  { raaga: 'Tōḍi', confidence: 0.1 },
];
const reply = (top3, extra = {}) => ({ no_prediction: false, tonic_hz: 146.2, heard_seconds: 20, swara_activation: ACT, top3, ...extra });
const stub = (page) => stubApi(page, { identify: (route) => answer(route, reply(TOP3)) });

// Start a live listen and let the first answer arrive (real time for the recorder to produce audio,
// then the page clock jumps past the first send).
async function listenUntilFirstAnswer(page) {
  await page.clock.install();
  await page.goto('/');
  await page.locator('#rec-orb').click();
  await page.waitForTimeout(1500);
  await page.clock.fastForward(6000);
  await page.waitForTimeout(500);
  await expect(page.locator('#rec-sa')).toContainText('146');
}

test('before a minute, an answer that has arrived is not shown as a raaga name', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 30_000);
  await expect(page.locator('#rec-top3 .rn')).toHaveCount(0);
  await expect(page.locator('#rec-raga')).toHaveText('');
  // It shows the listening instead, and says when names will come.
  await expect(page.locator('#rec-status')).toContainText(/minute/i);
});

test('after a minute the recognitions appear', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 60_000);
  await expect(page.locator('#rec-top3 .rn').first()).toHaveText('Kalyāṇi');
});

test('the orb centre shows words, never a seconds counter, before and after the minute', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 10_000);
  await expect(page.locator('#rec-orb')).toHaveAttribute('data-centre', 'Sa found');
  expect(await page.locator('#rec-orb').getAttribute('aria-label')).toMatch(/listening/i);
  await jump(page, 60_000);
  await expect(page.locator('#rec-orb')).toHaveAttribute('data-centre', 'Listening');
});

test('an answer that first arrives after the minute still switches the screen over', async ({ page }) => {
  // A cold recognizer or empty early replies: nothing to show at 60 s, then a raaga arrives.
  let ready = false;
  await stubApi(page, { identify: (route) => answer(route, ready
    ? reply(TOP3, { heard_seconds: 70 })
    : { no_prediction: true, reason: 'no_windows', tonic_hz: 146.2, heard_seconds: 20, top3: [] }) });
  await listenUntilFirstAnswer(page);
  await jump(page, 60_000);
  await expect(page.locator('#r-stop')).toHaveText('Stop now');
  ready = true;
  await jump(page, 8_000);
  await expect(page.locator('#rec-top3 .rn').first()).toHaveText('Kalyāṇi');
  await expect(page.locator('#r-stop')).toHaveText('Stop now');
  expect(await page.locator('#rec-orb').getAttribute('aria-label')).not.toMatch(/after a minute/);
});

test('stopping before a minute still gives the answer, labelled as an early guess', async ({ page }) => {
  const { results } = await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 20_000);
  await page.locator('#r-stop').click();
  await expect(page.locator('#rec-status')).toHaveText('Early guess');
  await expect(page.locator('#rec-raga')).toHaveText('Kalyāṇi');
  await expect(page.locator('#rec-lead')).toContainText(/half the time/i);
  await expect.poll(() => results.length).toBe(1);
});

test('nothing locks before a minute, even on a stable, confident answer', async ({ page }) => {
  await stubApi(page, { identify: (route) => answer(route,
    reply([{ raaga: 'Kalyāṇi', confidence: 0.95 }, { raaga: 'Tōḍi', confidence: 0.03 }])) });
  await listenUntilFirstAnswer(page);
  await jump(page, 50_000);
  await expect(page.locator('#r-stop')).toBeVisible();          // still listening at ~56 s
  await jump(page, 20_000);
  await expect(page.locator('#rec-status')).toHaveText('Confident');
});

// ---- the first minute shows the evidence building up ------------------------------------------
// The stub's swara_activation (helpers.ACT), normalised, puts at least 5% of the mass on Sa, G3, M1,
// P and N3; Ri and Da peak just under it. A note lights only once two replies in a row agree.
const lit = (page) => page.locator('#rec-pills .rec-pill.on');

test('a note lights up only after two replies in a row have heard it', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);                         // one reply so far
  await expect(lit(page)).toHaveCount(0);
  await jump(page, 4_000);                                    // a second reply
  await expect(lit(page)).toHaveCount(5);
  await expect(lit(page)).toContainText(['Sa', 'G3', 'M1', 'P', 'N3']);
});

test('the notes give way to the answers at the minute, in the same place', async ({ page }) => {
  await stub(page);
  await listenUntilFirstAnswer(page);
  await jump(page, 4_000);
  await expect(page.locator('#rec-notes')).not.toHaveClass(/\boff\b/);
  await expect(page.locator('#rec-answers')).toHaveClass(/\boff\b/);
  await jump(page, 60_000);
  await expect(page.locator('#rec-notes')).toHaveClass(/\boff\b/);
  await expect(page.locator('#rec-answers')).not.toHaveClass(/\boff\b/);
  await expect(page.locator('#rec-bridge')).toHaveText('Most likely so far');
});

test('an upload goes straight to the answers, with no notes phase', async ({ page }) => {
  await stubApi(page, { top3: TOP3 });
  await page.goto('/');
  await page.setInputFiles('#rec-file', require('path').join(__dirname, '..', 'fixtures', 'clip.wav'));
  await expect(page.locator('#rec-top3 .rn').first()).toHaveText('Kalyāṇi');
  await expect(page.locator('#rec-notes')).toHaveClass(/\boff\b/);
});

// ---- after the minute, as the mock-up: settling, one steady line, no tips over the answer ------
test('after the minute it says it is settling and to keep listening, with no tips over the answer', async ({ page }) => {
  await stub(page);                                             // 0.55: never confident enough to lock
  await listenUntilFirstAnswer(page);
  await jump(page, 60_000);
  await expect(page.locator('#rec-status')).toHaveText('Settling · keep listening');
  for (let i = 0; i < 8; i++) {                                 // ~25 s: tips would have come round 3 times
    await expect(page.locator('#rec-lead')).toHaveText('Keep listening for a surer answer.');
    await jump(page, 3_000);
  }
});

// Once confident, the big name is the answer; the rows below are the comparison, with no heading
// between them repeating the name, and the leading percentage in the settled colour like its bar.
test('once confident, the rows are an unheaded comparison with a green leading percentage', async ({ page }) => {
  await stubApi(page, { identify: (route) => answer(route,
    reply([{ raaga: 'Kalyāṇi', confidence: 0.95 }, { raaga: 'Tōḍi', confidence: 0.03 }])) });
  await listenUntilFirstAnswer(page);
  await jump(page, 72_000);
  await expect(page.locator('#rec-status')).toHaveText('Confident');
  await expect(page.locator('#rec-bridge')).toHaveText('');
  await expect(page.locator('#rec-top3 .rec-row.lead .rp')).toHaveCSS('color', 'rgb(116, 198, 157)');   // --jade-hi
  await expect(page.locator('#rec-top3 .rec-row.lead .rn')).toHaveCSS('font-weight', '500');
});
