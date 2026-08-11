# Trading Algorithm One — Project State Briefing

## Goal
Build a live earnings-call sentiment analyzer for equity research. Users search 
any ticker → tool scrapes the most recent earnings call → scores management 
communication across 5 dimensions (guidance, hedging, qa_directness, consistency, 
headwinds) → returns a report. Framed as analyst research, not trading signal.

## Current Status
**PIVOTED from hypothesis backtest (Phase 2/3/4) to live analyst tool.**

Phase 1 (Ingestion): COMPLETE
- 183 earnings call transcripts scraped and split (prepared remarks vs Q&A)
- 10 tickers × 2019-2025 window (with documented gaps for sparse tickers like SCVL)
- Dual source: stockanalysis.com (2021+) + fool.com (2019-2020)
- Infrastructure proven: list_stockanalysis.py, stockanalysis_fetch.py, fool_fetch.py

Phase 2 (Scoring): IN PROGRESS, DIRECTION CHANGED
- Original plan: score all 183 transcripts, run hypothesis backtest (sentiment vs returns)
- PIVOT: only 10 reference transcripts scored (for rubric proof-of-concept)
- Rubric v2 locked and validated (sharpened qa_directness/consistency anchors)
- All 10 reference transcripts re-scored under v2
- Reason for pivot: backtest validation not needed for analyst tool use case

Phase 3/4 (Prices & Backtest): CANCELLED
- Not needed for live analyst tool
- Original work paused at 18/183 scored; those transcripts remain, reused as 
  reference examples in the website's Rubric page

Website Dashboard: COMPLETE
- 5-page static site built via build.py (Jinja2 templates)
- Pages: Overview (methodology), Rubric (5 dimensions with proof examples), 
  Calibration Examples (the 10 reference transcripts), Recent Analyses (live 
  reports, currently empty), Limitations (known issues)
- Serves from site/index.html (no server needed, fully static)
- Idempotent: rebuild.py produces identical output except timestamp

## Architecture

### Databases
- `transcripts.db`: 183 ingested transcripts + metadata (legacy, backs Rubric page only)
- `sentiment_scores`: 10 reference scores (legacy, backs Rubric page only)
- `analyzed_calls.db` (NEW): live analyzer results, schema:
  ```
  ticker, company, sector, call_date, quarter_label, call_url, source,
  raw_transcript_path, guidance_score, hedging_score, qa_directness_score,
  consistency_score, headwinds_score, composite_score, divergence_note,
  notable_excerpt, notable_speaker, notable_dimension, rubric_version, analyzed_at
  UNIQUE(ticker, call_url)
  ```

### Caching Strategy (Two Tiers)
1. **Tier 1 (raw transcripts)**: data/raw/live_transcripts/{ticker}/{call_date}.json
   - Written before scoring; cheaper retry if scoring fails
2. **Tier 2 (scored analysis)**: analyzed_calls.db
   - Source of truth for "has this call been analyzed"
   - Feeds the Recent Analyses page and per-call reports
   - INSERT OR REPLACE keyed on (ticker, call_url) prevents duplicates

### Live Analyzer Flow (To Be Built)
1. User (in Claude Code session) requests analysis of a ticker
2. `src/analyzer/fetch_latest.py TICKER`:
   - Check analyzed_calls.db: if already scored, return cached result
   - Otherwise: look up ticker's most recent call via list_stockanalysis.py
   - Fetch transcript (stockanalysis.com primary, fool.com fallback for history)
   - Split prepared remarks / Q&A using structural detection (proven ~98% accurate)
   - Write raw transcript to Tier 1 cache
   - Print prepared/Q&A text for Claude to read
3. Claude reads transcript text (no scripting this step, human judgment)
4. Claude scores against config/rubric.md v2 manually
5. Claude runs `src/analyzer/insert_analysis.py` with scores → Tier 2 cache
6. Claude runs `python src/site/build.py`:
   - Renders site/tickers/{TICKER}_{quarter}.html (per-call report)
   - Regenerates site/assets/search-index.json (all ever-analyzed tickers)
   - Updates Recent Analyses page
7. User browses the report page (fully static, no session needed after this)

## Key Files & Paths

**Ingestion (Phase 1, complete, reused):**
- `src/ingest/list_stockanalysis.py` — ticker → available calls index
- `src/ingest/stockanalysis_fetch.py` — fetch + split stockanalysis.com transcripts
- `src/ingest/fool_fetch.py` — fetch + split fool.com transcripts

