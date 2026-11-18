"""Build docs/nvidia.html: the evidence behind the fourth finding, the supplier's side.

  1. Support: guarantees, investment promises, stakes and capacity NVIDIA rents back from
     customers and partners (nvidia_financing.py), split into promised and in force.
  2. Getting paid: how long customers take to pay, and the payment terms it now offers.
  3. Then and now: the same measures for telecom equipment makers in 1997-2003, from
     their filings (vendor_finance_history.py), including the path after the peak.
  4. Its own orders: what NVIDIA has committed to buy from its suppliers (nvidia_supply.py).

One denominator is used throughout: the latest quarter's sales times four. NVIDIA is
growing fast, so sales over the last twelve months would understate its current size and
make every ratio look larger. The telecom peaks for Lucent and Motorola are measured the
same way.

`build_payload()` is also imported by make_front.py, which quotes the headline figures.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

import edgar
import make_spenders
import site_shell

OUT = edgar.ROOT / "data" / "processed"
DOCS = edgar.ROOT / "docs"


def _num(x):
    return None if x is None or pd.isna(x) else float(x)


def near_term_years(r) -> float | None:
    """Supply commitments falling due in roughly the next twelve months, in years of cost.

    Older filings give the share due within twelve months directly. Newer ones
    give the rest of the current fiscal year and the next fiscal year, so the
    next twelve months is the first plus a pro-rated part of the second.
    """
    cost = _num(r.cost_of_revenue_ttm)
    if not cost:
        return None
    share = _num(r.share_due_next_12_months)
    if share is not None and _num(r.commitments_years_of_cost_of_revenue) is not None:
        return share * r.commitments_years_of_cost_of_revenue
    rest, nxt, total = _num(r.due_rest_of_fiscal_year), _num(r.due_next_fiscal_year), _num(r.due_total)
    years = _num(r.commitments_years_of_cost_of_revenue)
    if rest is None or nxt is None or not total or years is None:
        return None
    end = pd.Timestamp(r.period_end)
    months_left = (1 - end.month) % 12 or 12  # NVIDIA's fiscal year ends in late January
    # In some years the due-date schedule covers all purchase commitments, not only supply.
    # Use it for the SHARE falling due, and apply that share to the supply figure, so the
    # near-term number can never exceed the total.
    share = min(1.0, (rest + nxt * (12 - months_left) / 12) / total)
    return share * years


def supply_payload() -> dict:
    s = pd.read_csv(OUT / "nvidia_supply.csv").sort_values("period_end")
    series = [
        {
            "period_end": r.period_end,
            "form": r.form,
            "commitments": _num(r.supply_commitments),
            "years": _num(r.commitments_years_of_cost_of_revenue),
            "near_years": near_term_years(r),
            "years_run_rate": _num(r.commitments_years_of_latest_quarter_cost),
            "gross_margin": _num(r.gross_margin),
            "provisions_share": _num(r.provisions_share_of_revenue),
            "growth": _num(r.revenue_growth_year_on_year),
            "source": r.source if isinstance(r.source, str) else "",
        }
        for r in s.itertuples()
    ]
    for p in series:  # the part due within about a year, restated on the same run-rate basis
        ok = p["near_years"] is not None and p["years"] and p["years_run_rate"] is not None
        p["near_years_run_rate"] = p["near_years"] * p["years_run_rate"] / p["years"] if ok else None
    table = pd.read_csv(OUT / "nvidia_commitments_table.csv")
    latest = table[(table.period_end == table.period_end.max()) & (table.table == "commitments")]
    rows = []
    for name, grp in latest.groupby("row", sort=False):
        rows.append({"row": name, "buckets": {b.bucket: _num(b.amount) for b in grp.itertuples()}, "url": grp.url.iloc[0]})
    buckets = list(dict.fromkeys(latest.bucket))
    return {"series": series, "table": {"as_of": table.period_end.max(), "buckets": buckets, "rows": rows}, "peers": peers_payload(),
            "latest_filed": str(s.filed.dropna().max())}


def peers_payload() -> list[dict]:
    """Latest purchase commitments at two other chip designers. Definitions differ, so this is context, not a ranking."""
    path = OUT / "nvidia_supply_peers.csv"
    if not path.exists():
        return []
    p = pd.read_csv(path).sort_values("period_end").groupby("ticker").tail(1)
    names = {"AVGO": "Broadcom", "AMD": "AMD"}
    return [
        {"company": names.get(r.ticker, r.ticker), "period_end": r.period_end, "commitments": _num(r.purchase_commitments),
         "years": _num(r.commitments_years_of_cost_of_revenue), "includes": str(r.includes), "url": r.url}
        for r in p.itertuples()
    ]


def financing_payload() -> dict:
    f = pd.read_csv(OUT / "nvidia_financing_summary.csv").sort_values("period_end")
    series = []
    for r in f.itertuples():
        guarantees = _num(r.guarantees_max_exposure) or 0.0
        sb = _num(r.guarantees_sb_energy_cap) or 0.0
        series.append(
            {
                "period_end": r.period_end,
                "form": r.form,
                "revenue_ttm": _num(r.revenue_ttm),
                "revenue_quarter": _num(r.revenue_quarter),
                "revenue_annualized": _num(r.revenue_quarter) * 4,
                "guarantees_other": guarantees - sb,
                "guarantee_2029": sb,  # the Ohio campus guarantee: not yet in effect, first phase expected in 2028
                "unfunded_equity": _num(r.equity_investment_commitments) or 0.0,
                "equity_stakes": _num(r.equity_stakes_carrying_value) or 0.0,
                "capacity": (_num(r.capacity_buyback_commitments) or 0.0) + (_num(r.leases_not_commenced_for_third_parties) or 0.0),
                "narrow": _num(r.narrow_support),
                "broad": _num(r.broad_support),
                "dso": _num(r.days_sales_outstanding),
                "receivables": _num(r.accounts_receivable),
                "stretch": _num(r.receivables_stretch),  # receivables above 45 days of sales, NVIDIA's level in its tightest quarters
                "top_share": _num(r.receivables_top_customers_share),
                "top_count": _num(r.receivables_top_customers_count),
            }
        )
    # One quarterly report (July 2025) did not break out capacity agreements. Leaving the
    # bar empty would look like the agreements vanished, so the previous quarter's figure is
    # offered in a separate field for the chart to draw paler. The data itself is not altered.
    for i, p in enumerate(series):
        p["capacity_carried"] = 0.0
        if i and p["capacity"] == 0 and series[i - 1]["capacity"] > 0 and i + 1 < len(series) and series[i + 1]["capacity"] > 0:
            p["capacity_carried"] = series[i - 1]["capacity"]
    evidence = pd.read_csv(OUT / "nvidia_customer_financing.csv")
    latest = evidence[(evidence.period_end == evidence.period_end.max()) & evidence.amount.notna() & (evidence.unit == "USD")]
    keep = ["guarantees_sb_energy_cap", "guarantees_power_and_systems", "guarantees_land_power_shell", "equity_investment_commitments",
            "nonmarketable_equity_securities", "public_equity_securities", "ai_cloud_agreements", "cloud_service_agreements", "accounts_receivable"]
    items = [
        {"item": r.item, "amount": float(r.amount), "evidence": str(r.evidence)[:380], "url": r.url}
        for r in latest.itertuples()
        if r.item in keep
    ]
    items.sort(key=lambda x: keep.index(x["item"]))
    terms = evidence[evidence.item.isin(["extended_payment_terms", "days_sales_outstanding_reported"])].sort_values("period_end")
    said = [{"period_end": r.period_end, "evidence": str(r.evidence)[:420], "url": r.url}
            for r in terms.groupby("item").tail(1).sort_values("period_end").itertuples()]
    return {"series": series, "latest_items": items, "as_of": f.period_end.max(), "payment_terms": said}


def history_payload() -> dict:
    """Each telecom maker at the date its commitments to customers peaked."""
    v = pd.read_csv(OUT / "vendor_finance_history.csv")
    annual = v[v.period_type == "annual"]
    companies = []
    for name, grp in v.groupby("company"):
        if not grp.financing_made_available.notna().any():
            continue
        peak = grp.loc[grp.financing_made_available.idxmax()]
        high = grp.loc[grp.available_to_revenue.idxmax()]
        top = grp.loc[grp.drawn_plus_guarantees_to_revenue.idxmax()] if grp.drawn_plus_guarantees_to_revenue.notna().any() else None
        a = annual[annual.company == name].sort_values("fiscal_year")
        url = ""
        inputs = pd.read_csv(edgar.ROOT / "inputs" / "vendor_finance_2000.csv")
        src = inputs[(inputs.company == name) & (inputs.fiscal_period_end == peak.fiscal_period_end) & inputs.url.notna()]
        if not src.empty:
            url = src.url.iloc[0]
        companies.append(
            {
                "company": name,
                "peak_date": peak.fiscal_period_end,
                "peak_available": _num(peak.financing_made_available) * 1e6,
                "peak_ratio": _num(peak.available_to_revenue),
                "peak_drawn": (_num(peak.drawn_plus_guarantees) or 0) * 1e6,
                "peak_drawn_ratio": _num(peak.drawn_plus_guarantees_to_revenue),
                "commitments_complete": "guarantee" in str(peak.made_available_basis),  # False = a component was not disclosed, so a minimum
                "charges_share": _num(grp.charges_share_of_peak.max()),
                "narrow_charges_share": _num(grp.narrow_charges_share_of_peak.max()),
                "peak_dso": _num(grp.dso_days.max()),
                "url": url,
                "high_promised": _num(high.available_to_revenue),  # the highest share of sales its promises reached, whenever that was
                "high_promised_date": high.fiscal_period_end,
                "high_promised_complete": "guarantee" in str(high.made_available_basis),
                "peak_in_force_usd": _num(top.drawn_plus_guarantees) * 1e6 if top is not None else None,
                "peak_in_force_ratio": _num(grp.drawn_plus_guarantees_to_revenue.max()),
                "peak_in_force_date": grp.loc[grp.drawn_plus_guarantees_to_revenue.idxmax()].fiscal_period_end if grp.drawn_plus_guarantees_to_revenue.notna().any() else None,
                "peak_reserve_share": _num(grp.reserve_share_of_drawn.max()),
                "annual": [
                    {"year": int(r.fiscal_year), "available": _num(r.available_to_revenue), "drawn": _num(r.drawn_plus_guarantees_to_revenue), "dso": _num(r.dso_days)}
                    for r in a.itertuples()
                ],
                "path": [
                    {"date": r.fiscal_period_end, "promised": _num(r.available_to_revenue), "in_force": _num(r.drawn_plus_guarantees_to_revenue),
                     "in_force_usd": None if _num(r.drawn_plus_guarantees) is None else _num(r.drawn_plus_guarantees) * 1e6,
                     "dso": _num(r.dso_days), "reserved": _num(r.reserve_share_of_drawn)}
                    for r in grp.sort_values("fiscal_period_end").itertuples()
                    # Cisco's year-end figure includes its finance leases; its quarterly reports give
                    # only part of it, so mixing the two would draw a zigzag that is not in the data.
                    if not (name.startswith("Cisco") and r.period_type != "annual")
                ],
            }
        )
    companies.sort(key=lambda c: -(c["peak_ratio"] or 0))
    return {"companies": companies}


def customers_payload() -> dict:
    """The buyers' side, from the ledger. Years of cash flow are per company, never summed."""
    site = make_spenders.build_payload()
    rows = site["funding"]["rows"]
    years = sorted(r["years"] for r in rows if r["years"] is not None)
    return {
        "years_low": years[0],
        "years_high": years[-1],
        "capex_share_group": sum(r["capex"] for r in rows) / sum(r["cfo"] for r in rows),
        "over_100": [site["names"][r["ticker"]] for r in rows if r["capex_share"] and r["capex_share"] > 1],
        "n": len(rows),
    }


