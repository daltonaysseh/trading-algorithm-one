"""
Fallback path: fetch_latest.py returned "not_found_stockanalysis" -- Claude
then runs a Firecrawl search (an MCP tool, not callable from plain Python)
for "{ticker} earnings call transcript site:fool.com", and if a URL turns
up, feeds it here to extract/cache/split it the same way fetch_latest.py
does for the primary path.

Usage:
    python src/analyzer/fetch_from_url.py TICKER FOOL_URL
"""
import sys
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "ingest"))
from fool_fetch import extract_transcript  # noqa: E402

CACHE_DIR = ROOT / "data" / "raw" / "live_transcripts"


def main():
    if len(sys.argv) != 3:
        print(json.dumps({"status": "error", "message": "usage: fetch_from_url.py TICKER URL"}))
        return
    ticker, url = sys.argv[1].strip().upper(), sys.argv[2].strip()

    try:
        data = extract_transcript(url)
        call_date_raw = data.get("call_date_raw")
        call_date = None
        if call_date_raw:
            for fmt in ("%b. %d, %Y", "%B %d, %Y", "%b %d, %Y"):
                try:
                    call_date = datetime.strptime(
                        call_date_raw.replace(".", ""), fmt.replace(".", "")
                    ).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue
        if call_date is None:
            import re
            m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
            call_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else "unknown-date"

        ticker_dir = CACHE_DIR / ticker
        ticker_dir.mkdir(parents=True, exist_ok=True)
        safe_q = call_date.replace("-", "_")
        raw_path = ticker_dir / f"{ticker}_{safe_q}_foolcom.json"
        prepared_path = ticker_dir / f"{ticker}_{safe_q}_foolcom_prepared.txt"
        qa_path = ticker_dir / f"{ticker}_{safe_q}_foolcom_qa.txt"

        raw_path.write_text(json.dumps(data, indent=2, default=str))
        with open(prepared_path, "w") as f:
            for speaker, text in data.get("prepared_remarks", []):
                f.write(f"[{speaker}] {text}\n\n")
        with open(qa_path, "w") as f:
            for speaker, text in data.get("qa", []):
                f.write(f"[{speaker}] {text}\n\n")

        print(json.dumps({
            "status": "ready_to_score",
            "ticker": ticker,
            "quarter_label": None,  # fool.com pages don't reliably expose this in a parseable way
            "call_date": call_date,
            "call_url": url,
            "source": "fool.com",
            "prepared_path": str(prepared_path),
            "qa_path": str(qa_path),
            "raw_path": str(raw_path),
            "qa_split_found": data.get("qa_split_found", False),
            "n_prepared_paragraphs": data.get("n_prepared_paragraphs"),
            "n_qa_paragraphs": data.get("n_qa_paragraphs"),
        }))
    except Exception as e:
        print(json.dumps({"status": "error", "ticker": ticker, "message": str(e)}))


if __name__ == "__main__":
    main()
