"""Build checks/author_checks.csv: the headline figures for the author to re-check by hand.

Software found these numbers. A person should still look at the most important
ones with their own eyes. This script lists every headline figure shown on the
site, with a link to the filing and the sentence to look for. The author opens
each link, confirms the number, and fills in three columns:

    checked_by   initials
    checked_on   date, YYYY-MM-DD
    matches      yes / no  (if no, explain in `note`)

Re-running the script refreshes the figures but never overwrites those columns.
If a figure has changed since it was checked (a new filing), the check is
cleared and the row is marked so it gets looked at again.
"""
from __future__ import annotations

import re

import pandas as pd

import edgar

OUT = edgar.ROOT / "data" / "processed"
INPUTS = edgar.ROOT / "inputs"
REVIEW = edgar.ROOT / "checks"
PATH = REVIEW / "author_checks.csv"
HUMAN = ["checked_by", "checked_on", "matches", "note"]
HOW = "Open the link, search the page for the quoted words, and confirm the number."


def bn(v: float, d: int = 1) -> str:
    return f"${v / 1e9:,.{d}f}bn"


def _annual_report_url(ticker: str, fiscal_year: int) -> str:
    """Link to a company's 10-K for a fiscal year ('' if the filing list is unavailable offline)."""
    from universe import BY_TICKER

    try:
        cik = BY_TICKER[ticker]["cik"]
        for f in edgar.filings(cik, forms=("10-K",)):
            if f["period"].startswith(str(fiscal_year)):
                return edgar.primary_doc_url(cik, f)
    except Exception:
        pass
    return ""


