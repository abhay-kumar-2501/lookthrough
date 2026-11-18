"""Step 8: how much of a retirement fund is the AI bet?

What is Form N-PORT?
  Every US mutual fund and ETF must tell the SEC what it owns. The report is
  called Form N-PORT. It is a structured XML file: one block per holding with
  the security's name, its CUSIP and ISIN (the serial numbers of securities),
  its value in dollars, and its share of the fund's net assets (the fund's
  total value after debts). Funds file every month, but only the third month
  of each fiscal quarter is made public, about 60 days later. So the holdings
  used here are always a few weeks to a few months old.

What this script does
  1. Looks up the newest public N-PORT for each fund in inputs/funds.csv.
  2. Reads every holding. Target-date funds mostly own other funds, so those
     are "looked through": each underlying fund's weight is multiplied by that
     fund's own latest N-PORT holdings to get stock-level weights.
  3. Matches holdings to the AI names in inputs/ai_names.csv (NVIDIA, its six
     biggest customers, and other AI hardware companies) by CUSIP or ISIN
     first, then by exact name. Name-only matches are listed for checking.
  4. Writes data/processed/fund_ai_exposure.csv (one row per fund) and
     data/processed/fund_top_holdings.csv (top 25 holdings per fund).

All weights are percent of the fund's net assets as the fund itself filed
them. Nothing is estimated from memory.
"""
from __future__ import annotations

import re
from datetime import date
import xml.etree.ElementTree as ET

import pandas as pd

import edgar

edgar._MIN_INTERVAL = 0.4  # other processes share the SEC allowance

INPUTS = edgar.ROOT / "inputs"
OUT = edgar.ROOT / "data" / "processed"
SEC = "https://www.sec.gov"
NS = "{http://www.sec.gov/edgar/nport}"
STOCK_CATS = ("EC", "EP")  # N-PORT asset categories: equity-common, equity-preferred
TIER2 = ["Microsoft", "Meta Platforms", "Amazon", "Alphabet", "Oracle", "CoreWeave"]
TOP_N = 25
# Funds that target-date funds own. Equity ones are read holding by holding.
LOOK_THROUGH = {
    "922908355": dict(cik=36405, series="S000002848", kind="us_stock"),    # Total Stock Market Index
    "921909602": dict(cik=736054, series="S000002932", kind="non_us_stock"),  # Total International Stock Index
}


# ---------------------------------------------------------------- finding filings
def latest_nport(series_id: str) -> dict:
    """Newest public NPORT-P for one fund series, via EDGAR's per-series filing feed."""
    url = (f"{SEC}/cgi-bin/browse-edgar?action=getcompany&CIK={series_id}"
           "&type=NPORT-P&dateb=&owner=include&count=10&output=atom")
    feed = edgar.get(url, refresh=True).decode("latin-1")
    entries = re.findall(r"<filing-date>(.*?)</filing-date>.*?<filing-href>(.*?)-index\.htm</filing-href>",
                         feed, re.S)
    if not entries:
        raise RuntimeError(f"no NPORT-P found for {series_id}")
    filed, base = max(entries)  # ISO dates sort correctly
    folder = base.rsplit("/", 1)[0]
    return dict(filed=filed, url=f"{folder}/primary_doc.xml")


# ---------------------------------------------------------------- reading the XML
def _clean_id(value: str | None) -> str:
    value = (value or "").strip().upper()
    return "" if value in ("", "N/A", "NA", "000000000") else value


def _holding(node: ET.Element) -> dict:
    def t(tag: str) -> str:
        return (node.findtext(NS + tag) or "").strip()

    isin = node.find(f"{NS}identifiers/{NS}isin")
    lending = node.find(f"{NS}securityLending")
    cash_collateral = False
    if lending is not None:  # filers use either a plain flag or a "condition" element
        cond = lending.find(NS + "cashCollateralCondition")
        cash_collateral = (lending.findtext(NS + "isCashCollateral") == "Y"
                           or (cond is not None and cond.get("isCashCollateral") == "Y"))
    return dict(
        name=t("name"), cusip=_clean_id(t("cusip")),
        isin=_clean_id(isin.get("value") if isin is not None else ""),
        value_usd=float(t("valUSD") or 0), pct=float(t("pctVal") or 0),
        asset_cat=t("assetCat"), payoff=t("payoffProfile"), country=t("invCountry"),
        cash_collateral=cash_collateral,
    )


def parse_nport(xml: bytes) -> dict:
    """Fund header facts plus every holding from one N-PORT XML document."""
    root = ET.fromstring(xml)
    gen = root.find(f"{NS}formData/{NS}genInfo")
    info = root.find(f"{NS}formData/{NS}fundInfo")
    holdings = [_holding(n) for n in root.iter(NS + "invstOrSec")]
    return dict(
        series_name=gen.findtext(NS + "seriesName"), series_id=gen.findtext(NS + "seriesId"),
        as_of=gen.findtext(NS + "repPdDate"), net_assets=float(info.findtext(NS + "netAssets")),
        holdings=holdings,
    )


