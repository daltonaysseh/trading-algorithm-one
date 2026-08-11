"""
ticker -> most recent earnings-call transcript, cached, ready for Claude
to read and score. Reuses src/ingest/*.py (proven across 183 real
transcripts in Phase 1) rather than re-implementing scraping.

Usage:
    python src/analyzer/fetch_latest.py TICKER [--refresh]

Prints a JSON status to stdout:
  {"status": "cache_hit", "call_date": ..., "composite_score": ..., ...}
  {"status": "ready_to_score", "prepared_path": ..., "qa_path": ..., "call_date": ..., "call_url": ..., "source": "stockanalysis.com"}
  {"status": "not_found_stockanalysis", "ticker": ...}   -> Claude should try the Firecrawl+fool.com fallback,
                                                              then call fetch_from_url.py directly
  {"status": "error", "message": ...}

--refresh forces re-fetch of the ticker's current most-recent call even if
it matches what's cached (re-scores the same call under a possibly-updated
rubric). Does NOT need --refresh to pick up a genuinely new quarter --
that happens automatically since the live index is always checked.
"""
import sys
import os
import re
import json
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "ingest"))
from list_stockanalysis import list_transcripts  # noqa: E402
from stockanalysis_fetch import extract_transcript  # noqa: E402

DB_PATH = ROOT / "data" / "processed" / "analyzed_calls.db"
CACHE_DIR = ROOT / "data" / "raw" / "live_transcripts"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

QUARTER_RE = re.compile(r"^Q[1-4]\s+20\d{2}$")


def ensure_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text())
    conn.commit()
    return conn


def get_cached(conn, ticker):
    cur = conn.execute(
        """SELECT call_url, call_date, composite_score, guidance_score, hedging_score,
                  qa_directness_score, consistency_score, headwinds_score, divergence_note,
                  notable_excerpt, notable_speaker, notable_dimension, quarter_label
           FROM analyzed_calls WHERE ticker = ? ORDER BY call_date DESC LIMIT 1""",
        (ticker,),
    )
    return cur.fetchone()


def most_recent_quarterly(ticker):
    """Returns the most recent genuine quarterly-earnings-call entry from
    stockanalysis.com's own index (excludes AGMs/conferences/investor days,
    same filter as run_ingest.py), or None if the ticker has no page there."""
    entries = list_transcripts(ticker)
    quarterly = [e for e in entries if QUARTER_RE.match(e.get("quarter_label") or "")]
    if not quarterly:
        return None
    return max(quarterly, key=lambda e: e["event_date"])


def cache_and_split(ticker, entry, source="stockanalysis.com"):
    data = extract_transcript(entry["url"])
    ticker_dir = CACHE_DIR / ticker
    ticker_dir.mkdir(parents=True, exist_ok=True)
    safe_q = (entry.get("quarter_label") or data.get("quarter_label") or "unknown").replace(" ", "_")
    raw_path = ticker_dir / f"{ticker}_{safe_q}.json"
    prepared_path = ticker_dir / f"{ticker}_{safe_q}_prepared.txt"
    qa_path = ticker_dir / f"{ticker}_{safe_q}_qa.txt"

    raw_path.write_text(json.dumps(data, indent=2, default=str))
    with open(prepared_path, "w") as f:
        for speaker, text in data.get("prepared_remarks", []):
            f.write(f"[{speaker}] {text}\n\n")
    with open(qa_path, "w") as f:
        for speaker, text in data.get("qa", []):
            f.write(f"[{speaker}] {text}\n\n")

    return {
        "status": "ready_to_score",
        "ticker": ticker,
        "quarter_label": entry.get("quarter_label"),
        "call_date": entry["event_date"],
        "call_url": entry["url"],
        "source": source,
        "prepared_path": str(prepared_path),
        "qa_path": str(qa_path),
        "raw_path": str(raw_path),
        "qa_split_found": data.get("qa_split_found", False),
        "n_prepared_turns": len(data.get("prepared_remarks", [])),
        "n_qa_turns": len(data.get("qa", [])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--refresh", action="store_true",
                         help="re-fetch and re-score the current most-recent call even if cached")
    args = parser.parse_args()
    ticker = args.ticker.strip().upper()

    conn = ensure_db()
    try:
        entry = most_recent_quarterly(ticker)
        if entry is None:
            print(json.dumps({
                "status": "not_found_stockanalysis",
                "ticker": ticker,
                "message": (
                    f"No transcripts page found for {ticker} on stockanalysis.com "
                    "(confirmed failure mode for some small/thin-coverage tickers, "
                    "see known_issues.yaml MLI/NHC entries). Try a Firecrawl search "
                    f'for "{ticker} earnings call transcript site:fool.com" and, if '
                    "found, extract with fool_fetch.py, then score manually and call "
                    "insert_analysis.py with source='fool.com'."
                ),
            }))
            return

        cached = get_cached(conn, ticker)
        if cached and cached[0] == entry["url"] and not args.refresh:
            print(json.dumps({
                "status": "cache_hit",
                "ticker": ticker,
                "quarter_label": cached[12],
                "call_date": cached[1],
                "call_url": cached[0],
                "composite_score": cached[2],
                "guidance_score": cached[3],
                "hedging_score": cached[4],
                "qa_directness_score": cached[5],
                "consistency_score": cached[6],
                "headwinds_score": cached[7],
                "divergence_note": cached[8],
                "notable_excerpt": cached[9],
                "notable_speaker": cached[10],
                "notable_dimension": cached[11],
            }))
            return

        result = cache_and_split(ticker, entry)
        if cached and cached[0] == entry["url"] and args.refresh:
            result["note"] = "refresh requested for an already-cached call -- will overwrite on insert"
        print(json.dumps(result))

    except Exception as e:
        print(json.dumps({"status": "error", "ticker": ticker, "message": str(e)}))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