def _rows() -> list[dict]:
    rows: list[dict] = []

    def add(id_, page, claim, figure, url, sentence, how=HOW):
        rows.append({"id": id_, "page": page, "claim": claim, "figure": figure, "source_url": url, "sentence_to_find": " ".join(str(sentence).split())[:400], "how_to_check": how})

    leases = pd.read_csv(OUT / "uncommenced_leases.csv").dropna(subset=["uncommenced_leases"])
    names = {"MSFT": "Microsoft", "META": "Meta", "ORCL": "Oracle", "AMZN": "Amazon", "GOOGL": "Alphabet", "CRWV": "CoreWeave"}
    for t, name in names.items():
        r = leases[leases.ticker == t].sort_values("period_end").iloc[-1]
        how = HOW if t != "AMZN" else "Open the link, find the commitments table, and read the Total column of the row 'Leases not yet commenced' (in $ millions)."
        add(f"lease_{t}", "spenders", f"{name}: leases signed but not yet started, at {r.period_end}", bn(r.uncommenced_leases), r.url, r.evidence, how)

    com = pd.read_csv(OUT / "commitments.csv")
    for t, kind, label in [("GOOGL", "purchase_commitments", "Alphabet: purchase commitments"), ("META", "purchase_commitments", "Meta: non-cancelable contractual commitments"),
                           ("ORCL", "backlog_rpo", "Oracle: contracted customer backlog"), ("MSFT", "backlog_rpo", "Microsoft: contracted customer backlog")]:
        sel = com[(com.ticker == t) & (com.kind == kind) & com.in_total].sort_values("amount", ascending=False)
        if not sel.empty:
            r = sel.iloc[0]
            add(f"commit_{t}_{kind}", "spenders", f"{label}, at {r.as_of}", bn(r.amount), r.url, r.evidence)

    table = pd.read_csv(OUT / "nvidia_commitments_table.csv")
    latest = table[table.period_end == table.period_end.max()]
    for row, bucket, id_, label in [("Supply and capacity", "Total", "nvda_supply", "NVIDIA: supply and capacity commitments"), ("Total", "Total", "nvda_commit_total", "NVIDIA: all future commitments"),
                                    ("SB Energy Corp. credit support guarantees", "Maximum gross exposure", "nvda_sb_energy", "NVIDIA: maximum exposure on the Ohio campus guarantee"),
                                    ("Total", "Maximum gross exposure", "nvda_guarantees", "NVIDIA: maximum exposure on all guarantees")]:
        sel = latest[(latest.row == row) & (latest.bucket == bucket)]
        if not sel.empty:
            r = sel.iloc[0]
            add(id_, "nvidia", f"{label}, at {r.period_end}", bn(r.amount), r.url, r.evidence)

    fin = pd.read_csv(OUT / "nvidia_customer_financing.csv")
    fl = fin[fin.period_end == fin.period_end.max()]
    for item, id_, label, fmt in [("accounts_receivable", "nvda_receivables", "NVIDIA: owed by customers", bn), ("days_sales_outstanding_reported", "nvda_dso", "NVIDIA: days of sales outstanding", lambda v: f"{v:.0f} days"),
                                  ("equity_investment_commitments", "nvda_equity_commit", "NVIDIA: investments promised, not yet paid", bn), ("revenue_quarter", "nvda_revenue", "NVIDIA: revenue for the quarter", bn)]:
        sel = fl[fl.item == item].dropna(subset=["amount"])
        if not sel.empty:
            r = sel.iloc[0]
            add(id_, "nvidia", f"{label}, at {r.period_end}", fmt(r.amount), r.url, r.evidence)

    hist = pd.read_csv(INPUTS / "vendor_finance_2000.csv").dropna(subset=["amount_usd_millions"])
    for company, period, item, id_, label in [("Lucent", "1999-12-31", "commitments_total", "hist_lucent_peak", "Lucent: credit it had agreed to extend to customers"),
                                              ("Lucent", "2001-09-30", "reserves", "hist_lucent_reserves", "Lucent: reserves against customer loans"),
                                              ("Nortel", "2000-12-31", "commitments_total", "hist_nortel_peak", "Nortel: customer financing it had committed but not yet lent")]:
        sel = hist[hist.company.str.contains(company) & (hist.fiscal_period_end == period) & hist.item.str.startswith(item.split("_")[0])]
        if not sel.empty:
            r = sel.sort_values("amount_usd_millions", ascending=False).iloc[0]
            add(id_, "nvidia", f"{label}, at {period}", f"${r.amount_usd_millions:,.0f}m", r.url, r.evidence, "Open the link (an older plain-text filing), search for the quoted words, and confirm the number.")

    funds = pd.read_csv(OUT / "fund_ai_exposure.csv").set_index("fund_key")
    if "sp500" in funds.index:
        f = funds.loc["sp500"]
        add("fund_sp500_nvda", "index", f"S&P 500 index fund: share held in NVIDIA, at {f.as_of}", f"{f.pct_nvidia:.2f}%", str(f.source_urls).split(";")[0].split(" ")[0],
            "NVIDIA Corp", "Open the fund's holdings report, find NVIDIA, and read its percentage of net assets.")

    impacts = pd.read_csv(INPUTS / "disclosed_impacts.csv")
    for t, fy, id_, label in [("MSFT", 2023, "dep_msft_2023", "Microsoft: profit effect of lengthening server life (fiscal 2023)"), ("META", 2025, "dep_meta_2025", "Meta: depreciation effect of lengthening server life (2025)")]:
        sel = impacts[(impacts.ticker == t) & (impacts.fiscal_year == fy)]
        if not sel.empty:
            r = sel.iloc[0].copy()
            # The input file appends an editor's note in brackets to some quotes; keep only the filing's words.
            r.evidence = re.sub(r"\s*\((used to|subset|two mid-year)[^)]*\)\s*$", "", str(r.evidence))
            url = _annual_report_url(t, int(r.source_10k_fiscal_year))
            add(id_, "spenders", label, f"${abs(r.disclosed_reduction_bn):.2f}bn", url, r.evidence,
                HOW if url else f"Open {t}'s annual report (10-K) for fiscal {int(r.source_10k_fiscal_year)} on sec.gov, search for the quoted words, and confirm the number.")
    return rows


def build() -> pd.DataFrame:
    new = pd.DataFrame(_rows())
    for col in HUMAN:
        new[col] = ""
    if PATH.exists():
        old = pd.read_csv(PATH, dtype=str).fillna("").set_index("id")
        for i, r in new.iterrows():
            if r.id in old.index:
                prev = old.loc[r.id]
                if prev.figure == r.figure:  # unchanged: keep the author's check
                    for col in HUMAN:
                        new.at[i, col] = prev[col]
                elif prev.checked_by:
                    new.at[i, "note"] = f"Figure changed from {prev.figure} since last check on {prev.checked_on}; please re-check."
    return new


def status() -> dict:
    df = pd.read_csv(PATH, dtype=str).fillna("") if PATH.exists() else build()
    done = df[(df.checked_by != "") & (df.matches.str.lower() == "yes")]
    return {"total": int(len(df)), "checked": int(len(done)), "mismatches": int((df.matches.str.lower() == "no").sum()), "last": done.checked_on.max() if len(done) else ""}


def main() -> None:
    REVIEW.mkdir(exist_ok=True)
    df = build()
    df.to_csv(PATH, index=False)
    s = status()
    print(f"checks/author_checks.csv: {s['total']} headline figures, {s['checked']} checked by the author so far")


if __name__ == "__main__":
    main()