def load_fund(series_id: str) -> dict:
    """Fetch and parse the latest N-PORT for a series; record where it came from."""
    ref = latest_nport(series_id)
    fund = parse_nport(edgar.get(ref["url"]))
    if fund["series_id"] != series_id:
        raise RuntimeError(f"{ref['url']} is series {fund['series_id']}, expected {series_id}")
    fund.update(filed=ref["filed"], url=ref["url"])
    return fund


# ---------------------------------------------------------------- matching AI names
def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def load_ai_names() -> pd.DataFrame:
    return pd.read_csv(INPUTS / "ai_names.csv", dtype=str, keep_default_na=False)


def build_matcher(names: pd.DataFrame):
    """Return match(holding) -> (row, method) or None. CUSIP, then ISIN, then exact name."""
    by_cusip = {r.cusip: r for r in names.itertuples() if r.cusip}
    by_isin = {r.isin: r for r in names.itertuples() if r.isin}
    by_name = {}
    for r in names.itertuples():
        by_name.setdefault(_norm(r.filing_name), r)

    def match(h: dict):
        if h["asset_cat"] not in STOCK_CATS:
            return None
        if h["cusip"] in by_cusip:
            return by_cusip[h["cusip"]], "cusip"
        if h["isin"] in by_isin:
            return by_isin[h["isin"]], "isin"
        if _norm(h["name"]) in by_name:
            return by_name[_norm(h["name"])], "name"
        return None

    return match


# ---------------------------------------------------------------- fund-of-funds
def _fund_line_category(name: str) -> str:
    """Label an underlying fund by its own name; never opened, so only a label."""
    if re.search(r"bond|inflation|treasury|income", name, re.I):
        return "BOND_FUND"
    return "OTHER_FUND"


def expand(fund: dict, cache: dict, used: list) -> list:
    """Holdings of a fund with underlying equity funds replaced by their own holdings.

    Each underlying holding's weight = (fund's weight in that underlying) x
    (the underlying's weight in the holding). Underlying bond funds stay as one line.
    """
    lines = []
    is_fof = any(h["cusip"] in LOOK_THROUGH for h in fund["holdings"])
    for h in fund["holdings"]:
        spec = LOOK_THROUGH.get(h["cusip"])
        if spec is not None:
            if spec["series"] not in cache:
                cache[spec["series"]] = load_fund(spec["series"])
            under = cache[spec["series"]]
            used.append(under)
            for u in under["holdings"]:
                pct = h["pct"] / 100 * u["pct"]
                lines.append(dict(u, pct=pct, value_usd=pct / 100 * fund["net_assets"],
                                  held_via=under["series_name"].title()))
        else:
            cat = h["asset_cat"]
            if is_fof and cat == "EC" and re.search(r"\bfund\b", h["name"], re.I):
                cat = _fund_line_category(h["name"])
            lines.append(dict(h, asset_cat=cat, held_via=""))
    return lines


def merge_lines(lines: list) -> list:
    """Add up lines that are the same security (same ISIN, CUSIP or name)."""
    merged = {}
    for h in lines:
        key = h["isin"] or h["cusip"] or h["name"]
        if key in merged:
            merged[key]["pct"] += h["pct"]
            merged[key]["value_usd"] += h["value_usd"]
        else:
            merged[key] = dict(h)
    return list(merged.values())


# ---------------------------------------------------------------- numbers per fund
def _slug(company: str) -> str:
    return "pct_" + re.sub(r"[^a-z0-9]+", "_", company.lower()).strip("_")


def ai_weights(lines: list, match) -> tuple:
    """Tag each line with its AI name and sum weights by tier and company."""
    by_company, by_tier, name_only = {}, {"1": 0.0, "2": 0.0, "3": 0.0}, []
    for h in lines:
        hit = match(h)
        h["ai_tier"], h["ai_company"], h["match_method"] = "", "", ""
        if hit is None:
            continue
        row, method = hit
        h["ai_tier"], h["ai_company"], h["match_method"] = row.tier, row.company, method
        by_tier[row.tier] += h["pct"]
        by_company[row.company] = by_company.get(row.company, 0.0) + h["pct"]
        if method == "name":
            name_only.append(h["name"])
    return by_company, by_tier, name_only