**Live Analyzer (To Build):**
- `src/analyzer/fetch_latest.py` (NEW) — orchestrate fetch + caching
- `src/analyzer/insert_analysis.py` (NEW) — write scores to analyzed_calls.db

**Scoring:**
- `config/rubric.md` — v2 locked; 5 dimensions + anchors
- `config/tickers.yaml` — original validated_batch (legacy, still for reference)
- `evidence_excerpts.yaml` — the 10 reference examples + why they justify scores

**Website:**
- `src/site/build.py` — main rebuild script (run after adding new analyses)
- `src/site/templates/` — Jinja2 templates (base.html, rubric.html, call_report.html, etc.)
- `src/site/static/search.js` — client-side search (reads search-index.json)
- `site/` — generated output (gitignored, regenerate via build.py)

**Data:**
- `data/raw/transcripts/` — 183 legacy ingested transcripts
- `data/raw/live_transcripts/{ticker}/` — Tier 1 cache for live analyses (NEW)
- `data/processed/transcripts.db` — legacy (183 transcript metadata)
- `data/processed/sentiment_scores` — 10 reference scores (legacy)
- `data/processed/analyzed_calls.db` — live analyzer results (NEW)

## Important Decisions & Caveats

**Rubric & Scoring:**
- Rubric v2 has sharpened anchors for qa_directness and consistency (was over-compressing)
- Only the 10 reference transcripts have been scored; they're proof-of-concept
- Live scoring happens inside Claude Code sessions (no standalone API; no 24/7 server)
- Scoring rigor = actual human reading + judgment (not mechanical rubric application)

**Transcript Coverage:**
- stockanalysis.com data source goes back ~2021-2022 for most tickers
- fool.com fills in 2019-2021 (dual-source already built in Phase 1 infrastructure)
- Some tickers have no free coverage (confirmed: MLI, NHC — but already replaced in the 
  10-ticker reference batch with SXI, USPH)
- Live analyses will hit same gaps; explicit "no transcript found" state for these

**Data Quality Issues (Logged in known_issues.yaml):**
- fool.com older-template speaker mislabeling (content OK, speaker field unreliable)
- SCVL sparse coverage (5 total, not 19-28) + ticker renamed SHOE (handled)
- USPH content mismatch: one row mislabeled, excluded from reference set
- UTL: 4 transcripts with no Q&A section (full-text only, flagged in reports)
- CSGS: yfinance fails to fetch; quant score marked "not_computed"

**Search Behavior:**
- Now open-ended (any ticker), not gated to 10
- "Not analyzed yet" state + copyable prompt for unanalyzed tickers
- No rate-limit / 404 errors shown to user; explicit failure states instead

## Next Immediate Steps

1. **Build src/analyzer/fetch_latest.py**
   - Reuse src/ingest/*.py (proven at scale)
   - Implement Tier 1 + Tier 2 cache logic
   - Test against one already-scored reference ticker (cache hit)
   - Test against a never-analyzed ticker end-to-end (cache miss → fetch → score)
   - Test failure case: ticker with no transcript coverage (MLI, etc.)

2. **Build src/analyzer/insert_analysis.py**
   - Write Claude's manual scores to analyzed_calls.db
   - Handle INSERT OR REPLACE to avoid duplicates on re-analysis

3. **Wire into site build.py**
   - Read analyzed_calls.db
   - Render call_report.html templates per row
   - Rebuild search-index.json from all analyzed tickers (not fixed list)
   - Update Recent Analyses page

4. **Test end-to-end**
   - Analyze one ticker from scratch
   - Confirm report page renders correctly
   - Confirm sparkline appears on second analysis of same ticker
   - Confirm re-running build.py is idempotent

5. **Documentation & Go-Live**
   - Update README with user flow ("how to analyze a ticker")
   - Add disclaimer banners to all pages (analyst tool, not trading signal)
   - Point to site/index.html as the entry point

## How to Resume This Session

If context window fills:
1. Save this document (or create fresh PROJECT_STATE.md with current progress)
2. Start new Claude Code session
3. Paste this briefing + any updates to current status
4. Point to the git/file structure
5. Say "continue from [last completed step]"

The project is designed to be resumable because config files + DB are the source of truth, 
not this chat history.
