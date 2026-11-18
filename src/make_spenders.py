"""Build docs/spenders.html: the evidence behind the first three findings.

The six big AI spenders: what they have promised (leases signed but not started), what
that is worth today, whether their own cash covers it, how the gap is being funded, how
much debt each carries once the signed leases are counted, and who is on the other side.
Two appendices sit at the end: the server-life question and the scan of every other filer.

`build_payload()` is also imported by make_front.py, which quotes the headline figures.
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd

import edgar
import site_shell
from universe import COMPANIES

OUT = edgar.ROOT / "data" / "processed"
INPUTS = edgar.ROOT / "inputs"
DOCS = edgar.ROOT / "docs"
FIRST_LEASE_QUARTER = "2022Q4"
NAMES = {c["ticker"]: c["name"] for c in COMPANIES}


def calendar_quarter(ticker: str, period_end: str) -> str:
    """Calendar quarter label. Oracle's quarters end a month early (Aug 31 -> Q3)."""
    ts = pd.Timestamp(period_end)
    if ticker == "ORCL":
        ts = ts + pd.offsets.MonthEnd(1)
    return f"{ts.year}Q{ts.quarter}"


def _num(x):
    """JSON-safe number: NaN/None -> None."""
    return None if x is None or pd.isna(x) else float(x)


def _text(x) -> str:
    return "" if x is None or (isinstance(x, float) and pd.isna(x)) else str(x)


def sensitivity_payload() -> list[dict]:
    scen = pd.read_csv(OUT / "scenarios.csv")
    policy = pd.read_csv(INPUTS / "useful_life_policy.csv")
    assets = pd.read_csv(OUT / "server_assets.csv")
    out = []
    for c in COMPANIES:
        t = c["ticker"]
        s = scen[scen.ticker == t]
        fy = int(s.fiscal_year.max())
        latest = s[s.fiscal_year == fy].sort_values("life_years")
        first = latest.iloc[0]
        out.append(
            {
                "ticker": t,
                "name": c["name"],
                "fiscal_year": fy,
                "policy_life": float(first.policy_life),
                "net_income": float(first.net_income_reported),
                "operating_income": float(first.operating_income_reported),
                "eps": float(first.eps_reported),
                "asset_estimated": bool(assets[(assets.ticker == t) & (assets.fiscal_year == fy)].is_estimate.iloc[0]),
                "by_life": [
                    {
                        "life": float(r.life_years),
                        "extra_dep": float(r.extra_depreciation),
                        "low": float(r.extra_depreciation_low),
                        "high": float(r.extra_depreciation_high),
                        "switch_now": _num(r.switch_now_extra_depreciation),
                        "new_share": _num(r.current_year_share),
                        "eps_restated": float(r.eps_restated),
                    }
                    for r in latest.itertuples()
                ],
                "policy": [
                    {"from": int(r.from_fiscal_year), "life": float(r.life_years), "basis": r.basis, "evidence": r.evidence}
                    for r in policy[(policy.ticker == t) & (policy.applies_to.fillna("all") == "all")]
                    .sort_values("from_fiscal_year")
                    .itertuples()
                ],
            }
        )
    return out


def lease_payload() -> dict:
    leases = pd.read_csv(OUT / "uncommenced_leases.csv").dropna(subset=["uncommenced_leases"]).copy()
    leases["quarter"] = [calendar_quarter(t, p) for t, p in zip(leases.ticker, leases.period_end)]
    quarters = sorted(q for q in leases.quarter.unique() if q >= FIRST_LEASE_QUARTER)
    own = leases.pivot_table(index="quarter", columns="ticker", values="uncommenced_leases", aggfunc="last")
    own = own.reindex(sorted(leases.quarter.unique()))
    # A quarter with no disclosure carries the last disclosed figure, for at most three quarters
    # (Oracle did not disclose every quarter before fiscal 2025).
    grid = own.ffill(limit=3)
    # Never show a quarter until every company that has started reporting has filed for it:
    # otherwise the newest bar would mix one fresh figure with five stale ones.
    started = own.notna().cummax()
    complete = (own.notna() | ~started).all(axis=1)
    last_complete = complete[complete].index.max()
    quarters = [q for q in quarters if q <= last_complete]
    grid = grid.reindex(quarters)
    series = [{"quarter": q, "values": {t: _num(grid.loc[q, t]) for t in grid.columns}} for q in quarters]
    latest = []
    for c in COMPANIES:
        l = leases[(leases.ticker == c["ticker"]) & (leases.quarter <= last_complete)].sort_values("period_end")
        last = l.iloc[-1]
        cutoff = str((pd.Timestamp(last.period_end) - pd.DateOffset(months=11, days=15)).date())
        year_ago = l[l.period_end <= cutoff]
        latest.append(
            {
                "ticker": c["ticker"],
                "name": c["name"],
                "period_end": last.period_end,
                "form": last.form,
                "value": float(last.uncommenced_leases),
                "year_ago": float(year_ago.iloc[-1].uncommenced_leases) if not year_ago.empty else None,
                "evidence": last.evidence[:400],
                "url": last.url,
            }
        )
    return {"series": series, "latest": latest, "n_figures": int(len(leases)), "latest_filing": str(leases.filed.max())}


