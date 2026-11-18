"""Step 5: can the business pay for what it has promised?

Three tables, each answering one plain question.

1. funding_gap.csv - where did the last twelve months of cash go, and how big
   are the promises next to it?

     operating cash flow                 cash the business produced
     - capex                             cash spent on property and equipment
     = free cash flow                    what is left for everything else
     - finance lease principal           rent on leased assets that is booked as debt repayment
     - buybacks - dividends              cash returned to shareholders
     = cash after capex, leases and payouts   (if negative, someone else paid: lenders,
                                               new shareholders, or the cash pile)

   Next to that sit the promises that are not on the balance sheet:
   leases signed but not yet started (leases.py) plus purchase, construction
   and other commitments (commitments.py), expressed in years of today's
   operating cash flow; and the contracted backlog (signed customer revenue
   not yet delivered).

   Read the last two with care. Commitments are paid over many years, some
   past 2050, so "4 years of cash flow" does not mean four years of nothing
   else. Backlog is revenue, not profit, and commitments are costs, so
   backlog / commitments is a comparison of scale, not a coverage ratio. And
   one company's commitment is often another's backlog (Meta rents cloud
   capacity from the others), so neither column should be added across
   companies as if it were a net figure.

2. capex_vs_cashflow_history.csv - capex as a share of operating cash flow for
   each fiscal year since 2015, plus the trailing-twelve-month point.

3. required_revenue.csv - what the last twelve months of capex has to earn.
   THIS IS A SENSITIVITY GRID, NOT A FORECAST. It is the "capital charge" from
   a second-year finance course, applied to one year of spending:

     equipment          = capex x equipment share        (servers, network gear)
     buildings          = capex - equipment              (shells, power, cooling)
     depreciation       = equipment / equipment life + buildings / buildings life
     required return    = capex x required return on capital
     required profit    = depreciation + required return
     required revenue   = required profit / margin

   In words: every year the assets must earn back the slice of their cost that
   wore out, plus a return for whoever put up the money; and only part of each
   revenue dollar is available for that, because the service also costs power,
   people and rent to run. `margin` is that available part: the profit margin
   on the new revenue BEFORE the depreciation of this capex (which the formula
   already counts). Using a margin measured after depreciation would count it
   twice.

   What the grid leaves out, on purpose: the return is charged on the full
   purchase price every year (it would fall as the assets are written down);
   no taxes; no land; leased data centers and their rent are not in capex at
   all; and some capex replaces old equipment or serves products that already
   earn revenue. Each row answers "if all of this year's capex had to pay for
   itself with new revenue, under these assumptions, how much?" and nothing more.

Rule for missing data: an empty cell means the company did not disclose (or
did not tag) the item. It is never treated as zero. Anything that depends on a
missing item is left empty too, and the `not_disclosed` column names what is
missing.
"""
from __future__ import annotations

from datetime import date
from itertools import product

import pandas as pd

import edgar
import fundamentals
from universe import COMPANIES

OUT = edgar.ROOT / "data" / "processed"
HISTORY_FROM = 2015

# The sensitivity grid for required_revenue.csv.
EQUIPMENT_SHARES = [0.5, 0.6, 0.7]  # share of capex that is servers and network gear
EQUIPMENT_LIVES = [3, 4, 6]  # years
BUILDINGS_LIFE = 25  # years
REQUIRED_RETURNS = [0.08, 0.10, 0.12]  # annual return the capital has to earn
MARGINS = [0.3, 0.4, 0.5]  # profit margin on the new revenue, before depreciation of this capex
MIDDLE = dict(equipment_share=0.6, equipment_life_years=4, required_return=0.10, margin_before_depreciation=0.4)


def _value(x) -> float | None:
    """A CSV cell as a number, or None when the cell is empty."""
    return None if pd.isna(x) else float(x)


def _sum(*parts: float | None) -> float | None:
    """Add the parts, or None if any part is not disclosed."""
    return None if any(p is None for p in parts) else sum(parts)


def _ratio(top: float | None, bottom: float | None) -> float | None:
    """top / bottom, or None if either is missing or the bottom is not positive."""
    return None if top is None or bottom is None or bottom <= 0 else top / bottom


def _neg(x: float | None) -> float | None:
    return None if x is None else -x


def latest_leases() -> pd.DataFrame:
    """Each company's most recent disclosed uncommenced-lease total."""
    leases = pd.read_csv(OUT / "uncommenced_leases.csv").dropna(subset=["uncommenced_leases"])
    return leases.sort_values("period_end").groupby("ticker").tail(1).set_index("ticker")


def commitment_totals(ticker: str, commitments: pd.DataFrame) -> dict:
    """Add up one company's rows from commitments.csv that are flagged in_total."""
    rows = commitments[(commitments.ticker == ticker) & commitments.in_total]
    signed = rows[rows.kind != "backlog_rpo"]
    orders = signed[signed.kind.isin(["purchase_commitments", "construction"])]
    backlog = rows[rows.kind == "backlog_rpo"]
    # A 12-month figure only counts if every purchase and construction row has one.
    due_12m = orders.due_within_12_months.sum() if len(orders) and orders.due_within_12_months.notna().all() else None
    return {
        "other_signed_commitments": signed.amount.sum() if len(signed) else None,
        "other_commitments_as_of": " / ".join(sorted(set(signed.as_of))),
        "purchase_and_construction_due_within_12_months": due_12m,
        "contracted_backlog": backlog.amount.sum() if len(backlog) else None,
        "backlog_as_of": " / ".join(sorted(set(backlog.as_of))),
    }


