# Governance

twelveswaras is a **non-commercial, open-source public good**, built as an open commons:
the code, the model and the reference data are all public, and the point is that anyone can
use, check, fork or build on them.

## Stewardship

Maintained by Sathya Sankaran in the [`twelveswaras`](https://github.com/twelveswaras) GitHub
organisation, so the project and its commons stay independent of any one employer or company.

## Licensing

- **Code**: MIT. The recognizer bundles AGPL `essentia`, so the deployed recognizer carries
  AGPL obligations, satisfied because we publish all source.
- **Contributor commons**: CC-BY-4.0, in a repo kept **separate** from
  Saraga-derived artifacts so it stays cleanly reusable.
- **Seed model**: trained on Saraga (CC-BY-**NC-SA**) and the CMD / Indian Art Music
  Raga Recognition Dataset (CC-BY-**NC-ND** 3.0), so the released seed weights are treated
  as non-commercial. A model retrained purely on the CC-BY contributor commons can be clean CC-BY.

## Contribution & consent

- **Anonymous by default**: no login required to contribute. Dedup via `audio_sha256`;
  `contributor_id` is an optional, non-PII pseudonym; an optional handle only for those
  who want attribution.
- **Rights gate**: a clip is only accepted if the contributor affirms it is their own
  performance / they have the right to share it under the chosen license.

## Verification

Community votes promote a clip to `train` at **≥3 agree AND ≥80% agreement**.
Disagreement routes it to `disputed` → an expert queue (Sathya + a small trusted
circle). Thresholds are configurable (`raaga_id/config.py`).

## Moderation

None needed for v0. v1 adds: rights gate + dedup + quarantine (`split=pending`) +
per-pseudonym rate-limit + manual flag/reject + a melody-energy junk filter.
