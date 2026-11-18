"""funding_gap: missing data stays missing, the cash arithmetic, the capital-charge grid, and the committed tables."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import funding_gap as fg
from universe import COMPANIES


# --------------------------------------------------------------------------- helpers


def test_value_turns_blank_into_none():
    assert fg._value(np.nan) is None
    assert fg._value(None) is None
    assert fg._value("3") == 3.0
    assert fg._value(0) == 0.0          # a real zero is not a blank


def test_sum_is_none_if_any_part_is_none_never_zero():
    assert fg._sum(1.0, 2.0, 3.0) == 6.0
    assert fg._sum(1.0, None) is None
    assert fg._sum(0.0, 0.0) == 0.0


def test_ratio_needs_a_positive_denominator():
    assert fg._ratio(6.0, 4.0) == 1.5
    assert fg._ratio(None, 4.0) is None
    assert fg._ratio(6.0, None) is None
    assert fg._ratio(6.0, 0.0) is None
    assert fg._ratio(6.0, -4.0) is None
    assert fg._ratio(0.0, 4.0) == 0.0


def test_neg():
    assert fg._neg(None) is None and fg._neg(5.0) == -5.0 and fg._neg(0.0) == 0.0


# --------------------------------------------------------------------------- commitment totals


def commitments_frame():
    def row(ticker, kind, amount, in_total=True, due=None, as_of="2026-09-30"):
        return dict(ticker=ticker, kind=kind, amount=amount, in_total=in_total, due_within_12_months=due, as_of=as_of)

    return pd.DataFrame([
        row("AAA", "purchase_commitments", 100.0, due=40.0),
        row("AAA", "construction", 30.0, due=10.0, as_of="2026-06-30"),
        row("AAA", "other", 5.0),
        row("AAA", "purchase_commitments", 70.0, in_total=False, due=1.0),       # a part of another row
        row("AAA", "backlog_rpo", 500.0),
        row("AAA", "backlog_rpo", 450.0, in_total=False),
        row("BBB", "purchase_commitments", 200.0, due=None),
        row("BBB", "construction", 20.0, due=5.0),
    ])


def test_commitment_totals_adds_only_in_total_rows_and_splits_backlog():
    t = fg.commitment_totals("AAA", commitments_frame())
    assert t["other_signed_commitments"] == 135.0          # 100 + 30 + 5, not the 70 part and not backlog
    assert t["contracted_backlog"] == 500.0
    assert t["purchase_and_construction_due_within_12_months"] == 50.0
    assert t["other_commitments_as_of"] == "2026-06-30 / 2026-09-30"
    assert t["backlog_as_of"] == "2026-09-30"


def test_twelve_month_total_needs_every_order_row_to_have_a_figure():
    t = fg.commitment_totals("BBB", commitments_frame())
    assert t["other_signed_commitments"] == 220.0
    assert t["purchase_and_construction_due_within_12_months"] is None


def test_company_with_no_rows_has_nothing_not_zero():
    t = fg.commitment_totals("CCC", commitments_frame())
    assert t["other_signed_commitments"] is None and t["contracted_backlog"] is None
    assert t["other_commitments_as_of"] == "" and t["purchase_and_construction_due_within_12_months"] is None


# --------------------------------------------------------------------------- capital charge


def test_capital_charge_hand_computed_middle_case():
    # capex 100: 60 equipment over 4 years = 15, 40 buildings over 25 years = 1.6; 10% return = 10
    c = fg.capital_charge(100.0, 0.6, 4, 0.10, 0.4)
    assert c["annual_depreciation"] == pytest.approx(16.6)
    assert c["annual_required_return"] == pytest.approx(10.0)
    assert c["required_operating_profit"] == pytest.approx(26.6)
    assert c["required_revenue"] == pytest.approx(66.5)


def test_capital_charge_is_linear_in_capex():
    a, b = fg.capital_charge(100.0, 0.5, 3, 0.08, 0.3), fg.capital_charge(250.0, 0.5, 3, 0.08, 0.3)
    assert b["required_revenue"] == pytest.approx(2.5 * a["required_revenue"])


def test_capital_charge_directions():
    base = fg.capital_charge(100.0, 0.6, 4, 0.10, 0.4)["required_revenue"]
    assert fg.capital_charge(100.0, 0.6, 3, 0.10, 0.4)["required_revenue"] > base      # shorter life, bigger charge
    assert fg.capital_charge(100.0, 0.6, 4, 0.12, 0.4)["required_revenue"] > base      # higher return
    assert fg.capital_charge(100.0, 0.6, 4, 0.10, 0.5)["required_revenue"] < base      # fatter margin needs less revenue
    assert fg.capital_charge(100.0, 0.7, 4, 0.10, 0.4)["required_revenue"] > base      # more short-lived equipment


def test_all_equipment_and_all_buildings_limits():
    assert fg.capital_charge(100.0, 1.0, 5, 0.0, 1.0)["required_revenue"] == pytest.approx(20.0)
    assert fg.capital_charge(100.0, 0.0, 5, 0.0, 1.0)["required_revenue"] == pytest.approx(100 / fg.BUILDINGS_LIFE)


def test_the_middle_case_is_one_of_the_grid_cases():
    assert fg.MIDDLE["equipment_share"] in fg.EQUIPMENT_SHARES
    assert fg.MIDDLE["equipment_life_years"] in fg.EQUIPMENT_LIVES
    assert fg.MIDDLE["required_return"] in fg.REQUIRED_RETURNS
    assert fg.MIDDLE["margin_before_depreciation"] in fg.MARGINS


# --------------------------------------------------------------------------- the funding gap table, rebuilt from the committed inputs


@pytest.fixture(scope="module")
def gap(processed):
    return pd.read_csv(processed / "funding_gap.csv").set_index("ticker")


@pytest.fixture(scope="module")
def rebuilt():
    return fg.funding_gap().set_index("ticker")


def test_rebuilding_from_committed_inputs_gives_the_committed_table(gap, rebuilt):
    assert list(rebuilt.index) == [c["ticker"] for c in COMPANIES] == list(gap.index)
    for col in gap.columns:
        if col in ("not_disclosed",):
            continue
        a = gap[col].tolist()
        b = rebuilt[col].tolist()
        if gap[col].dtype.kind in "fi":
            assert [np.nan if x is None else x for x in b] == pytest.approx(a, nan_ok=True), col
        else:
            assert ["" if pd.isna(x) else x for x in b] == ["" if pd.isna(x) else x for x in a], col


def test_free_cash_flow_is_operating_cash_flow_less_capex(gap):
    assert (gap.ttm_operating_cash_flow - gap.ttm_capex).tolist() == pytest.approx(gap.free_cash_flow.tolist())


def test_cash_after_payouts_subtracts_each_use_and_is_blank_if_any_is_missing(gap):
    z = gap.free_cash_flow - gap.ttm_finance_lease_principal - gap.ttm_buybacks - gap.ttm_dividends
    ok = z.notna()
    assert ok.sum() >= 3
    assert z[ok].tolist() == pytest.approx(gap.cash_after_capex_leases_and_payouts[ok].tolist())
    assert gap.cash_after_capex_leases_and_payouts[~ok].isna().all()      # never filled with a partial sum


def test_ratios_follow_their_inputs(gap):
    assert (gap.ttm_capex / gap.ttm_operating_cash_flow).tolist() == pytest.approx(gap.capex_pct_of_operating_cash_flow.tolist())
    assert (gap.total_signed_commitments / gap.ttm_operating_cash_flow).tolist() == pytest.approx(
        gap.commitments_in_years_of_operating_cash_flow.tolist(), nan_ok=True)
    ok = gap.contracted_backlog.notna()
    assert (gap.contracted_backlog / gap.total_signed_commitments)[ok].tolist() == pytest.approx(gap.backlog_per_dollar_of_commitments[ok].tolist())
    assert (gap.ttm_debt_issued - gap.ttm_debt_repaid).dropna().tolist() == pytest.approx(gap.net_debt_issued.dropna().tolist())


def test_total_signed_is_leases_plus_in_total_non_lease_rows(gap, processed):
    c = pd.read_csv(processed / "commitments.csv")
    counted = c[c.in_total & (c.kind != "backlog_rpo")].groupby("ticker").amount.sum()
    backlog = c[c.in_total & (c.kind == "backlog_rpo")].groupby("ticker").amount.sum()
    for t, r in gap.iterrows():
        assert r.other_signed_commitments == pytest.approx(counted[t])
        assert r.total_signed_commitments == pytest.approx(counted[t] + r.uncommenced_leases)
        if t in backlog.index:
            assert r.contracted_backlog == pytest.approx(backlog[t])


def test_not_disclosed_names_exactly_the_blank_cells(gap):
    for t, r in gap.iterrows():
        blanks = {c for c in gap.columns if c != "not_disclosed" and pd.isna(r[c])}
        said = set(filter(None, (r.not_disclosed if isinstance(r.not_disclosed, str) else "").split("; ")))
        # text columns that are empty strings are not "not disclosed"; every named item must be blank
        assert said <= blanks, (t, said - blanks)
        assert {c for c in blanks if gap[c].dtype.kind == "f"} - {"leases_as_of"} <= said, (t, blanks - said)


def test_leases_and_fundamentals_are_for_the_same_date(gap):
    assert (gap.as_of == gap.leases_as_of).all()


# --------------------------------------------------------------------------- capex history


def test_capex_history_is_unique_and_ratios_match(processed):
    h = pd.read_csv(processed / "capex_vs_cashflow_history.csv")
    assert not h.duplicated(["ticker", "period"]).any()
    ok = h.capex.notna() & h.operating_cash_flow.notna() & (h.operating_cash_flow > 0)
    assert (h.capex / h.operating_cash_flow)[ok].tolist() == pytest.approx(h.capex_pct_of_operating_cash_flow[ok].tolist())
    assert h.capex_pct_of_operating_cash_flow[~ok].isna().all()
    assert set(h.ticker) == {c["ticker"] for c in COMPANIES}


def test_ttm_point_matches_the_funding_gap_table(processed, gap):
    h = pd.read_csv(processed / "capex_vs_cashflow_history.csv")
    ttm = h[h.period == "TTM"].set_index("ticker")
    for t, r in ttm.iterrows():
        assert r.capex == pytest.approx(gap.loc[t, "ttm_capex"])
        assert r.period_end == gap.loc[t, "as_of"]


def test_rebuilt_history_equals_the_committed_one(processed, rebuilt):
    h = fg.capex_history(rebuilt.reset_index())
    committed = pd.read_csv(processed / "capex_vs_cashflow_history.csv")
    assert len(h) == len(committed)
    assert h.capex_pct_of_operating_cash_flow.tolist() == pytest.approx(committed.capex_pct_of_operating_cash_flow.tolist(), nan_ok=True)


# --------------------------------------------------------------------------- required revenue grid


@pytest.fixture(scope="module")
def grid(processed):
    return pd.read_csv(processed / "required_revenue.csv")


def test_grid_has_every_case_for_every_company(grid):
    per_company = len(fg.EQUIPMENT_SHARES) * len(fg.EQUIPMENT_LIVES) * len(fg.REQUIRED_RETURNS) * len(fg.MARGINS)
    assert len(grid) == per_company * len(COMPANIES)
    assert not grid.duplicated(["ticker", "equipment_share", "equipment_life_years", "required_return", "margin_before_depreciation"]).any()


def test_every_grid_row_recomputes_from_capital_charge(grid):
    ok = grid.ttm_capex.notna()
    assert ok.all()
    for r in grid.itertuples():
        c = fg.capital_charge(r.ttm_capex, r.equipment_share, r.equipment_life_years, r.required_return, r.margin_before_depreciation)
        assert r.annual_depreciation == pytest.approx(c["annual_depreciation"])
        assert r.required_revenue == pytest.approx(c["required_revenue"])
        assert r.required_operating_profit == pytest.approx(r.annual_depreciation + r.annual_required_return)


def test_grid_extremes_bracket_the_middle_case(grid):
    mid = grid[(grid.equipment_share == 0.6) & (grid.equipment_life_years == 4) & (grid.required_return == 0.10) & (grid.margin_before_depreciation == 0.4)]
    assert len(mid) == len(COMPANIES)
    span = grid.groupby("ticker").required_revenue.agg(["min", "max"])
    for r in mid.itertuples():
        assert span.loc[r.ticker, "min"] < r.required_revenue < span.loc[r.ticker, "max"]


def test_grid_ratios_to_revenue_and_growth(grid):
    ok = grid.ttm_revenue.notna() & (grid.ttm_revenue > 0)
    assert (grid.required_revenue / grid.ttm_revenue)[ok].tolist() == pytest.approx(grid.required_revenue_pct_of_ttm_revenue[ok].tolist())
    g = grid.ttm_revenue_growth.notna() & (grid.ttm_revenue_growth > 0)
    assert (grid.required_revenue / grid.ttm_revenue_growth)[g].tolist() == pytest.approx(grid.required_revenue_as_multiple_of_revenue_growth[g].tolist())
    assert grid.required_revenue_as_multiple_of_revenue_growth[~g].isna().all()


def test_grid_capex_equals_the_funding_gap_capex(grid, gap):
    for t, g in grid.groupby("ticker"):
        assert g.ttm_capex.nunique() == 1
        assert g.ttm_capex.iloc[0] == pytest.approx(gap.loc[t, "ttm_capex"])
