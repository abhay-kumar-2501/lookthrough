"""Build docs/index.html: the argument on one page.

The page opens with a tool (pick a fund, type a balance, see how much of it sits in the
companies selling AI equipment and the companies paying for it), then makes one argument
in four findings. Each finding shows its number and one sentence; its chart and sources
stay folded away until the reader asks for them.

The figures are not recomputed here. They are taken from the two evidence pages'
payloads (make_spenders.py and make_nvidia.py), so the front page cannot disagree with
the evidence behind it.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

import edgar
import make_nvidia
import make_spenders
import site_shell

OUT = edgar.ROOT / "data" / "processed"
INPUTS = edgar.ROOT / "inputs"
ORDER = ["sp500", "total_us", "target_2060", "target_2030", "nasdaq100", "total_world", "equal_weight_500", "tech_sector", "semiconductors"]
TIER2 = {"pct_microsoft": "Microsoft", "pct_alphabet": "Alphabet", "pct_amazon": "Amazon", "pct_meta_platforms": "Meta", "pct_oracle": "Oracle", "pct_coreweave": "CoreWeave"}
NOT_A_HOLDING = {"STIV"}  # cash a fund holds as collateral for shares it has lent out; not an investment choice
SUFFIXES = {"inc", "incorporated", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "holdings", "nv", "sa", "ag", "the", "com"}


def holding_key(name: str) -> str:
    """One key per company, however a fund spells it: "NVIDIA Corp" and "NVIDIA Corp." are the same
    holding, and a company's share classes ("Alphabet Inc Class A", "Class C") are one company."""
    words = re.sub(r"[^a-z0-9 ]", " ", str(name).lower().replace("&", " and ")).split()
    out, skip = [], False
    for i, w in enumerate(words):
        if skip:
            skip = False
            continue
        if w in ("class", "cl") and i + 1 < len(words) and len(words[i + 1]) == 1:
            skip = True  # drop "class a"
            continue
        if w not in SUFFIXES:
            out.append(w)
    return " ".join(out) or str(name).lower()


def top_holdings(rows: pd.DataFrame, n: int = 12) -> list[dict]:
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
    """The slices of the evidence pages' data that the four findings quote or draw."""
    history = [{k: v for k, v in c.items() if k != "annual"} for c in nvda["history"]["companies"]]
    return {
        "names": site["names"],
        "latest_filing": max(site["latest_filing"], nvda["summary"]["filed"]),  # the newest filing any figure rests on
        "leases": {"series": site["leases"]["series"], "latest": site["leases"]["latest"], "n_figures": site["leases"]["n_figures"]},
        "pv": site["pv"],
        "funding": {"rows": site["funding"]["rows"], "history": site["funding"]["history"]},
        "sources_uses": site["sources_uses"],
        "leverage": site["leverage"],
        "nvidia": {
            "summary": nvda["summary"],
            "financing": nvda["financing"]["series"],
            "payment_terms": nvda["financing"]["payment_terms"],
            "items": nvda["financing"]["latest_items"],
            "history": history,
        },
    }


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
        "How much of an ordinary index fund depends on AI spending, and how that spending is being paid for: four findings from SEC filings, with a tool to see your own number.",
        f"Built from SEC filings · latest read {asof}",
        payload,
        card_title="AI spending now takes all the cash its biggest builders generate",
    )
    site_shell.write("index.html", html)
    sp = next(f for f in payload["funds"] if f["key"] == "sp500")
    print(f"S&P 500 fund: {sp['nvidia'] + sp['customers'] + sp['other_ai']:.1f}% in AI-linked names as of {sp['as_of']}")


if __name__ == "__main__":
    main()
