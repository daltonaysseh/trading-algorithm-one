-- Live analyzer cache DB. Separate from data/processed/transcripts.db
-- (the legacy backtest-era DB, which still backs the Rubric page's 10
-- reference examples -- untouched by the pivot).

CREATE TABLE IF NOT EXISTS analyzed_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    company TEXT,
    sector TEXT,
    call_date TEXT NOT NULL,
    quarter_label TEXT,
    call_url TEXT NOT NULL,
    source TEXT NOT NULL,              -- stockanalysis.com | fool.com
    raw_transcript_path TEXT NOT NULL,
    guidance_score REAL,
    hedging_score REAL,
    qa_directness_score REAL,
    consistency_score REAL,
    headwinds_score REAL,
    composite_score REAL,
    divergence_note TEXT,              -- prepared-vs-Q&A comparison, in words
    notable_excerpt TEXT,
    notable_speaker TEXT,
    notable_dimension TEXT,
    rubric_version TEXT NOT NULL,
    analyzed_at TEXT NOT NULL,
    UNIQUE(ticker, call_url)
);

CREATE INDEX IF NOT EXISTS idx_analyzed_calls_ticker ON analyzed_calls(ticker);
CREATE INDEX IF NOT EXISTS idx_analyzed_calls_analyzed_at ON analyzed_calls(analyzed_at);
