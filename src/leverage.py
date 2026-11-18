"""Who can carry it: debt against earnings, before and after the signed leases are counted.

The lease totals are large, but large against what? A credit analyst's first ratio is
debt to EBITDA (earnings before interest, tax, depreciation and amortisation): how many
years of today's cash earnings it would take to repay what is owed.

  today      = (borrowings + leases already on the balance sheet) / EBITDA
  pro forma  = (the same + present value of leases signed but not yet started) / EBITDA

EBITDA = trailing-twelve-month operating income + depreciation and amortisation (the cash-flow
statement's total, or depreciation plus amortisation of intangible assets where it gives two lines).

Read with care:
* EBITDA is held at today's level. The leased data centers are meant to bring in new
  revenue, so the pro forma figure is the load IF earnings did not grow. It is a stress
  reading, not a forecast.
* Reported operating income is already after rent on operating leases, so adding those
  leases to debt makes the ratio slightly harsher than a rent-adjusted (EBITDAR) version.
  Depreciation and amortization covers property, equipment and intangibles for every company;
  Amazon's broader cash-flow line (which adds back leased-asset and content amortization) is
  not used, so the six are on one footing.
* Cash is not netted off. Net figures are given alongside, because some of these companies
  hold more cash than debt. The net figures leave out holdings a company is barred from selling
  (Alphabet's SpaceX shares), since those cannot pay a bill today.
* The signed leases are valued at each company's current borrowing cost (see lease_pv.py); the
  value at its older lease-book rate is carried alongside.
* The present value has a range (see lease_pv.py), so pro forma leverage does too.

Also written here: sources and uses of cash for the same twelve months, which answers
"where did the outside money come from?" from the cash-flow statements: debt raised and
repaid, and new shares sold.
"""
from __future__ import annotations

import pandas as pd

import edgar

OUT = edgar.ROOT / "data" / "processed"


def _f(x):
    return None if x is None or pd.isna(x) else float(x)


def _ratio(a, b):
    return None if a is None or b is None or b <= 0 else a / b


