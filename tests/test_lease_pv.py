"""lease_pv: present-value arithmetic on hand-computable schedules, then the committed lease_pv tables."""
from __future__ import annotations

import math
import re

import pandas as pd
import pytest

import lease_pv as lp


def annuity(annual: float, years: int, rate: float, start: float = 0.0) -> float:
    """Closed form for `annual` paid in the middle of each of `years` years: sum of annual / (1+r)^(k + 0.5)."""
    v = 1 / (1 + rate)
    if rate == 0:
        return annual * years
    return annual * v ** (start + 0.5) * (1 - v ** years) / (1 - v)


# --------------------------------------------------------------------------- decimal_year


@pytest.mark.parametrize("iso, expected", [
    ("2026-09-30", 2026.75),
    ("2026-12-31", 2027.0),
    ("2026-06-30", 2026.5),
    ("2026-03-31", 2026.25),
    ("2026-08-31", 2026 + 8 / 12),
    ("2024-02-29", 2024 + 2 / 12),  # leap February ends on the 29th
])
def test_decimal_year_is_month_end_convention(iso, expected):
    assert lp.decimal_year(iso) == pytest.approx(expected)


# --------------------------------------------------------------------------- block_pv and pv


def test_level_annuity_matches_closed_form():
    # $300 over three years = $100 a year, each paid mid-year
    assert lp.block_pv(300.0, 0.0, 3.0, 0.05) == pytest.approx(annuity(100, 3, 0.05))
    assert lp.block_pv(300.0, 0.0, 3.0, 0.05) == pytest.approx(100 / 1.05 ** 0.5 + 100 / 1.05 ** 1.5 + 100 / 1.05 ** 2.5)


def test_hand_computed_one_year_block():
    # $110 paid in one year, mid-year, at 10%: 110 / 1.1^0.5
    assert lp.block_pv(110.0, 0.0, 1.0, 0.10) == pytest.approx(110 / math.sqrt(1.1))


def test_start_delay_discounts_by_that_many_more_years():
    now = lp.block_pv(100.0, 0.0, 4.0, 0.06)
    later = lp.block_pv(100.0, 2.0, 4.0, 0.06)
    assert later == pytest.approx(now / 1.06 ** 2)


def test_partial_final_year_is_weighted_and_discounted_at_its_midpoint():
    # 150 over 1.5 years: 100 a year. Year one at t = 0.5, then half a year of rent at t = 1.25.
    expected = 100 / 1.05 ** 0.5 + 50 / 1.05 ** 1.25
    assert lp.block_pv(150.0, 0.0, 1.5, 0.05) == pytest.approx(expected)


def test_short_first_block_for_a_quarter_year():
    # 25 over a quarter: the whole amount lands at t = 0.125
    assert lp.block_pv(25.0, 0.0, 0.25, 0.08) == pytest.approx(25 / 1.08 ** 0.125)


def test_zero_rate_returns_the_undiscounted_amount():
    assert lp.block_pv(1234.0, 3.0, 7.5, 0.0) == pytest.approx(1234.0)


def test_degenerate_blocks_are_worth_nothing():
    assert lp.block_pv(0.0, 0.0, 5.0, 0.05) == 0.0
    assert lp.block_pv(100.0, 0.0, 0.0, 0.05) == 0.0


def test_pv_is_the_sum_of_blocks_and_falls_as_rate_rises():
    blocks = [(100.0, 0.0, 1.0), (200.0, 1.0, 2.0)]
    assert lp.pv(blocks, 0.04) == pytest.approx(100 / 1.04 ** 0.5 + 100 / 1.04 ** 1.5 + 100 / 1.04 ** 2.5)
    assert lp.pv(blocks, 0.0) == pytest.approx(300.0)
    assert lp.pv(blocks, 0.08) < lp.pv(blocks, 0.04)


# --------------------------------------------------------------------------- implied_rate


