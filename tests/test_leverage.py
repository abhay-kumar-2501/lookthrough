"""leverage.py: debt against cash earnings before and after the signed leases, and where twelve months of cash went."""
from __future__ import annotations

import pandas as pd
import pytest

import leverage


def fundamentals(**over):
    row = {"ticker": "AAA", "as_of": "2026-09-30", "debt": 100.0, "operating_lease_liability": 30.0, "finance_lease_liability": 20.0,
           "cash_and_securities": 40.0, "ttm_operating_income": 40.0, "ttm_depreciation": 10.0}
    row.update(over)
    return pd.DataFrame([row])


def pv(**over):
    row = {"ticker": "AAA", "pv_low": 80.0, "pv_base": 100.0, "pv_high": 120.0}
    row.update(over)
    return pd.DataFrame([row])


def test_leverage_arithmetic_on_a_hand_worked_example():
    r = leverage.leverage_table(fundamentals(), pv()).iloc[0]
    assert r.ebitda_ttm == 50.0                         # 40 operating income + 10 depreciation
    assert r.obligations_today == 150.0                 # 100 borrowed + 30 + 20 of leases on the books
    assert r.leverage_today == pytest.approx(3.0)       # 150 / 50
    assert r.leverage_pro_forma == pytest.approx(5.0)   # (150 + 100) / 50
    assert r.leverage_pro_forma_low == pytest.approx(4.6) and r.leverage_pro_forma_high == pytest.approx(5.4)
    assert r.net_leverage_today == pytest.approx(2.2)   # (150 - 40) / 50
    assert r.net_leverage_pro_forma == pytest.approx(4.2)


def test_range_always_brackets_the_middle_estimate():
    r = leverage.leverage_table(fundamentals(), pv()).iloc[0]
    assert r.leverage_today < r.leverage_pro_forma_low <= r.leverage_pro_forma <= r.leverage_pro_forma_high


def test_a_missing_lease_liability_counts_as_none_not_as_an_error():
    r = leverage.leverage_table(fundamentals(finance_lease_liability=float("nan")), pv()).iloc[0]
    assert r.leases_on_balance_sheet == 30.0 and r.leverage_today == pytest.approx(130.0 / 50.0)


@pytest.mark.parametrize("over", [{"ttm_depreciation": float("nan")}, {"ttm_operating_income": float("nan")}, {"ttm_operating_income": -20.0}])
def test_no_ratio_is_given_when_earnings_are_missing_or_not_positive(over):
    r = leverage.leverage_table(fundamentals(**over), pv()).iloc[0]
    assert r.leverage_today is None and r.leverage_pro_forma is None and r.net_leverage_pro_forma is None


def test_a_company_with_more_cash_than_debt_has_negative_net_leverage():
    r = leverage.leverage_table(fundamentals(cash_and_securities=400.0), pv()).iloc[0]
    assert r.net_leverage_today < 0 < r.leverage_today


def test_companies_without_a_lease_value_are_left_out():
    two = pd.concat([fundamentals(), fundamentals(ticker="BBB")])
    assert list(leverage.leverage_table(two, pv()).ticker) == ["AAA"]


def test_committed_leverage_file_matches_a_fresh_calculation(processed):
    saved = pd.read_csv(processed / "lease_adjusted_leverage.csv")
    fresh = leverage.leverage_table(pd.read_csv(processed / "latest_fundamentals.csv"), pd.read_csv(processed / "lease_pv.csv"))
    assert list(saved.ticker) == list(fresh.ticker) and len(saved) == 6
    for col in ["leverage_today", "leverage_pro_forma", "leverage_pro_forma_low", "leverage_pro_forma_high", "net_leverage_pro_forma", "ebitda_ttm"]:
        assert saved[col].tolist() == pytest.approx(fresh[col].tolist()), col


def test_committed_leverage_file_is_internally_consistent(processed):
    lev = pd.read_csv(processed / "lease_adjusted_leverage.csv")
    for r in lev.itertuples():
        assert r.obligations_today == pytest.approx(r.debt + r.leases_on_balance_sheet)
        assert r.leverage_today == pytest.approx(r.obligations_today / r.ebitda_ttm)
        assert r.leverage_pro_forma == pytest.approx((r.obligations_today + r.signed_leases_pv_base) / r.ebitda_ttm)
        assert r.leverage_pro_forma_low <= r.leverage_pro_forma <= r.leverage_pro_forma_high
        assert r.ebitda_ttm > 0


def funding_row(**over):
    row = {"ticker": "AAA", "as_of": "2026-09-30", "ttm_operating_cash_flow": 100.0, "ttm_capex": 90.0, "free_cash_flow": 10.0,
           "ttm_buybacks": 5.0, "ttm_dividends": 3.0, "ttm_debt_issued": 40.0, "ttm_debt_repaid": 6.0}
    row.update(over)
    return pd.DataFrame([row])


def sold(value=12.0, ticker="AAA"):
    return pd.DataFrame([{"ticker": ticker, "ttm_shares_sold": value}])


def test_sources_and_uses_adds_buybacks_and_dividends():
    r = leverage.sources_and_uses(funding_row(), sold()).iloc[0]
    assert r.paid_to_shareholders == 8.0 and r.debt_raised == 40.0 and r.debt_repaid == 6.0 and r.free_cash_flow == 10.0
    assert r.shares_sold == 12.0


def test_shares_sold_stays_empty_when_the_company_reports_none():
    assert leverage.sources_and_uses(funding_row(), sold(float("nan"))).shares_sold.isna().all()
    assert leverage.sources_and_uses(funding_row(), sold(ticker="ZZZ")).shares_sold.isna().all()     # no row for this company
    assert leverage.sources_and_uses(funding_row(), pd.DataFrame([{"ticker": "AAA"}])).shares_sold.isna().all()   # an older file without the column


def test_payouts_use_whichever_item_is_disclosed():
    r = leverage.sources_and_uses(funding_row(ttm_buybacks=float("nan")), sold()).iloc[0]
    assert r.paid_to_shareholders == 3.0


def test_payouts_stay_empty_when_neither_item_is_disclosed():
    out = leverage.sources_and_uses(funding_row(ttm_buybacks=float("nan"), ttm_dividends=float("nan"), ttm_debt_repaid=float("nan")), sold())
    assert out.paid_to_shareholders.isna().all() and out.debt_repaid.isna().all()        # blank, never zero


def test_committed_sources_and_uses_agree_with_the_funding_file(processed):
    su = pd.read_csv(processed / "sources_and_uses.csv").set_index("ticker")
    f = pd.read_csv(processed / "funding_gap.csv").set_index("ticker")
    assert list(su.index) == list(f.index)
    assert su.operating_cash_flow.tolist() == pytest.approx(f.ttm_operating_cash_flow.tolist())
    assert su.capital_spending.tolist() == pytest.approx(f.ttm_capex.tolist())
    assert (su.operating_cash_flow - su.capital_spending).tolist() == pytest.approx(su.free_cash_flow.tolist())
    assert su.debt_raised.sum() == pytest.approx(f.ttm_debt_issued.sum())
    lf = pd.read_csv(processed / "latest_fundamentals.csv").set_index("ticker")
    assert su.shares_sold.fillna(-1).tolist() == pytest.approx(lf.ttm_shares_sold.reindex(su.index).fillna(-1).tolist())
    assert (su.shares_sold.dropna() >= 0).all()
