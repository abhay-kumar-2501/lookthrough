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
# Not sparse: a company that does not report it gets a blank, never a zero.

# Flow items: companyfacts tags in order of preference.
FLOWS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss"],
    "cash_from_operations": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    # Buildings and equipment taken on under finance leases: no cash changes hands, so they are in no capital-spending line.
    "finance_lease_additions": ["RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"],
    "finance_lease_principal": ["FinanceLeasePrincipalPayments", "RepaymentsOfLongTermCapitalLeaseObligations"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    "dividends": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends"],
    "debt_issued": ["ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromDebtNetOfIssuanceCosts", "ProceedsFromIssuanceOfSeniorLongTermDebt",
                    "ProceedsFromIssuanceOfDebt", "ProceedsFromNotesPayable", "ProceedsFromDebtMaturingInMoreThanThreeMonths"],
    "debt_repaid": ["RepaymentsOfLongTermDebt", "RepaymentsOfDebt", "RepaymentsOfNotesPayable", "RepaymentsOfSeniorDebt",
                    "RepaymentsOfDebtMaturingInMoreThanThreeMonths", "RepaymentsOfDebtAndCapitalLeaseObligations"],
}

# Depreciation and amortization, the amount added back to operating income to get cash profit (EBITDA).
# A cash-flow statement either gives one total line, or gives depreciation and the amortization of
# intangible assets on two lines. Until 18 November 2026 this code took the "Depreciation" tag first,
# which left the second line out for Microsoft, Meta, Oracle and CoreWeave and so understated their
# cash profit (Oracle's by about $1.5bn). Rebuilding Oracle's figures by hand is what showed it.
DA_TOTAL = ["DepreciationDepletionAndAmortization", "DepreciationAmortizationAndOther", "DepreciationAndAmortization"]
DA_PARTS = ("Depreciation", "AmortizationOfIntangibleAssets")

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
    # Carrying value, like the others (the "LongTermDebt" tag is face value), plus short-term borrowings and the
    # financing obligations Amazon records for buildings it is treated as owning (debt in all but name).
    "AMZN": ["LongTermDebtCurrent", "LongTermDebtNoncurrent", "ShortTermBorrowings", "FinancingObligationsCurrent", "FinancingObligationsNoncurrent"],
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


# Holdings counted inside "cash and marketable securities" that the filing says cannot yet be sold.
# (concept, text that must appear in the fact's dimensions). Alphabet's note 3: its SpaceX shares are
# "subject to short-term restrictions on the ability to sell".
RESTRICTED_IN_CASH = {"GOOGL": [("EquitySecuritiesFvNi", "SpaceXMember")]}

# Depreciation and amortization lines, chosen by reading each cash-flow statement and notes. They are ADDED.
#   Amazon: its cash-flow line also covers amortization of leased assets and of video content, which the other
#     five do not add back, so the property-and-equipment figure from its notes is used instead. It gives its
#     amortization of intangibles once a year, so the last fiscal year's figure stands in for the twelve months.
#   Microsoft: its cash-flow line carries a company-specific tag; the two notes figures come within 1% of it.
#   Alphabet: amortization of intangibles is given only for the year to date, so the missing months are estimated.
DA = {
    "MSFT": ["Depreciation", "AmortizationOfIntangibleAssets"],
    "GOOGL": ["Depreciation", "AmortizationOfIntangibleAssets"],
    "AMZN": ["Depreciation", "AmortizationOfIntangibleAssets"],
    "META": ["DepreciationDepletionAndAmortization"],
    "ORCL": ["Depreciation", "AmortizationOfIntangibleAssets"],
    "CRWV": ["DepreciationDepletionAndAmortization"],
}


