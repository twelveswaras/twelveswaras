# twelveswaras.com — static site

A single-page, brand-matched landing site (About · how-it-works · FAQ · embedded
recognizer) with SEO + Open Graph + JSON-LD (AEO) + a PWA manifest. Pure static — deploy
on GitHub Pages, Cloudflare Pages, or any static host.

## Deploy on GitHub Pages (free, no Cloudflare needed)
- Push this `site/` as the published folder (Pages → deploy from a branch → `/site`), or
  copy its contents to a `twelveswaras.github.io` repo.
- Add the custom domain `twelveswaras.com` in the Pages settings; set the DNS
  A/ALIAS/CNAME records GitHub gives you.

## Wire the recognizer
`index.html` embeds the Space at `https://twelveswaras-twelveswaras.hf.space` (the
expected URL once the Space is deployed — see `../space/DEPLOY.md`). Update the iframe
`src` and the OG `og:url` if the Space slug differs.

## Polish TODO
- **`og.png`**: social scrapers (Twitter/Facebook) often don't render SVG OG images.
  Export `og.svg` → `og.png` (1200×630) and switch the `og:image`/`twitter:image` back to
  `og.png`. (Any SVG→PNG tool: `rsvg-convert og.svg -o og.png`, or an online converter.)
- **PWA icons**: modern Android accepts the SVG icon; for the best iOS "Add to Home
  Screen" result, add 180×180 / 192 / 512 PNG icons and an `apple-touch-icon`.
