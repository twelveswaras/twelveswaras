# Security Policy

twelveswaras is a non-commercial, open-source public good. We take the safety of the
website, its users, and the contributed audio commons seriously, and we appreciate
reports made in good faith.

## Reporting a vulnerability

**Please do not open a public GitHub issue for security reports.** Public disclosure
before a fix puts users at risk.

Instead, email **sathya@urbanmorph.com** with:

- a description of the vulnerability and its impact,
- the steps to reproduce it (a proof of concept helps),
- the affected URL, endpoint, or component,
- and any suggested fix, if you have one.

If you would like to encrypt your report or exchange keys, say so in a first short email
and we will arrange it.

## Scope

In scope:

- **The website**, [twelveswaras.com](https://twelveswaras.com) (the static site and its
  client-side code).
- **The Cloudflare Worker API** behind the site, including the `/identify` and `/health`
  endpoints.
- **The audio-upload / contribute endpoint** (`/contribute`) and the handling, storage,
  and consent/rights gating of contributed clips.

Also of interest, though lower priority: the Hugging Face Space recognizer and anything
that could expose contributor data or bypass the rights/consent gate.

Out of scope: reports that require physical access, social engineering of the maintainer,
volumetric denial-of-service, or issues in third-party platforms (GitHub, Cloudflare,
Hugging Face) themselves rather than in our configuration of them.

## Response expectations

This project is maintained by one person on a best-effort basis, so please be patient:

- We aim to **acknowledge** your report within about **5 business days**.
- We aim to give an **initial assessment** within about **2 weeks**.
- Remediation time depends on severity and complexity; we will keep you informed and will
  credit you (if you wish) once a fix ships.

Please give us reasonable time to fix an issue before any public disclosure.

## Removing a contributed clip

Because the project accepts user-submitted audio, you may want a clip removed, for example
if it was contributed in error or you have changed your mind about sharing it.

Email **sathya@urbanmorph.com** with enough detail to identify the clip (an approximate
date and time of contribution, the handle used if any, or the raaga and any details you
remember). We will remove it from the active dataset and from future published releases of
the commons. Note that already-published, openly-licensed snapshots that others have
downloaded cannot be recalled, but we will stop redistributing the clip going forward.