# When a later report re-presents the prior-year year-to-date figure of a line, which version pairs with the
# fiscal-year figure in the annual report? It depends on which presentation the annual report itself used, so
# each case is settled by reading the statements, and a new case stops the build until someone has.
#   "first_filed": the annual report still used the old presentation (the usual case)
#   "restated":    the annual report had already moved to the new presentation
PRIOR_BASIS = {
    ("ORCL", "ProceedsFromIssuanceOfCommonStock"): "first_filed",  # employee plans moved to their own line in fiscal 2027; the 10-K's 1,449 is the old line
    ("GOOGL", "PaymentsForRepurchaseOfCommonStock"): "first_filed",  # $400m moved to "other financing" in 2026; the 10-K's 45,709 includes it
    ("CRWV", "RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"): "first_filed",  # the 10-K's 343 includes the $123m lease
    ("CRWV", "ProceedsFromIssuanceInitialPublicOffering"): "restated",  # the 10-K's 1,491 already includes the over-allotment shown apart in the 2025 10-Q
    ("CRWV", "ProceedsFromIssuanceOfLongTermDebt"): "restated",  # the 10-K's 11,829 is net of issuance costs; the 2025 10-Q showed them on a separate line
}
# Borrowing lines that would be debt if a company started to use them. If one appears and is not in DEBT, stop.
WATCHED_DEBT = ["CommercialPaper", "ShortTermBorrowings", "OtherShortTermBorrowings", "LineOfCredit", "ConvertibleNotesPayable"]


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _history(facts: dict, tag: str) -> dict[tuple[str, str], list[tuple[str, float]]]:
    """Every duration fact for a tag, with every value it has been given: {(start, end): [(filed, value), ...]} oldest first."""
    node = facts["facts"].get("us-gaap", {}).get(tag)
    rows: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for vals in (node or {"units": {}})["units"].values():
        for f in vals:
            if "start" in f and not str(f.get("form", "")).startswith(("DEF", "PRE")):  # proxy statements re-file some figures on another basis
                rows.setdefault((f["start"], f["end"]), []).append((f["filed"], f["val"]))
    return {k: sorted(v) for k, v in rows.items()}


def _spans(facts: dict, tag: str) -> dict[tuple[str, str], float]:
    """Every duration fact for a tag: {(start, end): value}, latest filing wins."""
    return {k: v[-1][1] for k, v in _history(facts, tag).items()}


def _as_filed_by(history: dict, key: tuple[str, str], cutoff: str) -> float:
    """The value a period carried on `cutoff`: the last one filed on or before it, else the first one filed."""
    older = [v for filed, v in history[key] if filed <= cutoff]
    return older[-1] if older else history[key][0][1]


def prior_versions(facts: dict, tag: str, as_of: str) -> tuple[float, float] | None:
    """The prior-year year-to-date figure for a tag as first filed and as latest re-presented, or None if the sum never uses one."""
    h = _history(facts, tag)
    fy = [k for k in h if 350 <= _days(*k) <= 380 and 0 < _days(k[1], as_of) < 350]
    if not fy:
        return None
    fk = max(fy)
    prior = [k for k in h if abs(_days(fk[0], k[0])) <= 5 and abs(_days(k[1], as_of) - 365) <= 5]
    if not prior:
        return None
    pk = max(prior)
    return _as_filed_by(h, pk, h[fk][-1][0]), h[pk][-1][1]


def restated_tags(ticker: str, facts: dict, tags: list[str], as_of: str) -> set[str]:
    """Tags whose prior-year figure must be read as re-presented. Stops the build on a case nobody has looked at."""
    out = set()
    for tag in tags:
        v = prior_versions(facts, tag, as_of)
        if v is None or abs(v[0] - v[1]) <= max(20e6, 0.005 * abs(v[1])):
            continue  # no re-presentation, or only rounding
        basis = PRIOR_BASIS.get((ticker, tag))
        if basis is None:
            raise ValueError(f"{ticker}: {tag} was re-presented ({v[0] / 1e6:,.0f} first filed, {v[1] / 1e6:,.0f} now). "
                             "Read the annual report and the latest report, then add the case to PRIOR_BASIS.")
        if basis == "restated":
            out.add(tag)
    return out


