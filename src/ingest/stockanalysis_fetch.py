"""
Fetch a full earnings-call transcript from stockanalysis.com's SvelteKit
__data.json endpoint (structured, speaker-role-tagged data straight from
their upstream provider, Quartr) rather than scraping rendered HTML.

Discovered 2026-08-11: stockanalysis.com blocks bare curl (400) but not a
plain `requests` call with a normal browser User-Agent (200) -- no headless
browser needed. The transcript body isn't in the server-rendered HTML; it's
in a SvelteKit `devalue`-encoded JSON payload at `<page_url>/__data.json`,
which includes `transcriptTurns`: a list of speaker turns, each with role,
speakerName, company, and per-sentence paragraphs (with even startSec/endSec
audio timestamps). This is structurally superior to text-scraping for
prepared-remarks/Q&A splitting -- we get explicit turn boundaries and roles.
"""
import requests
import json
import re
import sys

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def _devalue_resolve(i, arr, cache):
    """Recursively resolve SvelteKit's devalue flat-array encoding into a
    normal Python object. Handles the plain dict/list/primitive case, which
    covers everything this endpoint has produced so far. Does NOT handle
    devalue's special tagged forms (Date/Map/Set/BigInt/-0/NaN/Infinity) --
    none observed in transcript payloads to date; add if a KeyError/shape
    surprise shows up on a new ticker."""
    if i in cache:
        return cache[i]
    v = arr[i]
    if isinstance(v, dict):
        result = {}
        cache[i] = result
        for k, ref in v.items():
            result[k] = _devalue_resolve(ref, arr, cache)
        return result
    elif isinstance(v, list):
        result = []
        cache[i] = result
        for ref in v:
            result.append(_devalue_resolve(ref, arr, cache))
        return result
    else:
        cache[i] = v
        return v


def fetch_transcript_json(page_url: str) -> dict:
    """page_url like https://stockanalysis.com/stocks/mtx/transcripts/659240-q2-2026/"""
    data_url = page_url.rstrip("/") + "/__data.json"
    r = requests.get(data_url, headers=UA, timeout=20)
    r.raise_for_status()
    payload = json.loads(r.text)
    # nodes[-1] (or whichever node has type 'data' and the largest array) holds
    # the page-specific data; node[0]/[1] are typically shared layout/session data.
    data_nodes = [n for n in payload["nodes"] if n and n.get("type") == "data"]
    best = max(data_nodes, key=lambda n: len(n["data"]))
    arr = best["data"]
    root = _devalue_resolve(0, arr, {})
    return root


