"""build_dataset: annual financials from companyfacts and the server asset base, on synthetic data.

These cover the joins the model depends on: fiscal-year labels, which filing wins
when a number is restated, stock splits, and the tax-rate clip.
"""
from __future__ import annotations

import pandas as pd
import pytest

import build_dataset as bd


def fact(start, end, val, filed, form="10-K"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def companyfacts(**tags) -> dict:
    return {"facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}}}


# --------------------------------------------------------------------------- _annual


def test_annual_keeps_full_year_values_from_10k_only():
    facts = companyfacts(
        NetIncomeLoss=[
            fact("2024-07-01", "2025-06-30", 100, "2025-07-30"),
            fact("2025-04-01", "2025-06-30", 30, "2025-07-30"),  # fourth quarter, reported in the 10-K
            fact("2025-07-01", "2025-09-30", 40, "2025-10-29", "10-Q"),
            fact("2025-07-01", "2026-06-30", 140, "2026-07-29"),
            {"end": "2026-06-30", "val": 999, "filed": "2026-07-29", "form": "10-K"},  # instant
        ]
    )
    assert bd._annual(facts, "NetIncomeLoss") == {"2025-06-30": 100, "2026-06-30": 140}


def test_annual_latest_filing_wins_when_a_year_is_restated():
    facts = companyfacts(
        NetIncomeLoss=[
            fact("2024-01-01", "2024-12-31", 100, "2025-02-05"),
            fact("2024-01-01", "2024-12-31", 90, "2026-02-05"),  # comparative column a year later
            fact("2024-01-01", "2024-12-31", 95, "2025-06-01", "10-K/A"),
        ]
    )
    assert bd._annual(facts, "NetIncomeLoss") == {"2024-12-31": 90}


def test_annual_ignores_a_full_year_span_reported_in_a_10q():
    facts = companyfacts(NetIncomeLoss=[fact("2025-10-01", "2026-09-30", 500, "2026-10-30", "10-Q")])
    assert bd._annual(facts, "NetIncomeLoss") == {}


def test_annual_missing_tag():
    assert bd._annual(companyfacts(), "NetIncomeLoss") == {}
    assert bd._annual({"facts": {}}, "NetIncomeLoss") == {}


# --------------------------------------------------------------------------- build_financials

# A June-year-end company that split its stock 20-for-1 during fiscal 2022. The FY2022 10-K
# restates FY2020 and FY2021 per-share figures; FY2019 only ever appears pre-split.
SPLIT_FACTS = companyfacts(
    Revenues=[
        fact("2018-07-01", "2019-06-30", 9000, "2019-08-01"),
        fact("2019-07-01", "2020-06-30", 10000, "2020-08-01"),
        fact("2020-07-01", "2021-06-30", 12000, "2021-08-01"),
        fact("2021-07-01", "2022-06-30", 13000, "2022-08-01"),
    ],
    SalesRevenueNet=[
        fact("2010-07-01", "2011-06-30", 1, "2011-08-01"),
        fact("2018-07-01", "2019-06-30", 1, "2019-08-01"),  # lower-priority tag must not override
    ],
    NetIncomeLoss=[
        fact("2018-07-01", "2019-06-30", 900, "2019-08-01"),
        fact("2019-07-01", "2020-06-30", 1000, "2020-08-01"),
        fact("2020-07-01", "2021-06-30", 1200, "2021-08-01"),
        fact("2021-07-01", "2022-06-30", -500, "2022-08-01"),
    ],
    IncomeTaxExpenseBenefit=[
        fact("2018-07-01", "2019-06-30", 100, "2019-08-01"),  # 10% of 1000
        fact("2019-07-01", "2020-06-30", 1500, "2020-08-01"),  # one-off charge: 60% of 2500
        fact("2020-07-01", "2021-06-30", -200, "2021-08-01"),  # benefit: negative rate
        fact("2021-07-01", "2022-06-30", -300, "2022-08-01"),  # loss year: -300 / -800 = 37.5%
    ],
    EarningsPerShareDiluted=[
        fact("2018-07-01", "2019-06-30", 9.0, "2019-08-01"),
        fact("2019-07-01", "2020-06-30", 10.0, "2020-08-01"),
        fact("2019-07-01", "2020-06-30", 0.5, "2022-08-01"),
        fact("2020-07-01", "2021-06-30", 12.0, "2021-08-01"),
        fact("2020-07-01", "2021-06-30", 0.6, "2022-08-01"),
        fact("2021-07-01", "2022-06-30", -0.25, "2022-08-01"),
    ],
    WeightedAverageNumberOfDilutedSharesOutstanding=[
        fact("2019-07-01", "2020-06-30", 100, "2020-08-01"),
        fact("2019-07-01", "2020-06-30", 2000, "2022-08-01"),
        fact("2020-07-01", "2021-06-30", 100, "2021-08-01"),
        fact("2020-07-01", "2021-06-30", 2000, "2022-08-01"),
        fact("2021-07-01", "2022-06-30", 2000, "2022-08-01"),
    ],
)


@pytest.fixture
def fin(monkeypatch) -> pd.DataFrame:
    filings = [{"form": "10-K", "period": p} for p in ("2011-06-30", "2019-06-30", "2020-06-30", "2021-06-30", "2022-06-30", "2023-06-30")]
    monkeypatch.setattr(bd, "COMPANIES", [{"ticker": "TST", "name": "Test Co", "cik": 1}])
    monkeypatch.setattr(bd.edgar, "companyfacts", lambda cik, refresh=False: SPLIT_FACTS)
    monkeypatch.setattr(bd.edgar, "filings", lambda cik, forms=("10-K",), refresh=False: filings)
    return bd.build_financials().set_index("fiscal_year")


def test_fiscal_year_is_the_calendar_year_in_which_the_year_ends(fin):
    # FY2020 runs July 2019 to June 2020 and is labelled 2020; years before FIRST_YEAR are dropped.
    assert list(fin.index) == [2019, 2020, 2021, 2022, 2023]
    assert fin.loc[2020, "period_end"] == "2020-06-30"
    assert fin.loc[2020, "revenue"] == 10000


def test_earlier_tags_take_priority(fin):
    assert fin.loc[2019, "revenue"] == 9000


def test_eps_and_share_count_are_on_the_same_split_basis(fin):
    # Restated years: both EPS and shares come from the post-split 10-K.
    assert (fin.loc[2020, "eps_diluted"], fin.loc[2020, "diluted_shares"]) == (0.5, 2000)
    assert (fin.loc[2021, "eps_diluted"], fin.loc[2021, "diluted_shares"]) == (0.6, 2000)
    # FY2019 was never restated: it stays pre-split, with shares backed out of EPS.
    assert fin.loc[2019, "eps_diluted"] == 9.0
    assert fin.loc[2019, "diluted_shares"] == pytest.approx(100)
    # Whatever the basis, EPS x shares must reproduce net income in every year.
    have = fin.dropna(subset=["net_income"])
    assert (have.eps_diluted * have.diluted_shares).tolist() == pytest.approx(have.net_income.tolist())


def test_pretax_income_falls_back_to_net_income_plus_tax(fin):
    assert fin.loc[2019, "pretax_income"] == 1000
    assert fin.loc[2022, "pretax_income"] == -800


def test_effective_tax_rate_is_clipped_to_0_35(fin):
    assert fin.loc[2019, "effective_tax_rate"] == pytest.approx(0.10)
    assert fin.loc[2020, "effective_tax_rate"] == pytest.approx(0.35)  # 60% clipped down
    assert fin.loc[2021, "effective_tax_rate"] == 0.0  # negative clipped up
    assert fin.loc[2022, "effective_tax_rate"] == pytest.approx(0.35)  # 37.5% on a loss, clipped


def test_a_10k_missing_from_companyfacts_gives_an_empty_row_not_an_error(fin):
    # What a stale companyfacts cache looks like after a new 10-K appears in the filing list.
    assert pd.isna(fin.loc[2023, "net_income"])
    assert pd.isna(fin.loc[2023, "effective_tax_rate"])


# --------------------------------------------------------------------------- build_server_assets

PPE_GROSS = "PropertyPlantAndEquipmentGross"
BY_TYPE = "PropertyPlantAndEquipmentByTypeAxis"


def xfact(concept, value, end, dims, period, filed, accession, form="10-K", start=None):
    return {
        "prefix": "us-gaap", "concept": concept, "value": str(value), "start": start, "end": end, "dims": dims,
        "unit": "usd", "accession": accession, "filed": filed, "form": form, "period": period,
    }


def run_assets(monkeypatch, tmp_path, ticker, facts, manual_rows=()):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    pd.DataFrame(manual_rows, columns=["ticker", "fiscal_year", "period_end", "gross_server_assets", "line_item", "source"]).to_csv(
        inputs / "manual_asset_balances.csv", index=False
    )
    monkeypatch.setattr(bd.edgar, "ROOT", tmp_path)
    monkeypatch.setattr(bd, "COMPANIES", [{"ticker": ticker, "name": ticker, "cik": 1}])
    monkeypatch.setattr(bd, "load_facts", lambda t, cik: pd.DataFrame(facts))
    return bd.build_server_assets().set_index("fiscal_year")


def rule_for(ticker: str, fiscal_year: int) -> dict:
    return next(r for r in bd.ASSET_RULES[ticker] if r["first"] <= fiscal_year <= r["last"])


def tag(rule: dict) -> tuple[str, str]:
    """A (concept, dims) pair that the rule selects."""
    concept = PPE_GROSS if rule["concept"] == bd.PPE else rule["concept"]
    dims = "" if rule["member"] is None else f"{BY_TYPE}={rule['member']}"
    return concept, dims


def test_server_assets_first_10k_also_supplies_the_prior_year_end(monkeypatch, tmp_path):
    # CoreWeave: one 10-K (FY2025) whose comparative column is the only XBRL source for 2024;
    # 2023 exists only in the prospectus and is entered by hand.
    rule = rule_for("CRWV", 2025)
    concept, dims = tag(rule)
    facts = [
        xfact(concept, 20_903e6, "2025-12-31", dims, "2025-12-31", "2026-03-02", "K25"),
        xfact(concept, 9_146e6, "2024-12-31", dims, "2025-12-31", "2026-03-02", "K25"),
        xfact(concept, 47_023e6, "2026-09-30", dims, "2026-09-30", "2026-11-12", "Q3", form="10-Q"),
        xfact(concept, 5_000e6, "2025-12-31", f"{dims}|RangeAxis=MaximumMember", "2025-12-31", "2026-03-02", "K25"),
        xfact(concept, 7_777e6, "2025-12-31", f"{BY_TYPE}=SomeOtherMember", "2025-12-31", "2026-03-02", "K25"),
        xfact("Depreciation", 2_400e6, "2025-12-31", dims, "2025-12-31", "2026-03-02", "K25", start="2025-01-01"),
    ]
    manual = [("CRWV", 2023, "2023-12-31", 1_298_127_000, "Technology equipment", "Prospectus")]
    got = run_assets(monkeypatch, tmp_path, "CRWV", facts, manual)
    s = rule["scale"]
    assert got.gross_server_assets.to_dict() == pytest.approx({2023: 1_298_127_000, 2024: 9_146e6 * s, 2025: 20_903e6 * s})
    assert got.loc[2024, "source_accession"] == "K25"
    assert got.loc[2023, "source_accession"] == "Prospectus"
    assert got.period_end.to_dict() == {2023: "2023-12-31", 2024: "2024-12-31", 2025: "2025-12-31"}


def test_server_assets_most_recently_filed_value_wins(monkeypatch, tmp_path):
    # A later 10-K reclassifies the prior year-end: the restated comparative replaces the original.
    rule = rule_for("META", 2024)
    assert rule is rule_for("META", 2025) is rule_for("META", 2023)
    concept, dims = tag(rule)
    facts = [
        xfact(concept, 100e9, "2024-12-31", dims, "2024-12-31", "2025-01-30", "K24"),
        xfact(concept, 70e9, "2023-12-31", dims, "2024-12-31", "2025-01-30", "K24"),
        xfact(concept, 150e9, "2025-12-31", dims, "2025-12-31", "2026-01-29", "K25"),
        xfact(concept, 104e9, "2024-12-31", dims, "2025-12-31", "2026-01-29", "K25"),
    ]
    got = run_assets(monkeypatch, tmp_path, "META", facts)
    assert got.reported_value.to_dict() == {2023: 70e9, 2024: 104e9, 2025: 150e9}
    assert got.loc[2024, "source_accession"] == "K25"


def test_server_assets_rules_switch_by_year_and_scales_mark_estimates(monkeypatch, tmp_path):
    old, new = rule_for("GOOGL", 2023), rule_for("GOOGL", 2024)
    if old is new:
        pytest.skip("Alphabet no longer changes line item between 2023 and 2024")
    (c_old, d_old), (c_new, d_new) = tag(old), tag(new)
    facts = [
        xfact(c_old, 80.6e9, "2023-12-31", d_old, "2023-12-31", "2024-01-31", "K23"),
        xfact(c_new, 112.5e9, "2023-12-31", d_new, "2024-12-31", "2025-02-05", "K24"),  # outside the new rule's years
        xfact(c_new, 139.6e9, "2024-12-31", d_new, "2024-12-31", "2025-02-05", "K24"),
    ]
    got = run_assets(monkeypatch, tmp_path, "GOOGL", facts)
    assert list(got.index) == [2023, 2024]
    assert got.loc[2023, "gross_server_assets"] == pytest.approx(80.6e9 * old["scale"])
    assert got.loc[2024, "gross_server_assets"] == pytest.approx(139.6e9 * new["scale"])
    assert got.loc[2024, "reported_value"] == 139.6e9
    for year, rule in ((2023, old), (2024, new)):
        assert bool(got.loc[year, "is_estimate"]) is (rule["scale"] != 1.0)


def test_server_assets_june_year_end_is_labelled_by_the_year_it_ends_in(monkeypatch, tmp_path):
    concept, dims = tag(rule_for("MSFT", 2026))
    facts = [
        xfact(concept, 132_836e6, "2025-06-30", dims, "2025-06-30", "2025-07-30", "K25"),
        xfact(concept, 215_874e6, "2026-06-30", dims, "2026-06-30", "2026-07-29", "K26"),
        xfact(concept, 132_836e6, "2025-06-30", dims, "2026-06-30", "2026-07-29", "K26"),
        xfact(concept, 1e6, "2026-06-30", "SegmentAxis=GamingMember", "2026-06-30", "2026-07-29", "K26"),
        xfact(concept, 240_000e6, "2026-09-30", dims, "2026-09-30", "2026-10-28", "Q1", form="10-Q"),
    ]
    got = run_assets(monkeypatch, tmp_path, "MSFT", facts)
    assert got.reported_value.to_dict() == {2025: 132_836e6, 2026: 215_874e6}
    assert got.period_end.to_dict() == {2025: "2025-06-30", 2026: "2026-06-30"}


def test_server_assets_xbrl_wins_over_a_manual_balance_for_the_same_year(monkeypatch, tmp_path):
    concept, dims = tag(rule_for("CRWV", 2024))
    facts = [xfact(concept, 9_146e6, "2024-12-31", dims, "2024-12-31", "2025-03-01", "K24")]
    manual = [("CRWV", 2024, "2024-12-31", 1.0, "Technology equipment", "typed by hand")]
    got = run_assets(monkeypatch, tmp_path, "CRWV", facts, manual)
    assert got.reported_value.to_dict() == {2024: 9_146e6}