def present_value_payload() -> dict:
    pv = pd.read_csv(OUT / "lease_pv.csv")
    check = pd.read_csv(OUT / "lease_method_check.csv")
    rows = [
        {
            "ticker": r.ticker,
            "undiscounted": float(r.undiscounted),
            "low": float(r.pv_low),
            "base": float(r.pv_base),
            "high": float(r.pv_high),
            "rate": float(r.discount_rate_base),
            "term": float(r.term_base),
            "annual_rent": float(r.annual_rent_base),
            "debt": float(r.debt),
            "existing_leases": float(r.existing_lease_liabilities),
            "cash": float(r.cash_and_securities),
            "ttm_operating_income": _num(r.ttm_operating_income),
            "ttm_cfo": _num(r.ttm_cash_from_operations),
        }
        for r in pv.itertuples()
    ]
    return {
        "rows": rows,
        "check": {"n": int(len(check)), "mean_abs": float(check.error_pct.abs().mean()), "max_abs": float(check.error_pct.abs().max())},
    }


def funding_payload() -> dict:
    f = pd.read_csv(OUT / "funding_gap.csv")
    h = pd.read_csv(OUT / "capex_vs_cashflow_history.csv")
    c = pd.read_csv(OUT / "commitments.csv")
    rows = [
        {
            "ticker": x.ticker,
            "cfo": _num(x.ttm_operating_cash_flow),
            "capex": _num(x.ttm_capex),
            "fcf": _num(x.free_cash_flow),
            "capex_share": _num(x.capex_pct_of_operating_cash_flow),
            "leases": _num(x.uncommenced_leases),
            "other": _num(x.other_signed_commitments),
            "total": _num(x.total_signed_commitments),
            "years": _num(x.commitments_in_years_of_operating_cash_flow),
            "backlog": _num(x.contracted_backlog),
            "net_debt_issued": _num(x.net_debt_issued),
            "cash": _num(x.cash_and_securities),
        }
        for x in f.itertuples()
    ]
    h = h[h.period_end >= "2019-01-01"]
    history = {
        t: [{"period": x.period, "share": _num(x.capex_pct_of_operating_cash_flow)} for x in g.sort_values("period_end").itertuples()]
        for t, g in h.groupby("ticker")
    }
    items = [
        {
            "ticker": x.ticker,
            "as_of": x.as_of,
            "kind": x.kind,
            "item": _text(x.item),
            "amount": _num(x.amount),
            "due_12m": _num(x.due_within_12_months),
            "in_total": bool(x.in_total),
            "evidence": _text(x.evidence)[:420],
            "url": _text(x.url),
        }
        for x in c.itertuples()
    ]
    return {"rows": rows, "history": history, "items": items}


def counterparties_payload() -> list[dict]:
    c = pd.read_csv(INPUTS / "counterparties.csv")
    return [
        {
            "id": x.id,
            "tenant": _text(x.tenant),
            "end_user": _text(x.end_user),
            "landlord": _text(x.landlord_or_provider),
            "site": _text(x.site),
            "announced": _text(x.announced),
            "value": _num(x.contract_value_usd_bn),
            "term": _num(x.term_years),
            "mw": _num(x.capacity_mw),
            "financing": _text(x.financing),
            "lenders": _text(x.lenders_or_investors),
            "guarantee": _text(x.tenant_guarantee),
            "guarantee_bn": _num(x.guarantee_amount_usd_bn),
            "cross": str(x.is_cross_deal_between_tracked_companies).lower() == "true",
            "url": _text(x.source_url),
            "confidence": _text(x.confidence),
            "notes": _text(x.notes),
        }
        for x in c.itertuples()
    ]


def market_payload() -> dict | None:
    path = OUT / "market_scan.csv"
    if not path.exists():
        return None
    m = pd.read_csv(path)
    m = m[m.verified.astype(str).str.lower() == "yes"] if (m.verified.astype(str).str.lower() == "yes").any() else m
    m = m.sort_values("uncommenced_leases_usd", ascending=False).head(25)
    return {
        "rows": [
            {
                "company": x.company,
                "ticker": _text(x.ticker),
                "period_end": x.period_end,
                "value": float(x.uncommenced_leases_usd),
                "what_for": _text(x.what_for),
                "url": _text(x.url),
            }
            for x in m.itertuples()
        ]
    }


