-- D1 schema for twelveswaras. Apply with:
--   wrangler d1 execute twelveswaras --remote --file cloudflare/schema.sql

-- Result-metadata log. NO audio, no PII. Mirrors the old HF-Dataset logger.
CREATE TABLE IF NOT EXISTS identifications (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  ts            TEXT    NOT NULL,          -- ISO8601
  top1          TEXT,                      -- predicted raaga
  confidence    REAL,
  top3          TEXT,                      -- JSON array of {raaga, confidence}
  tonic_hz      REAL,
  heard_s       REAL,
  no_prediction INTEGER DEFAULT 0,
  country       TEXT,                      -- request.cf.country (coarse geo, not PII)
  referrer      TEXT                       -- acquisition referrer HOST only (e.g. "www.google.com",
                                           -- "t.co"), never a full URL/path/query; '' -> NULL = direct.
                                           -- On a live DB that predates this column, run once:
                                           --   ALTER TABLE identifications ADD COLUMN referrer TEXT;
);
CREATE INDEX IF NOT EXISTS idx_ident_ts   ON identifications(ts);
CREATE INDEX IF NOT EXISTS idx_ident_top1 ON identifications(top1);
CREATE INDEX IF NOT EXISTS idx_ident_ref  ON identifications(referrer);

-- Opt-in contributions to the commons. The audio clip is stored PRIVATELY in R2 (used to improve
-- the model and for human verification). By default we publish the improved MODEL and the
-- non-reconstructable FEATURES, never the recording; the raw audio joins a public CC-BY dataset
-- only if the contributor set release_public=1. New rows land split='pending' and never enter
-- training until a human verifies the label (Phase 3). Rights gate: is_own must be 1 to accept.
-- (Supersedes the Phase-0 scaffold {r2_key, declared_raaga, confidence, verified}; that table had
--  no rows, so on the live DB run: DROP TABLE contributions;  then this CREATE.)
CREATE TABLE IF NOT EXISTS contributions (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ts              TEXT    NOT NULL,              -- ISO8601
  r2_key          TEXT    NOT NULL,              -- clip location in the PRIVATE R2 bucket
  audio_sha256    TEXT,                          -- dedup identical uploads
  raaga           TEXT,                          -- confirmed/corrected canonical raaga (the label)
  label_source    TEXT,                          -- 'model_confirmed' | 'contributor_declared'
  model_pred      TEXT,                          -- the model's top-1 guess (surfaces failure cases)
  confidence      REAL,
  tonic_hz        REAL,
  instrument      TEXT,                          -- optional
  is_own          INTEGER NOT NULL DEFAULT 0,    -- rights attestation ("my own performance")
  license         TEXT    DEFAULT 'CC-BY-4.0',
  release_public  INTEGER DEFAULT 0,             -- may the AUDIO go in a public CC-BY dataset?
  consent_version TEXT,                          -- which consent text was agreed to
  country         TEXT,                          -- coarse geo (request.cf.country), not PII
  verification_status TEXT DEFAULT 'unverified', -- unverified | community_verified | disputed
  split           TEXT    DEFAULT 'pending',     -- pending | train | val | test | rejected
  votes_agree     INTEGER DEFAULT 0,
  votes_disagree  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_contrib_ts    ON contributions(ts);
CREATE INDEX IF NOT EXISTS idx_contrib_split ON contributions(split);
CREATE INDEX IF NOT EXISTS idx_contrib_sha   ON contributions(audio_sha256);

-- Community verification votes (Phase 3): one row per vote on a pending contribution.
CREATE TABLE IF NOT EXISTS votes (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           TEXT    NOT NULL,
  contribution INTEGER NOT NULL,                 -- contributions.id
  vote         TEXT    NOT NULL,                 -- 'agree' | 'disagree' | 'unsure'
  voter        TEXT                              -- optional pseudonymous session id
);
CREATE INDEX IF NOT EXISTS idx_votes_contrib ON votes(contribution);
