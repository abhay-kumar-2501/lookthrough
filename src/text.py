"""Turn a filing's HTML into sentences and search them.

Used to pull the exact wording of accounting-policy disclosures (useful lives,
changes in estimate, leases not yet commenced) so every hand-entered number in
this project can be traced to a sentence in a specific filing.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

import edgar

_cache: dict[str, list[str]] = {}


def filing_sentences(cik: int, filing: dict) -> list[str]:
    url = edgar.primary_doc_url(cik, filing)
    if url in _cache:
        return _cache[url]
    soup = BeautifulSoup(edgar.get(url), "lxml")
    for tag in soup(["script", "style", "ix:header"]):
        tag.decompose()
    text = soup.get_text(" ")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    # Split on sentence ends, but not on decimals ("$2.9 billion") or "U.S.".
    parts = re.split(r"(?<=[a-z0-9\)%][.;])\s+(?=[A-Z(])", text)
    _cache[url] = [p.strip() for p in parts if p.strip()]
    return _cache[url]


def find(cik: int, filing: dict, pattern: str, also: str | None = None, max_len: int = 900) -> list[str]:
    """Sentences matching `pattern` (and `also`, if given), de-duplicated."""
    rx, rx2 = re.compile(pattern, re.I), re.compile(also, re.I) if also else None
    seen, out = set(), []
    for s in filing_sentences(cik, filing):
        if rx.search(s) and (rx2 is None or rx2.search(s)) and len(s) <= max_len:
            key = re.sub(r"\W+", "", s.lower())[:160]
            if key not in seen:
                seen.add(key)
                out.append(s)
    return out