def test_implied_rate_recovers_the_rate_used():
    blocks = [(100.0, 0.0, 1.0), (500.0, 1.0, 5.0)]
    target = lp.pv(blocks, 0.0375)
    assert lp.implied_rate(blocks, target) == pytest.approx(0.0375, abs=1e-9)


def test_implied_rate_none_when_the_target_is_out_of_range():
    blocks = [(100.0, 0.0, 1.0)]
    assert lp.implied_rate(blocks, 101.0) is None  # more than the undiscounted amount
    assert lp.implied_rate(blocks, 1.0) is None    # less than the value at 100%


# --------------------------------------------------------------------------- taper_blocks


def test_taper_conserves_the_total():
    blocks = lp.taper_blocks(100.0, 3.0, 40.0)
    assert sum(a for a, _, _ in blocks) == pytest.approx(100.0)


def test_taper_hand_values():
    # total 100, first year 50 falling linearly to zero: lasts 2 x 100 / 50 = 4 years.
    blocks = lp.taper_blocks(100.0, 0.0, 50.0)
    assert [round(a, 4) for a, _, _ in blocks] == [43.75, 31.25, 18.75, 6.25]
    assert [s for _, s, _ in blocks] == [0.0, 1.0, 2.0, 3.0]
    assert all(y == 1.0 for _, _, y in blocks)


def test_taper_with_fractional_life_ends_with_a_short_block():
    blocks = lp.taper_blocks(30.0, 0.0, 40.0)   # lasts 1.5 years
    assert len(blocks) == 2
    assert blocks[1][2] == pytest.approx(0.5)
    assert sum(a for a, _, _ in blocks) == pytest.approx(30.0)


def test_taper_is_worth_less_than_a_level_stream_of_the_same_total_over_the_same_start():
    level = [(100.0, 0.0, 4.0)]
    tapered = lp.taper_blocks(100.0, 0.0, 50.0)
    assert lp.pv(tapered, 0.05) > lp.pv([(100.0, 0.0, 8.0)], 0.05)  # front-loaded beats a slower level stream


# --------------------------------------------------------------------------- window_blocks / window_scenarios


def test_window_blocks_split_into_equal_monthly_tranches():
    blocks = lp.window_blocks(120.0, 1.0, 2.0, 10.0)
    assert len(blocks) == 12
    assert all(a == pytest.approx(10.0) and y == 10.0 for a, _, y in blocks)
    assert blocks[0][1] == pytest.approx(1.0 + 0.5 / 12)
    assert blocks[-1][1] == pytest.approx(2.0 - 0.5 / 12)
    assert sum(a for a, _, _ in blocks) == pytest.approx(120.0)


def test_window_in_the_past_is_clamped_to_now():
    blocks = lp.window_blocks(60.0, -3.0, -1.0, 5.0)
    assert len(blocks) == 1 and blocks[0][1] == 0.0


def test_window_scenarios_hand_computed():
    # everything starts now (zero-width window), $120 over 10 years = $12 a year, at 5%
    out = lp.window_scenarios(120.0, 0.0, 0.0, {"term_low": 5, "term_base": 10, "term_high": 20}, 0.05)
    assert out["pv_base"] == pytest.approx(annuity(12, 10, 0.05))
    assert out["pv_high"] == pytest.approx(annuity(24, 5, 0.05))
    # low: longest term and two points more discount
    assert out["pv_low"] == pytest.approx(annuity(6, 20, 0.07))
    assert out["pv_low"] < out["pv_base"] < out["pv_high"] < 120.0
    assert out["annual_rent_base"] == 12.0 and out["term_base"] == 10


# --------------------------------------------------------------------------- amazon schedule


AMZN_ROW = "Leases not yet commenced 2,590 12,448 11,477 12,193 11,385 114,829 164,922"


