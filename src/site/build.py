"""
Static site generator for the earnings-call sentiment analyzer. Reads
data/processed/analyzed_calls.db (live analyses, current focus),
data/processed/transcripts.db (legacy calibration examples, kept as rubric
reference material), and config/*.yaml -- no hand-typed content. Rerun
after any new analysis is committed via src/analyzer/insert_analysis.py:

    python src/site/build.py

Output goes to site/ (plain HTML/CSS/JS, no server needed -- open
site/index.html directly, or `python -m http.server` from site/).
"""
import sqlite3
import shutil
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[2]
LEGACY_DB_PATH = ROOT / "data" / "processed" / "transcripts.db"
ANALYZED_DB_PATH = ROOT / "data" / "processed" / "analyzed_calls.db"
CONFIG_DIR = ROOT / "config"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
OUT_DIR = ROOT / "site"

DIMENSIONS = [
    {
        "key": "guidance",
        "label": "Guidance",
        "plain_language": (
            "Did management raise, maintain, or cut their forward outlook, and how "
            "specifically did they communicate it? A raise with real numbers scores high; "
            "a cut or a withdrawn outlook scores low."
        ),
        "hook": "Are they confident enough to raise targets, or just reaffirming?",
        "why_it_matters": (
            "Guidance is one of the few forward-looking signals management controls directly — "
            "unlike the quarter just reported, they choose what to say about the one ahead. A "
            "specific raise is a real commitment they'll be held to next quarter. Reaffirming "
            "after a beat isn't automatically weak, but it's worth noticing when it happens "
            "without a stated reason."
        ),
    },
    {
        "key": "hedging",
        "label": "Hedging",
        "plain_language": (
            "How much qualifying language did management use — 'may,' 'could,' 'we're "
            "monitoring' — versus declarative statements like 'will' and 'on track'? "
            "More qualifiers, lower score."
        ),
        "hook": "Are they committing to statements, or leaving themselves an out?",
        "why_it_matters": (
            "Qualifiers aren't inherently dishonest — real uncertainty exists and should sound "
            "uncertain. The signal is density and placement: heavy hedging concentrated on the "
            "questions an analyst actually cares about is different from routine caution "
            "sprinkled through boilerplate risk language."
        ),
    },
    {
        "key": "qa_directness",
        "label": "Q&A directness",
        "plain_language": (
            "When analysts asked pointed questions in the live Q&A, did management answer "
            "with specific numbers, or deflect into generalities? Direct answers score high."
        ),
        "hook": "When asked a specific question, do they give a specific answer?",
        "why_it_matters": (
            "Q&A is the one part of the call that isn't scripted in advance. Evasive Q&A often "
            "signals genuine uncertainty about forward guidance, not just a communications "
            "preference — management usually can answer if the number is one they're comfortable "
            "with."
        ),
    },
    {
        "key": "consistency",
        "label": "Consistency",
        "plain_language": (
            "Does the confidence level in the scripted prepared remarks match the confidence "
            "level in the unscripted Q&A? A confident script paired with an evasive Q&A is a "
            "red flag and scores low, even if each half looks fine in isolation."
        ),
        "hook": "Does the confident script survive contact with unscripted questions?",
        "why_it_matters": (
            "Prepared remarks are written and rehearsed; Q&A isn't. A gap between the two — "
            "upbeat framing in the script, evasion on the same topic under questioning — is "
            "harder to fake than either half alone, which makes it one of the more useful "
            "single signals in the rubric."
        ),
    },
    {
        "key": "headwinds",
        "label": "Headwinds",
        "plain_language": (
            "How were risks and problems discussed — named specifically with a quantified "
            "impact, or minimized and glossed over? Specific and quantified scores high."
        ),
        "hook": "Do they name the problem and put a number on it, or wave at it?",
        "why_it_matters": (
            "Quantifying a headwind ('$10M of higher costs') is a testable claim you can check "
            "against next quarter's results. Vague acknowledgment ('challenging environment') "
            "costs nothing to say and commits management to nothing — it's the easiest thing to "
            "get right on a good call and the easiest thing to fake on a bad one."
        ),
    },
]

STRENGTH_LABELS = {"strong": "Strong", "neutral": "Solid", "caution": "Caution"}


def tier(score, high=80, low=60):
    """3-tier communication-strength bucket for a 0-100 score. Composite scores
    use (75, 60); per-dimension scores use (80, 60) -- see plan for why these
    differ. Never used alone in a template -- always paired with the numeric
    score and a text label (score_legend / TIER_LABELS)."""
    if score is None:
        return "neutral"
    if score >= high:
        return "strong"
    if score < low:
        return "caution"
    return "neutral"


