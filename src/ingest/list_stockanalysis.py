"""List all available transcripts for a ticker from stockanalysis.com's
index page __data.json (same devalue decoding as stockanalysis_fetch.py)."""
import requests
import json
import sys
from stockanalysis_fetch import _devalue_resolve, UA


def list_transcripts(ticker: str, _redirected_from: str = None) -> list[dict]:
    url = f"https://stockanalysis.com/stocks/{ticker.lower()}/transcripts/__data.json"
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    payload = json.loads(r.text)
    if payload.get("type") == "redirect":
        # SvelteKit app-level redirect, e.g. SCVL -> SHOE after a ticker rename.
        # Not an HTTP redirect, so requests doesn't follow it automatically.
        new_slug = payload["location"].strip("/").split("/")[1]  # 'stocks/shoe/transcripts' -> 'shoe'
        if _redirected_from is None:  # guard against redirect loops
            return list_transcripts(new_slug, _redirected_from=ticker)
        return []
    data_nodes = [n for n in payload["nodes"] if n and n.get("type") == "data"]
    if not data_nodes:
        return []
    best = max(data_nodes, key=lambda n: len(n["data"]))
    arr = best["data"]
    root = _devalue_resolve(0, arr, {})
    entries = root.get("transcripts", [])
    out = []
    for e in entries:
        out.append({
            "quarter_label": e.get("quarterLabel"),
            "detail_slug": e.get("detailSlug"),
            "event_date": e.get("eventDate"),
            "fiscal_year": e.get("fiscalYear"),
            "url": f"https://stockanalysis.com/stocks/{ticker.lower()}/transcripts/{e.get('detailSlug')}/",
        })
    return out


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "mtx"
    for t in list_transcripts(ticker):
        print(t["event_date"], t["quarter_label"], t["url"])
