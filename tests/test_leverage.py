"""leverage.py: debt against cash earnings before and after the signed leases, and where twelve months of cash went."""
from __future__ import annotations

import pandas as pd
import pytest

import leverage


def fundamentals(**over):
    row = {"ticker": "AAA", "as_of": "2026-09-30", "debt": 100.0, "operating_lease_liability": 30.0, "finance_lease_liability": 20.0,
           "cash_and_securities": 40.0, "ttm_operating_income": 40.0, "ttm_depreciation_and_amortization": 10.0}
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


@pytest.mark.parametrize("over", [{"ttm_depreciation_and_amortization": float("nan")}, {"ttm_operating_income": float("nan")}, {"ttm_operating_income": -20.0}])
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


def test_oracle_cash_profit_matches_the_figures_read_by_hand_from_its_filings(processed):
    """Operating income plus depreciation plus amortization of intangibles, each as year + new quarter - old quarter.

    From Oracle's 10-K for the year ended 31 May 2026 and 10-Q for the quarter ended 31 August 2026, in $ millions.
    An earlier version left the amortization line out; this pins the corrected figure to the filings.
    """
    lev = pd.read_csv(processed / "lease_adjusted_leverage.csv").set_index("ticker").loc["ORCL"]
    if lev.as_of != "2026-08-31":
        pytest.skip("Oracle has reported a later quarter; the hand-read figures below are for August 2026")
    operating_income = 20606 + 6728 - 4277
    depreciation = 7623 + 3156 - 1351
    amortization = 1671 + 202 - 420
    assert lev.ebitda_ttm == pytest.approx((operating_income + depreciation + amortization) * 1e6)
    assert lev.debt == pytest.approx((7625 + 117712) * 1e6) and lev.leases_on_balance_sheet == pytest.approx((34621 + 9185) * 1e6)
    assert lev.leverage_today == pytest.approx((7625 + 117712 + 34621 + 9185) / (operating_income + depreciation + amortization), rel=1e-6)


def test_cash_a_company_cannot_sell_is_left_out_when_cash_is_subtracted():
    r = leverage.leverage_table(fundamentals(cash_it_cannot_sell_yet=30.0), pv()).iloc[0]
    assert r.cash_and_securities == 40.0 and r.cash_it_cannot_sell_yet == 30.0
    assert r.net_leverage_today == pytest.approx((150 - 10) / 50) and r.net_leverage_pro_forma == pytest.approx((250 - 10) / 50)
    assert r.leverage_pro_forma == pytest.approx(5.0)      # the main ratio does not subtract cash at all


# Figures printed on the face of each company's latest report, read independently of the project's code on
# 18 November 2026 ($ millions). If the code's choice of lines drifts, or a tag is renamed, these fail.
PRINTED = {
    "MSFT": dict(as_of="2026-09-30", debt=4391 + 31090, leases=27477 + 70973, cash=64509, operating_income=155237 + 45915 - 37961),
    "GOOGL": dict(as_of="2026-09-30", debt=125102 + 1016, leases=20508 + 3705, cash=265098, operating_income=129039 + 121042 - 93105),
    "AMZN": dict(as_of="2026-09-30", debt=6827 + 173125 + 380 + 426 + 9300, leases=100288 + 14495, cash=55783 + 58443, operating_income=79975 + 79389 - 54998),
    "META": dict(as_of="2026-09-30", debt=2747 + 80922, leases=31173 + 1184, cash=11222 + 71227, operating_income=83276 + 54635 - 58531),
    "ORCL": dict(as_of="2026-08-31", debt=7625 + 117712, leases=34621 + 9185, cash=36369 + 708, operating_income=20606 + 6728 - 4277),
    "CRWV": dict(as_of="2026-09-30", debt=41600 + 5273, leases=18697 + 649, cash=4184, operating_income=None),
}
DEPRECIATION_AND_AMORTIZATION = {"AMZN": (41860 + 41845 - 29747) + 817, "META": 18616 + 19509 - 13205, "ORCL": (7623 + 3156 - 1351) + (1671 + 202 - 420), "CRWV": 2454 + 4429 - 1633,
                                 "GOOGL": (21136 + 21955 - 15096) + 920 + 375 * 3 / 9}


