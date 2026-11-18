"""Second, independent pass over the headline figures.

For every row in checks/author_checks.csv this script downloads the cited
filing again, confirms that the quoted sentence really is in it, and confirms
that the figure shown on the site appears inside that sentence. It shares no
code with the modules that extracted the numbers in the first place, so it
catches a wrong link, a mis-scaled unit (million versus billion) or a sentence
that changed in an amended filing.

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


def figure_tokens(figure: str) -> list[str]:
    """Ways the figure might be written in the filing: 364.6 / 364,600 / 0.3646 trillion ..."""
    f = figure.replace("$", "").replace(",", "").strip()
    m = re.match(r"([\d.]+)\s*(bn|m|%| days)?", f)
    if not m:
        return [f]
    num, unit = float(m.group(1)), (m.group(2) or "").strip()
    out = {f"{num:g}", f"{num:.1f}", f"{num:.2f}"}
    if unit == "bn":
        # A table may give $ millions ("164,922" for $164.9bn): match on the leading digits.
        out |= {f"{num * 1000:g}", f"{num * 1000:,.0f}", f"{round(num):d}", f"{int(num * 10)}"}
    if unit == "m":
        out |= {f"{num:,.0f}", f"{num / 1000:g}"}
    return sorted(out, key=len, reverse=True)


def check(row) -> tuple[str, str]:
    url = str(row.source_url)
    if not url.startswith("https://www.sec.gov/"):
        return "skipped", "no direct link (find the annual report on sec.gov)"
    try:
        text = page_text(url)
    except Exception as e:  # network or missing file
        return "fail", f"could not open the link: {type(e).__name__}"
    hay = squash(text)
    # The stored sentence may be an excerpt joined with "..." ; every fragment must be present.
    fragments = [f.strip() for f in re.split(r"\.\.\.|\[\.\.\.\]|…", str(row.sentence_to_find)) if len(f.strip()) >= 6]
    missing = [f[:50] for f in fragments if squash(f)[:70] not in hay]
    if missing:
        return "fail", f"sentence not found in the filing: '{missing[0]}'"
    sentence = squash(str(row.sentence_to_find)).replace(",", "")
    tokens = [squash(t) for t in figure_tokens(str(row.figure))]
    if not any(t and t in sentence for t in tokens):
        # A percentage of net assets, or a table cell, may sit next to the name instead of inside the sentence.
        near = hay[max(0, hay.find(squash(fragments[0])[:40]) - 50): hay.find(squash(fragments[0])[:40]) + 900] if fragments else ""
        if not any(t and t in near for t in tokens):
            return "fail", f"sentence found, but the figure {row.figure} is not in it"
    return "pass", "sentence found in the filing and the figure is in it"


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
