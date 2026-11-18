"""How much did telecom equipment makers finance their own customers in 1997-2003?

Today's suppliers of AI hardware are sometimes compared with Lucent, Nortel,
Cisco and Motorola at the end of the 1990s, which lent money to the phone
companies that bought their equipment, guaranteed those customers' bank debt,
and then wrote much of it off. This script turns that comparison into numbers.

It does not download anything. The figures were read by hand from each
company's 10-K and 10-Q filings of the time and typed into
inputs/vendor_finance_2000.csv, one row per figure, each with the sentence or
table row it came from and a link to the filing. Those filings are plain text
with no machine-readable tags, so there is nothing to parse automatically.
(In the evidence column, runs of dots or dashes used as table rulers have been
collapsed to a space; nothing else was changed.)

WHAT THE INPUT ROWS MEAN (column `item`, amounts in millions of US dollars)

  commitments_total       loans plus guarantees the company had agreed to
                          provide, drawn or not, when the filing gives one total
  commitments_loans       the loan part of that total (drawn plus undrawn)
  commitments_guarantees  the guarantee part (drawn plus undrawn)
  commitments_undrawn     promised but not yet lent, when only that is given
  drawn_outstanding       loans and notes actually lent and still owed, before
                          any reserve
  drawn_outstanding_net   the same after deducting reserves, when the filing
                          only gives the net figure
  guarantees              customer debt guaranteed and outstanding
  lease_receivables_gross equipment leased to customers on finance leases
                          (Cisco), before unearned income and reserves
  lease_receivables_net   the same after those deductions (quarterly filings)
  lease_reserves          "unearned income and other reserves" on those leases
  sold_with_recourse      loans or receivables sold to someone else who can
                          hand the loss back
  reserves                money set aside against the loans (and, at Lucent,
                          the guarantees) for expected losses
  charges                 the expense taken in the period for bad debts and
                          customer financing (negative = money recovered)
  charges_customer_financing
                          the part of `charges` a filing attributes to customer
                          financing alone or to one named borrower; a memo
                          item, never added to `charges`
  receivables             ordinary trade receivables on the balance sheet
  revenue, net_income     for the period the filing covers (a year for a 10-K,
                          three months for a 10-Q)

An empty amount means the filing does not give the figure. It never means zero.

WHAT THIS SCRIPT COMPUTES, one row per company and period

  financing_made_available = the total promised: the stated total if there is
      one; otherwise loans plus guarantees committed; otherwise undrawn
      commitments plus loans drawn plus guarantees. Finance leases are added
      for Cisco. `made_available_basis` says which route was used.
  loans_drawn_gross = loans before reserves. If only the net figure is given
      and the reserve is known, the two are added back together.
  drawn_plus_guarantees = loans drawn + finance leases + guarantees.
  available_to_revenue, drawn_plus_guarantees_to_revenue = the two above
      divided by a year of revenue. For a quarter, the quarter's revenue is
      multiplied by four (the old quarterly filings do not give a clean
      trailing-twelve-month figure because of restatements and spin-offs).
  dso_days = days sales outstanding: receivables / annual revenue x 365, or
      receivables / quarterly revenue x 91, the same formula as
      src/nvidia_financing.py.
  reserve_share_of_drawn = reserves / the balance they protect: loans (plus
      drawn guarantees at Lucent, whose filings say the reserve covers both);
      lease reserves / gross leases at Cisco.

  For each company's peak (the period with the largest financing_made_available):
  charges_from_peak = `charges` summed over the fiscal years ending on or
      after the peak date, through fiscal 2003, and charges_share_of_peak =
      that sum / the peak. Lucent's and Nortel's charges include ordinary
      trade bad debts, so the share is an upper bound for them; Cisco booked
      most lease and loan reserves as a reduction of revenue, so its share is
      a lower bound. Two cross-checks sit beside it: narrow_charges_from_peak
      (only the `charges_customer_financing` memo items of those same fiscal
      years, a floor) and peak_reserve_share_of_peak (largest reserve balance
      ever reported / the peak).

Output: data/processed/vendor_finance_history.csv. Limits of the comparison
are written up in notes/vendor_finance_2000_notes.md.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "inputs" / "vendor_finance_2000.csv"
OUTPUT = ROOT / "data" / "processed" / "vendor_finance_history.csv"

ITEMS = (
    "commitments_total",
    "commitments_loans",
    "commitments_guarantees",
    "commitments_undrawn",
    "drawn_outstanding",
    "drawn_outstanding_net",
    "guarantees",
    "lease_receivables_gross",
    "lease_receivables_net",
    "lease_reserves",
    "sold_with_recourse",
    "reserves",
    "charges",
    "charges_customer_financing",
    "receivables",
    "revenue",
    "revenue_q4",  # the final quarter of a fiscal year, from the quarterly table in the annual report
    "revenue_first_reported",  # a fiscal year's sales as first reported, where the figure on file was later restated
    "net_income",
)
# Recorded with their source for reference and for the notes; not used in any ratio on the site.
MEMO_ITEMS = (
    "revenue_restated", "revenue_q4_restated", "revenue_restated_ex_avaya", "revenue_q4_restated_ex_avaya",
    "revenue_restated_ex_avaya_agere", "revenue_q4_restated_ex_avaya_agere", "investment_commitments",
    "commitments_nextel_equipment_financing", "nextel_equipment_financing_outstanding",
)
# Month in which each company's fiscal year ends; any other period end is a quarter.
FISCAL_YEAR_END_MONTH = {"Lucent Technologies": 9, "Cisco Systems": 7, "Nortel Networks": 12, "Motorola": 12}
# Items a filing may split into a current and a non-current row, which are added together.
MAY_REPEAT = {"lease_receivables_net"}
# Lucent says its reserve covers drawn loans and drawn guarantees together.
RESERVE_COVERS_GUARANTEES = {"Lucent Technologies"}
LAST_FISCAL_YEAR = 2003

OUT_COLUMNS = (
    ["company", "cik", "fiscal_period_end", "fiscal_year", "period_type"]
    + list(ITEMS)
    + [
        "financing_made_available",
        "made_available_basis",
        "loans_drawn_gross",
        "drawn_basis",
        "drawn_plus_guarantees",
        "guarantees_basis",
        "revenue_annualized",
        "sales_basis",
        "available_to_revenue",
        "drawn_plus_guarantees_to_revenue",
        "revenue_trailing",
        "available_to_revenue_trailing",
        "drawn_plus_guarantees_to_revenue_trailing",
        "dso_days",
        "reserve_share_of_drawn",
        "is_peak",
        "charges_from_peak",
        "charges_share_of_peak",
        "narrow_charges_from_peak",
        "narrow_charges_share_of_peak",
        "peak_reserve_balance",
        "peak_reserve_share_of_peak",
        "not_disclosed",
    ]
)


def load(path: Path = INPUT) -> list[dict]:
    """Read the hand-entered rows and refuse anything that breaks the file's own rules."""
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for n, r in enumerate(rows, start=2):
        where = f"{path.name} line {n}"
        if r["item"] not in ITEMS + MEMO_ITEMS:
            raise ValueError(f"{where}: unknown item {r['item']!r}")
        if r["company"] not in FISCAL_YEAR_END_MONTH:
            raise ValueError(f"{where}: unknown company {r['company']!r}")
        if r["verified"] not in ("yes", "no"):
            raise ValueError(f"{where}: verified must be yes or no")
        if not r["url"].startswith("https://www.sec.gov/Archives/edgar/data/"):
            raise ValueError(f"{where}: url is not an EDGAR filing")
        if r["amount_usd_millions"] != "":
            float(r["amount_usd_millions"])  # raises if not a number
            if r["verified"] != "yes" or not r["evidence"].strip():
                raise ValueError(f"{where}: a number needs its evidence sentence and verified=yes")
    return rows


