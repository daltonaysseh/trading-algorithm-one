"""
Master ingestion script: pulls all quarterly-earnings-call transcripts for
the validation batch, 2019-01-01 through 2025-12-31, from stockanalysis.com
(2021+, programmatic via __data.json) and fool.com (2019-2021 gap, targeted
URLs supplied in FOOL_URLS below since fool.com has no clean index endpoint
found -- URLs discovered via Firecrawl search and hand-verified per ticker).

Writes: data/raw/transcripts/{ticker}/{ticker}_{quarter_label}.json (raw
structured turns) + data/processed/transcripts.db rows.

public_availability_ts methodology: call_date + 7 calendar days (the
calibrated default from config/tickers.yaml -- see that file for why).
"""
import sys
import os
import json
import re
import sqlite3
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from list_stockanalysis import list_transcripts as sa_list
from stockanalysis_fetch import extract_transcript as sa_extract
from fool_fetch import extract_transcript as fool_extract

PROJECT = "/Users/dalton/Projects/Trading Algorithm One"
DB_PATH = f"{PROJECT}/data/processed/transcripts.db"
RAW_DIR = f"{PROJECT}/data/raw/transcripts"
WINDOW_START = "2019-01-01"
WINDOW_END = "2025-12-31"

# Regex for a genuine quarterly earnings call label, excluding AGMs,
# conferences, investor days, M&A announcements etc. -- those aren't the
# earnings call and don't have the same prepared-remarks/Q&A structure.
QUARTER_RE = re.compile(r"^Q[1-4]\s+20\d{2}$")

# Ticker -> list of {quarter_label, url} for the pre-SA-coverage gap years,
# sourced from fool.com. Discovered via Firecrawl search 2026-08-11.
# SCVL intentionally excluded from gap-filling per approved decision to
# accept its sparse coverage as-is rather than force additional sourcing.
FOOL_GAP_URLS = {
    "MTX": [
        ("Q1 2019", "https://www.fool.com/earnings/call-transcripts/2019/05/04/minerals-technologies-inc-mtx-q1-2019-earnings-cal.aspx"),
        ("Q2 2019", "https://www.fool.com/earnings/call-transcripts/2019/08/06/minerals-technologies-inc-mtx-q2-2019-earnings-cal.aspx"),
        ("Q4 2019", "https://www.fool.com/earnings/call-transcripts/2020/01/31/minerals-technologies-inc-mtx-q4-2019-earnings-cal.aspx"),
    ],
    "JJSF": [
        ("Q1 2019", "https://www.fool.com/earnings/call-transcripts/2019/01/29/jj-snack-foods-corp-jjsf-q1-2019-earnings-conferen.aspx"),
        ("Q3 2019", "https://www.fool.com/earnings/call-transcripts/2019/07/30/jj-snack-foods-corp-jjsf-q3-2019-earnings-call-tra.aspx"),
    ],
    "CSGS": [
        ("Q1 2019", "https://www.fool.com/earnings/call-transcripts/2019/05/02/csg-systems-international-csgs-q1-2019-earnings-ca.aspx"),
        ("Q3 2019", "https://www.fool.com/earnings/call-transcripts/2019/10/31/csg-systems-international-csgs-q3-2019-earnings-ca.aspx"),
        ("Q4 2019", "https://www.fool.com/earnings/call-transcripts/2020/02/06/csg-systems-international-csgs-q4-2019-earnings-ca.aspx"),
    ],
    "SHEN": [
        ("Q3 2019", "https://www.fool.com/earnings/call-transcripts/2019/11/01/shenandoah-telecommunications-shen-q3-2019-earning.aspx"),
        ("Q4 2019", "https://www.fool.com/earnings/call-transcripts/2020/02/27/shenandoah-telecommunications-shen-q4-2019-earning.aspx"),
    ],
    "WSFS": [
        ("Q2 2019", "https://www.fool.com/earnings/call-transcripts/2019/07/23/wsfs-financial-corp-wsfs-q2-2019-earnings-call-tra.aspx"),
        ("Q3 2019", "https://www.fool.com/earnings/call-transcripts/2019/10/22/wsfs-financial-corp-wsfs-q3-2019-earnings-call-tra.aspx"),
        ("Q4 2019", "https://www.fool.com/earnings/call-transcripts/2020/01/22/wsfs-financial-corp-wsfs-q4-2019-earnings-call-tra.aspx"),
    ],
    "UTL": [
        ("Q2 2019", "https://www.fool.com/earnings/call-transcripts/2019/07/31/unitil-corp-utl-q2-2019-earnings-call-transcript.aspx"),
        ("Q3 2019", "https://www.fool.com/earnings/call-transcripts/2019/10/24/unitil-corp-utl-q3-2019-earnings-call-transcript.aspx"),
        ("Q4 2019", "https://www.fool.com/earnings/call-transcripts/2020/01/30/unitil-corp-utl-q4-2019-earnings-call-transcript.aspx"),
    ],
    "SXI": [
        ("Q3 2019", "https://www.fool.com/earnings/call-transcripts/2019/04/30/standex-international-corp-sxi-q3-2019-earnings-ca.aspx"),
        ("Q4 2019", "https://www.fool.com/earnings/call-transcripts/2019/08/27/standex-international-corp-sxi-q4-2019-earnings-ca.aspx"),
        ("Q2 2020", "https://www.fool.com/earnings/call-transcripts/2020/02/04/standex-international-corp-sxi-q2-2020-earnings-ca.aspx"),
    ],
    "USPH": [
        ("Q3 2019", "https://www.fool.com/earnings/call-transcripts/2019/11/07/us-physical-therapy-inc-usph-q3-2019-earnings-call.aspx"),
        ("Q4 2019", "https://www.fool.com/earnings/call-transcripts/2020/02/27/us-physical-therapy-inc-usph-q4-2019-earnings-call.aspx"),
        ("Q2 2021", "https://www.fool.com/earnings/call-transcripts/2021/08/05/us-physical-therapy-inc-usph-q2-2021-earnings-call/"),
    ],
    "SCVL": [
        ("Q1 2021", "https://www.fool.com/earnings/call-transcripts/2021/05/19/shoe-carnival-inc-scvl-q1-2021-earnings-call-trans/"),
    ],
}

