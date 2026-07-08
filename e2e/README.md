# End-to-end user tests

Browser tests that drive the real site the way a person does, in headless Chromium via
[Playwright](https://playwright.dev). They complement the Python suite in `../tests/` (which
asserts source structure and model math): these assert the actual **user experience**, the
recognizer wheel locking, naming a raaga, showing the tonic, and abstaining on low confidence.

The recognizer API is **stubbed per test** with `page.route()`, so the tests are fully offline
and deterministic: no Cloudflare Worker, no Hugging Face Space, no model, no microphone. The
static site is served straight from `../site/` by `python -m http.server` (no build step).

## Run locally

```bash
cd e2e
npm install
npx playwright install chromium   # one-time browser download
npm test                          # or: npx playwright test --headed
```

## What's covered

- `tests/identify.spec.js`
  - **confident identify** — upload a clip, the wheel names the raaga, shows the detected Sa,
    and offers a "how to hear it" link.
  - **low-confidence identify** — the recognizer abstains (no confident name, no learn link) and
    reframes the contribute card as the "teach me this raaga" funnel.

Headless has no mic, so tests use the **upload** path (`#rec-file`); the live-mic path is a
manual check. Follow-ups: the `/contribute` flow (rights gate, release opt-in) and a Lighthouse
budget check.
