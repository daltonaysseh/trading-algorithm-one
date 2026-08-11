"""
Fetch a full earnings-call transcript from a fool.com transcript page.
Confirmed 2026-08-11: plain `requests` with a browser User-Agent gets a
full 200 with the transcript body server-rendered directly in HTML (no JS
execution needed, unlike stockanalysis.com). Structure is consistent:
  <h2>Prepared Remarks:</h2>  <p><strong>Speaker</strong></p> <p>text</p> ...
  <h2>Questions and Answers:</h2>  <p><strong>Speaker</strong></p> <p>text</p> ...
  <h2>Call Participants:</h2>  ...
"""
import requests
from bs4 import BeautifulSoup
import re
import sys
import json

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}


def extract_transcript(page_url: str) -> dict:
    r = requests.get(page_url, headers=UA, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Call date: fool.com pages have <span id="date">Aug. 02, 2019</span>
    date_el = soup.find(id="date")
    call_date_raw = date_el.get_text(strip=True) if date_el else None

    # Walk the whole document in order, tracking which named section (h2)
    # we're under; collect (speaker, text) pairs per section. `article` scoping
    # was tried and dropped: on fool.com the h2/p transcript content isn't
    # actually nested inside the <article> tag's subtree (confirmed empirically
    # 2026-08-11 -- find_all inside <article> returned zero elements despite
    # top-level h2 search finding all 6 headings), so we operate on the full
    # soup and explicitly stop capturing once we leave the named sections.
    sections = {"Prepared Remarks": [], "Questions and Answers": [], "Call Participants": []}
    current_section = None
    current_speaker = None

    for el in soup.find_all(["h2", "p"]):
        if el.name == "h2":
            # Normalize: older fool.com pages use "Questions & Answers:" (ampersand),
            # newer ones "Questions and Answers:" -- both map to the same section key.
            heading_norm = el.get_text(strip=True).rstrip(":").lower().replace("&", "and")
            if heading_norm == "prepared remarks":
                current_section = "Prepared Remarks"
            elif heading_norm == "questions and answers":
                current_section = "Questions and Answers"
            elif heading_norm == "call participants":
                current_section = "Call Participants"
            else:
                current_section = None  # left the transcript (e.g. "Read Next")
            continue
        if current_section is None:
            continue
        strong = el.find("strong")
        text = el.get_text(strip=True)
        if strong is not None and text == strong.get_text(strip=True):
            # This <p><strong>Name</strong></p> pattern marks a speaker label
            current_speaker = text
            continue
        if text:
            sections[current_section].append((current_speaker, text))

    return {
        "call_date_raw": call_date_raw,
        "prepared_remarks": sections["Prepared Remarks"],
        "qa": sections["Questions and Answers"],
        "qa_split_found": len(sections["Questions and Answers"]) > 0,
        "n_prepared_paragraphs": len(sections["Prepared Remarks"]),
        "n_qa_paragraphs": len(sections["Questions and Answers"]),
    }


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else \
        "https://www.fool.com/earnings/call-transcripts/2019/08/06/minerals-technologies-inc-mtx-q2-2019-earnings-cal.aspx"
    result = extract_transcript(url)
    print(json.dumps({
        "call_date_raw": result["call_date_raw"],
        "qa_split_found": result["qa_split_found"],
        "n_prepared_paragraphs": result["n_prepared_paragraphs"],
        "n_qa_paragraphs": result["n_qa_paragraphs"],
        "first_prepared": result["prepared_remarks"][0] if result["prepared_remarks"] else None,
        "first_qa": result["qa"][0] if result["qa"] else None,
    }, indent=2, default=str))