@pytest.mark.parametrize("ticker", sorted(PRINTED))
def test_each_bill_starts_from_the_figures_printed_in_the_filing(processed, ticker):
    lev = pd.read_csv(processed / "lease_adjusted_leverage.csv").set_index("ticker").loc[ticker]
    f = pd.read_csv(processed / "latest_fundamentals.csv").set_index("ticker").loc[ticker]
    want = PRINTED[ticker]
    if lev.as_of != want["as_of"]:
        pytest.skip(f"{ticker} has reported a later quarter; the hand-read figures are for {want['as_of']}")
    assert lev.debt == pytest.approx(want["debt"] * 1e6, abs=1.5e6)
    assert lev.leases_on_balance_sheet == pytest.approx(want["leases"] * 1e6, abs=1.5e6)
    assert lev.cash_and_securities == pytest.approx(want["cash"] * 1e6, abs=1.5e6)
    if want["operating_income"] is not None:
        assert f.ttm_operating_income == pytest.approx(want["operating_income"] * 1e6, abs=1.5e6)
    if ticker in DEPRECIATION_AND_AMORTIZATION:
        assert f.ttm_depreciation_and_amortization == pytest.approx(DEPRECIATION_AND_AMORTIZATION[ticker] * 1e6, abs=1.5e6)


def test_alphabets_locked_shares_are_the_figure_in_its_note(processed):
    lev = pd.read_csv(processed / "lease_adjusted_leverage.csv").set_index("ticker")
    if lev.loc["GOOGL", "as_of"] != "2026-09-30":
        pytest.skip("later quarter")
    assert lev.loc["GOOGL", "cash_it_cannot_sell_yet"] == pytest.approx(75.2e9)
    assert (lev.drop(index="GOOGL").cash_it_cannot_sell_yet == 0).all()


# Twelve-month cash-flow figures rebuilt by hand from the printed statements (fiscal year + year to date - prior year to date), $ millions.
CASH_PRINTED = {
    "MSFT": dict(operating_cash_flow=182935 + 58000 - 45057, capital_spending=115948 + 39367 - 19394, debt_raised=0, debt_repaid=3000 + 4850),
    "GOOGL": dict(operating_cash_flow=164713 + 127149 - 112311, capital_spending=91447 + 131953 - 63596, debt_raised=111784),
    "AMZN": dict(operating_cash_flow=168300, capital_spending=215192, debt_raised=130027, debt_repaid=4021),
    "META": dict(operating_cash_flow=115800 + 96873 - 79586, capital_spending=69691 + 83055 - 48308, debt_raised=29906 + 24910),
    "ORCL": dict(operating_cash_flow=31977 + 23103 - 8140, capital_spending=55663 + 28499 - 8502, debt_repaid=6942 + 4202 - 1052, shares_sold=19909 + 4954 + 1449 - 1170),
    "CRWV": dict(operating_cash_flow=3058 + 5638 - 1499, capital_spending=10309 + 23558 - 6249, debt_raised=11829 + 27048 - 7517, shares_sold=2982),
}


@pytest.mark.parametrize("ticker", sorted(CASH_PRINTED))
def test_twelve_month_cash_figures_match_the_printed_statements(processed, ticker):
    su = pd.read_csv(processed / "sources_and_uses.csv").set_index("ticker").loc[ticker]
    if su.as_of != PRINTED[ticker]["as_of"]:
        pytest.skip("later quarter")
    for item, value in CASH_PRINTED[ticker].items():
        assert su[item] == pytest.approx(value * 1e6, abs=1.5e6), (ticker, item)


def test_oracles_customer_prepayments_are_the_two_printed_lines(processed):
    su = pd.read_csv(processed / "sources_and_uses.csv").set_index("ticker")
    assert su.loc["ORCL", "customer_prepayments_in_operating_cash"] == pytest.approx((11363 + 4592) * 1e6)