def validation_payload() -> dict:
    val = pd.read_csv(OUT / "validation.csv")
    fit = pd.read_csv(OUT / "retire_lag_fit.csv")
    used = val[val.in_validation]
    return {
        "rows": [
            {
                "ticker": r.ticker,
                "fiscal_year": int(r.fiscal_year),
                "change": r.change,
                "basis": r.basis,
                "disclosed": float(r.disclosed_bn),
                "modeled": float(r.modeled_bn),
                "error": float(r.error_pct),
                "used": bool(r.in_validation),
            }
            for r in val.itertuples()
        ],
        "fit": {
            "retire_lag": float(val.retire_lag.iloc[0]),
            "mean_abs_error": float(used.error_pct.abs().mean()),
            "max_abs_error": float(used.error_pct.abs().max()),
            "n": int(len(used)),
            "no_retirement_error": float(fit[fit.retire_lag == 99].mean_abs_error_pct.iloc[0]),
        },
    }


def leverage_payload() -> list[dict]:
    lev = pd.read_csv(OUT / "lease_adjusted_leverage.csv")
    return [
        {
            "ticker": r.ticker,
            "ebitda": _num(r.ebitda_ttm),
            "debt": _num(r.debt),
            "leases": _num(r.leases_on_balance_sheet),
            "cash": _num(r.cash_and_securities),
            "signed": _num(r.signed_leases_pv_base),
            "today": _num(r.leverage_today),
            "pro_forma": _num(r.leverage_pro_forma),
            "pro_forma_low": _num(r.leverage_pro_forma_low),
            "pro_forma_high": _num(r.leverage_pro_forma_high),
            "net_today": _num(r.net_leverage_today),
            "net_pro_forma": _num(r.net_leverage_pro_forma),
        }
        for r in lev.itertuples()
    ]


def sources_uses_payload() -> list[dict]:
    su = pd.read_csv(OUT / "sources_and_uses.csv")
    return [
        {
            "ticker": r.ticker,
            "cfo": _num(r.operating_cash_flow),
            "capex": _num(r.capital_spending),
            "fcf": _num(r.free_cash_flow),
            "payouts": _num(r.paid_to_shareholders),
            "raised": _num(r.debt_raised),
            "repaid": _num(r.debt_repaid),
            "shares": _num(r.shares_sold),
        }
        for r in su.itertuples()
    ]


def required_revenue_payload() -> dict:
    """What one year of capital spending has to earn back, for three server lives.

    The middle of the sensitivity grid in funding_gap.py: 60% of spending on equipment,
    an 8% return, and half of each new revenue dollar left after running costs.
    """
    r = pd.read_csv(OUT / "required_revenue.csv")
    r = r[(r.equipment_share == 0.6) & (r.required_return == 0.08) & (r.margin_before_depreciation == 0.5)]
    return {
        "assumptions": {"equipment_share": 0.6, "required_return": 0.08, "margin": 0.5, "buildings_life": int(r.buildings_life_years.iloc[0])},
        "lives": sorted(int(x) for x in r.equipment_life_years.unique()),
        "rows": [
            {"ticker": x.ticker, "life": int(x.equipment_life_years), "capex": _num(x.ttm_capex), "needed": _num(x.required_revenue), "revenue": _num(x.ttm_revenue),
             "share_of_revenue": _num(x.required_revenue_pct_of_ttm_revenue), "times_growth": _num(x.required_revenue_as_multiple_of_revenue_growth)}
            for x in r.itertuples()
        ],
    }


def build_payload() -> dict:
    prior = pd.read_csv(INPUTS / "prior_work.csv")
    scen = pd.read_csv(OUT / "scenarios.csv")
    leases = lease_payload()
    return {
        "generated": date.today().isoformat(),
        "latest_filing": leases["latest_filing"],
        "names": NAMES,
        "companies": sensitivity_payload(),
        "lives": sorted(scen.life_years.unique().tolist()),
        "leases": leases,
        "pv": present_value_payload(),
        "funding": funding_payload(),
        "sources_uses": sources_uses_payload(),
        "leverage": leverage_payload(),
        "required": required_revenue_payload(),
        "counterparties": counterparties_payload(),
        "market": market_payload(),
        "validation": validation_payload(),
        "prior": prior.fillna("").to_dict("records"),
    }


def main() -> None:
    payload = build_payload()
    asof = pd.Timestamp(payload["latest_filing"]).strftime("%-d %B %Y")
    html = site_shell.render(
        "spenders.html",
        "Evidence: the six big AI spenders",
        "What six companies have promised to spend on AI data centers, what it is worth today, how it is being funded and who can carry it. Every figure links to its filing.",
        f"Latest filing read: {asof}",
        payload,
    )
    site_shell.write("spenders.html", html)
    total = sum(r["value"] for r in payload["leases"]["latest"])
    print(f"Leases signed but not started: ${total / 1e9:,.1f}bn")


if __name__ == "__main__":
    main()