def ttm(facts: dict, tags: list[str], as_of: str, sparse: bool = False, restated: set[str] | frozenset = frozenset()) -> float | None:
    """Trailing-twelve-month value of a flow item ending at `as_of`.

    Each of the three pieces (last fiscal year, this year-to-date, prior
    year-to-date) is taken from the first tag in `tags` that has it, because
    companies sometimes switch tags mid-year.

    `restated` names tags whose prior year-to-date should instead be read as later re-presented, because the
    annual report itself had already moved to the new presentation (see PRIOR_BASIS and restated_tags).

    The sum is (fiscal year - prior year-to-date) + this year-to-date. The first bracket is the
    closing months of last year, so its two numbers must be on the same basis. When a company later
    re-presents a line (splits it, moves part elsewhere), the newest report restates the prior
    year-to-date but not the fiscal year. The prior year-to-date is therefore read as it stood when
    the annual report was filed, not as later re-presented. (Oracle moved its employee share plans
    to a new line in 2026; reading the restated comparative overstated new shares sold by $1.1bn.)

    `sparse=True` is for financing flows that can genuinely be absent in a
    period (no debt issued this quarter, no buyback): a missing year-to-date
    piece then counts as zero. For core flows a missing piece returns None,
    so a data gap can never pass as a number.
    """
    histories = [(_history(facts, tag), tag) for tag in tags]

    def first(match):
        for h, tag in histories:
            hits = [k for k in h if match(*k)]
            if hits:
                return max(hits), h, tag  # latest start among matches
        return None

    # Case 1: a twelve-month span ending at as_of (a fiscal year-end, or a company that reports TTM).
    full = first(lambda s, e: e == as_of and 350 <= _days(s, e) <= 380)
    if full:
        return full[1][full[0]][-1][1]
    # Case 2: last full fiscal year + this year-to-date - the same year-to-date a year earlier.
    fy = first(lambda s, e: 350 <= _days(s, e) <= 380 and 0 < _days(e, as_of) < 350)
    if not fy:
        return None
    (fy_start, fy_end), fy_hist, _ = fy
    fy_filed, fy_val = fy_hist[(fy_start, fy_end)][-1]
    ytd = first(lambda s, e: e == as_of and abs(_days(fy_end, s) - 1) <= 5)
    prior = first(lambda s, e: abs(_days(fy_start, s)) <= 5 and abs(_days(e, as_of) - 365) <= 5)
    if not sparse and (ytd is None or prior is None):
        return None
    ytd_val = ytd[1][ytd[0]][-1][1] if ytd else 0.0
    if not prior:
        prior_val = 0.0
    elif prior[2] in restated:  # the annual report had already adopted the new presentation (see PRIOR_BASIS)
        prior_val = prior[1][prior[0]][-1][1]
    else:
        prior_val = _as_filed_by(prior[1], prior[0], fy_filed)
    return fy_val + ytd_val - prior_val


def ttm_estimated(facts: dict, tag: str, as_of: str) -> float | None:
    """For a small line a company gives only for the year to date: this year to date plus the missing
    months, taken as the same share of last year's matching year-to-date. An estimate, flagged as one."""
    spans = _spans(facts, tag)
    now = [(k, v) for k, v in spans.items() if k[1] == as_of and 60 < _days(*k) < 350]
    if not now:
        return None
    (start, _), value = min(now)  # earliest start = the year to date
    months = round(_days(start, as_of) / 30.4)
    before = [v for k, v in spans.items() if abs(_days(k[0], start) - 365) <= 5 and abs(_days(k[1], as_of) - 365) <= 5]
    if not before or not 0 < months < 12:
        return None
    return value + before[0] * (12 - months) / months


def depreciation_and_amortization(facts: dict, as_of: str, ticker: str | None = None) -> tuple[float | None, str]:
    """Trailing-twelve-month depreciation plus amortization, and a note on how it was built.

    For the six companies the lines are listed in DA. For any other company: its own total line when it
    tags one, otherwise depreciation plus amortization of intangible assets.
    """
    if ticker in DA:
        total, notes = 0.0, []
        for i, tag in enumerate(DA[ticker]):
            value = ttm(facts, [tag], as_of)
            if value is None and i > 0:
                value = ttm_estimated(facts, tag, as_of)
                if value is not None:
                    notes.append(f"{tag} estimated from year-to-date figures")
                else:  # given once a year only: the last fiscal year's figure stands in
                    years = {k: v[-1][1] for k, v in _history(facts, tag).items() if 350 <= _days(*k) <= 380 and _days(k[1], as_of) < 400}
                    if years:
                        value = years[max(years)]
                        notes.append(f"{tag} is the last fiscal year's figure")
            if value is None:
                if i == 0:
                    return None, f"{tag} not found"
                notes.append(f"{tag} not reported")
                continue
            total += value
        return total, "; ".join([" + ".join(DA[ticker])] + notes)
    total = ttm(facts, DA_TOTAL, as_of)
    if total is not None:
        return total, "company total line"
    depreciation = ttm(facts, [DA_PARTS[0]], as_of)
    if depreciation is None:
        return None, "Depreciation not found"
    return depreciation + (ttm(facts, [DA_PARTS[1]], as_of) or 0.0), " + ".join(DA_PARTS)


