"""
Reusable batch inserter for Phase 2 scale-up scoring (the 173 transcripts
beyond the 10-transcript calibration batch). Same DB write logic as
insert_calibration_scores.py, parameterized so each ticker batch can import
and call insert_batch() with its own SCORES list, rather than duplicating
the sqlite boilerplate per ticker.

section='full' -- holistic scoring across the whole call, matching the
calibration batch's convention (split-level prepared_remarks/qa scoring
was scoped out of Phase 2, see config/rubric.md).
"""
import sqlite3
from datetime import datetime, timezone

DB_PATH = "/Users/dalton/Projects/Trading Algorithm One/data/processed/transcripts.db"
RUBRIC_VERSION = "rubric.md@2026-08-11-v2"


def insert_batch(scores, ticker_label=""):
    """scores: list of (ticker, quarter, guidance, hedging, qa_directness,
    consistency, headwinds, notes) tuples."""
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for ticker, quarter, guidance, hedging, qa_d, consistency, headwinds, notes in scores:
        cur = conn.execute(
            "SELECT transcript_id, data_quality_flag FROM transcripts WHERE ticker=? AND quarter=?",
            (ticker, quarter),
        )
        row = cur.fetchone()
        if row is None:
            print(f"  SKIP {ticker} {quarter}: no matching transcript row found")
            continue
        transcript_id, flag = row
        if flag:
            print(f"  SKIP {ticker} {quarter}: has data_quality_flag, not scoring ({flag[:60]}...)")
            continue
        composite = round((guidance + hedging + qa_d + consistency + headwinds) / 5, 1)
        conn.execute(
            """INSERT OR REPLACE INTO sentiment_scores
               (transcript_id, section, guidance_score, hedging_score, qa_directness_score,
                consistency_score, headwinds_score, transcript_composite, rubric_version,
                scored_at, scorer_notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (transcript_id, "full", guidance, hedging, qa_d, consistency, headwinds,
             composite, RUBRIC_VERSION, now, notes),
        )
        inserted += 1
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) FROM sentiment_scores")
    total = cur.fetchone()[0]
    conn.close()
    print(f"[{ticker_label}] Inserted/updated {inserted}/{len(scores)}. sentiment_scores now has {total} rows.")
    return inserted