def funding_gap() -> pd.DataFrame:
    """Table 1: trailing-twelve-month cash flows next to signed commitments and backlog."""
    latest = pd.read_csv(OUT / "latest_fundamentals.csv").set_index("ticker")
    commitments = pd.read_csv(OUT / "commitments.csv")
    leases = latest_leases()
    rows = []
    for c in COMPANIES:
        t = c["ticker"]
        f = {k: _value(v) for k, v in latest.loc[t].items() if k.startswith("ttm_") or k == "cash_and_securities"}
        ocf, capex = f["ttm_cash_from_operations"], f["ttm_capex"]
        fcf = _sum(ocf, _neg(capex))
        lease_total = _value(leases.loc[t, "uncommenced_leases"]) if t in leases.index else None
        totals = commitment_totals(t, commitments)
        signed = _sum(lease_total, totals["other_signed_commitments"])
        row = {
            "ticker": t,
            "as_of": latest.loc[t, "as_of"],
            "ttm_operating_cash_flow": ocf,
            "ttm_capex": capex,
            "free_cash_flow": fcf,
            "capex_pct_of_operating_cash_flow": _ratio(capex, ocf),
            "ttm_finance_lease_principal": f["ttm_finance_lease_principal"],
            "ttm_buybacks": f["ttm_buybacks"],
            "ttm_dividends": f["ttm_dividends"],
            "cash_after_capex_leases_and_payouts": _sum(
                fcf, _neg(f["ttm_finance_lease_principal"]), _neg(f["ttm_buybacks"]), _neg(f["ttm_dividends"])
            ),
            "ttm_debt_issued": f["ttm_debt_issued"],
            "ttm_debt_repaid": f["ttm_debt_repaid"],
            "net_debt_issued": _sum(f["ttm_debt_issued"], _neg(f["ttm_debt_repaid"])),
            "cash_and_securities": f["cash_and_securities"],
            "uncommenced_leases": lease_total,
            "leases_as_of": leases.loc[t, "period_end"] if t in leases.index else "",
            **totals,
            "total_signed_commitments": signed,
            "commitments_in_years_of_operating_cash_flow": _ratio(signed, ocf),
            "backlog_per_dollar_of_commitments": _ratio(totals["contracted_backlog"], signed),
        }
        row["not_disclosed"] = "; ".join(k for k, v in row.items() if v is None)
        rows.append(row)
    return pd.DataFrame(rows)


def capex_history(gap: pd.DataFrame) -> pd.DataFrame:
    """Table 2: capex / operating cash flow by fiscal year, then the TTM point."""
    annual = pd.read_csv(OUT / "financials.csv")
    annual = annual[annual.fiscal_year >= HISTORY_FROM]
    rows = []
    for _, r in annual.iterrows():
        rows.append(dict(ticker=r.ticker, period=f"FY{int(r.fiscal_year)}", period_end=r.period_end, basis="fiscal year",
                         capex=_value(r.capex), operating_cash_flow=_value(r.cash_from_operations)))
    for _, r in gap.iterrows():
        if r.as_of in set(annual[annual.ticker == r.ticker].period_end):
            continue  # the latest filing is a 10-K, so the fiscal year already is the TTM
        rows.append(dict(ticker=r.ticker, period="TTM", period_end=r.as_of, basis="trailing twelve months",
                         capex=_value(r.ttm_capex), operating_cash_flow=_value(r.ttm_operating_cash_flow)))
    out = pd.DataFrame(rows)
    out["capex_pct_of_operating_cash_flow"] = [_ratio(c, o) for c, o in zip(map(_value, out.capex), map(_value, out.operating_cash_flow))]
    out["not_disclosed"] = ["; ".join(k for k in ("capex", "operating_cash_flow") if pd.isna(r[k])) for _, r in out.iterrows()]
    order = {c["ticker"]: i for i, c in enumerate(COMPANIES)}
    return out.sort_values(["ticker", "period_end"], key=lambda s: s.map(order) if s.name == "ticker" else s).reset_index(drop=True)


def capital_charge(capex: float, equipment_share: float, equipment_life: float, required_return: float, margin: float) -> dict:
    """Yearly revenue one year of capex has to produce to pay for itself."""
    equipment = capex * equipment_share
    buildings = capex - equipment
    depreciation = equipment / equipment_life + buildings / BUILDINGS_LIFE
    return_on_capital = capex * required_return
    required_profit = depreciation + return_on_capital
    return {
        "annual_depreciation": depreciation,
        "annual_required_return": return_on_capital,
        "required_operating_profit": required_profit,
        "required_revenue": required_profit / margin,
    }


