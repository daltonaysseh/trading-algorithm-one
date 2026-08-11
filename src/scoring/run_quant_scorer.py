"""
Computes quant fundamentals scores for the 10 validated tickers (from
config/tickers.yaml's validated_batch) and caches them to
data/processed/quant_scores.json. A manual, explicit script run -- like
run_ingest.py and insert_calibration_scores.py -- never invoked live by
the site or the browser.

Reuses ../Equity Research/stock_scorer.py's build_dataframe() and
score_universe() directly rather than reimplementing the scoring logic.
That module is importable with no side effects (checked -- it guards its
CLI behind `if __name__ == "__main__":`).

Important caveat, also logged in config/known_issues.yaml: stock_scorer.py
ranks each metric *sector-relative* by design, but our validated batch is
deliberately one company per sector (10 sectors, 10 tickers) -- below its
own MIN_SECTOR_PEERS=4 threshold, so every metric silently falls back to
*whole-universe* ranking (stock_scorer.py:217). The scores below are
therefore "ranked against the other 9 validated tickers", not true
sector-relative scores. Recorded as ranking_method so the site can state
this plainly rather than let it read as the tool's normal output.
"""
import sys
import json
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
EQUITY_RESEARCH_DIR = ROOT.parent / "Equity Research"
CONFIG_DIR = ROOT / "config"
OUT_PATH = ROOT / "data" / "processed" / "quant_scores.json"

sys.path.insert(0, str(EQUITY_RESEARCH_DIR))


def load_validated_tickers():
    import yaml
    with open(CONFIG_DIR / "tickers.yaml") as f:
        cfg = yaml.safe_load(f)
    return [row["ticker"] for row in cfg["validation_batch"]]


def main():
    from stock_scorer import build_dataframe, score_universe, MIN_SECTOR_PEERS

    tickers = load_validated_tickers()
    print(f"Fetching fundamentals for {len(tickers)} validated tickers via yfinance...")
    df = build_dataframe(tickers)

    if df.empty:
        print("ERROR: no fundamentals fetched for any ticker.", file=sys.stderr)
        sys.exit(1)

    scored = score_universe(df)

    # Every sector in our batch has exactly 1 member, well below
    # MIN_SECTOR_PEERS -- confirm that assumption rather than silently
    # trusting it, since a future ticker addition could change it.
    sector_counts = scored.groupby("sector")["ticker"].count()
    all_below_threshold = (sector_counts < MIN_SECTOR_PEERS).all()
    ranking_method = (
        "whole_universe_fallback" if all_below_threshold else "mixed_sector_relative"
    )
    if not all_below_threshold:
        print(
            "NOTE: at least one sector now has >= MIN_SECTOR_PEERS members -- "
            "some scores may be true sector-relative, not whole-universe. "
            "Update the caveat copy on the report page if so.",
            file=sys.stderr,
        )

    now = datetime.now(timezone.utc).isoformat()
    out = {}
    fetched = set(scored["ticker"])
    for ticker in tickers:
        if ticker not in fetched:
            print(f"  WARNING: {ticker} missing from results (fetch likely failed)")
            continue
        row = scored[scored["ticker"] == ticker].iloc[0]

        # yfinance can 404 a symbol yet still let fetch_fundamentals() return a
        # row (info = t.info or {} -> {}), which score_universe()'s .fillna(0)
        # composite math then turns into a misleading composite_score of 0.0
        # instead of a missing value. sector == "Unknown" is fetch_fundamentals'
        # own fallback for a dead info dict, so treat it as "fetch failed" and
        # write an explicit not-computed entry rather than a fake zero score.
        # Confirmed happening for real on this run (CSGS: yfinance 404).
        if row.get("sector") in (None, "Unknown") or pd.isna(row.get("composite_score")):
            print(f"  WARNING: {ticker} fetch returned no usable data (sector=Unknown) -- marking not_computed")
            out[ticker] = {"not_computed": True, "computed_at": now}
            continue

        out[ticker] = {
            "sector": row.get("sector"),
            "composite_score": None if pd.isna(row.get("composite_score")) else round(float(row["composite_score"]), 1),
            "cat_quality": None if pd.isna(row.get("cat_quality")) else round(float(row["cat_quality"]), 1),
            "cat_growth": None if pd.isna(row.get("cat_growth")) else round(float(row["cat_growth"]), 1),
            "cat_valuation": None if pd.isna(row.get("cat_valuation")) else round(float(row["cat_valuation"]), 1),
            "cat_financial_health": None if pd.isna(row.get("cat_financial_health")) else round(float(row["cat_financial_health"]), 1),
            "ranking_method": ranking_method,
            "computed_at": now,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {len(out)}/{len(tickers)} tickers to {OUT_PATH}")


if __name__ == "__main__":
    main()