def summary(supply: dict, fin: dict) -> dict:
    """Headline figures for the front page and the README."""
    s = [x for x in supply["series"] if x["years"] is not None]
    last, f_last = s[-1], fin["series"][-1]
    target = pd.Timestamp(f_last["period_end"]) - pd.DateOffset(years=1)
    year_ago = min(fin["series"][:-1], key=lambda x: abs((pd.Timestamp(x["period_end"]) - target).days))
    peak_2022 = max((x for x in s if x["period_end"] < "2023-01-01"), key=lambda x: x["years"])
    rev = f_last["revenue_annualized"]
    return {
        "as_of": last["period_end"],
        "supply_commitments": last["commitments"],
        "supply_years": last["years"],
        "supply_near_years": last["near_years"],
        "supply_years_2022_peak": peak_2022["years"],
        "supply_near_years_2022_peak": peak_2022["near_years"],
        "narrow": f_last["narrow"],
        "narrow_year_ago": year_ago["narrow"],
        "narrow_ex_2029": f_last["narrow"] - f_last["guarantee_2029"],
        "guarantees_in_effect": f_last["guarantees_other"],
        "narrow_share": f_last["narrow"] / rev,
        "in_effect_share": f_last["guarantees_other"] / rev,
        "broad": f_last["broad"],
        "broad_share": f_last["broad"] / rev,
        "dso": f_last["dso"],
        "supply_years_run_rate": last["years_run_rate"],
        "supply_near_years_run_rate": last["near_years_run_rate"],
        "supply_years_run_rate_2022_peak": peak_2022["years_run_rate"],
        "dso_two_quarters_ago": fin["series"][-3]["dso"],
        "dso_year_ago": year_ago["dso"],
        "receivables_top_share": f_last.get("top_share"),
        "receivables_top_count": f_last.get("top_count"),
        "filed": supply.get("latest_filed"),
        "receivables": f_last["receivables"],
        "receivables_stretch": f_last["stretch"],
        "equity_stakes": f_last["equity_stakes"],
    }


def build_payload() -> dict:
    supply, fin = supply_payload(), financing_payload()
    return {
        "generated": date.today().isoformat(),
        "supply": supply,
        "financing": fin,
        "history": history_payload(),
        "customers": customers_payload(),
        "summary": summary(supply, fin),
    }


def main() -> None:
    payload = build_payload()
    sm = payload["summary"]
    asof = pd.Timestamp(sm["as_of"]).strftime("%-d %B %Y")
    html = site_shell.render(
        "nvidia.html",
        "Evidence: NVIDIA and its customers",
        "What NVIDIA has promised its customers and partners, what is actually in force, how long it waits to be paid, and the same measures for the telecom equipment makers of 1997-2003.",
        f"Figures to {asof}",
        payload,
    )
    site_shell.write("nvidia.html", html)
    print(f"Promised {sm['narrow_share'] * 100:.0f}% of annualised sales, in force {sm['in_effect_share'] * 100:.1f}%; supply {sm['supply_years_run_rate']:.1f} years at the current pace")


if __name__ == "__main__":
    main()
