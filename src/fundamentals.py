"""Latest-quarter balance sheet and trailing-twelve-month (TTM) flows.

Annual figures are a year stale for a buildout moving this fast, so the
commitment analysis uses the most recent 10-Q or 10-K:

  * balance sheet items (debt, lease liabilities, cash) as of the latest
    quarter-end, read from that filing's XBRL instance;
  * flows (revenue, operating income, operating cash flow, capex ...) over the
    trailing twelve months:  TTM = last fiscal year + this year-to-date
                                   - same year-to-date one year earlier.

Output: data/processed/latest_fundamentals.csv
"""
from __future__ import annotations

from datetime import date

import pandas as pd

import edgar
import xbrl
from universe import COMPANIES

OUT = edgar.ROOT / "data" / "processed"

# Financing flows that can be legitimately absent in a period (treated as zero, see ttm()).
SPARSE = {"finance_lease_principal", "buybacks", "dividends", "debt_issued", "debt_repaid"}

# Flow items: companyfacts tags in order of preference.
FLOWS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "cash_from_operations": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "finance_lease_principal": ["FinanceLeasePrincipalPayments", "RepaymentsOfLongTermCapitalLeaseObligations"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "dividends": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends"],
    "debt_issued": ["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromDebtNetOfIssuanceCosts", "ProceedsFromIssuanceOfSeniorLongTermDebt",
                    "ProceedsFromIssuanceOfDebt", "ProceedsFromNotesPayable", "ProceedsFromDebtMaturingInMoreThanThreeMonths"],
    "debt_repaid": ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "RepaymentsOfNotesPayable", "RepaymentsOfSeniorDebt",
                    "RepaymentsOfDebtMaturingInMoreThanThreeMonths", "RepaymentsOfDebtAndCapitalLeaseObligations"],
    "depreciation": ["Depreciation", "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndOther"],
}

# Cash raised by selling new shares. Each tag is a different line of the cash-flow statement
# (ordinary shares, preferred shares, a stock-market listing, a private sale), so they are ADDED.
# "Common stock" proceeds include shares bought by employees through company plans.
SHARE_SALES = [
    "ProceedsFromIssuanceOfCommonStock",
    "ProceedsFromIssuanceOfConvertiblePreferredStock",
    "ProceedsFromIssuanceOfPreferredStockAndPreferenceStock",
    "ProceedsFromIssuanceOfRedeemablePreferredStock",
    "ProceedsFromIssuanceInitialPublicOffering",
    "ProceedsFromIssuanceOfPrivatePlacement",
]

