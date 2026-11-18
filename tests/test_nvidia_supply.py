"""nvidia_supply: sentence and table parsing, trailing-year arithmetic, ratios, and the committed CSV."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import nvidia_supply as ns

PROCESSED_SUPPLY = "nvidia_supply.csv"


# --------------------------------------------------------------------------- fiscal calendar


@pytest.mark.parametrize(
    "period_end, expected",
    [
        ("2019-01-27", (2019, 4)),
        ("2019-04-28", (2020, 1)),
        ("2021-05-02", (2022, 1)),  # a first quarter can end in early May
        ("2024-07-28", (2025, 2)),
        ("2024-08-01", (2025, 2)),
        ("2024-10-27", (2025, 3)),
        ("2021-10-31", (2022, 3)),
        ("2021-01-31", (2021, 4)),  # a fourth quarter can end on 31 January
    ],
)
def test_fiscal_year_and_quarter(period_end, expected):
    assert ns.fiscal(period_end) == expected


# --------------------------------------------------------------------------- supply commitment sentences


def test_definition_a_million_with_everything_due_in_twelve_months():
    text = ("We repurchased $5.0 billion of stock. As of January 26, 2020 , we had outstanding inventory purchase obligations "
            "totaling $1.16 billion , which are expected to occur over the next 12 months. Cash was $10.0 billion.")
    hit = ns.supply_commitment(text)
    assert hit["definition"] == "A_inventory_purchase_obligations"
    assert hit["amount"] == 1_160_000_000
    assert hit["due12"] == hit["amount"]  # "all expected over the next 12 months"


def test_definition_a_million_not_billion_and_no_due_split():
    text = "As of October 27, 2019 , we had outstanding inventory purchase obligations totaling $980 million."
    hit = ns.supply_commitment(text)
    assert hit["amount"] == 980_000_000
    assert hit["due12"] is None


def test_definition_b_picks_the_total_not_the_twelve_month_part():
    text = ("As of July 28, 2024 , we had outstanding inventory purchase and long-term supply commitment obligations totaling "
            "$27.8 billion , of which $21.9 billion is expected to occur over the next 12 months.")
    hit = ns.supply_commitment(text)
    assert hit["definition"] == "B_plus_long_term_supply"
    assert hit["amount"] == 27_800_000_000
    assert hit["due12"] == 21_900_000_000


def test_definition_b_second_wording_with_unpaid_prefix():
    text = ("We have entered into several long-term supply agreements, under which we have made advance payments and have "
            "$2.9 billion remaining unpaid. As of January 26, 2025 , we had outstanding inventory purchase and long-term supply "
            "obligations totaling $30.8 billion.")
    hit = ns.supply_commitment(text)
    assert hit["amount"] == 30_800_000_000
    assert hit["unpaid"] == 2_900_000_000


def test_definition_c_capacity_wording_wins_over_nothing():
    text = "As of October 26, 2025 , we had outstanding inventory purchase and long-term supply and capacity obligations totaling $50.3 billion."
    hit = ns.supply_commitment(text)
    assert hit["definition"] == "C_plus_capacity"
    assert hit["amount"] == 50_300_000_000


def test_definition_d_reads_the_second_sentence_and_the_remainder_of_year_figure():
    text = ("Manufacturing, supply, and capacity commitments reflect our obligations to foundries and memory makers. "
            "Our other obligations were $1.0 billion. "
            "As of April 26, 2026, these commitments were $119 billion for which $95 billion will be paid in the remainder of fiscal year 2027 and the rest later.")
    hit = ns.supply_commitment(text)
    assert hit["definition"] == "D_manufacturing_supply_capacity"
    assert hit["amount"] == 119_000_000_000
    assert hit["first"] == 95_000_000_000


def test_definition_e_table_row_is_in_billions_and_takes_the_last_cell_as_total():
    text = ("Future commitments by fiscal year as of July 26, 2026 , were as follows: Remainder of 2027 2028 2029 2030 2031 "
            "2032 and thereafter Total (In billions) Supply and capacity $92 $100 $50 $10 $— $27 $279")
    hit = ns.supply_commitment(text)
    assert hit["definition"] == "E_supply_and_capacity_row"
    assert hit["amount"] == 279e9
    assert hit["first"] == 92e9 and hit["second"] == 100e9


def test_newer_wording_beats_older_when_both_appear():
    text = ("As of January 26, 2025 , we had outstanding inventory purchase obligations totaling $1.0 billion. "
            "As of January 26, 2025 , we had outstanding inventory purchase and long-term supply and capacity obligations totaling $9.0 billion.")
    assert ns.supply_commitment(text)["amount"] == 9_000_000_000


def test_no_commitment_sentence_returns_none():
    assert ns.supply_commitment("We repurchased $5.0 billion of stock in the quarter.") is None


def test_evidence_text_is_tidied():
    text = "As of October 27, 2019 , we had outstanding inventory purchase obligations totaling $ 980 million ."
    ev = ns.supply_commitment(text)["evidence"]
    assert "$980 million" in ev and "$ 980" not in ev


# --------------------------------------------------------------------------- other sentence parsers


def test_prepaid_short_term_reads_the_footnote_amount_not_the_table_cells():
    text = ("Prepaid supply and capacity agreements (1) $ 2,458 $ 3,664 Other 100 200 Total other assets 3,000 4,000 "
            "(1) Prepaid supply and capacity agreements due within one year were $1.2 billion as of July 27, 2025.")
    value, _ = ns.prepaid_short_term(text)
    assert value == 1_200_000_000


def test_accrual_in_table_is_in_millions():
    text = ("Accrued and Other Current Liabilities: Customer program accruals 100 90 Excess inventory purchase obligations (2) 2,770 2,095 "
            "Deferred revenue 50 40")
    value, ev = ns.accrual_in_table(text)
    assert value == 2_770e6
    assert "2,770" in ev


def test_accrual_in_table_absent():
    assert ns.accrual_in_table("nothing here") is None


def test_cells_treats_dash_as_zero_and_strips_thousand_separators():
    assert ns._cells("92 — 1,234 5.5") == [92.0, 0.0, 1234.0, 5.5]


def test_buckets_for_10k_and_10q():
    assert ns._buckets(3, "2025-01-26", "10-K") == ["2026", "2027", "2028 and thereafter"]
    assert ns._buckets(3, "2025-07-27", "10-Q") == ["Remainder of 2026", "2027", "2028 and thereafter"]


# --------------------------------------------------------------------------- commitments tables


def test_billions_grid_gives_one_row_per_cell_and_dash_is_zero():
    text = ("Future commitments by fiscal year as of July 26, 2026 , were as follows: Remainder of 2027 2028 2029 2030 2031 "
            "2032 and thereafter Total (In billions) Supply and capacity $92 $100 $50 $10 $— $27 $279 Cloud service agreements $3 $4 $— $— $— $2 $9")
    rows = ns.commitment_tables(text, "2026-07-26", "10-Q")
    supply = {r["bucket"]: r["amount"] for r in rows if r["row"] == "Supply and capacity"}
    assert supply["Remainder of 2027"] == 92e9
    assert supply["2031"] == 0.0  # a dash is zero
    assert supply["2032 and thereafter"] == 27e9
    assert supply["Total"] == 279e9
    # buckets add up to the printed total, so each cell was read once and in the right column
    assert sum(v for k, v in supply.items() if k != "Total") == supply["Total"]
    cloud = {r["bucket"]: r["amount"] for r in rows if r["row"] == "Cloud service agreements"}
    assert cloud["2029"] == 0.0 and cloud["Total"] == 9e9


def test_one_row_schedule_of_purchase_commitments():
    text = ("Total future purchase commitments as of October 31, 2021 , are as follows: Commitments (In millions) Fiscal Year: "
            "2022 $ 5,000 2023 $ 2,000 2024 $ 1,000 Total $ 8,000")
    rows = [r for r in ns.commitment_tables(text, "2021-10-31", "10-Q") if r["table"] == "purchase_commitments_schedule"]
    got = {r["bucket"]: r["amount"] for r in rows}
    assert got["2022"] == 5_000e6 and got["Total"] == 8_000e6
    assert ns.schedule_total(rows) == 8_000e6


def test_sentence_items_do_not_mix_up_nearby_amounts():
    text = ("As of July 27, 2025 , we had outstanding capital purchase obligations totaling $1.5 billion. "
            "Investment commitments are $3.0 billion as of July 27, 2025 , including $5.0 billion in Intel Corporation. "
            "Other commitments were $200 million.")
    rows = {r["row"]: r["amount"] for r in ns._sentence_items(text, "2025-07-27", "10-Q")}
    assert rows["Capital purchase obligations"] == 1.5e9
    assert rows["Investment commitments"] == 3.0e9
    assert rows["Other commitments"] == 200e6


def test_cloud_service_agreement_split_by_year():
    text = ("Multi-year cloud service agreement commitments as of July 26, 2026 , were $26.0 billion, for which $3.0 billion, "
            "$7.0 billion and $16.0 billion will be paid in the remainder of fiscal year 2027 and fiscal year 2028 and thereafter.")
    rows = [r for r in ns._sentence_items(text, "2026-07-26", "10-Q") if r["row"] == "Multi-year cloud service agreements"]
    assert [r["amount"] for r in rows] == [3e9, 7e9, 16e9, 26e9]
    assert rows[-1]["bucket"] == "Total"


# --------------------------------------------------------------------------- due split


def test_due_split_prefers_the_sentence_figure():
    hit = {"due12": 21.9e9, "amount": 27.8e9, "first": None, "second": None, "evidence": ""}
    out = ns.due_split(hit, [], "10-Q")
    assert out["due_next_12_months"] == 21.9e9 and out["due_total"] == 27.8e9


def test_due_split_10k_uses_first_bucket_as_twelve_months_but_10q_does_not():
    hit = {"due12": None, "amount": 100.0, "first": 40.0, "second": 30.0, "evidence": ""}
    k = ns.due_split(hit, [], "10-K")
    q = ns.due_split(hit, [], "10-Q")
    assert k["due_next_12_months"] == 40.0 and k["due_rest_of_fiscal_year"] is None
    assert q["due_next_12_months"] is None and q["due_rest_of_fiscal_year"] == 40.0 and q["due_next_fiscal_year"] == 30.0


def test_due_split_falls_back_to_old_contractual_table():
    tables = [{"table": "contractual_obligations", "row": "Inventory purchase obligations", "bucket": "Less than 1 Year", "amount": 700.0},
              {"table": "contractual_obligations", "row": "Inventory purchase obligations", "bucket": "Total", "amount": 912.0}]
    out = ns.due_split(None, tables, "10-K")
    assert (out["due_next_12_months"], out["due_total"]) == (700.0, 912.0)


# --------------------------------------------------------------------------- charges


def test_quarter_and_nine_month_provision_are_split_correctly():
    text = ("Inventory provisions totaled $73 million and $253 million for the third quarter and first nine months of fiscal year 2022, respectively. "
            "Inventory provisions totaled $50 million and $120 million for the third quarter and first nine months of fiscal year 2021, respectively.")
    out = ns.inventory_charges(text, "2021-10-31")  # fiscal 2022 Q3
    assert out["provision"]["quarter"] == 73e6
    assert out["provision"]["ytd"] == 253e6
    assert out["provision"]["annual"] is None


def test_annual_provision_in_a_10k_and_the_year_before_is_ignored():
    text = ("Inventory provisions totaled $2.2 billion for fiscal year 2023. Inventory provisions totaled $0.4 billion for fiscal year 2022.")
    out = ns.inventory_charges(text, "2023-01-29")
    assert out["provision"]["annual"] == 2.2e9


# --------------------------------------------------------------------------- XBRL helpers on a synthetic fact table


def facts_frame():
    rows = []

    def add(concept, start, end, value, dims=""):
        rows.append(dict(concept=concept, start=start, end=end, value=value, dims=dims))

    add("Revenues", "2025-04-28", "2025-07-27", 100.0)   # quarter
    add("Revenues", "2025-01-27", "2025-07-27", 190.0)   # six months
    add("Revenues", "2024-04-29", "2024-07-28", 60.0)    # a year earlier, quarter
    add("Revenues", "2024-01-29", "2024-07-28", 110.0)   # a year earlier, six months
    add("CostOfRevenue", "2025-04-28", "2025-07-27", 40.0)
    add("CostOfRevenue", "2025-04-28", "2025-07-27", 7.0, ns.PO_CHARGE_DIM)
    add("InventoryNet", None, "2025-07-27", 55.0)
    return pd.DataFrame(rows)


def test_flow_splits_quarter_from_year_to_date():
    f = ns._flow(facts_frame(), ns.REVENUE, "2025-07-27")
    assert f == {"quarter": 100.0, "ytd": 190.0}


def test_flow_ignores_dimensioned_rows_unless_asked():
    df = facts_frame()
    assert ns._flow(df, ns.COST, "2025-07-27")["quarter"] == 40.0
    assert ns._flow(df, ns.COST, "2025-07-27", ns.PO_CHARGE_DIM)["quarter"] == 7.0


def test_year_earlier_picks_the_longest_comparative_span():
    assert ns._year_earlier(facts_frame(), ns.REVENUE, "2025-07-27") == 110.0


def test_instant_needs_a_row_without_a_start():
    df = facts_frame()
    assert ns._instant(df, ["InventoryNet"], "2025-07-27") == 55.0
    assert ns._instant(df, ["Revenues"], "2025-07-27") is None


@pytest.mark.xfail(strict=True, reason="nvidia_supply.py:409 drops a quarter-only tagged purchase-obligation charge when no year-to-date fact exists")
def test_statement_facts_keeps_a_quarter_only_purchase_obligation_charge(monkeypatch):
    monkeypatch.setattr(ns, "facts", lambda filing: facts_frame())
    assert ns.statement_facts({"period": "2025-07-27", "accession": "x"})["purchase_obligation_charge"] == 7.0


def test_statement_facts_wiring(monkeypatch):
    monkeypatch.setattr(ns, "facts", lambda filing: facts_frame())
    out = ns.statement_facts({"period": "2025-07-27", "accession": "x"})
    assert out["revenue"] == 100.0 and out["revenue_ytd"] == 190.0 and out["revenue_ytd_year_earlier"] == 110.0
    assert out["cost_of_revenue"] == 40.0
    assert out["inventories"] == 55.0


# --------------------------------------------------------------------------- trailing four quarters


def row(cls="10-Q", **kw):
    base = dict(form=cls, revenue_ytd=np.nan, cost_ytd=np.nan, revenue_ytd_year_earlier=np.nan, cost_ytd_year_earlier=np.nan,
                gross_ytd=np.nan, po_charge_ytd=np.nan, writedown_ytd=np.nan)
    base.update(kw)
    return pd.Series(base)


def test_trailing_year_in_a_10q_is_ytd_plus_last_year_minus_same_months_last_year():
    df = pd.DataFrame({"revenue_ttm": [np.nan], "cost_of_revenue_ttm": [np.nan]})
    r = row(revenue_ytd=700.0, revenue_ytd_year_earlier=450.0, cost_ytd=300.0, cost_ytd_year_earlier=200.0)
    last = SimpleNamespace(revenue_ytd=1000.0, cost_ytd=400.0)
    ns._fill_statements(df, 0, r, None, last)
    assert df.at[0, "revenue_ttm"] == 700 + 1000 - 450
    assert df.at[0, "cost_of_revenue_ttm"] == 300 + 400 - 200


def test_fourth_quarter_is_the_year_less_nine_months_and_ttm_is_the_year():
    cols = ["revenue", "cost_of_revenue", "gross_profit", "purchase_obligation_charge", "inventory_writedown", "revenue_ttm", "cost_of_revenue_ttm"]
    df = pd.DataFrame({c: [np.nan] for c in cols})
    r = row("10-K", revenue_ytd=1000.0, cost_ytd=400.0, gross_ytd=600.0)
    nine = SimpleNamespace(revenue_ytd=700.0, cost_ytd=290.0, gross_ytd=410.0, po_charge_ytd=np.nan, writedown_ytd=np.nan)
    ns._fill_statements(df, 0, r, nine, None)
    assert df.at[0, "revenue"] == 300.0
    assert df.at[0, "cost_of_revenue"] == 110.0
    assert df.at[0, "gross_profit"] == 190.0
    assert df.at[0, "revenue_ttm"] == 1000.0 and df.at[0, "cost_of_revenue_ttm"] == 400.0


# --------------------------------------------------------------------------- ratios


def ratio_frame():
    return pd.DataFrame({
        "period_end": ["2024-01-28", "2024-04-28", "2024-07-28", "2024-10-27", "2025-01-26"],
        "revenue": [10.0, 11.0, 12.0, 13.0, 20.0],
        "gross_profit": [6.0, 6.6, 7.2, 7.8, 12.0],
        "inventory_provisions": [1.0, 1.1, 1.2, 1.3, 2.0],
        "provision_releases": [0.5, 0.0, 0.2, 0.3, 1.0],
        "supply_commitments": [20.0, 33.0, 60.0, 78.0, 160.0],
        "cost_of_revenue_ttm": [10.0, 11.0, 12.0, 13.0, 20.0],
        "revenue_ttm": [40.0, 44.0, 48.0, 52.0, 80.0],
        "cost_of_revenue": [4.0, 4.4, 4.8, 5.2, 8.0],
        "due_next_12_months": [10.0, np.nan, np.nan, np.nan, 100.0],
        "due_rest_of_fiscal_year": [np.nan, 5.0, 6.0, 7.0, np.nan],
        "due_next_fiscal_year": [np.nan, 10.0, 12.0, 14.0, np.nan],
        "due_total": [20.0, 33.0, 60.0, 70.0, 160.0],
        "form": ["10-K", "10-Q", "10-Q", "10-Q", "10-K"],
        "commit_definition": ["A", "A", "B", "B", "B"],
    })


def test_ratios_commitments_over_trailing_cost_is_exact():
    df = ratio_frame()
    ns._ratios(df)
    assert df.commitments_years_of_cost_of_revenue.tolist() == pytest.approx([2.0, 3.0, 5.0, 6.0, 8.0])
    assert df.commitments_to_revenue_ttm.tolist() == pytest.approx([0.5, 0.75, 1.25, 1.5, 2.0])
    # scaled by latest quarter x 4: 20 / (4 x 4.0) = 1.25
    assert df.commitments_years_of_latest_quarter_cost[0] == pytest.approx(1.25)
    assert df.gross_margin.tolist() == pytest.approx([0.6] * 5)
    assert df.net_inventory_charge.tolist() == pytest.approx([0.5, 1.1, 1.0, 1.0, 1.0])
    assert df.provisions_share_of_revenue[4] == pytest.approx(0.1)
    # year-on-year growth is revenue against the same quarter four rows back
    assert df.revenue_growth_year_on_year[4] == pytest.approx(20 / 10 - 1)
    assert df.revenue_growth_year_on_year[:4].isna().all()


def test_ratios_due_shares_differ_for_10k_and_10q():
    df = ratio_frame()
    ns._ratios(df)
    assert df.share_due_next_12_months[0] == pytest.approx(0.5)
    # in a 10-Q "through next fiscal year" is the rest of this year plus the next year
    assert df.share_due_through_next_fiscal_year[1] == pytest.approx((5 + 10) / 33)
    assert df.share_due_through_next_fiscal_year[4] == pytest.approx(100 / 160)


def test_ratios_flags_a_change_of_definition_once():
    df = ratio_frame()
    ns._ratios(df)
    assert df.series_break.tolist() == ["", "", "definition changed from A to B", "", ""]


def test_zero_cost_does_not_raise_a_divide_error():
    df = ratio_frame()
    df.loc[0, "cost_of_revenue_ttm"] = 0.0
    ns._ratios(df)
    assert np.isinf(df.commitments_years_of_cost_of_revenue[0]) or np.isnan(df.commitments_years_of_cost_of_revenue[0])


# --------------------------------------------------------------------------- verified flag


def test_verified_needs_every_hand_read_number_to_match():
    p = "2024-01-28"  # (16100, 810, 168, 1655, 17316)
    good = SimpleNamespace(period_end=p, supply_commitments=16100e6, inventory_provisions=810e6, provision_releases=168e6,
                           accrual_in_text=1655e6, excess_purchase_accrual=1655e6, due_rest_of_fiscal_year=np.nan, due_next_12_months=17316e6)
    assert ns.verified(good) == "yes"
    bad = SimpleNamespace(**{**good.__dict__, "inventory_provisions": 811e6})
    assert ns.verified(bad) == "no"
    unknown = SimpleNamespace(**{**good.__dict__, "period_end": "2099-01-01"})
    assert ns.verified(unknown) == "no"


def test_verified_when_accrual_in_text_disagrees_with_xbrl():
    p = "2024-01-28"
    r = SimpleNamespace(period_end=p, supply_commitments=16100e6, inventory_provisions=810e6, provision_releases=168e6,
                        accrual_in_text=1655e6, excess_purchase_accrual=1600e6, due_rest_of_fiscal_year=np.nan, due_next_12_months=17316e6)
    assert ns.verified(r) == "no"


# --------------------------------------------------------------------------- peaks and aftermath


def test_peaks_only_counts_highs_that_stand_for_four_quarters():
    ratio = [1.0, 2.0, 3.0, 2.5, 2.0, 2.0, 2.0, 2.0, 4.0, 3.0]
    df = pd.DataFrame({"commitments_years_of_cost_of_revenue": ratio})
    assert ns.peaks(df) == [2]  # index 8 is a high but has fewer than 4 later quarters


def test_aftermath_columns_are_scaled_as_labelled():
    n = 10
    df = pd.DataFrame({
        "period_end": [f"2022-{i + 1:02d}-28" for i in range(n)],
        "supply_commitments": [9e9] * n, "commitments_years_of_cost_of_revenue": [1.5] * n,
        "revenue": [10e9, 8e9] + [9e9] * (n - 2), "revenue_growth_year_on_year": [0.5] * n, "gross_margin": [0.625] * n,
        "inventory_provisions": [1e9] * n, "provisions_share_of_revenue": [0.1] * n, "provision_releases": [2e8] * n,
        "excess_purchase_accrual": [3e8] * n,
    })
    a = ns.aftermath(df, 0)
    assert len(a) == 9
    assert a["commit_$bn"][0] == 9.0
    assert a["revenue_vs_peak_qtr_%"][1] == -20.0
    assert a["gross_margin_%"][0] == 62.5
    assert a["provisions_$m"][0] == 1000.0


# --------------------------------------------------------------------------- peer trailing year


def span(start, end, val):
    return {"start": start, "end": end, "val": val}


def test_trailing_year_prefers_a_full_year_fact():
    facts = {"CostOfRevenue": {"units": {"USD": [span("2024-07-01", "2025-06-30", 500.0)]}}}
    assert ns._trailing_year(facts, ["CostOfRevenue"], "2025-06-30") == 500.0


def test_trailing_year_from_year_to_date_plus_last_year_minus_prior_to_date():
    facts = {"CostOfRevenue": {"units": {"USD": [
        span("2024-01-01", "2024-12-31", 400.0),   # last full year
        span("2025-01-01", "2025-06-30", 230.0),   # this year to date
        span("2024-01-01", "2024-06-30", 190.0),   # same months last year
    ]}}}
    assert ns._trailing_year(facts, ["CostOfRevenue"], "2025-06-30") == 230 + 400 - 190


def test_trailing_year_is_none_without_the_comparative():
    facts = {"CostOfRevenue": {"units": {"USD": [span("2024-01-01", "2024-12-31", 400.0), span("2025-01-01", "2025-06-30", 230.0)]}}}
    assert ns._trailing_year(facts, ["CostOfRevenue"], "2025-06-30") is None


# --------------------------------------------------------------------------- the committed CSV


@pytest.fixture(scope="module")
def supply(processed):
    return pd.read_csv(processed / PROCESSED_SUPPLY).sort_values("period_end").reset_index(drop=True)


def test_one_row_per_quarter_and_quarters_are_consecutive(supply):
    assert not supply.duplicated("period_end").any()
    gaps = pd.to_datetime(supply.period_end).diff().dt.days.dropna()
    assert gaps.between(80, 100).all()
    assert [ns.fiscal(p) for p in supply.period_end] == list(zip(supply.fiscal_year, supply.fiscal_quarter))


def test_ratio_equals_commitments_over_trailing_cost(supply):
    ok = supply.supply_commitments.notna() & supply.cost_of_revenue_ttm.notna()
    assert ok.sum() >= 25
    expected = supply.supply_commitments[ok] / supply.cost_of_revenue_ttm[ok]
    assert supply.commitments_years_of_cost_of_revenue[ok].tolist() == pytest.approx(expected.tolist(), rel=1e-9)
    expected_rev = supply.supply_commitments[ok] / supply.revenue_ttm[ok]
    assert supply.commitments_to_revenue_ttm[ok].tolist() == pytest.approx(expected_rev.tolist(), rel=1e-9)


def test_trailing_cost_is_the_sum_of_the_last_four_quarters(supply):
    rolled = supply.cost_of_revenue.rolling(4).sum()
    ok = rolled.notna()
    # the filings round to $ millions, so allow a few million
    assert (rolled[ok] - supply.cost_of_revenue_ttm[ok]).abs().max() <= 5e6
    rolled_rev = supply.revenue.rolling(4).sum()
    assert (rolled_rev[ok] - supply.revenue_ttm[ok]).abs().max() <= 5e6


def test_margin_and_growth_columns_follow_their_inputs(supply):
    assert (supply.gross_profit / supply.revenue).tolist() == pytest.approx(supply.gross_margin.tolist(), nan_ok=True)
    growth = supply.revenue / supply.revenue.shift(4) - 1
    assert growth.tolist() == pytest.approx(supply.revenue_growth_year_on_year.tolist(), nan_ok=True)


def test_amounts_that_must_be_positive_are_positive(supply):
    for col in ["supply_commitments", "revenue", "cost_of_revenue", "cost_of_revenue_ttm", "revenue_ttm", "inventories"]:
        assert (supply[col].dropna() > 0).all(), col
    assert (supply.gross_margin.dropna().between(0, 1)).all()
    assert (supply.inventory_provisions.dropna() >= 0).all()
    assert (supply.provision_releases.dropna() >= 0).all()


def test_due_amounts_never_exceed_their_total(supply):
    d = supply.dropna(subset=["due_total"])
    for col in ["due_next_12_months", "due_rest_of_fiscal_year", "due_next_fiscal_year"]:
        part = d[col].dropna()
        assert (part <= d.loc[part.index, "due_total"] * 1.0001).all(), col


def test_verified_rows_have_evidence_and_an_sec_url(supply):
    v = supply[supply.verified == "yes"]
    assert len(v) >= 25
    assert v.url.str.startswith("https://www.sec.gov/").all()
    has_number = v[v.supply_commitments.notna()]
    assert (has_number.commit_evidence.fillna("").str.strip().str.len() > 20).all()


def test_verified_rows_reproduce_the_hand_read_commitments(supply):
    for r in supply[supply.verified == "yes"].itertuples():
        want = ns.HAND_READ[r.period_end][0]
        if want is None:
            assert pd.isna(r.supply_commitments)
        else:
            assert r.supply_commitments == pytest.approx(want * 1e6), r.period_end


def test_every_hand_read_date_is_in_the_csv(supply):
    assert set(ns.HAND_READ) == set(supply.period_end)


def test_evidence_sentence_contains_the_amount_it_supports(supply):
    for r in supply[supply.supply_commitments.notna() & supply.commit_evidence.notna()].itertuples():
        ev = r.commit_evidence.replace(",", "")
        billions, millions = r.supply_commitments / 1e9, r.supply_commitments / 1e6
        assert (f"{billions:g}" in ev) or (f"{billions:.1f}" in ev) or (f"{billions:.2f}" in ev) or (f"{millions:g}" in ev) or \
               ("billion" in ev), r.period_end


def test_peers_file_has_unique_keys_and_matching_ratio(processed):
    p = pd.read_csv(processed / "nvidia_supply_peers.csv")
    assert not p.duplicated(["ticker", "period_end"]).any()
    ok = p.cost_of_revenue_ttm.notna() & (p.cost_of_revenue_ttm > 0)
    assert (p.purchase_commitments / p.cost_of_revenue_ttm)[ok].tolist() == pytest.approx(p.commitments_years_of_cost_of_revenue[ok].tolist())
    v = p[p.verified == "yes"]
    assert (v.evidence.fillna("").str.len() > 0).all()
    assert v.url.str.startswith("https://www.sec.gov/").all()
    # verified means the hand-read number agrees with the tagged number
    for r in v.itertuples():
        assert abs(ns.PEER_READ[(r.ticker, r.period_end)][0] * 1e6 - r.purchase_commitments) < 1


def test_commitments_table_has_no_duplicate_cells_and_no_negative_amounts(processed):
    t = pd.read_csv(processed / "nvidia_commitments_table.csv")
    assert (t.amount.dropna() >= 0).all()
    assert t.url.str.startswith("https://www.sec.gov/").all()
    assert (t.evidence.fillna("").str.len() > 0).all()
    dup = t[t.duplicated(["period_end", "table", "row", "bucket"], keep=False)]
    assert dup.empty, dup[["period_end", "table", "row", "bucket"]].head()
