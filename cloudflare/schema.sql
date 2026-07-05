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
  country       TEXT                       -- request.cf.country (coarse geo, not PII)
);
CREATE INDEX IF NOT EXISTS idx_ident_ts   ON identifications(ts);
CREATE INDEX IF NOT EXISTS idx_ident_top1 ON identifications(top1);

-- Opt-in CC-BY contributions: the R2 key of a clip the user chose to donate, plus the
-- model's guess. `verified` flips to 1 once a human confirms the label for the commons.
CREATE TABLE IF NOT EXISTS contributions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  ts             TEXT    NOT NULL,
  r2_key         TEXT    NOT NULL,
  declared_raaga TEXT,
  confidence     REAL,
  verified       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_contrib_ts ON contributions(ts);
