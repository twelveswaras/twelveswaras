# twelveswaras

An open-source "Shazam for raagas" — listen to a clip of Indian classical music and identify
its **raaga** — paired with a community-contributed, openly-licensed **data commons** that lets
the model improve over time.

> **Status:** Planning / pre-v0. Implementation starting.
> **Focus:** Carnatic first — but the name, schema, and pipeline are **tradition-neutral** by
> design, with Hindustani planned as a fast-follow once the Carnatic v0 proves out.
> **Scope:** Non-commercial, open-source only (never commercial). A public good stewarded in
> the neutral [`twelveswaras`](https://github.com/twelveswaras) GitHub + HF org — not a
> commercial product, and not owned by any company.
> The detailed product spec, background, tech stack, and decisions log live in
> `supporting-docs/PRD.md` (local only — gitignored, not published).

## Why "twelveswaras"?

The twelve swaras are the twelve note-positions of the octave — the shared alphabet of **both**
Carnatic and Hindustani music. The name is tradition-neutral on purpose: Carnatic is where we
start, but nothing in the name, the schema, or the pipeline locks us to one tradition.

## Why this is different from Shazam

Shazam does audio *fingerprinting* — it matches a specific recording. twelveswaras does audio
*classification* — it infers the musical structure (the raaga) of **any** performance, including
one it has never heard. That's a Music Information Retrieval problem, not a lookup.

## Roadmap

- **v0 — proof:** identify only. Seed model (~12 raagas, **tonic-normalized**, trained on
  Saraga) + a demo. A shareable "Shazam for raagas" with no contribution loop yet.
- **v1 — commons:** add contribute + verify loop, publish the open dataset, consolidation job.
- **v2 — quality:** gamaka-aware features, retraining pipeline, public benchmark/leaderboard,
  expert-annotation tier, and Hindustani.

## Public artifacts (when released)

- **Code** (this repo, GitHub) — MIT
- **Model** — HF Hub (weights + model card)
- **Dataset** — HF Hub (the commons; CC-BY-4.0)
- **Live demo** — HF Space (identify + contribute + verify)

## Licensing

- **Code:** MIT (open source).
- **Contributor dataset (the commons):** CC-BY-4.0 — kept **separate** from any non-commercial
  source data so it stays cleanly reusable.
- **Seed model:** trained on Saraga (which is CC-BY-**NC-SA**), so the seed weights carry
  **CC-BY-NC-SA**; a later model retrained purely on the contributor commons can be clean CC-BY.

This is a non-commercial, open-source project. See `supporting-docs/PRD.md` for the full plan
and the decisions log.
