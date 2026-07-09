# How twelveswaras follows PDGI

[twelveswaras](https://twelveswaras.com) is a free, open-source raaga recognizer and an openly-licensed data commons for Carnatic music (Hindustani planned). It is built on the principles of [People's Digital Goods and Infrastructure (PDGI)](https://pdgi.org/blog/peoples-digital-goods-and-infrastructure/): people before digital, rights-centric, commons-oriented, transparent.

This is a public scorecard of how those principles are actually implemented, with links to the evidence and honest notes on where we fall short.

Status key: ✅ implemented · 🟡 partial · ⛳ gap, with intended direction.

## Scorecard

### People before digital (rights and collective identity): ✅
The commons only ever accepts audio you attest is your own performance, or that you hold the rights to share, and that rights gate is enforced in the Cloudflare Worker, not just the UI. A contributed clip stays private and is used only to check its label; it joins the public CC-BY dataset only if you explicitly release it. Every new clip lands quarantined (`split=pending`) and never enters training until a human confirms the label. You keep control after the fact: email us and a contributed clip is removed, no account needed to make the request. The music's traditions and the source corpora are credited, and the name, schema and pipeline are tradition-neutral by design, so no single tradition or company owns the effort.
Evidence: the [/contribute](https://twelveswaras.com/contribute/) rights gate, the removal-on-request note on [/about](https://twelveswaras.com/about/), [cloudflare/schema.sql](./cloudflare/schema.sql) (`is_own`, `release_public`, `split=pending`), the Data & attribution section of the [README](./README.md).

### Transparency and accountability: ✅
Open source (MIT), open repository, a full written method with citations, and honest accuracy: the headline cross-validated number is published right next to a plain caveat that in-the-wild accuracy is lower, with the whole progression in a public leaderboard. Confidence is temperature-calibrated (a shown "70%" is right about 70% of the time), and the raaga reference facts are marked *draft, pending a musician's review*. Governance and this scorecard live in the repo, so the record is version-controlled and public.
Evidence: this repository, [METHODOLOGY.md](./METHODOLOGY.md), [benchmark/leaderboard.md](./benchmark/leaderboard.md), [GOVERNANCE.md](./GOVERNANCE.md), the "accuracy in the wild is lower" caveat in the [README](./README.md).

### Decentralisation and no lock-in: ✅
No account, no signup to identify a raaga or browse the reference. The raaga reference is published as open data ([/data/raagas.json](https://twelveswaras.com/data/raagas.json), CC-BY-4.0) and downloads in full; the model lives on the Hugging Face Hub; the code is MIT and the site is static, so the whole thing is forkable and self-hostable. Nothing is trapped in the platform.
Evidence: [/data/raagas.json](https://twelveswaras.com/data/raagas.json), the [MIT LICENSE](./LICENSE), the Hugging Face Space, the static site.

### Free software and the digital commons: ✅
MIT code. The contributor dataset is CC-BY-4.0 and kept deliberately separate from the non-commercial research corpora so it stays cleanly reusable, and the contribute flow rejects anything that isn't your own or rights-cleared at the door. We take clean provenance seriously in practice, not just in principle: the deployed model was retrained on only permissively-licensed clean audio (CC-BY plus Wikimedia Commons), *deliberately excluding* unlicensed concert recordings that were on hand, at no measurable accuracy cost.
Evidence: [LICENSE](./LICENSE), the rights gate and CC-BY dataset in [CONTRIBUTING.md](./CONTRIBUTING.md), the licensing section of the [README](./README.md).
Honest note: the seed model is trained partly on Saraga (CC-BY-**NC**-SA), so the seed weights carry NC. A model retrained purely on the CC-BY commons can be cleanly CC-BY, which is the goal.

### Privacy: ✅
The recognizer never stores your recording: it is analysed to find the raaga, then discarded. Contribution is anonymous, no account, no email, no personal data collected. The only thing logged is result metadata (the raaga guess, the tonic, the listen time, a coarse country code), never audio and never PII, and contributed clips stay private unless you release them. First-party, cookieless analytics only; no ad tech, no cross-site tracking.
Evidence: [/about](https://twelveswaras.com/about/) ("your recording is never stored"), [cloudflare/schema.sql](./cloudflare/schema.sql) (metadata-only log, no audio column), the anonymous [/contribute](https://twelveswaras.com/contribute/) flow.

### Platform cooperativism: ✅
Anyone can contribute a recording to the commons for free and anonymously, credited under CC-BY on their own terms: private by default, public only if they choose. The commons improves one shared model that everyone benefits from, and a later model trained purely on it can be cleanly CC-BY, owned by no company. The project is stewarded in a neutral GitHub and Hugging Face org, not a corporate account.
Evidence: the [/contribute](https://twelveswaras.com/contribute/) flow, the CC-BY dataset, [GOVERNANCE.md](./GOVERNANCE.md).

### Humans in the loop (AI does not cut people out): 🟡
The recognizer is built to defer to people, not overrule them. Below a calibrated-confidence threshold it says "not sure" and shows tentative closest guesses instead of confidently naming a raaga, and it invites you to teach it the raaga you know (the vocabulary-growth path). It always shows the top three with honest confidence, never a single false answer, and the reference facts wait on a musician's review. The rights travel with the data for agents too: every raaga page's structured data carries the licence and the exact attribution string, so an agent gets the terms whether it reads the bulk `/data/raagas.json` or a single page.
Evidence: the abstention and "teach me this raaga" funnel on the site, the per-page JSON-LD (`license`, `creditText`, `usageInfo`), `/data/raagas.json`'s embedded licence and attribution, [/llms.txt](https://twelveswaras.com/llms.txt)'s attribution line, the draft-pending-review banners on the raaga pages.
Direction (why 🟡): the community-verification tier for pending contributions and an expert-annotation tier aren't shipped yet.

### A non-digital alternative must exist: ✅
Learning a raaga has always had living non-digital paths, a guru, a rasika, printed notation, and we bridge to them rather than replacing them. Every raaga page has a dedicated print stylesheet so it prints as a clean one-page reference card (the scale, the life notes, the signature phrases, how to hear it), the swara data downloads in full as open files you can use offline, and the pages read without JavaScript. The tool behaves as an aid, not an oracle: when it isn't sure it says so and hands you back to human ears.
Evidence: the raaga-page print stylesheet, [/data/raagas.json](https://twelveswaras.com/data/raagas.json) (full offline download), the abstention and "teach me this raaga" behaviour.
Commitment: never make a learning path digital-only, and keep framing the tool as a companion to human teaching, not a substitute for it.

### Grassroots and reaching the divide-affected: ⛳
Today's reach is English-literate and already a little raaga-curious. Raaga names are shown in transliteration; there is no vernacular (Tamil, Telugu, Kannada, Malayalam, Hindi) access, and a true beginner far from the tradition is not served yet.
Direction: conversational, multilingual access, let the AI layer take a question and explain a raaga in any Indian language over the canonical data, rather than editorialising the transliterated reference itself; and grow the commons through the communities where the music actually lives.

### Algorithmic fairness: mostly not applicable
twelveswaras makes no decisions about people; it classifies musical structure (the raaga). The fairness that does apply is per-raaga: some raagas are recognised more reliably than others, so the model's accuracy is published openly per raaga and it abstains rather than guess when a raaga is beyond it. The one AI-access surface (agents via structured data) is covered by the "humans in the loop" row above.
Evidence: [benchmark/leaderboard.md](./benchmark/leaderboard.md) (per-raaga accuracy), the abstention behaviour.

## Fork this

Want to show your project follows PDGI? Map each principle to the concrete thing you do, link the evidence, and mark the gaps honestly, the honest 🟡s and ⛳s matter more than a wall of green. Copy this file as a template and keep it in your repo, where its git history becomes the record of your work.

Built by [Urban Morph](https://urbanmorph.com). PDGI framework: [pdgi.org](https://pdgi.org/). Sibling scorecards: [mugilu](https://github.com/urbanmorph/mugilu/blob/main/PDGI.md), [bharatlas/geodata](https://github.com/urbanmorph/geodata/blob/main/PDGI.md).