def pivot(rows: list[dict]) -> dict[tuple[str, str], dict]:
    """One record per company and period, holding every disclosed item."""
    out: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["company"], r["fiscal_period_end"])
        rec = out.setdefault(key, {"company": r["company"], "cik": r["cik"], "fiscal_period_end": r["fiscal_period_end"], "_missing": []})
        if r["amount_usd_millions"] == "":
            if r["item"] not in rec:
                rec["_missing"].append(r["item"])
            continue
        value = float(r["amount_usd_millions"])
        if r["item"] in rec:
            if r["item"] not in MAY_REPEAT:
                raise ValueError(f"{key}: {r['item']} entered twice")
            value += rec[r["item"]]
        rec[r["item"]] = value
    return out


def _ratio(top: float | None, bottom: float | None) -> float | None:
    if top is None or bottom is None or bottom <= 0:
        return None
    return top / bottom


def derive(rec: dict) -> dict:
    """Add the computed columns to one company-period record."""
    g = rec.get
    year, month = int(rec["fiscal_period_end"][:4]), int(rec["fiscal_period_end"][5:7])
    annual = month == FISCAL_YEAR_END_MONTH[rec["company"]]
    rec["period_type"] = "annual" if annual else "quarter"
    rec["fiscal_year"] = year if annual or month < FISCAL_YEAR_END_MONTH[rec["company"]] else year + 1

    # Loans actually lent, before reserves.
    if g("drawn_outstanding") is not None:
        loans, basis = g("drawn_outstanding"), "gross as stated"
    elif g("drawn_outstanding_net") is not None and g("reserves") is not None:
        loans, basis = g("drawn_outstanding_net") + g("reserves"), "net figure plus reserve"
    elif g("drawn_outstanding_net") is not None:
        loans, basis = g("drawn_outstanding_net"), "net of an undisclosed reserve (lower bound)"
    else:
        loans, basis = None, ""
    rec["loans_drawn_gross"], rec["drawn_basis"] = loans, basis

    leases = g("lease_receivables_gross") if g("lease_receivables_gross") is not None else g("lease_receivables_net")

    if g("guarantees") is not None:
        guar, gbasis = g("guarantees"), "outstanding as stated"
    elif g("commitments_guarantees") is not None:
        guar, gbasis = g("commitments_guarantees"), "amount committed (upper bound)"
    else:
        guar, gbasis = None, "none disclosed"
    rec["guarantees_basis"] = gbasis

    parts = [x for x in (loans, leases, guar) if x is not None]
    rec["drawn_plus_guarantees"] = sum(parts) if loans is not None or leases is not None else None

    # Total promised.
    if g("commitments_total") is not None:
        avail, abasis = g("commitments_total"), "total as stated"
    elif g("commitments_loans") is not None:
        avail = g("commitments_loans") + (g("commitments_guarantees") or 0.0)
        abasis = "loan commitments + guarantee commitments" if g("commitments_guarantees") is not None else "loan commitments only"
    elif g("commitments_undrawn") is not None and loans is not None:
        avail = g("commitments_undrawn") + loans + (g("commitments_guarantees") or g("guarantees") or 0.0)
        abasis = "undrawn + loans drawn" + (" + guarantees" if guar is not None else "")
    elif g("commitments_undrawn") is not None:
        avail, abasis = g("commitments_undrawn"), "undrawn only (lower bound)"
    else:
        avail, abasis = None, ""
    if avail is not None and leases is not None:
        avail += leases
        abasis += " + finance leases"
    rec["financing_made_available"], rec["made_available_basis"] = avail, abasis

    # Sales. Every ratio is measured against the latest quarter's sales times four, the same yardstick used for
    # NVIDIA, so a fiscal year-end row uses that year's fourth quarter. Where no quarterly figure exists the
    # fiscal year's sales are used and the row says so. A second set of ratios, on the trailing twelve months,
    # is added in add_trailing() so the site can show how much the yardstick matters.
    revenue = g("revenue")
    quarter = g("revenue_q4") if annual else revenue
    rec["_quarter_revenue"] = quarter
    if quarter is not None:
        rec["revenue_annualized"], rec["sales_basis"] = quarter * 4, "latest quarter x 4"
    elif annual and revenue is not None:
        rec["revenue_annualized"], rec["sales_basis"] = revenue, "fiscal year (no quarterly figure)"
    else:
        rec["revenue_annualized"], rec["sales_basis"] = None, ""
    rec["available_to_revenue"] = _ratio(avail, rec["revenue_annualized"])
    rec["drawn_plus_guarantees_to_revenue"] = _ratio(rec["drawn_plus_guarantees"], rec["revenue_annualized"])
    # Days to be paid: what customers owe over one day of the latest quarter's sales (a quarter counted as 91 days).
    if quarter is not None and _ratio(g("receivables"), quarter) is not None:
        rec["dso_days"] = g("receivables") / quarter * 91
    elif annual and _ratio(g("receivables"), revenue) is not None:
        rec["dso_days"] = g("receivables") / revenue * 365
    else:
        rec["dso_days"] = None

    # Reserves against the balance they protect.
    top = bottom = 0.0
    if g("reserves") is not None and loans is not None:
        top += g("reserves")
        bottom += loans + ((g("guarantees") or 0.0) if rec["company"] in RESERVE_COVERS_GUARANTEES else 0.0)
    if g("lease_reserves") is not None and g("lease_receivables_gross") is not None:
        top += g("lease_reserves")
        bottom += g("lease_receivables_gross")
    rec["reserve_share_of_drawn"] = _ratio(top, bottom) if bottom else None
    rec["_reserve_balance"] = (g("reserves") or 0.0) + (g("lease_reserves") or 0.0) if (g("reserves") is not None or g("lease_reserves") is not None) else None
    rec["not_disclosed"] = ", ".join(sorted(set(rec.pop("_missing"))))
    return rec


