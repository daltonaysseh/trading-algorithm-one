-- SQLite schema for transcript metadata + sentiment scores.
-- Prices live separately in Parquet (data/processed/prices.parquet) —
-- columnar time-series is a poor fit for row-oriented SQLite at that volume.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS transcripts (
    transcript_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker              TEXT NOT NULL,
    quarter             TEXT NOT NULL,             -- e.g. 'Q2 2026'
    fiscal_period       TEXT,                       -- e.g. 'FY2026 Q2', as reported by source
    call_date           TEXT NOT NULL,              -- ISO date of the earnings call itself
    public_availability_ts TEXT NOT NULL,           -- ISO timestamp transcript was actually
                                                      -- publicly postable/scraped-visible.
                                                      -- THIS is what all downstream signals
                                                      -- and forward returns anchor to —
                                                      -- never call_date. See config/rubric.md
                                                      -- and CLAUDE.md for why.
    source               TEXT NOT NULL,             -- 'stockanalysis.com' | 'fool.com' | 'sec_edgar' | ...
    source_url           TEXT NOT NULL,
    raw_text_path         TEXT NOT NULL,            -- path under data/raw/transcripts/
    prepared_remarks_path TEXT,                     -- path to prepared-remarks-only excerpt
    qa_path                TEXT,                    -- path to Q&A-only excerpt
    scraped_at             TEXT NOT NULL,           -- when WE captured it (audit trail; distinct
                                                      -- from public_availability_ts)
    ingest_batch            TEXT,                    -- e.g. 'validation_batch_2026-08-11'
    UNIQUE(ticker, quarter)
);

CREATE TABLE IF NOT EXISTS sentiment_scores (
    score_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id        INTEGER NOT NULL REFERENCES transcripts(transcript_id),
    section              TEXT NOT NULL CHECK(section IN ('full', 'prepared_remarks', 'qa')),
    guidance_score        REAL,
    hedging_score          REAL,
    qa_directness_score     REAL,
    consistency_score        REAL,
    headwinds_score            REAL,
    transcript_composite        REAL,               -- mean of the 5 above, per config/rubric.md
    rubric_version               TEXT NOT NULL,      -- points at a version/commit of rubric.md
    scored_at                     TEXT NOT NULL,
    scorer_notes                   TEXT,             -- free-text justification, for Phase 5 spot checks
    UNIQUE(transcript_id, section)
);

-- Separate table for article-derived sentiment (public employee/news sentiment,
-- secondary per CLAUDE.md). Kept structurally distinct from transcript scores —
-- article_composite (mean of 3) is never averaged with transcript_composite
-- (mean of 5). See "Comparability constraint" in config/rubric.md.
CREATE TABLE IF NOT EXISTS article_scores (
    article_score_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker                 TEXT NOT NULL,
    article_url             TEXT NOT NULL,
    published_ts              TEXT NOT NULL,         -- public availability, same discipline as transcripts
    sentiment_score             REAL,                 -- independently judged for articles, see rubric.md
    hedging_score                 REAL,
    headwinds_score                 REAL,
    article_composite                 REAL,           -- mean of the 3 above
    rubric_version                     TEXT NOT NULL,
    scored_at                           TEXT NOT NULL,
    UNIQUE(article_url)
);

CREATE INDEX IF NOT EXISTS idx_transcripts_ticker ON transcripts(ticker);
CREATE INDEX IF NOT EXISTS idx_transcripts_avail_ts ON transcripts(public_availability_ts);
CREATE INDEX IF NOT EXISTS idx_scores_transcript ON sentiment_scores(transcript_id);
CREATE INDEX IF NOT EXISTS idx_article_scores_ticker ON article_scores(ticker);
