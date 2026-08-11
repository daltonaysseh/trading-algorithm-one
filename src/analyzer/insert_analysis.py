"""
Commits Claude's scores for one analyzed call into analyzed_calls.db.
Called after Claude has read the prepared/qa text fetch_latest.py (or
fetch_from_url.py) produced and scored it against config/rubric.md.

Usage (as a library, from a short inline Python -c call or a tiny driver
script -- there's no CLI arg parser here because the payload includes
free-text notes/excerpts that are awkward as shell args):

    import sys; sys.path.insert(0, "src/analyzer")
    from insert_analysis import insert

    insert({
        "ticker": "PBF", "company": "PBF Energy", "sector": "Energy",
        "call_date": "2025-10-30", "quarter_label": "Q3 2025",
        "call_url": "...", "source": "stockanalysis.com",
        "raw_transcript_path": "...",
        "guidance_score": 35, "hedging_score": 30, "qa_directness_score": 30,
        "consistency_score": 20, "headwinds_score": 65,
        "divergence_note": "...", "notable_excerpt": "...",
        "notable_speaker": "...", "notable_dimension": "consistency",
    })
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "processed" / "analyzed_calls.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"
RUBRIC_VERSION = "rubric.md@2026-08-11-v2"

REQUIRED_FIELDS = [
    "ticker", "call_date", "call_url", "source", "raw_transcript_path",
    "guidance_score", "hedging_score", "qa_directness_score",
    "consistency_score", "headwinds_score",
]


def insert(record: dict) -> dict:
    missing = [f for f in REQUIRED_FIELDS if f not in record or record[f] is None]
    if missing:
        raise ValueError(f"insert_analysis: missing required fields: {missing}")

    composite = round(sum(record[f] for f in [
        "guidance_score", "hedging_score", "qa_directness_score",
        "consistency_score", "headwinds_score",
    ]) / 5, 1)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """INSERT OR REPLACE INTO analyzed_calls
           (ticker, company, sector, call_date, quarter_label, call_url, source,
            raw_transcript_path, guidance_score, hedging_score, qa_directness_score,
            consistency_score, headwinds_score, composite_score, divergence_note,
            notable_excerpt, notable_speaker, notable_dimension, rubric_version, analyzed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            record["ticker"], record.get("company"), record.get("sector"),
            record["call_date"], record.get("quarter_label"), record["call_url"],
            record["source"], record["raw_transcript_path"],
            record["guidance_score"], record["hedging_score"], record["qa_directness_score"],
            record["consistency_score"], record["headwinds_score"], composite,
            record.get("divergence_note"), record.get("notable_excerpt"),
            record.get("notable_speaker"), record.get("notable_dimension"),
            RUBRIC_VERSION, now,
        ),
    )
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) FROM analyzed_calls")
    total = cur.fetchone()[0]
    conn.close()
    return {"composite_score": composite, "total_analyzed_calls": total}


if __name__ == "__main__":
    print("This module is meant to be imported, not run directly -- see docstring for usage.")