# From these dates a company's quarterly sales as first reported leave out a business it separated, which earlier
# quarters still include. A twelve-month sum that crosses the date must use the earlier quarters as the company
# later restated them for the same set of businesses (the memo rows with this suffix), or it mixes two companies.
PERIMETER_CHANGES = {"Lucent Technologies": [("2000-06-30", "ex_avaya"), ("2001-03-31", "ex_avaya_agere")]}


def _quarter_on_perimeter(rec: dict, suffix: str) -> float | None:
    """A period's quarterly sales restated to a later perimeter, from the memo rows."""
    return rec.get(f"revenue_q4_restated_{suffix}" if rec["period_type"] == "annual" else f"revenue_restated_{suffix}")


def add_trailing(records: list[dict]) -> None:
    """Sales over the twelve months to each date, and the two ratios on that basis.

    A fiscal year-end uses the year's sales as first reported. Any other date needs its own quarter and
    the three before it, all covering the same set of businesses (see PERIMETER_CHANGES); if one is
    missing the trailing figure is left empty rather than estimated.
    """
    by_company: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_company[rec["company"]].append(rec)
    for company, recs in by_company.items():
        by_date = {date.fromisoformat(r["fiscal_period_end"]): r for r in recs}
        changes = PERIMETER_CHANGES.get(company, [])
        for rec in recs:
            if rec["period_type"] == "annual":
                trailing = rec.get("revenue_first_reported") if rec.get("revenue_first_reported") is not None else rec.get("revenue")
            else:
                end, parts = date.fromisoformat(rec["fiscal_period_end"]), []
                current = [c for c in changes if c[0] <= rec["fiscal_period_end"]]  # the perimeter this quarter is reported on
                since, suffix = current[-1] if current else (None, None)
                for back in range(4):
                    near = [r for d, r in by_date.items() if abs((end - d).days - 91.3 * back) <= 12]
                    if not near:
                        parts.append(None)
                    elif since is None or near[0]["fiscal_period_end"] >= since:
                        parts.append(near[0].get("_quarter_revenue"))
                    else:  # an earlier quarter, still reported with the business since separated
                        parts.append(_quarter_on_perimeter(near[0], suffix))
                trailing = None if any(x is None for x in parts) else sum(parts)
            rec["revenue_trailing"] = trailing
            rec["available_to_revenue_trailing"] = _ratio(rec["financing_made_available"], trailing)
            rec["drawn_plus_guarantees_to_revenue_trailing"] = _ratio(rec["drawn_plus_guarantees"], trailing)


