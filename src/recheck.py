"""A second pass over the source figures, on fresh downloads.

For every row in checks/author_checks.csv this script downloads the cited filing again and
confirms two things against that fresh copy:
  1. every fragment of the quoted sentence is in the filing, in full (not just its opening words);
  2. the figure is in that text as a number of the right size: "$364.6bn" must appear as 364.6 followed
     by "billion", or as about 364,600 in a table of $ millions. A sentence saying 364.6 million fails.

It uses the same downloader as the rest of the project but none of the code that extracted the numbers,
so it catches a wrong link, a wrong unit, or a sentence that changed in an amended filing.

What it does not do: it checks figures that are READ from a filing. Figures that are CALCULATED (totals,
ratios, values in today's money) are covered by the tests that pin each company's inputs to the lines
printed in its statements (tests/test_leverage.py) and by the audit recorded in checks/.

Output: checks/machine_recheck.csv (one row per figure: pass / fail and why).
This is a machine check. It does not replace the author's own reading.
"""
from __future__ import annotations

import re
from html import unescape

import pandas as pd

import edgar

REVIEW = edgar.ROOT / "checks"


def page_text(url: str) -> str:
    raw = edgar.get(url, refresh=True).decode("utf-8", "ignore")  # a fresh copy, not the cached one
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text.replace("\xa0", " "))


def squash(s: str) -> str:
    """Compare text ignoring spacing, punctuation spacing and case."""
    return re.sub(r"[^a-z0-9$.%]", "", s.lower())


def figure_in(text: str, figure: str, in_billions: bool = False) -> bool:
    """Is the figure in this text, as a number of the right size?

    `in_billions` is for a table whose heading says "(In billions)": its cells carry no unit word of their own.
    """
    f = figure.replace("$", "").replace(",", "").strip()
    m = re.match(r"([\d.]+)\s*(bn|m|%| days)?", f)
    if not m:
        return squash(f) in squash(text)
    num, unit = float(m.group(1)), (m.group(2) or "").strip()
    decimals = len(m.group(1).split(".")[1]) if "." in m.group(1) else 0
    tol = 0.5 * 10 ** -decimals + 1e-9
    for hit in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            value = float(hit.group().replace(",", ""))
        except ValueError:
            continue
        after = text[hit.end(): hit.end() + 14].lower()
        if unit == "bn":
            if abs(value - num) <= tol and ("billion" in after or in_billions):
                return True
            if "billion" not in after and value >= 100 and abs(value / 1e3 - num) <= tol:   # a table or sentence in $ millions
                return True
            if "illion" not in after and value >= 1e5 and abs(value / 1e6 - num) <= tol:    # a table in $ thousands
                return True
        elif unit == "m":
            if abs(value - num) <= tol and "billion" not in after:
                return True
            if "billion" in after and abs(value * 1e3 - num) <= tol * 1e3:
                return True
        elif abs(value - num) <= tol:
            return True
    return False


def check(row) -> tuple[str, str]:
    url = str(row.source_url)
    if not url.startswith("https://www.sec.gov/"):
        return "skipped", "no direct link (find the annual report on sec.gov)"
    try:
        text = page_text(url)
    except Exception as e:  # network or missing file
        return "fail", f"could not open the link: {type(e).__name__}"
    hay = squash(text)
    # The stored sentence may be an excerpt joined with "..." ; every fragment must be present in full.
    fragments = [f.strip() for f in re.split(r"\.\.\.|\[\.\.\.\]|…", str(row.sentence_to_find)) if len(f.strip()) >= 6]
    missing = [f[:50] for f in fragments if squash(f) not in hay]
    if missing:
        return "fail", f"sentence not found in full in the filing: '{missing[0]}'"
    in_billions = "(in billions)" in str(row.sentence_to_find).lower()   # the heading is part of the quoted text, which was just found in the filing
    if any(figure_in(f, str(row.figure), in_billions) for f in fragments):
        return "pass", "the whole sentence is in the filing and the figure is in it"
    # A table cell or a percentage may sit beside the quoted words, not inside them: look in the filing itself, just after them.
    words = [w for w in re.findall(r"[A-Za-z]{4,}", fragments[0])][:3] if fragments else []
    pattern = r"\W+(?:\w+\W+){0,3}?".join(map(re.escape, words))
    for hit in re.finditer(pattern, text) if words else []:
        if figure_in(text[hit.start(): hit.start() + 900], str(row.figure)):
            return "pass", "the whole sentence is in the filing and the figure is beside it"
    return "fail", f"sentence found, but the figure {row.figure} is not in or beside it"


def main() -> None:
    edgar._MIN_INTERVAL = 0.4
    df = pd.read_csv(REVIEW / "author_checks.csv", dtype=str).fillna("")
    results = [check(r) for r in df.itertuples()]
    out = df[["id", "claim", "figure", "source_url"]].copy()
    out["machine_result"] = [r[0] for r in results]
    out["detail"] = [r[1] for r in results]
    out.to_csv(REVIEW / "machine_recheck.csv", index=False)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 70)
    print(out[["id", "figure", "machine_result", "detail"]].to_string(index=False))
    print("\n" + ", ".join(f"{k}: {v}" for k, v in out.machine_result.value_counts().items()))


if __name__ == "__main__":
    main()