def test_amazon_schedule_10q_first_bucket_is_the_rest_of_the_year():
    s = lp.amazon_schedule(AMZN_ROW, "2026-09-30")
    assert s["total"] == 164_922e6 and s["after"] == 114_829e6
    assert s["head"][0] == (2_590e6, 0.0, pytest.approx(0.25))
    assert s["head"][1] == (12_448e6, pytest.approx(0.25), 1.0)
    assert s["after_start"] == pytest.approx(0.25 + 4)   # stub, then four full years
    assert s["last"] == 11_385e6
    assert s["peak"] == 12_448e6          # the 2,590 stub is not a full year
    assert sum(a for a, _, _ in s["head"]) + s["after"] == pytest.approx(s["total"])


def test_amazon_schedule_year_end_first_bucket_is_a_full_year():
    row = "Leases not yet commenced 10,000 12,000 11,000 9,000 8,000 50,000 100,000"
    s = lp.amazon_schedule(row, "2025-12-31")
    assert s["head"][0] == (10_000e6, 0.0, pytest.approx(1.0))
    assert s["peak"] == 12_000e6
    assert s["after_start"] == pytest.approx(5.0)   # five full years


def test_amazon_schedule_that_does_not_add_up_is_refused():
    with pytest.raises(ValueError):
        lp.amazon_schedule("Leases not yet commenced 2,590 12,448 11,477 12,193 11,385 114,829 999,999", "2026-09-30")


def test_amazon_scenarios_order_and_hand_check_of_the_base_case():
    out = lp.amazon_scenarios(AMZN_ROW, "2026-09-30", 0.04)
    assert out["pv_low"] < out["pv_base"] < out["pv_high"] < 164_922e6
    s = lp.amazon_schedule(AMZN_ROW, "2026-09-30")
    base = s["head"] + [(s["after"], s["after_start"], s["after"] / s["last"])]
    assert out["pv_base"] == pytest.approx(lp.pv(base, 0.04))
    assert out["term_base"] == round(164_922 / 12_448, 1)
    assert out["annual_rent_base"] == 12_448e6


# --------------------------------------------------------------------------- disclosed schedule from XBRL facts


def instance(as_of, **tags):
    return pd.DataFrame([dict(concept=k, value=str(v), start=None, end=as_of, dims="") for k, v in tags.items()])


STEM = lp.LEASE_TYPES["operating"]["stem"]


def test_disclosed_schedule_10k_with_tagged_thereafter():
    inst = instance("2025-12-31", **{STEM + "Due": 1000, STEM + "DueNextTwelveMonths": 200, STEM + "DueYearTwo": 200, STEM + "DueYearThree": 200,
                                     STEM + "DueYearFour": 100, STEM + "DueYearFive": 100, STEM + "DueAfterYearFive": 200})
    s = lp.disclosed_schedule(inst, STEM, "2025-12-31", 0.0)
    assert s["after"] == 200 and s["after_tagged"]
    assert s["after_years"] == pytest.approx(2.0)     # 200 at the last annual run rate of 100
    assert s["blocks"][0] == (0.0, 0.0, 0.0)
    assert [b[0] for b in s["blocks"][1:6]] == [200, 200, 200, 100, 100]
    assert s["blocks"][-1][1] == 5.0
    assert sum(b[0] for b in s["blocks"]) == pytest.approx(1000)


def test_disclosed_schedule_untagged_thereafter_is_what_the_other_buckets_leave():
    inst = instance("2026-09-30", **{STEM + "Due": 1000, STEM + "RemainderOfFiscalYear": 50, STEM + "DueNextTwelveMonths": 200,
                                     STEM + "DueYearTwo": 200, STEM + "DueYearThree": 200, STEM + "DueYearFour": 100, STEM + "DueYearFive": 100})
    s = lp.disclosed_schedule(inst, STEM, "2026-09-30", 0.25)
    assert s["after"] == 1000 - 50 - 800 and not s["after_tagged"]
    assert s["blocks"][0] == (50, 0.0, 0.25)
    assert s["blocks"][1][1] == pytest.approx(0.25)
    assert sum(b[0] for b in s["blocks"]) == pytest.approx(1000)