def year_to_date(facts: dict, tag: str, as_of: str) -> float | None:
    """The fiscal-year-to-date value of a flow item ending at `as_of` (the longest span under a year)."""
    hits = [(k, v) for k, v in _spans(facts, tag).items() if k[1] == as_of and _days(*k) < 350]
    return min(hits)[1] if hits else None  # min = earliest start = the year-to-date span, not the single quarter


def shares_sold(facts: dict, as_of: str, restated: set[str] | frozenset = frozenset()) -> float | None:
    """Cash raised by selling new shares over the twelve months to `as_of`; None if the company reports none.

    A company that sells shares for the first time in years has no earlier full-year figure
    for that line, so the usual twelve-month sum cannot be formed. In that case the
    year-to-date figure is used, which leaves out the final months of the previous fiscal
    year (when, by the same reports, the line did not exist).

    A line can come out negative when a company folds it into another line in its annual report
    and never re-tags the earlier interim figure (CoreWeave's over-allotment proceeds: 67.7 in the
    2025 third-quarter report, zero in the annual report, where it sits inside the offering line).
    That negative is an artefact of the stale interim figure, not money paid back, so each line is
    floored at zero. The line it moved INTO is read on the annual report's basis (see PRIOR_BASIS).
    """
    total, seen = 0.0, False
    for tag in SHARE_SALES:
        v = ttm(facts, [tag], as_of, sparse=True, restated=restated)
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
            vals = {x: instance_value(inst, x, as_of) for x in concepts}
            missing = [x for x, v in vals.items() if v is None]
            if missing:  # a renamed tag would otherwise shrink the total without anyone noticing
                raise ValueError(f"{t}: {missing} not in the {latest['form']} for {as_of}; re-read the balance sheet and update the list")
            return sum(vals.values())

        for concept in WATCHED_DEBT:  # a borrowing line the list above does not know about
            value = instance_value(inst, concept, as_of)
            if value and concept not in DEBT[t]:
                raise ValueError(f"{t}: {concept} of {value / 1e6:,.0f} is on the balance sheet but not in DEBT; re-read it and update the list")
        every_tag = sorted({x for tags in FLOWS.values() for x in tags} | set(SHARE_SALES) | set(DA.get(t, [])))
        restated = restated_tags(t, facts, every_tag, as_of)

        def restricted():
            total = 0.0
            for concept, member in RESTRICTED_IN_CASH.get(t, []):
                sel = inst[(inst.concept == concept) & (inst.end == as_of) & inst.dims.str.contains(member, na=False) & inst.start.isna()]
                if sel.empty:
                    raise ValueError(f"{t}: {concept} / {member} not found; re-read the note on marketable securities")
                total += float(pd.to_numeric(sel.value, errors="coerce").max())
            return total

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
            "cash_it_cannot_sell_yet": restricted(),
            "operating_lease_rate": op_rate,
            "finance_lease_rate": fin_rate,
            "lease_rate_as_of": rate_date,
        }
        for item, tags in FLOWS.items():
            row[f"ttm_{item}"] = ttm(facts, tags, as_of, sparse=item in SPARSE, restated=restated)
        row["ttm_depreciation_and_amortization"], row["depreciation_basis"] = depreciation_and_amortization(facts, as_of, t)
        row["ttm_shares_sold"] = shares_sold(facts, as_of, restated)
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    df = build()
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / "latest_fundamentals.csv", index=False)
    show = df.set_index("ticker").drop(columns=["as_of", "form", "finance_lease_liability_as_of", "lease_rate_as_of"])
    show = show.drop(columns=["depreciation_basis"])
    money = [c for c in show.columns if "rate" not in c]
    show[money] = (show[money] / 1e9).round(1)
    pd.set_option("display.width", 250)
    print(show.T.to_string())


if __name__ == "__main__":
    main()