def flags_for(fund: dict, lines: list, today: date) -> str:
    notes = []
    age = (today - date.fromisoformat(fund["as_of"])).days
    if age > 150:
        notes.append(f"older than five months ({age} days)")
    collateral = sum(h["pct"] for h in lines if h["cash_collateral"])
    if collateral:
        notes.append(f"securities-lending cash collateral {collateral:.2f}%")
    deriv = [h for h in lines if h["asset_cat"].startswith("D")]
    if deriv:
        notes.append(f"{len(deriv)} derivative lines (futures/swaps/forwards), net {sum(h['pct'] for h in deriv):.3f}%")
    cash = sum(h["pct"] for h in lines if h["asset_cat"] in ("STIV", "RA", "RE"))
    if cash:
        notes.append(f"cash-like/money-market/repo {cash:.2f}%")
    if any(h["payoff"] == "Short" for h in lines):
        notes.append("has short positions")
    return "; ".join(notes)


def fund_row(spec: pd.Series, fund: dict, lines: list, used: list, names: pd.DataFrame, match, today: date):
    """One row of fund_ai_exposure.csv plus its sorted merged lines."""
    merged = sorted(merge_lines(lines), key=lambda h: -h["pct"])
    by_company, by_tier, name_only = ai_weights(merged, match)
    weights = [h["pct"] / 100 for h in merged]
    stocks = sum(h["pct"] for h in merged if h["asset_cat"] in STOCK_CATS)
    total = sum(h["pct"] for h in merged)
    row = dict(
        fund_key=spec.fund_key, display_name=spec.display_name, as_of=fund["as_of"], n_holdings=len(fund["holdings"]),
        pct_nvidia=by_tier["1"], pct_tier2=by_tier["2"],
    )
    for company in TIER2:
        row[_slug(company)] = by_company.get(company, 0.0)
    row.update(
        pct_tier3=by_tier["3"], pct_ai_total=sum(by_tier.values()), pct_top10=sum(h["pct"] for h in merged[:10]),
        effective_number_of_holdings=1 / sum(w * w for w in weights), pct_stocks=stocks,
        pct_bonds_and_other=total - stocks, pct_sum_check=total,
        as_of_underlying="; ".join(f"{u['series_name'].title()} {u['as_of']}" for u in used),
        filed=fund["filed"], name_only_matches="; ".join(sorted(set(name_only))),
        flags=flags_for(fund, lines, today),
        source_urls=" ".join([fund["url"]] + [u["url"] for u in used]),
    )
    return row, merged


def top_rows(key: str, merged: list) -> list:
    return [
        dict(fund_key=key, rank=i, name=h["name"], cusip=h["cusip"], isin=h["isin"], value_usd=round(h["value_usd"], 2),
             pct_net_assets=h["pct"], asset_category=h["asset_cat"], held_via=h["held_via"], ai_tier=h["ai_tier"],
             ai_company=h["ai_company"], match_method=h["match_method"])
        for i, h in enumerate(merged[:TOP_N], 1)
    ]


# ---------------------------------------------------------------- main
def main() -> None:
    today = date.today()
    funds = pd.read_csv(INPUTS / "funds.csv", dtype=str, keep_default_na=False)
    names = load_ai_names()
    match = build_matcher(names)
    cache, rows, tops, notes = {}, [], [], []
    for spec in funds.itertuples():
        fund = load_fund(spec.series_id)
        cache[spec.series_id] = fund
        used: list = []
        lines = expand(fund, cache, used)
        row, merged = fund_row(pd.Series(spec._asdict()), fund, lines, used, names, match, today)
        rows.append(row)
        tops.extend(top_rows(spec.fund_key, merged))
        notes.append((spec.fund_key, fund["series_name"], fund["as_of"], fund["filed"], row["pct_sum_check"], row["flags"]))
    OUT.mkdir(parents=True, exist_ok=True)
    expo = pd.DataFrame(rows)
    expo.to_csv(OUT / "fund_ai_exposure.csv", index=False)
    pd.DataFrame(tops).to_csv(OUT / "fund_top_holdings.csv", index=False)
    show = expo[["fund_key", "as_of", "pct_nvidia", "pct_tier2", "pct_tier3", "pct_ai_total", "pct_top10",
                 "effective_number_of_holdings", "pct_stocks", "pct_sum_check"]]
    print(show.round(2).to_string(index=False))
    for key, sname, as_of, filed, total, flag in notes:
        print(f"{key}: {sname} as of {as_of} (filed {filed}); weights sum {total:.2f}%; {flag or 'no flags'}")
    sp = pd.DataFrame(tops).query("fund_key == 'sp500'").head(10)
    print("\nS&P 500 fund, top 10 holdings:")
    print(sp[["rank", "name", "pct_net_assets"]].round(2).to_string(index=False))
    print("\nMatched by name only:", "; ".join(f"{r.fund_key}: {r.name_only_matches}" for r in expo.itertuples()
                                              if r.name_only_matches) or "none")


if __name__ == "__main__":
    main()
