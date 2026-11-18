"""Step 3: leases signed but not yet commenced.

Under US GAAP (ASC 842) a lease only goes on the balance sheet when it
*commences* - when the landlord hands over the asset. A company can sign a
20-year data center lease today and show nothing on its balance sheet until
the building is delivered. The only trace is one sentence in the lease
footnote. This script collects that sentence from every 10-K and 10-Q.

Output: data/processed/uncommenced_leases.csv, one row per filing, with the
sentence the number came from so each figure can be checked by eye.

Amounts are total undiscounted future payments over the life of the leases
(often 15-20+ years). They are NOT debt and NOT one year's spending.
"""
from __future__ import annotations

import re

import pandas as pd

import edgar
import text
from universe import COMPANIES

OUT = edgar.ROOT / "data" / "processed"
SINCE = "2021-01-01"
MONEY = r"\$ ?([\d,]+(?:\.\d+)?) ?(trillion|billion|million)"

# Where each company puts the number: an anchor phrase, then how far to read.
# `before`: the amount comes before the anchor (Oracle's wording).
PATTERNS = {
    "MSFT": [dict(anchor=r"(had|have) not yet commenced of", after=110)],
    "GOOGL": [dict(anchor=r"have not yet commenced with", after=170)],
    "META": [dict(anchor=r"(leases|leases,) that have not yet commenced", after=260)],
    "ORCL": [
        dict(anchor=r"of additional (operating )?lease commitments", before=40),
        dict(anchor=r"increase in our operating lease commitments to", after=30),  # older 10-Qs
    ],
    "CRWV": [dict(anchor=r"(had|have) not yet commenced\. The aggregate amount", after=130)],
}


_UNITS = {"trillion": 1e12, "billion": 1e9, "million": 1e6}


def _to_usd(num: str, unit: str) -> float:
    return float(num.replace(",", "")) * _UNITS[unit.lower()]


def extract(ticker: str, full_text: str) -> tuple[float, str] | None:
    """Return (amount in USD, evidence snippet) or None if not disclosed."""
    if ticker == "AMZN":
        # Amazon reports it as a row in its commitments table (in $ millions); the last number is the total.
        m = re.search(r"Leases not yet commenced((?: [\d,]+){3,8})", full_text)
        if not m:
            return None
        nums = [float(x.replace(",", "")) for x in m.group(1).split()]
        return nums[-1] * 1e6, m.group(0).strip()
    matches = [(m, p) for p in PATTERNS[ticker] for m in re.finditer(p["anchor"], full_text, re.I)]
    for m, p in sorted(matches, key=lambda mp: mp[0].start()):
        if "before" in p:
            window = full_text[max(0, m.start() - p["before"]): m.end()]
        else:
            window = full_text[m.start(): m.end() + p["after"]]
        first = re.search(MONEY, window)
        if not first:
            continue
        # "of $7.5 billion and $75.1 billion" = two parts of the same total (operating + finance,
        # or short-term + long-term): add them. The pair must START at the first amount; amounts
        # later in the window belong to other commitments.
        pair = re.match(MONEY + r" and " + MONEY, window[first.start():])
        value = _to_usd(*first.groups())
        if pair:
            value += _to_usd(*pair.groups()[2:])
        start = max(0, m.start() - 60)
        return value, full_text[start: m.end() + p.get("after", 0)].strip()
    return None


def main() -> None:
    rows = []
    for c in COMPANIES:
        for f in edgar.filings(c["cik"], forms=("10-K", "10-Q")):
            if f["period"] < SINCE:
                continue
            full = " ".join(text.filing_sentences(c["cik"], f))
            hit = extract(c["ticker"], full)
            rows.append(
                {
                    "ticker": c["ticker"],
                    "period_end": f["period"],
                    "form": f["form"],
                    "filed": f["filed"],
                    "uncommenced_leases": hit[0] if hit else None,
                    "evidence": hit[1] if hit else "",
                    "url": edgar.primary_doc_url(c["cik"], f),
                }
            )
    df = pd.DataFrame(rows).sort_values(["ticker", "period_end"])
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "uncommenced_leases.csv", index=False)
    wide = df.pivot_table(index="period_end", columns="ticker", values="uncommenced_leases").div(1e9).round(1)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_rows", 100)
    print(wide.to_string())
    print(f"\nfilings with no figure found: {int(df.uncommenced_leases.isna().sum())} of {len(df)}")


if __name__ == "__main__":
    main()
