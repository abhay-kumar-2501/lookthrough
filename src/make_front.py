"""Build docs/index.html: Lookthrough's front page.

One topic: what a retirement fund has riding on AI's data centers. The page opens with the tool
(pick a fund, type a balance, see how much of it is in the six companies building the data centers
and in the companies selling them equipment), then shows what those six have promised to pay: a
ledger with one bill per company. Each bill opens to show its lines and the filing behind them.
After that come why the bill keeps growing and the author's read. Charts stay folded away until
the reader asks for them. NVIDIA's guarantees are a separate companion page, not part of this one.

The figures are not recomputed here. They are taken from the evidence pages' payloads
(make_spenders.py and make_nvidia.py), so the front page cannot disagree with the evidence behind it.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

import edgar
import fund_holdings
import make_nvidia
import make_spenders
import site_shell

OUT = edgar.ROOT / "data" / "processed"
INPUTS = edgar.ROOT / "inputs"
ORDER = ["sp500", "total_us", "target_2060", "target_2050", "target_2040", "target_2030", "nasdaq100", "total_world", "equal_weight_500", "tech_sector", "semiconductors"]
TIER2 = {"pct_microsoft": "Microsoft", "pct_alphabet": "Alphabet", "pct_amazon": "Amazon", "pct_meta_platforms": "Meta", "pct_oracle": "Oracle", "pct_coreweave": "CoreWeave"}
NOT_A_HOLDING = {"STIV"}  # cash a fund holds as collateral for shares it has lent out; not an investment choice


holding_key = fund_holdings.issuer_key  # one key per company, however a fund spells it


def top_holdings(rows: pd.DataFrame, n: int = 25) -> list[dict]:
    """A fund's largest holdings, with each company's lines added together."""
    merged: dict[str, dict] = {}
    for h in rows.itertuples():
        k = holding_key(h.name)
        m = merged.setdefault(k, {"k": k, "name": re.sub(r"\s+(class|cl)\.?\s+[a-z]\b\.?$", "", str(h.name).strip(), flags=re.I).rstrip("."), "pct": 0.0, "tier": None})
        m["pct"] += float(h.pct_net_assets)
        if not pd.isna(h.ai_tier):
            m["tier"] = int(h.ai_tier)
    return sorted(merged.values(), key=lambda m: -m["pct"])[:n]


def _num(x):
    return None if x is None or pd.isna(x) else float(x)


def funds_payload() -> list[dict]:
    exposure = pd.read_csv(OUT / "fund_ai_exposure.csv").set_index("fund_key")
    info = pd.read_csv(INPUTS / "funds.csv").set_index("fund_key")
    top = pd.read_csv(OUT / "fund_top_holdings.csv")
    top = top[~top.asset_category.isin(NOT_A_HOLDING)]
    out = []
    for key in ORDER:
        if key not in exposure.index:
            continue
        e, i = exposure.loc[key], info.loc[key]
        holdings = top[top.fund_key == key].sort_values("rank")
        out.append(
            {
                "key": key,
                "name": i.display_name,
                "tickers": str(i.example_tickers),
                "what": i.what_it_is,
                "as_of": e.as_of,
                "nvidia": float(e.pct_nvidia),
                "customers": float(e.pct_tier2),
                "other_ai": float(e.pct_tier3),
                "by_customer": {name: float(e[col]) for col, name in TIER2.items()},
                "stocks": _num(e.pct_stocks),
                "n_holdings": int(e.n_holdings),
                "n_companies": int(e.n_companies),
                "n_ai": int(e.n_ai_companies),
                "fund_of_funds": bool(isinstance(e.as_of_underlying, str) and e.as_of_underlying.strip()),
                "top10": _num(e.pct_top10),
                "effective_n": _num(e.effective_number_of_holdings),
                "top": top_holdings(holdings),
            }
        )
    return out


def fund_tickers() -> list[dict]:
    """Tickers a visitor might type, each mapped to one of the fund types on the page.

    match is "same_fund" (a share class of the fund whose holdings are shown), "same_index"
    (a different fund tracking the same index) or "similar" (a rough guide; the note says how it differs).
    """
    t = pd.read_csv(INPUTS / "fund_tickers.csv", keep_default_na=False)
    return [{"t": r.ticker.upper(), "key": r.fund_key, "match": r.match, "name": r.fund_name, "note": r.note} for r in t.itertuples()]


def ai_names() -> list[dict]:
    names = pd.read_csv(INPUTS / "ai_names.csv")
    names = names[(names.tier == 3) & ~names.reason.str.startswith("Same company")]
    return [{"company": r.company.split(" (")[0], "reason": r.reason} for r in names.itertuples()]


def argument_payload(site: dict, nvda: dict) -> dict:
    """The slices of the evidence pages' data that the front page quotes or draws."""
    return {
        "names": site["names"],
        "latest_filing": max(site["latest_filing"], nvda["summary"]["filed"]),  # the newest filing any figure rests on
        "leases": {"series": site["leases"]["series"], "latest": site["leases"]["latest"], "n_figures": site["leases"]["n_figures"]},
        "pv": site["pv"],
        "funding": {"rows": site["funding"]["rows"], "history": site["funding"]["history"]},
        "sources_uses": site["sources_uses"],
        "leverage": site["leverage"],
        # the companion page's headline only: the front page links to it and does not tell its story
        "nvidia": {"narrow": nvda["summary"]["narrow"], "filed": nvda["summary"]["filed"]},
    }


def ledger_totals(argument: dict) -> dict:
    """The six bills added together: what the front page's headline quotes."""
    lev = argument["leverage"]
    t = {k: sum(r[k] for r in lev) for k in ("debt", "leases", "signed", "ebitda")}
    t["total"] = t["debt"] + t["leases"] + t["signed"]
    return t


def description(argument: dict) -> str:
    """The sentence shown under the title when the address is pasted somewhere."""
    t = ledger_totals(argument)
    return (f"Pick the fund in your 401(k) or IRA and see how much of it is in the six companies building AI's data centers, "
            f"and what those six have promised to pay: ${t['total'] / 1e12:.1f} trillion. Every figure comes from an SEC filing.")


def rent_share_in_words(t: dict) -> str:
    """How much of the total is rent, for sentences: only a phrase the figure supports."""
    share = (t["leases"] + t["signed"]) / t["total"]
    if 0.655 <= share <= 0.70:
        return "two thirds"
    if 0.60 <= share < 0.655:
        return "nearly two thirds"
    return f"{share * 100:.0f}%"


def build_payload() -> dict:
    site, nvda = make_spenders.build_payload(), make_nvidia.build_payload()
    return {
        "generated": date.today().isoformat(),
        "funds": funds_payload(),
        "tickers": fund_tickers(),
        "other_ai_names": ai_names(),
        "argument": argument_payload(site, nvda),
    }


def main() -> None:
    payload = build_payload()
    asof = pd.Timestamp(payload["argument"]["latest_filing"]).strftime("%-d %B %Y")
    html = site_shell.render(
        "index.html",
        site_shell.SITE_NAME,
        description(payload["argument"]),
        f"Built from SEC filings · latest read {asof}",
        payload,
        card_title="How much of your retirement fund is riding on AI's data centers?",
    )
    site_shell.write("index.html", html)
    sp = next(f for f in payload["funds"] if f["key"] == "sp500")
    print(f"S&P 500 fund: {sp['nvidia'] + sp['customers'] + sp['other_ai']:.1f}% in AI-linked names as of {sp['as_of']}")


if __name__ == "__main__":
    main()