def test_disclosed_schedule_missing_total_or_buckets_is_none():
    assert lp.disclosed_schedule(instance("2025-12-31", **{STEM + "Due": 1000}), STEM, "2025-12-31", 0.0) is None
    assert lp.disclosed_schedule(instance("2025-12-31", **{STEM + "DueYearTwo": 100}), STEM, "2025-12-31", 0.0) is None


# --------------------------------------------------------------------------- pv_row


def test_pv_row_refuses_mismatched_dates():
    latest = pd.Series({"period_end": "2026-09-30", "uncommenced_leases": 100.0, "evidence": ""})
    f = pd.Series({"as_of": "2026-06-30"})
    with pytest.raises(ValueError):
        lp.pv_row("MSFT", latest, f, pd.DataFrame())


def fundamentals(**kw):
    base = {"as_of": "2026-09-30", "operating_lease_rate": 0.04, "finance_lease_rate": 0.06, "operating_lease_liability": 60.0,
            "finance_lease_liability": 40.0, "debt": 200.0, "cash_and_securities": 50.0, "ttm_operating_income": 25.0,
            "ttm_cash_from_operations": 80.0, "lease_rate_as_of": "2026-09-30"}
    base.update(kw)
    return pd.Series(base)


def terms_frame(as_of="2026-09-30"):
    return pd.DataFrame([dict(ticker="XYZ", as_of=as_of, commence_from=2026.75, commence_to=2026.75, term_low=5, term_base=10, term_high=20)]).set_index("ticker")


def test_pv_row_hand_computed_company():
    latest = pd.Series({"period_end": "2026-09-30", "uncommenced_leases": 120.0, "evidence": ""})
    r = lp.pv_row("XYZ", latest, fundamentals(), terms_frame())
    rate = 0.05                                 # simple average of operating 4% and finance 6%
    assert r["discount_rate_base"] == rate
    assert r["pv_base"] == round(annuity(12, 10, rate))
    assert r["pv_base_ratio"] == round(annuity(12, 10, rate) / 120, 4)
    assert r["annual_rent_base"] == 12
    assert r["existing_lease_liabilities"] == 100.0
    assert r["total_obligations_today"] == 300.0
    assert r["total_with_signed_leases"] == round(300.0 + annuity(12, 10, rate))
    assert r["annual_rent_pct_of_ttm_operating_income"] == round(100 * 12 / 25, 1)
    assert r["pv_base_vs_debt"] == round(annuity(12, 10, rate) / 200, 3)


def test_pv_row_leaves_rent_share_blank_when_operating_income_is_not_positive():
    latest = pd.Series({"period_end": "2026-09-30", "uncommenced_leases": 120.0, "evidence": ""})
    r = lp.pv_row("XYZ", latest, fundamentals(ttm_operating_income=-5.0), terms_frame())
    assert r["annual_rent_pct_of_ttm_operating_income"] is None


def test_pv_row_refuses_stale_terms():
    latest = pd.Series({"period_end": "2026-09-30", "uncommenced_leases": 120.0, "evidence": ""})
    with pytest.raises(ValueError):
        lp.pv_row("XYZ", latest, fundamentals(), terms_frame(as_of="2026-06-30"))


# --------------------------------------------------------------------------- committed tables


@pytest.fixture(scope="module")
def table(processed):
    return pd.read_csv(processed / "lease_pv.csv")


def test_one_row_per_company(table):
    assert not table.ticker.duplicated().any()
    assert len(table) == 6


def test_scenarios_are_ordered_and_below_the_undiscounted_amount(table):
    assert (table.pv_low < table.pv_base).all()
    assert (table.pv_base < table.pv_high).all()
    assert (table.pv_high < table.undiscounted).all()
    assert (table.pv_low > 0).all()