def extract_transcript(page_url: str) -> dict:
    """Returns {call_date, quarter_label, prepared_remarks: [...], qa: [...],
    raw_turns: [...]} -- prepared_remarks/qa split heuristically on the
    Operator's 'question-and-answer' announcement turn, falling back to
    treating everything as prepared_remarks if no such turn is found (flag
    for manual check rather than silently mis-splitting)."""
    root = fetch_transcript_json(page_url)
    meta = root.get("transcriptQuarter", root)  # shape may vary; meta is top-level here
    turns = meta.get("transcriptTurns", [])

    # Multiple transition-phrasing patterns observed across real calls (2026-08-11
    # audit): some operators explicitly say "question-and-answer session", others
    # just say "we'll open the call/floor/lines to questions", others skip the
    # announcement and go straight to "Our first question comes from...". Try
    # patterns in order of specificity; first match wins.
    # PRIMARY method: structural, not phrase-guessing. Each turn carries a
    # `company` field identifying the speaker's employer. Management turns
    # all share the reporting company's own name; the first turn whose
    # `company` is set AND differs from that "home company" is the first
    # analyst question -- a reliable signal straight from the source data,
    # discovered 2026-08-11 after the phrase-matching approach kept missing
    # real transitions (e.g. matched a CFO's own closing line "I'll turn it
    # over to the operator to facilitate the Q&A" as if it were the Q&A
    # itself starting, on CSGS_Q2_2025 -- caught by hand-checking a sample
    # before scoring). Falls back to phrase-matching only if `company` is
    # never populated (some transcripts have hollow role/company fields).
    home_company = None
    for t in turns:
        c = t.get("company")
        if c:
            home_company = c
            break

    qa_start_idx = None
    if home_company is not None:
        for idx, t in enumerate(turns):
            c = t.get("company")
            if c and c != home_company:
                qa_start_idx = idx
                break

    if qa_start_idx is not None:
        def turn_text(t):
            lines = []
            speaker = t.get("speakerName") or t.get("role") or "Unknown"
            for para_group in t.get("paragraphs", []):
                for p in para_group:
                    lines.append(p.get("text", ""))
            return speaker, " ".join(lines)
        prepared = [turn_text(t) for t in turns[:qa_start_idx]]
        qa = [turn_text(t) for t in turns[qa_start_idx:]]
        return {
            "call_date": meta.get("eventDate"),
            "quarter_label": meta.get("quarterLabel"),
            "detail_slug": meta.get("detailSlug"),
            "prepared_remarks": prepared,
            "qa": qa,
            "qa_split_found": True,
            "qa_split_method": "structural_company_field",
            "n_turns": len(turns),
        }

    # FALLBACK: phrase-matching, only reached if the company field is absent
    # for this transcript. Two tiers. Tier 1 patterns only ever occur at the
    # literal moment the first question is asked, so any match is trustworthy
    # regardless of turn index. Tier 2 ("question and answer session" etc.) is
    # unreliable in isolation -- operators/executives routinely preview or
    # reference it before the actual handoff -- so tier 2 excludes turn index 0
    # only (a partial mitigation; known to still misfire occasionally, which is
    # exactly why the structural method above is now primary).
    QA_PATTERNS_TIER1 = [
        r"\bour first question comes from\b",
        r"\bfirst question comes from the line of\b",
        r"\bwe will take our (next|first) question\b",
        r"\btake your first question\b",
        r"\bpleased to take\b.{0,15}\bquestions\b",
        r"\bmy first question is\b",
        r"\bturn the call over to the operator\b.{0,20}\bquestions\b",
    ]
    QA_PATTERNS_TIER2 = [
        r"\bquestion[s]?[\s-]+and[\s-]+answer\b",
        r"\bopen\b.{0,20}\b(call|floor|lines?|line)\b.{0,15}\bto\b.{0,10}questions",
        r"\bopen it up for questions\b",
        r"\bbegin\b.{0,15}\bq\s*[&\.]?\s*a\b",
    ]

    def _find(patterns, skip_first_turn):
        for idx, turn in enumerate(turns):
            if skip_first_turn and idx == 0:
                continue
            for para_group in turn.get("paragraphs", []):
                for p in para_group:
                    if any(re.search(pat, p.get("text", ""), re.I) for pat in patterns):
                        return idx
        return None

    qa_start_idx = _find(QA_PATTERNS_TIER1, skip_first_turn=False)
    if qa_start_idx is None:
        qa_start_idx = _find(QA_PATTERNS_TIER2, skip_first_turn=True)

    def turn_text(t):
        lines = []
        speaker = t.get("speakerName") or t.get("role") or "Unknown"
        for para_group in t.get("paragraphs", []):
            for p in para_group:
                lines.append(p.get("text", ""))
        return speaker, " ".join(lines)

    # NOTE: must check `is not None`, not truthiness -- qa_start_idx can
    # legitimately be a valid index that is falsy-zero-adjacent in principle;
    # more importantly this was the second half of the 2026-08-11 bug (an
    # `if qa_start_idx else ...` truthiness check silently mishandled any
    # transcript where the real split point happened to resolve at index 0).
    prepared = [turn_text(t) for t in (turns[:qa_start_idx] if qa_start_idx is not None else turns)]
    qa = [turn_text(t) for t in (turns[qa_start_idx:] if qa_start_idx is not None else [])]

    return {
        "call_date": meta.get("eventDate"),
        "quarter_label": meta.get("quarterLabel"),
        "detail_slug": meta.get("detailSlug"),
        "prepared_remarks": prepared,
        "qa": qa,
        "qa_split_found": qa_start_idx is not None,
        "n_turns": len(turns),
    }


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://stockanalysis.com/stocks/mtx/transcripts/659240-q2-2026/"
    result = extract_transcript(url)
    print(json.dumps({
        "call_date": result["call_date"],
        "quarter_label": result["quarter_label"],
        "qa_split_found": result["qa_split_found"],
        "n_turns": result["n_turns"],
        "n_prepared_turns": len(result["prepared_remarks"]),
        "n_qa_turns": len(result["qa"]),
        "first_prepared_line": result["prepared_remarks"][0] if result["prepared_remarks"] else None,
        "first_qa_line": result["qa"][0] if result["qa"] else None,
    }, indent=2, default=str))