def load_yaml(name):
    with open(CONFIG_DIR / name) as f:
        return yaml.safe_load(f)


def safe_quarter(quarter_label, call_date):
    label = quarter_label or call_date or "unknown"
    return label.replace(" ", "_").replace("/", "-")


def get_legacy_stats(conn):
    scored_count = conn.execute(
        "SELECT COUNT(DISTINCT transcript_id) FROM sentiment_scores"
    ).fetchone()[0]
    return {"scored_count": scored_count}


def get_legacy_scored_rows(conn):
    cur = conn.execute(
        """SELECT t.ticker, t.quarter, s.guidance_score, s.hedging_score,
                  s.qa_directness_score, s.consistency_score, s.headwinds_score,
                  s.transcript_composite, s.rubric_version, s.scorer_notes
           FROM sentiment_scores s
           JOIN transcripts t ON t.transcript_id = s.transcript_id
           WHERE s.section = 'full'
           ORDER BY t.ticker"""
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def get_all_analyzed_calls(conn):
    cur = conn.execute(
        """SELECT ticker, company, sector, call_date, quarter_label, call_url, source,
                  guidance_score, hedging_score, qa_directness_score, consistency_score,
                  headwinds_score, composite_score, divergence_note, notable_excerpt,
                  notable_speaker, notable_dimension, rubric_version, analyzed_at
           FROM analyzed_calls ORDER BY ticker, call_date"""
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def main():
    legacy_conn = sqlite3.connect(LEGACY_DB_PATH)
    stats = get_legacy_stats(legacy_conn)
    scored_rows = get_legacy_scored_rows(legacy_conn)
    legacy_conn.close()

    known_issues = load_yaml("known_issues.yaml")["issues"]
    evidence = load_yaml("evidence_excerpts.yaml")
    stats["issue_count"] = len(known_issues)

    # Filter to exactly the 10 curated reference examples (evidence_excerpts.yaml's
    # `tickers` list is the authoritative set) -- sentiment_scores also holds 8
    # leftover rows from the cancelled Phase-2 scale-up (SCVL/JJSF extra quarters)
    # that were never meant to be shown as reference examples.
    evidence_by_key = {(e["ticker"], e["quarter"]): e for e in evidence["tickers"]}
    scored_rows = [row for row in scored_rows if (row["ticker"], row["quarter"]) in evidence_by_key]
    for row in scored_rows:
        row["evidence"] = evidence_by_key.get((row["ticker"], row["quarter"]))
    stats["scored_count"] = len(scored_rows)

    analyzed_conn = sqlite3.connect(ANALYZED_DB_PATH)
    analyzed_conn.executescript((ROOT / "src" / "analyzer" / "schema.sql").read_text())
    all_calls = get_all_analyzed_calls(analyzed_conn)
    analyzed_conn.close()

    for c in all_calls:
        c["safe_quarter"] = safe_quarter(c["quarter_label"], c["call_date"])
        c["report_path"] = f"tickers/{c['ticker']}_{c['safe_quarter']}.html"

    history_by_ticker = {}
    for c in all_calls:
        history_by_ticker.setdefault(c["ticker"], []).append(c)

    # one search-index entry per ticker, pointing at its most recent analysis
    latest_by_ticker = {t: hist[-1] for t, hist in history_by_ticker.items()}
    search_index = [
        {
            "ticker": c["ticker"], "company": c["company"], "sector": c["sector"],
            "quarter_label": c["quarter_label"], "report_path": c["report_path"],
        }
        for c in sorted(latest_by_ticker.values(), key=lambda c: c["ticker"])
    ]

    recent = sorted(all_calls, key=lambda c: c["analyzed_at"], reverse=True)[:5]

    stats["analyzed_ticker_count"] = len(history_by_ticker)
    stats["analyzed_call_count"] = len(all_calls)

    # Three worked examples for the How It Works page: two live analyses
    # (the strongest and most middling of the 3 calls analyzed so far) plus
    # the legacy PBF Q3 2025 calibration row -- reused because none of the
    # 3 live analyses score low enough to honestly illustrate the low end of
    # the range (see rubric.md's own "the PBF pattern" note on consistency).
    live_by_ticker_quarter = {(c["ticker"], c["quarter_label"]): c for c in all_calls}
    aap = live_by_ticker_quarter[("AAP", "Q1 2026")]
    wsfs = live_by_ticker_quarter[("WSFS", "Q2 2026")]
    pbf_legacy = evidence_by_key[("PBF", "Q3 2025")]
    case_studies = [
        {
            "ticker": "PBF", "company": "PBF Energy", "quarter": "Q3 2025",
            "composite": pbf_legacy["composite"], "report_path": None,
            "what_happened": (
                "CFO asked twice by the same analyst to normalize net debt for "
                "one-time items, declined both times with qualifiers instead of a "
                "number -- a confident prepared script paired with genuine Q&A "
                "evasion on a specific, knowable figure."
            ),
        },
        {
            "ticker": "AAP", "company": aap["company"], "quarter": aap["quarter_label"],
            "composite": aap["composite_score"], "report_path": aap["report_path"],
            "what_happened": (
                "Guidance reaffirmed, not raised, despite a Q1 beat -- but backed "
                "with a specific, credible reason (post-tax-refund seasonal lull, "
                "budget-constrained consumer) rather than vague caution. Solid, "
                "professional communication even though the number didn't move."
            ),
        },
        {
            "ticker": "WSFS", "company": wsfs["company"], "quarter": wsfs["quarter_label"],
            "composite": wsfs["composite_score"], "report_path": wsfs["report_path"],
            "what_happened": (
                "CFO answers Q&A with exact figures throughout (deposit mix split, "
                "CET1 timeline, deposit beta) and volunteers a competitive weakness "
                "unprompted rather than waiting to be asked -- direct answers plus "
                "proactive disclosure."
            ),
        },
    ]
    for cs in case_studies:
        cs["tier"] = tier(cs["composite"], 75, 60)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    env.filters["tier"] = tier
    env.globals["TIER_LABELS"] = STRENGTH_LABELS
    build_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    OUT_DIR.mkdir(exist_ok=True)
    assets_dir = OUT_DIR / "assets"
    assets_dir.mkdir(exist_ok=True)
    tickers_dir = OUT_DIR / "tickers"
    if tickers_dir.exists():
        shutil.rmtree(tickers_dir)  # clean slate each build -- stale report pages from a
    tickers_dir.mkdir(exist_ok=True)  # dropped naming scheme should never linger silently
    shutil.copy(STATIC_DIR / "style.css", assets_dir / "style.css")
    shutil.copy(STATIC_DIR / "search.js", assets_dir / "search.js")

    with open(assets_dir / "search-index.json", "w") as f:
        json.dump(search_index, f, indent=2)

    root_pages = [
        ("overview.html", "index.html", "overview", {
            "stats": stats,
        }),
        ("how_it_works.html", "how-it-works.html", "how_it_works", {
            "dimensions": DIMENSIONS,
            "examples": evidence["rubric_dimension_examples"],
            "case_studies": case_studies,
        }),
        ("rubric.html", "rubric.html", "rubric", {
            "dimensions": DIMENSIONS,
            "examples": evidence["rubric_dimension_examples"],
        }),
        ("tickers.html", "tickers.html", "tickers", {
            "rows": scored_rows,
            "stats": stats,
        }),
        ("recent_analyses.html", "recent-analyses.html", "recent_analyses", {
            "recent": recent,
        }),
        ("limitations.html", "limitations.html", "limitations", {
            "issues": known_issues,
        }),
    ]

    for template_name, out_name, active, context in root_pages:
        template = env.get_template(template_name)
        html = template.render(active=active, build_time=build_time, base_href="", **context)
        (OUT_DIR / out_name).write_text(html)

    # One report page per analyzed call (every quarter ever analyzed, not
    # just the latest -- older ones stay browsable via a ticker's history).
    report_template = env.get_template("call_report.html")
    for c in all_calls:
        row = {
            "ticker": c["ticker"], "quarter": c["quarter_label"],
            "guidance_score": c["guidance_score"], "hedging_score": c["hedging_score"],
            "qa_directness_score": c["qa_directness_score"],
            "consistency_score": c["consistency_score"], "headwinds_score": c["headwinds_score"],
            "transcript_composite": c["composite_score"], "rubric_version": c["rubric_version"],
            "scorer_notes": None,  # divergence_note is rendered in its own section instead
            "evidence": {
                "excerpt": c["notable_excerpt"], "speaker": c["notable_speaker"],
                "notable_dimension": c["notable_dimension"],
                "notable_score": c.get(f"{c['notable_dimension']}_score") if c["notable_dimension"] else None,
            } if c["notable_excerpt"] else None,
        }
        html = report_template.render(
            active="recent_analyses",
            build_time=build_time,
            base_href="../",
            call=c,
            row=row,
            history=history_by_ticker[c["ticker"]],
        )
        (tickers_dir / f"{c['ticker']}_{c['safe_quarter']}.html").write_text(html)

    print(f"Built {len(root_pages)} root pages + {len(all_calls)} call report pages to {OUT_DIR}/")
    print(f"  calibration_examples={stats['scored_count']} issues={stats['issue_count']} "
          f"analyzed_tickers={stats['analyzed_ticker_count']} analyzed_calls={stats['analyzed_call_count']}")


if __name__ == "__main__":
    main()