def test_ratio_and_totals_follow_their_inputs(table):
    assert (table.pv_base / table.undiscounted).round(4).tolist() == pytest.approx(table.pv_base_ratio.tolist())
    assert (table.debt + table.existing_lease_liabilities).tolist() == pytest.approx(table.total_obligations_today.tolist())
    assert (table.total_obligations_today + table.pv_base).round().tolist() == pytest.approx(table.total_with_signed_leases.tolist(), abs=1)
    assert (table.pv_base / table.debt).round(3).tolist() == pytest.approx(table.pv_base_vs_debt.tolist())
    pos = table.ttm_operating_income > 0
    assert (100 * table.annual_rent_base / table.ttm_operating_income)[pos].round(1).tolist() == pytest.approx(table.annual_rent_pct_of_ttm_operating_income[pos].tolist())
    assert table.annual_rent_pct_of_ttm_operating_income[~pos].isna().all()


def test_discount_rates_are_plausible(table):
    assert table.discount_rate_base.between(0.02, 0.12).all()


def test_each_pv_recomputes_from_the_committed_inputs(table, root):
    leases = pd.read_csv(root / "data" / "processed" / "uncommenced_leases.csv").dropna(subset=["uncommenced_leases"])
    terms = pd.read_csv(root / "inputs" / "lease_terms.csv").set_index("ticker")
    for r in table.itertuples():
        latest = leases[(leases.ticker == r.ticker) & (leases.period_end == r.as_of)].iloc[0]
        assert latest.uncommenced_leases == pytest.approx(r.undiscounted)
        if r.ticker == "AMZN":
            s = lp.amazon_scenarios(latest.evidence, r.as_of, r.discount_rate_base)
        else:
            t = terms.loc[r.ticker]
            now = lp.decimal_year(r.as_of)
            s = lp.window_scenarios(r.undiscounted, t.commence_from - now, t.commence_to - now, t.to_dict(), r.discount_rate_base)
        for key in ("pv_low", "pv_base", "pv_high"):
            assert getattr(r, key) == pytest.approx(s[key], rel=2e-3), (r.ticker, key)


def test_lease_terms_are_ordered_and_current(table, root):
    terms = pd.read_csv(root / "inputs" / "lease_terms.csv")
    assert not terms.ticker.duplicated().any()
    assert (terms.term_low <= terms.term_base).all() and (terms.term_base <= terms.term_high).all()
    assert (terms.commence_from <= terms.commence_to).all()
    asof = table.set_index("ticker").as_of
    for r in terms.itertuples():
        assert asof[r.ticker] == r.as_of
        assert len(r.evidence) > 20


def test_history_is_unique_and_ratios_are_fractions(processed):
    h = pd.read_csv(processed / "lease_pv_history.csv")
    assert not h.duplicated(["ticker", "period_end"]).any()
    assert h.pv_base_ratio.between(0.2, 1.0).all()
    assert (h.pv_base < h.undiscounted).all()
    assert (h.undiscounted > 0).all()


def test_history_last_point_agrees_with_the_headline_table(processed, table):
    h = pd.read_csv(processed / "lease_pv_history.csv").sort_values("period_end").groupby("ticker").tail(1).set_index("ticker")
    for r in table.itertuples():
        assert h.loc[r.ticker, "pv_base"] == pytest.approx(r.pv_base, rel=0.05), r.ticker


def test_method_check_errors_are_small_and_rates_plausible(processed):
    m = pd.read_csv(processed / "lease_method_check.csv")
    assert not m.duplicated(["ticker", "lease_type"]).any()
    assert m.error_pct.abs().max() < 15
    assert (m.pv_of_schedule / m.recorded_liability - 1).mul(100).round(2).tolist() == pytest.approx(m.error_pct.tolist(), abs=0.011)
    assert (m.pv_of_schedule < m.undiscounted_payments).all()
    assert m.discount_rate.between(0.01, 0.15).all() or m.discount_rate.between(1, 15).all()