def add_peaks(records: list[dict]) -> None:
    """Mark each company's peak period and what was charged off from then on."""
    by_company: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        rec["is_peak"] = ""
        by_company[rec["company"]].append(rec)
    for recs in by_company.values():
        with_total = [r for r in recs if r["financing_made_available"] is not None]
        if not with_total:
            continue
        peak = max(with_total, key=lambda r: r["financing_made_available"])
        later = [
            r
            for r in recs
            if r["period_type"] == "annual"
            and r["fiscal_period_end"] >= peak["fiscal_period_end"]
            and r["fiscal_year"] <= LAST_FISCAL_YEAR
            and r.get("charges") is not None
        ]
        narrow = [
            r["charges_customer_financing"]
            for r in recs
            if r["period_type"] == "annual"
            and r["fiscal_period_end"] >= peak["fiscal_period_end"]
            and r["fiscal_year"] <= LAST_FISCAL_YEAR
            and r.get("charges_customer_financing") is not None
        ]
        balances = [r["_reserve_balance"] for r in recs if r["_reserve_balance"] is not None]
        peak["is_peak"] = "yes"
        peak["charges_from_peak"] = sum(r["charges"] for r in later) if later else None
        peak["charges_share_of_peak"] = _ratio(peak["charges_from_peak"], peak["financing_made_available"])
        peak["narrow_charges_from_peak"] = sum(narrow) if narrow else None
        peak["narrow_charges_share_of_peak"] = _ratio(peak["narrow_charges_from_peak"], peak["financing_made_available"])
        peak["peak_reserve_balance"] = max(balances) if balances else None
        peak["peak_reserve_share_of_peak"] = _ratio(peak["peak_reserve_balance"], peak["financing_made_available"])


