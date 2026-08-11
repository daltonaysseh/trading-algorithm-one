# Sentiment Scoring Rubric

Approved 2026-08-11. Derived from the undocumented 5-dimension scheme found in
`../Equity Research/earnings_sentiment.csv` (column names only, no written
criteria existed there — this document supplies the criteria). That prior
scoring was **never validated against forward returns**; the only check
in that project was a same-day Spearman correlation (≈ -0.25) between the
quant composite score and the sentiment score across ~25 tickers, one
quarter each — not a returns test. Treat this rubric as untested until
Phase 4 says otherwise.

All dimensions are scored 0-100. Anchors below are reference points, not
a rigid formula — score holistically against the anchors.

**Revision 2026-08-11 (v2): `qa_directness` and `consistency` anchors
sharpened.** Measured across the 10-transcript calibration batch: with the
original 3-point (20/50/80) anchors, both dimensions compressed into a
~10-15pt band for 9 of 10 transcripts (stdev 4.4-7.0 excluding the one
genuine outlier, PBF) while `guidance`/`hedging` spread across their full
range (stdev 12-15) with no single-outlier dependency. The rubric was
functioning as a binary "blatant stonewalling" detector on these two
dimensions rather than a continuous scale — a real problem for a
quintile-based test, which needs separation across the whole distribution.
Expanded to 6 anchor points to force mid-range discrimination; all 183
transcripts (including the original 10, re-scored) are scored under v2.

## Transcript dimensions (5, independently judged)

| Dimension | 20 | 50 | 80 |
|---|---|---|---|
| `guidance` | Guidance cut or withdrawn | Guidance maintained, no new detail | Guidance raised with specific, confident numbers |
| `hedging` | Heavy qualifiers ("may," "could," "monitoring," "if conditions allow") | Mixed confident/hedged language | Declarative, low-qualifier language ("will," "on track," "committed") |
| `headwinds` | Risks minimized, vague, or omitted | Risks acknowledged generically | Risks named specifically with quantified mitigation |

`qa_directness` (v2, 6-point anchor):
| 20 | 40 | 55 | 70 | 85 | 95 |
|---|---|---|---|---|---|
| Question ignored or refused ("we don't disclose that") | Answered only with vague generality when a specific was asked | Partial/directional answer that dodges the specific number or metric asked | Real answer but roundabout — takes a follow-up question to land on specifics | Answers directly with the specific number/metric first, minimal padding | Answers directly and proactively adds detail beyond what was asked |

`consistency` (v2, 6-point anchor — compares prepared-remarks tone to Q&A tone):
| 20 | 40 | 55 | 70 | 85 | 95 |
|---|---|---|---|---|---|
| Confident script, repeated Q&A deflection on the same specific ask (the PBF pattern) | Noticeable gap on 1-2 topics between script and Q&A | Minor gap — Q&A slightly more hedged than the script, no real evasion | Q&A matches script tone on most topics, one minor exception | Q&A matches script confidence and specificity throughout | Q&A is *more* candid/specific than the script (management volunteers extra detail under questioning) |

`transcript_composite` = mean(guidance, hedging, qa_directness, consistency, headwinds)

Each transcript is additionally split into **prepared remarks** and **Q&A**
sections and scored separately on the dimensions that apply to each
(guidance/hedging/headwinds apply to both; qa_directness and consistency
are Q&A-only / cross-section measures — consistency specifically compares
the two).

## Article dimensions (3, independently judged)

News articles (not call transcripts) lack the guidance/Q&A structure, so
only the dimensions that transfer are scored, using the *same definitions*
as above where they overlap:

| Dimension | 20 (poor) | 50 (neutral) | 80 (strong) |
|---|---|---|---|
| `sentiment` | Negative framing of company outlook/performance | Neutral/balanced coverage | Positive framing of company outlook/performance |
| `hedging` | Article emphasizes uncertainty/qualifiers in sourcing and framing | Mixed | Article reports confident, declarative claims about the company |
| `headwinds` | Risks/problems minimized or omitted | Acknowledged generically | Risks specifically named |

`article_composite` = mean(sentiment, hedging, headwinds)

**`sentiment` here is independently judged** (not derived), unlike the
transcript composite — approved 2026-08-11 because articles lack the
5-dimension structure that makes derivation meaningful.

## Comparability constraint

`transcript_composite` (mean of 5) and `article_composite` (mean of 3) are
stored in **separate columns** and are never averaged together naively —
dropping dimensions changes what the mean represents even though each
underlying dimension is still 0-100. Any single blended score across
sources requires an explicit, stated weighting, defined only if/when needed.