def revenue_a_year_earlier(company: dict, as_of: str) -> float | None:
    """Trailing-twelve-month revenue at the same date one year before, from XBRL facts."""
    d = date.fromisoformat(as_of)
    prior = d.replace(year=d.year - 1, day=min(d.day, 28) if d.month == 2 else d.day).isoformat()
    return fundamentals.ttm(edgar.companyfacts(company["cik"]), fundamentals.FLOWS["revenue"], prior)


def required_revenue() -> pd.DataFrame:
    """Table 3: the capital-charge grid for each company's trailing-twelve-month capex."""
    latest = pd.read_csv(OUT / "latest_fundamentals.csv").set_index("ticker")
    rows = []
    for c in COMPANIES:
        t = c["ticker"]
        as_of = latest.loc[t, "as_of"]
        capex, revenue = _value(latest.loc[t, "ttm_capex"]), _value(latest.loc[t, "ttm_revenue"])
        growth = _sum(revenue, _neg(revenue_a_year_earlier(c, as_of)))
        for share, life, rate, margin in product(EQUIPMENT_SHARES, EQUIPMENT_LIVES, REQUIRED_RETURNS, MARGINS):
            charge = capital_charge(capex, share, life, rate, margin) if capex is not None else {}
            need = charge.get("required_revenue")
            row = {
                "ticker": t,
                "as_of": as_of,
                "ttm_capex": capex,
                "equipment_share": share,
                "equipment_life_years": life,
                "buildings_life_years": BUILDINGS_LIFE,
                "required_return": rate,
                "margin_before_depreciation": margin,
                "annual_depreciation": charge.get("annual_depreciation"),
                "annual_required_return": charge.get("annual_required_return"),
                "required_operating_profit": charge.get("required_operating_profit"),
                "required_revenue": need,
                "ttm_revenue": revenue,
                "required_revenue_pct_of_ttm_revenue": _ratio(need, revenue),
                "ttm_revenue_growth": growth,
                "required_revenue_as_multiple_of_revenue_growth": _ratio(need, growth),
            }
            row["not_disclosed"] = "; ".join(k for k, v in row.items() if v is None)
            rows.append(row)
    return pd.DataFrame(rows)


def _bn(df: pd.DataFrame, money: list[str]) -> pd.DataFrame:
    """Copy of df with the money columns in $ billions, for printing."""
    out = df.copy()
    out[money] = (out[money].astype(float) / 1e9).round(1)
    return out


def main() -> None:
    gap = funding_gap()
    history = capex_history(gap)
    grid = required_revenue()
    OUT.mkdir(parents=True, exist_ok=True)
    gap.to_csv(OUT / "funding_gap.csv", index=False)
    history.to_csv(OUT / "capex_vs_cashflow_history.csv", index=False)
    grid.to_csv(OUT / "required_revenue.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.max_colwidth", 70)
    ratios = ["capex_pct_of_operating_cash_flow", "commitments_in_years_of_operating_cash_flow", "backlog_per_dollar_of_commitments"]
    text_cols = ["as_of", "leases_as_of", "other_commitments_as_of", "backlog_as_of", "not_disclosed"]
    money = [c for c in gap.columns if c not in ratios + text_cols + ["ticker"]]
    show = _bn(gap, money).set_index("ticker")
    show[ratios] = show[ratios].astype(float).round(2)
    print("Trailing twelve months, $bn (NaN = not disclosed, never zero)\n")
    print(show.drop(columns=["not_disclosed"]).T.to_string())
    print("\nNot disclosed:")
    for t, missing in gap.set_index("ticker").not_disclosed.items():
        print(f"  {t}: {missing or '-'}")

    wide = history.pivot(index="period", columns="ticker", values="capex_pct_of_operating_cash_flow")
    print("\nCapex as a share of operating cash flow (fiscal years differ by company)\n")
    print(wide[[c["ticker"] for c in COMPANIES]].astype(float).round(2).to_string())

    mid = grid[(grid[list(MIDDLE)] == pd.Series(MIDDLE)).all(axis=1)].set_index("ticker")
    span = grid.groupby("ticker").required_revenue.agg(["min", "max"])
    summary = pd.DataFrame(
        {
            "ttm_capex": mid.ttm_capex,
            "required_revenue_lowest": span["min"],
            "required_revenue_middle": mid.required_revenue,
            "required_revenue_highest": span["max"],
            "ttm_revenue": mid.ttm_revenue,
            "ttm_revenue_growth": mid.ttm_revenue_growth,
        }
    ).div(1e9).round(1)
    summary["middle_as_multiple_of_growth"] = mid.required_revenue_as_multiple_of_revenue_growth.astype(float).round(2)
    print(f"\nRequired yearly revenue on TTM capex, $bn - a sensitivity grid ({len(grid) // len(COMPANIES)} cases per company), not a forecast")
    print("middle = 60% equipment, 4-year life, 10% return, 40% margin before depreciation\n")
    print(summary.reindex([c["ticker"] for c in COMPANIES]).to_string())


if __name__ == "__main__":
    main()
