"""Step 1: build the two input tables the model needs, straight from EDGAR.

  data/processed/financials.csv     one row per company per fiscal year
  data/processed/server_assets.csv  gross "servers & network equipment" by year

Fiscal years are labelled by the calendar year in which they end
(Microsoft FY2026 ends June 2026, Oracle FY2026 ends May 2026).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

import pandas as pd

import edgar
import xbrl
from universe import COMPANIES

OUT = edgar.ROOT / "data" / "processed"
FIRST_YEAR = 2012

# companyfacts tags, in order of preference, for each line item we need.
TAGS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "operating_income": ["OperatingIncomeLoss"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "net_income": ["NetIncomeLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "diluted_shares": ["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndOther",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ],
    # Depreciation of property and equipment only (no intangibles amortization).
    "depreciation": ["Depreciation"],
    "cash_from_operations": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
}


def _annual(facts: dict, tag: str) -> dict[str, float]:
    """Full-fiscal-year values for one tag: {period_end: value}, latest filing wins."""
    node = facts["facts"].get("us-gaap", {}).get(tag)
    if not node:
        return {}
    best: dict[str, tuple[str, float]] = {}
    for unit_vals in node["units"].values():
        for f in unit_vals:
            if not f.get("form", "").startswith("10-K") or "start" not in f:
                continue
            days = (date.fromisoformat(f["end"]) - date.fromisoformat(f["start"])).days
            if not 350 <= days <= 380:
                continue
            if f["end"] not in best or f["filed"] > best[f["end"]][0]:
                best[f["end"]] = (f["filed"], f["val"])
    return {end: v for end, (_, v) in best.items()}


def build_financials() -> pd.DataFrame:
    rows = []
    for c in COMPANIES:
        facts = edgar.companyfacts(c["cik"])
        year_ends = sorted({f["period"] for f in edgar.filings(c["cik"], forms=("10-K",))})
        series = {}
        for item, tags in TAGS.items():
            merged: dict[str, float] = {}
            for tag in tags:  # earlier tags take priority; later ones only fill gaps
                for end, val in _annual(facts, tag).items():
                    merged.setdefault(end, val)
            series[item] = merged
        for end in year_ends:
            if int(end[:4]) < FIRST_YEAR:
                continue
            row = {"ticker": c["ticker"], "fiscal_year": int(end[:4]), "period_end": end}
            row.update({item: series[item].get(end) for item in TAGS})
            rows.append(row)
    df = pd.DataFrame(rows)
    # Fallbacks where a company does not tag the line directly.
    df["pretax_income"] = df["pretax_income"].fillna(df["net_income"] + df["income_tax"])
    df["diluted_shares"] = df["diluted_shares"].fillna(df["net_income"] / df["eps_diluted"])
    df["effective_tax_rate"] = (df["income_tax"] / df["pretax_income"]).clip(0, 0.35)
    return df


# ---------------------------------------------------------------------------
# Gross servers & network equipment, from each 10-K's PP&E footnote.
#
# Every company labels this asset class differently, and some changed their
# labels over time. Each rule below says: for fiscal years in [first, last],
# take the fact with this concept and this dimension member, times `scale`.
# scale != 1 marks an ESTIMATE - see README "Where the asset base is estimated".
# ---------------------------------------------------------------------------
PPE = r"PropertyPlantAndEquipment(Gross|AndFinanceLeaseRightOfUseAssetBeforeAccumulatedDepreciationAndAmortization)"
# Alphabet's FY2025 10-K: "As of December 31, 2024 and 2025, approximately 60% of technical
# infrastructure assets were comprised of servers and network equipment."
GOOGL_SERVER_SHARE = 0.60
# Before 2024 Alphabet reported "information technology assets" ($80.6bn at end-2023), which also
# held corporate IT. Rescale that series so end-2023 equals 60% of technical infrastructure ($112.5bn).
GOOGL_PRE_2024_SCALE = GOOGL_SERVER_SHARE * 112.504 / 80.6
AMZN_SERVER_SHARE = 113.156 / 218.893  # servers & networking / total equipment, 31 Dec 2024

ASSET_RULES = {
    "MSFT": [dict(first=2012, last=2100, concept="ComputerHardwareAndSoftware", member=None, scale=1.0,
                  label="Servers, network equipment, and software")],
    "ORCL": [dict(first=2012, last=2100, concept="MachineryAndEquipmentGross", member=None, scale=1.0,
                  label="Computer, network, machinery and equipment")],
    "META": [
        dict(first=2012, last=2019, concept=PPE, member="ComputerEquipmentMember", scale=1.0, label="Network equipment"),
        dict(first=2020, last=2020, concept=PPE, member="NetworkEquipmentMember", scale=1.0, label="Network equipment"),
        dict(first=2021, last=2021, concept=PPE, member="ServersAndNetworkAssetsMember", scale=1.0,
             label="Servers and network assets"),
        dict(first=2022, last=2100, concept=PPE, member="ServersAndNetworkAssetsComponentsStoredBySuppliersMember",
             scale=1.0, label="Servers and network assets"),
    ],
    "GOOGL": [
        dict(first=2012, last=2023, concept=PPE, member="TechnologyEquipmentMember", scale=GOOGL_PRE_2024_SCALE,
             label="Information technology assets, rescaled to the 2024 basis (estimate)"),
        dict(first=2024, last=2100, concept=PPE, member="TechnicalInfrastructureMember", scale=GOOGL_SERVER_SHARE,
             label="Technical infrastructure x 60% (share disclosed in the 10-K)"),
    ],
    "AMZN": [
        dict(first=2012, last=2017, concept=PPE, member="EquipmentAndInternalUseSoftwareMember", scale=AMZN_SERVER_SHARE,
             label="Equipment x 2024 server share (estimate)"),
        dict(first=2018, last=2023, concept=PPE, member="EquipmentMember", scale=AMZN_SERVER_SHARE,
             label="Equipment x 2024 server share (estimate)"),
        dict(first=2024, last=2100, concept=PPE, member="ServersAndNetworkingEquipmentMember", scale=1.0,
             label="Servers and networking equipment"),
    ],
    "CRWV": [dict(first=2012, last=2100, concept=PPE, member="TechnologyEquipmentMember", scale=1.0,
                  label="Technology equipment")],
}


def load_facts(ticker: str, cik: int) -> pd.DataFrame:
    """All dimensional facts from every 10-K since FIRST_YEAR.

    Parsing ~15 large XBRL files per company is slow, so the result is cached,
    keyed by the list of filings: a newly filed 10-K changes the key and
    triggers a rebuild.
    """
    filings = [f for f in edgar.filings(cik, forms=("10-K",)) if f["period"] >= f"{FIRST_YEAR}-01-01"]
    key = hashlib.sha1("|".join(sorted(f["accession"] for f in filings)).encode()).hexdigest()[:10]
    cache = edgar.RAW / f"facts10k_{ticker}_{key}.pkl"
    if cache.exists():
        return pd.read_pickle(cache)
    parts = []
    for f in filings:
        df = xbrl.filing_facts(cik, f)
        if not df.empty:
            df["period"] = f["period"]
            parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    out.to_pickle(cache)
    return out


def build_server_assets() -> pd.DataFrame:
    rows = []
    for c in COMPANIES:
        t = c["ticker"]
        facts = xbrl.numeric(load_facts(t, c["cik"]))
        facts = facts[(facts.form == "10-K") & facts.start.isna()]
        year_end_months = {p[5:7] for p in facts.period.unique()}
        for rule in ASSET_RULES[t]:
            sel = facts[facts.concept.str.fullmatch(rule["concept"])]
            if rule["member"] is None:
                sel = sel[sel.dims == ""]
            else:  # exactly one dimension, whose member is the one we want
                sel = sel[sel.dims.str.fullmatch(rf"[A-Za-z]+Axis={re.escape(rule['member'])}")]
            # Balance-sheet dates that are fiscal year-ends inside this rule's range. Each 10-K
            # also carries the prior year-end as a comparative, which fills years with no 10-K
            # of their own (CoreWeave 2024) and picks up reclassified figures.
            sel = sel[sel.end.str[5:7].isin(year_end_months)]
            sel = sel[sel.end.str[:4].astype(int).between(rule["first"], rule["last"])]
            for end, grp in sel.groupby("end"):
                pick = grp.sort_values("filed").iloc[-1]  # most recently filed value wins
                rows.append(
                    {
                        "ticker": t,
                        "fiscal_year": int(end[:4]),
                        "period_end": end,
                        "gross_server_assets": pick.value * rule["scale"],
                        "reported_value": pick.value,
                        "scale": round(rule["scale"], 4),
                        "is_estimate": rule["scale"] != 1.0,
                        "line_item": rule["label"],
                        "source_accession": pick.accession,
                    }
                )
    df = pd.DataFrame(rows)
    # Balances that exist only in non-XBRL filings (e.g. an IPO prospectus), entered by hand.
    manual = pd.read_csv(edgar.ROOT / "inputs" / "manual_asset_balances.csv")
    manual = manual.assign(reported_value=manual.gross_server_assets, scale=1.0, is_estimate=False,
                           source_accession=manual.source).drop(columns="source")
    df = pd.concat([df, manual], ignore_index=True).drop_duplicates(["ticker", "fiscal_year"])
    return df.sort_values(["ticker", "fiscal_year"]).reset_index(drop=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fin = build_financials()
    fin.to_csv(OUT / "financials.csv", index=False)
    assets = build_server_assets()
    assets.to_csv(OUT / "server_assets.csv", index=False)
    print(f"financials.csv: {len(fin)} rows | server_assets.csv: {len(assets)} rows")


if __name__ == "__main__":
    main()
