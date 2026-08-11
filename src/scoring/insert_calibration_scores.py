"""
The 10 hand-scored calibration transcripts, re-scored 2026-08-11 against
rubric v2 (config/rubric.md) after the compression check showed qa_directness/
consistency needed sharper anchors -- see known_issues.yaml for the full
before/after analysis. guidance/hedging/headwinds are unchanged from v1 (they
showed real discrimination, no rework needed); qa_directness/consistency
were re-derived from the same underlying reads/notes under the new 6-point
anchors, not re-read from scratch (the notes already captured the specific
behavioral detail the new anchors key off of).

USPH note: the DB's USPH "Q3 2025" row is flagged data_quality_flag
(content is actually the Q2 2025 call). The calibration score below is
for the correctly-labeled USPH Q2 2025 transcript, not the flagged row.
"""
import sqlite3
from datetime import datetime, timezone

DB_PATH = "/Users/dalton/Projects/Trading Algorithm One/data/processed/transcripts.db"
RUBRIC_VERSION = "rubric.md@2026-08-11-v2"

# (ticker, quarter, guidance, hedging, qa_directness, consistency, headwinds, notes)
SCORES = [
    ("CSGS", "Q2 2025", 75, 65, 85, 85, 80,
     "Raised profitability guidance 2nd consecutive quarter; revenue guidance reiterated but "
     "narrowed to low end (2-3% of 2-6% range). Direct answers on FX drag, ROIC, LatAm contract "
     "termination -- number-first, minimal padding (v2 qa_directness=85). Consistent confident "
     "tone prepared vs Q&A throughout (v2 consistency=85)."),
    ("MTX", "Q3 2025", 50, 55, 85, 85, 85,
     "Sales flat amid mixed end-market softness (construction, heavy truck/ag, Europe); Q4 guide "
     "slightly down sequentially on seasonality, not raised. Very direct Q&A ($ figures on Turkey "
     "expansion, MinScan economics, talc litigation run-rate) -- including the litigation question, "
     "which could easily have been deflected (v2 consistency raised 80->85: matches script tone "
     "throughout, no exception found on re-check). Headwinds named and quantified."),
    ("PBF", "Q3 2025", 35, 30, 30, 20, 65,
     "Adjusted net LOSS; Martinez refinery still down post-fire. CFO repeatedly declined to "
     "quantify normalized net debt/2026 capex when asked directly, twice, by the same analyst "
     "(\"hard to put a fine point on that... we don't have an exact impact\") -- a vague non-answer "
     "to a specific ask, not a flat refusal (v2 qa_directness=30). This is the exact pattern the "
     "v2 consistency=20 anchor is written from: confident script, repeated Q&A deflection on the "
     "same specific ask. Clearest consistency-divergence case in the batch, now scored as the "
     "outlier it is rather than pulled toward the pack by a compressed scale."),
    ("SCVL", "Q1 2026", 70, 55, 80, 80, 75,
     "(Fiscal label 'Q1 2026' on stockanalysis.com; content is the May 2025 call -- SCVL's fiscal-"
     "year labeling runs one year ahead of the content, a known convention quirk, see "
     "known_issues.yaml.) Profits beat ~10%, reaffirmed FY guide despite tariff volatility, "
     "aggressive Shoe Station expansion acceleration (51%->80% of fleet). Patrick/Mark gave detailed "
     "$ figures on P&L drag, store counts, category splits throughout Q&A (v2 qa_directness=80); "
     "no real script-vs-Q&A gap found on re-check (v2 consistency raised 75->80)."),
    ("SHEN", "Q3 2025", 55, 65, 80, 80, 70,
     "Revenue +2.5%, adjusted EBITDA +11.7%, guidance reiterated not raised. Direct Q&A on "
     "subsidized-passing targets and penetration rates. Note: source data merged the first "
     "analyst's (Frank Loudon) question into the Operator's turn -- a diarization defect, see "
     "known_issues.yaml -- so that exchange was scored as read, not excluded."),
    ("SXI", "Q1 2026", 85, 70, 90, 85, 75,
     "Explicit, numbered FY sales outlook raise (+$10M on top of prior raise), record orders, "
     "margin expansion. David Dunbar answered almost every Q&A question with a specific number "
     "immediately (book-to-bill ratios, dollar capacity figures, tax detail) -- v2 qa_directness "
     "raised 85->90, among the most direct in the batch. Highest composite in the calibration batch."),
    ("USPH", "Q2 2025", 85, 70, 90, 85, 80,
     "Raised full-year EBITDA guidance meaningfully ($88-93M -> $93-97M), record visit volumes, "
     "Medicare headwind ($25M cumulative) named and quantified rather than minimized. Carey "
     "Hendrickson answered with exact figures on request (commercial rate %, Michigan payer impact "
     "quantified to the dollar -- \"$0.30 per visit\", turnover data) -- v2 qa_directness raised "
     "85->90. Scored in place of the flagged 'Q3 2025' DB row, whose content is actually this Q2 "
     "2025 call."),
    ("UTL", "Q3 2025", 55, 65, 70, 75, 55,
     "Thin quarter (seasonally weak for a gas/electric utility, $0.03 adjusted EPS) but guidance "
     "reaffirmed and M&A integration (Bangor/Maine Natural Gas, pending Aquarion) on track. Only "
     "one analyst asked questions -- consistent with UTL's very light coverage. The rate-base "
     "reconciliation answer was real but somewhat technical/roundabout rather than immediately "
     "landing on the number (v2 qa_directness lowered 75->70, matches the 'real answer but "
     "roundabout' anchor rather than the 85 'direct, minimal padding' one)."),
    ("WSFS", "Q3 2025", 65, 75, 90, 85, 75,
     "Core EPS up sequentially, credit quality improved, buybacks ~100% of net income. Highest "
     "qa_directness in the batch -- detailed numeric walkthroughs on margin sensitivity (bps per "
     "rate cut), deposit betas, hedge program notional, answered with the number first every time."),
    ("JJSF", "Q4 2025", 55, 55, 55, 70, 85,
     "Sales down 3.9% (lapping a strong prior-year comp), cost program (\"Project Apollo\", "
     "$20M+ savings) announced with 3 plant closures. M&A question notably deflected "
     "(\"I wouldn't go that far, John\") -- a directional-but-dodging answer to a specific ask "
     "(v2 qa_directness=55, matches that anchor exactly) and a real but single-topic consistency "
     "gap against an otherwise candid call (v2 consistency=70, 'one minor exception')."),
]


def main():
    conn = sqlite3.connect(DB_PATH)
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for ticker, quarter, guidance, hedging, qa_d, consistency, headwinds, notes in SCORES:
        cur = conn.execute(
            "SELECT transcript_id FROM transcripts WHERE ticker=? AND quarter=?",
            (ticker, quarter),
        )
        row = cur.fetchone()
        if row is None:
            print(f"  SKIP {ticker} {quarter}: no matching transcript row found")
            continue
        transcript_id = row[0]
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
    print(f"Inserted/updated {inserted} scores. sentiment_scores now has {total} rows.")


if __name__ == "__main__":
    main()