def build() -> list[dict]:
    records = [derive(rec) for rec in pivot(load()).values()]
    order = list(FISCAL_YEAR_END_MONTH)
    records.sort(key=lambda r: (order.index(r["company"]), r["fiscal_period_end"]))
    add_trailing(records)
    add_peaks(records)
    return records


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".") if abs(value) < 10 else f"{value:.1f}".rstrip("0").rstrip(".")
    return str(value)


def write(records: list[dict], path: Path = OUTPUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(OUT_COLUMNS)
        for rec in records:
            writer.writerow([_cell(rec.get(col)) for col in OUT_COLUMNS])


def _money(value) -> str:
    return "n/d" if value is None else f"{value:,.0f}"


def _pct(value) -> str:
    return "n/d" if value is None else f"{value * 100:.1f}%"


def summary(records: list[dict]) -> str:
    lines = ["Customer financing by telecom equipment makers, from their own filings ($ millions; n/d = not disclosed)", ""]
    head = f"{'company':<20}{'period end':<12}{'available':>10}{'drawn':>8}{'guarant.':>9}{'revenue':>9}{'avail/rev':>10}{'drawn+g/rev':>12}{'DSO':>6}{'reserve/drawn':>14}"
    lines += ["Fiscal years", head, "-" * len(head)]
    for rec in records:
        if rec["period_type"] != "annual":
            continue
        drawn = None
        if rec["loans_drawn_gross"] is not None or rec.get("lease_receivables_gross") is not None:
            drawn = (rec["loans_drawn_gross"] or 0.0) + (rec.get("lease_receivables_gross") or 0.0)
        guar = rec.get("guarantees") if rec.get("guarantees") is not None else rec.get("commitments_guarantees")
        dso = "n/d" if rec["dso_days"] is None else f"{rec['dso_days']:.0f}"
        lines.append(
            f"{rec['company']:<20}{rec['fiscal_period_end']:<12}{_money(rec['financing_made_available']):>10}{_money(drawn):>8}"
            f"{_money(guar):>9}{_money(rec.get('revenue')):>9}{_pct(rec['available_to_revenue']):>10}"
            f"{_pct(rec['drawn_plus_guarantees_to_revenue']):>12}{dso:>6}{_pct(rec['reserve_share_of_drawn']):>14}"
        )
    lines += ["", "Peak for each company (largest financing made available in any annual or quarterly filing read)"]
    for rec in records:
        if rec["is_peak"] != "yes":
            continue
        lines.append(
            f"  {rec['company']}: {_money(rec['financing_made_available'])} at {rec['fiscal_period_end']} "
            f"({rec['made_available_basis']}), {_pct(rec['available_to_revenue'])} of annualized revenue. "
            f"Charges from that fiscal year through {LAST_FISCAL_YEAR}: {_money(rec.get('charges_from_peak'))} "
            f"= {_pct(rec.get('charges_share_of_peak'))} of the peak. "
            f"Of which tied by the filings to customer financing or a named borrower: {_money(rec.get('narrow_charges_from_peak'))} "
            f"= {_pct(rec.get('narrow_charges_share_of_peak'))}. "
            f"Largest reserve balance reported: {_money(rec.get('peak_reserve_balance'))} "
            f"= {_pct(rec.get('peak_reserve_share_of_peak'))} of the peak."
        )
    n_rows = len(load())
    lines += ["", f"{len(records)} company-periods from {n_rows} hand-entered rows -> {OUTPUT.relative_to(ROOT)}"]
    return "\n".join(lines)


def main() -> None:
    records = build()
    write(records)
    print(summary(records))


if __name__ == "__main__":
    main()