# Balance sheet items: for each company, the instance concepts to ADD together.
# Chosen by reading each balance sheet; totals are used where the company tags one.
DEBT = {
    "MSFT": ["LongTermDebt"],
    "GOOGL": ["LongTermDebtNoncurrent", "LongTermDebtCurrent"],
    "AMZN": ["LongTermDebt"],
    "META": ["LongTermDebtNoncurrent", "LongTermDebtCurrent"],
    "ORCL": ["NotesPayableCurrent", "LongTermNotesAndLoans"],
    "CRWV": ["RecourseDebtCurrent", "NonRecourseDebtCurrent", "RecourseDebtNonCurrent", "NonRecourseDebtNonCurrent"],
}
CASH = {
    "MSFT": ["CashCashEquivalentsAndShortTermInvestments"],
    "GOOGL": ["CashCashEquivalentsAndShortTermInvestments"],
    "AMZN": ["CashAndCashEquivalentsAtCarryingValue", "MarketableSecuritiesCurrent"],
    "META": ["CashAndCashEquivalentsAtCarryingValue", "MarketableSecuritiesCurrent"],
    "ORCL": ["CashAndCashEquivalentsAtCarryingValue", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "CRWV": ["CashAndCashEquivalentsAtCarryingValue", "MarketableSecuritiesCurrent"],
}


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _spans(facts: dict, tag: str) -> dict[tuple[str, str], float]:
    """Every duration fact for a tag: {(start, end): value}, latest filing wins."""
    node = facts["facts"].get("us-gaap", {}).get(tag)
    rows: dict[tuple[str, str], tuple[str, float]] = {}
    for vals in (node or {"units": {}})["units"].values():
        for f in vals:
            if "start" in f:
                key = (f["start"], f["end"])
                if key not in rows or f["filed"] > rows[key][0]:
                    rows[key] = (f["filed"], f["val"])
    return {k: v[1] for k, v in rows.items()}


def ttm(facts: dict, tags: list[str], as_of: str, sparse: bool = False) -> float | None:
    """Trailing-twelve-month value of a flow item ending at `as_of`.

    Each of the three pieces (last fiscal year, this year-to-date, prior
    year-to-date) is taken from the first tag in `tags` that has it, because
    companies sometimes switch tags mid-year.

    `sparse=True` is for financing flows that can genuinely be absent in a
    period (no debt issued this quarter, no buyback): a missing year-to-date
    piece then counts as zero. For core flows a missing piece returns None,
    so a data gap can never pass as a number.
    """
    spans = [_spans(facts, tag) for tag in tags]

    def first(match) -> tuple[tuple[str, str], float] | None:
        for sp in spans:
            hits = [(k, v) for k, v in sp.items() if match(*k)]
            if hits:
                return max(hits)  # latest start among matches
        return None

    # Case 1: a twelve-month span ending at as_of (a fiscal year-end, or a company that reports TTM).
    full = first(lambda s, e: e == as_of and 350 <= _days(s, e) <= 380)
    if full:
        return full[1]
    # Case 2: last full fiscal year + this year-to-date - the same year-to-date a year earlier.
    fy = first(lambda s, e: 350 <= _days(s, e) <= 380 and 0 < _days(e, as_of) < 350)
    if not fy:
        return None
    (fy_start, fy_end), fy_val = fy
    ytd = first(lambda s, e: e == as_of and abs(_days(fy_end, s) - 1) <= 5)
    prior = first(lambda s, e: abs(_days(fy_start, s)) <= 5 and abs(_days(e, as_of) - 365) <= 5)
    if not sparse and (ytd is None or prior is None):
        return None
    return fy_val + (ytd[1] if ytd else 0.0) - (prior[1] if prior else 0.0)


def year_to_date(facts: dict, tag: str, as_of: str) -> float | None:
    """The fiscal-year-to-date value of a flow item ending at `as_of` (the longest span under a year)."""
    hits = [(k, v) for k, v in _spans(facts, tag).items() if k[1] == as_of and _days(*k) < 350]
    return min(hits)[1] if hits else None  # min = earliest start = the year-to-date span, not the single quarter


def shares_sold(facts: dict, as_of: str) -> float | None:
    """Cash raised by selling new shares over the twelve months to `as_of`; None if the company reports none.

    A company that sells shares for the first time in years has no earlier full-year figure
    for that line, so the usual twelve-month sum cannot be formed. In that case the
    year-to-date figure is used, which leaves out the final months of the previous fiscal
    year (when, by the same reports, the line did not exist). A line that a company
    re-labelled between reports can come out slightly negative; it is floored at zero.
    """
    total, seen = 0.0, False
    for tag in SHARE_SALES:
        v = ttm(facts, [tag], as_of, sparse=True)
        if v is None:
            v = year_to_date(facts, tag, as_of)
        if v is not None:
            seen = True
            total += max(v, 0.0)
    return total if seen else None


def instance_value(df: pd.DataFrame, concept: str, as_of: str) -> float | None:
    sel = df[(df.concept == concept) & (df.end == as_of) & (df.dims == "") & df.start.isna()]
    if sel.empty:
        return None
    return float(pd.to_numeric(sel.value, errors="coerce").max())  # max = the total when parts are also tagged


def build() -> pd.DataFrame:
    rows = []
    for c in COMPANIES:
        t = c["ticker"]
        filings = edgar.filings(c["cik"], forms=("10-K", "10-Q"))
        latest = filings[0]
        last_10k = next(f for f in filings if f["form"] == "10-K")
        as_of = latest["period"]
        inst = xbrl.filing_facts(c["cik"], latest)
        inst_k = xbrl.filing_facts(c["cik"], last_10k)
        facts = edgar.companyfacts(c["cik"], refresh=False)

        def bs(concepts):
            vals = [instance_value(inst, x, as_of) for x in concepts]
            return sum(v for v in vals if v is not None)

        def either(concept):
            """Latest quarter if tagged there, else the last 10-K (some items are annual-only)."""
            v = instance_value(inst, concept, as_of)
            if v is not None:
                return v, as_of
            return instance_value(inst_k, concept, last_10k["period"]), last_10k["period"]

        op_total = instance_value(inst, "OperatingLeaseLiability", as_of)
        if op_total is None or op_total < (instance_value(inst, "OperatingLeaseLiabilityNoncurrent", as_of) or 0):
            op_total = bs(["OperatingLeaseLiabilityCurrent", "OperatingLeaseLiabilityNoncurrent"])
        fin_total, fin_date = either("FinanceLeaseLiability")
        op_rate, rate_date = either("OperatingLeaseWeightedAverageDiscountRatePercent")
        fin_rate, _ = either("FinanceLeaseWeightedAverageDiscountRatePercent")
        row = {
            "ticker": t,
            "as_of": as_of,
            "form": latest["form"],
            "debt": bs(DEBT[t]),
            "operating_lease_liability": op_total,
            "finance_lease_liability": fin_total,
            "finance_lease_liability_as_of": fin_date,
            "cash_and_securities": bs(CASH[t]),
            "operating_lease_rate": op_rate,
            "finance_lease_rate": fin_rate,
            "lease_rate_as_of": rate_date,
        }
        for item, tags in FLOWS.items():
            row[f"ttm_{item}"] = ttm(facts, tags, as_of, sparse=item in SPARSE)
        row["ttm_shares_sold"] = shares_sold(facts, as_of)
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    df = build()
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "latest_fundamentals.csv", index=False)
    show = df.set_index("ticker").drop(columns=["as_of", "form", "finance_lease_liability_as_of", "lease_rate_as_of"])
    money = [c for c in show.columns if "rate" not in c]
    show[money] = (show[money] / 1e9).round(1)
    pd.set_option("display.width", 250)
    print(show.T.to_string())


if __name__ == "__main__":
    main()