BATCH = ["PBF", "MTX", "SXI", "SCVL", "JJSF", "USPH", "WSFS", "CSGS", "SHEN", "UTL"]

# SCVL -> SHOE ticker rename, effective 2026-06-12. Not relevant to our
# 2019-2025 window (rename postdates it) but recorded for when price data
# (Phase 3) needs to stitch the two symbols together.
TICKER_RENAMES = {"SCVL": {"new_ticker": "SHOE", "effective": "2026-06-12"}}


def save_and_insert(conn, ticker, quarter_label, call_date, source, source_url, turns_data):
    os.makedirs(f"{RAW_DIR}/{ticker}", exist_ok=True)
    safe_q = quarter_label.replace(" ", "_")
    raw_path = f"{RAW_DIR}/{ticker}/{ticker}_{safe_q}.json"
    with open(raw_path, "w") as f:
        json.dump(turns_data, f, indent=2, default=str)

    prepared_path = f"{RAW_DIR}/{ticker}/{ticker}_{safe_q}_prepared.txt"
    qa_path = f"{RAW_DIR}/{ticker}/{ticker}_{safe_q}_qa.txt"
    with open(prepared_path, "w") as f:
        for speaker, text in turns_data.get("prepared_remarks", []):
            f.write(f"[{speaker}] {text}\n\n")
    with open(qa_path, "w") as f:
        for speaker, text in turns_data.get("qa", []):
            f.write(f"[{speaker}] {text}\n\n")

    call_dt = datetime.strptime(call_date, "%Y-%m-%d")
    public_avail = (call_dt + timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        conn.execute(
            """INSERT OR REPLACE INTO transcripts
               (ticker, quarter, call_date, public_availability_ts, source,
                source_url, raw_text_path, prepared_remarks_path, qa_path,
                scraped_at, ingest_batch)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (ticker, quarter_label, call_date, public_avail, source, source_url,
             raw_path, prepared_path, qa_path,
             datetime.utcnow().isoformat(), "validation_batch_2026-08-11"),
        )
        conn.commit()
        return True, turns_data.get("qa_split_found", False)
    except sqlite3.Error as e:
        return False, str(e)


def ingest_ticker(conn, ticker):
    results = {"ticker": ticker, "sa_ok": 0, "sa_fail": 0, "fool_ok": 0, "fool_fail": 0, "skipped_nonquarterly": 0}

    # -- stockanalysis.com (2021+) --
    try:
        entries = sa_list(ticker)
    except Exception as e:
        entries = []
        print(f"  [{ticker}] SA list failed: {e}")

    for e in entries:
        label = e["quarter_label"]
        date = e["event_date"]
        if not date or not (WINDOW_START <= date <= WINDOW_END):
            continue
        if not QUARTER_RE.match(label or ""):
            results["skipped_nonquarterly"] += 1
            continue
        try:
            data = sa_extract(e["url"])
            ok, info = save_and_insert(conn, ticker, label, date, "stockanalysis.com", e["url"], data)
            if ok:
                results["sa_ok"] += 1
            else:
                results["sa_fail"] += 1
                print(f"  [{ticker}] {label} SA insert failed: {info}")
        except Exception as ex:
            results["sa_fail"] += 1
            print(f"  [{ticker}] {label} SA fetch failed: {ex}")

    # -- fool.com (2019-2021 gap) --
    for label, url in FOOL_GAP_URLS.get(ticker, []):
        try:
            data = fool_extract(url)
            call_date_raw = data.get("call_date_raw")
            call_date = None
            if call_date_raw:
                for fmt in ("%b. %d, %Y", "%B %d, %Y", "%b %d, %Y"):
                    try:
                        call_date = datetime.strptime(call_date_raw.replace(".", ""), fmt.replace(".", "")).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue
            if call_date is None:
                # last resort: pull YYYY/MM/DD from the URL path
                m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
                call_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
            if call_date is None:
                results["fool_fail"] += 1
                print(f"  [{ticker}] {label} fool.com: could not parse call date from '{call_date_raw}'")
                continue
            ok, info = save_and_insert(conn, ticker, label, call_date, "fool.com", url, data)
            if ok:
                results["fool_ok"] += 1
            else:
                results["fool_fail"] += 1
                print(f"  [{ticker}] {label} fool insert failed: {info}")
        except Exception as ex:
            results["fool_fail"] += 1
            print(f"  [{ticker}] {label} fool fetch failed: {ex}")

    return results


if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    summary = []
    for ticker in BATCH:
        print(f"=== {ticker} ===")
        r = ingest_ticker(conn, ticker)
        summary.append(r)
        print(f"  SA ok={r['sa_ok']} fail={r['sa_fail']} | fool ok={r['fool_ok']} fail={r['fool_fail']} | skipped non-quarterly={r['skipped_nonquarterly']}")
    conn.close()

    print("\n=== SUMMARY ===")
    total = 0
    for r in summary:
        n = r["sa_ok"] + r["fool_ok"]
        total += n
        print(f"{r['ticker']:6s} {n:3d} transcripts ingested")
    print(f"TOTAL: {total}")