def leverage_table(fundamentals: pd.DataFrame, pv: pd.DataFrame) -> pd.DataFrame:
    pv = pv.set_index("ticker")
    rows = []
    for f in fundamentals.itertuples():
        if f.ticker not in pv.index:
            continue
        p = pv.loc[f.ticker]
        op, dep = _f(f.ttm_operating_income), _f(f.ttm_depreciation_and_amortization)
        ebitda = None if op is None or dep is None else op + dep
        debt = _f(f.debt) or 0.0
        leases = (_f(f.operating_lease_liability) or 0.0) + (_f(f.finance_lease_liability) or 0.0)
        cash = _f(f.cash_and_securities) or 0.0
        locked = _f(getattr(f, "cash_it_cannot_sell_yet", 0.0)) or 0.0  # e.g. shares it holds but may not sell yet
        spendable = cash - locked
        today = debt + leases
        row = {
            "ticker": f.ticker,
            "as_of": f.as_of,
            "ebitda_ttm": ebitda,
            "debt": debt,
            "leases_on_balance_sheet": leases,
            "obligations_today": today,
            "cash_and_securities": cash,
            "cash_it_cannot_sell_yet": locked,
            "signed_leases_pv_at_book_rate": float(p.get("pv_base_at_book_rate", p.pv_base)),
            "discount_rate_base": _f(p.get("discount_rate_base")),
            "discount_rate_book": _f(p.get("discount_rate_book")),
            "discount_rate_source": p.get("discount_rate_source", ""),
            "depreciation_basis": getattr(f, "depreciation_basis", ""),
            "lease_figures_as_of": getattr(f, "finance_lease_liability_as_of", f.as_of),
            "lease_rate_as_of": getattr(f, "lease_rate_as_of", f.as_of),
            "signed_leases_pv_low": float(p.pv_low),
            "signed_leases_pv_base": float(p.pv_base),
            "signed_leases_pv_high": float(p.pv_high),
            "leverage_today": _ratio(today, ebitda),
            "leverage_pro_forma_low": _ratio(today + float(p.pv_low), ebitda),
            "leverage_pro_forma": _ratio(today + float(p.pv_base), ebitda),
            "leverage_pro_forma_high": _ratio(today + float(p.pv_high), ebitda),
            "net_leverage_today": _ratio(today - spendable, ebitda),
            "net_leverage_pro_forma": _ratio(today + float(p.pv_base) - spendable, ebitda),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def sources_and_uses(funding: pd.DataFrame, fundamentals: pd.DataFrame, notes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Where twelve months of cash came from and went, per company. Missing items stay empty, never zero.

    Debt raised and repaid are the LONG-TERM lines of each cash-flow statement. Short-term borrowing that is
    drawn and repaid within the year (Amazon about $23bn each way, Oracle's commercial paper) is left out,
    because it would inflate both columns without changing what the company owes.
    """
    fund = fundamentals.set_index("ticker")
    sold = fund.ttm_shares_sold if "ttm_shares_sold" in fund else pd.Series(dtype=float)
    leased = fund.ttm_finance_lease_additions if "ttm_finance_lease_additions" in fund else pd.Series(dtype=float)
    prepaid = pd.Series(dtype=float)
    if notes is not None:  # customer prepayments a company counts inside cash from operations, hand-read from its statements
        prepaid = notes[notes["item"] == "customer_prepayments_in_operating_cash"].groupby("ticker").amount_usd.sum()
    rows = []
    for f in funding.itertuples():
        payouts = [_f(f.ttm_buybacks), _f(f.ttm_dividends)]
        rows.append(
            {
                "ticker": f.ticker,
                "as_of": f.as_of,
                "operating_cash_flow": _f(f.ttm_operating_cash_flow),
                "capital_spending": _f(f.ttm_capex),
                "free_cash_flow": _f(f.free_cash_flow),
                "paid_to_shareholders": None if all(x is None for x in payouts) else sum(x or 0.0 for x in payouts),
                "debt_raised": _f(f.ttm_debt_issued),
                "debt_repaid": _f(f.ttm_debt_repaid),
                "shares_sold": _f(sold.get(f.ticker)),
                "assets_added_under_finance_leases": _f(leased.get(f.ticker)),
                "customer_prepayments_in_operating_cash": _f(prepaid.get(f.ticker)),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    lev = leverage_table(pd.read_csv(OUT / "latest_fundamentals.csv"), pd.read_csv(OUT / "lease_pv.csv"))
    lev.to_csv(OUT / "lease_adjusted_leverage.csv", index=False)
    su = sources_and_uses(pd.read_csv(OUT / "funding_gap.csv"), pd.read_csv(OUT / "latest_fundamentals.csv"), pd.read_csv(edgar.ROOT / "inputs" / "ledger_notes.csv"))
    su.to_csv(OUT / "sources_and_uses.csv", index=False)
    for r in lev.itertuples():
        print(f"{r.ticker:6s} debt+leases / EBITDA: {r.leverage_today:5.1f}x today -> {r.leverage_pro_forma:5.1f}x with signed leases ({r.leverage_pro_forma_low:.1f}x to {r.leverage_pro_forma_high:.1f}x)")
    tot = su.sum(numeric_only=True)
    print(f"Six together: operating cash ${tot.operating_cash_flow / 1e9:,.0f}bn, capital spending ${tot.capital_spending / 1e9:,.0f}bn, "
          f"paid to shareholders ${tot.paid_to_shareholders / 1e9:,.0f}bn, debt raised ${tot.debt_raised / 1e9:,.0f}bn, repaid ${tot.debt_repaid / 1e9:,.0f}bn, "
          f"new shares sold ${tot.shares_sold / 1e9:,.0f}bn")


if __name__ == "__main__":
    main()
