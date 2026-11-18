"""model.py: the vintage depreciation model, checked against hand-computed cases."""
from __future__ import annotations

import random

import pandas as pd
import pytest

import model


def by_year(additions, life, through):
    """Total depreciation per year as a plain list, first year first."""
    dep = model.depreciate(additions, life, through)
    return [model.total(dep, t) for t in range(min(additions), through + 1)]


def by_year_frac(additions, life, through, fraction):
    dep = model.depreciate(additions, life, through, first_year_fraction=fraction)
    return [model.total(dep, t) for t in range(min(additions), through + 1)]


def by_vintage(additions, life, through):
    dep = model.depreciate(additions, life, through)
    out: dict[int, float] = {}
    for year in dep.values():
        for v, d in year.items():
            out[v] = out.get(v, 0.0) + d
    return out


# --------------------------------------------------------------------------- depreciate


def test_half_year_convention_three_year_life():
    # 600 bought in year 0, 3-year life: half a year, two full years, half a year.
    assert by_year({0: 600.0}, {0: 3}, 5) == pytest.approx([100, 200, 200, 100, 0, 0])


def test_result_is_indexed_by_year_then_vintage():
    dep = model.depreciate({0: 600.0, 1: 300.0}, {0: 3}, 2)
    assert dep[0] == pytest.approx({0: 100})
    assert dep[1] == pytest.approx({0: 200, 1: 50})
    assert dep[2] == pytest.approx({0: 200, 1: 100})


def test_vintages_are_independent_and_additive():
    both = by_year({0: 600.0, 2: 1200.0}, {0: 3}, 6)
    a = by_year({0: 600.0}, {0: 3}, 6)
    b = [0, 0] + by_year({2: 1200.0}, {2: 3}, 6)
    assert both == pytest.approx([x + y for x, y in zip(a, b)])


def test_fractional_life():
    # 700 on a 3.5-year life: 100 in the half year, then 200 a year for three years.
    assert by_year({0: 700.0}, {0: 3.5}, 4) == pytest.approx([100, 200, 200, 200, 0])


def test_lengthened_life_is_applied_prospectively():
    # 600 bought in year 0 on a 3-year life; from year 2 the life is 5 years.
    # End of year 1: book value 300, age 1.5 years -> 3.5 years left on the new life.
    life = {0: 3, 1: 3, 2: 5}
    got = by_year({0: 600.0}, life, 6)
    per_year = 300 / 3.5
    assert got == pytest.approx([100, 200, per_year, per_year, per_year, per_year / 2, 0])
    # Not retrospective: a catch-up to the 5-year schedule would book 0 in year 2
    # (600 * 2.5 / 5 = 300 is already accumulated).
    assert got[2] > 0
    # Years before the change are untouched.
    assert got[:2] == pytest.approx(by_year({0: 600.0}, {0: 3}, 1))


def test_shortened_life_is_applied_prospectively():
    # 600 on a 6-year life; from year 2 the life is 4 years.
    # End of year 1: book value 450, age 1.5 -> 2.5 years left.
    got = by_year({0: 600.0}, {0: 6, 1: 6, 2: 4}, 5)
    assert got == pytest.approx([50, 100, 180, 180, 90, 0])


def test_life_shortened_below_current_age_writes_off_the_remainder():
    # 600 on a 6-year life for three years (50 + 100 + 100), then the life drops to
    # 2 years: the asset is already 2.5 years old, so the remaining 350 goes at once.
    got = by_year({0: 600.0}, {0: 6, 1: 6, 2: 6, 3: 2}, 5)
    assert got == pytest.approx([50, 100, 100, 350, 0, 0])


def test_change_only_affects_assets_still_on_the_books():
    # A fully depreciated vintage does not come back to life when the life is extended.
    life = {y: 3 for y in range(0, 4)} | {y: 6 for y in range(4, 12)}
    got = by_year({0: 600.0}, life, 10)
    assert got[:4] == pytest.approx([100, 200, 200, 100])
    assert got[4:] == pytest.approx([0] * 7)


def test_life_outside_the_dict_uses_nearest_end():
    # Years after the last key use the last life; years before the first key use the first.
    assert by_year({0: 600.0}, {0: 3}, 3) == pytest.approx(by_year({0: 600.0}, {0: 3, 1: 3, 2: 3, 3: 3}, 3))
    assert by_year({0: 600.0}, {2: 3, 3: 5}, 1) == pytest.approx([100, 200])


def test_zero_additions_create_no_vintage():
    dep = model.depreciate({0: 0.0, 1: 600.0}, {0: 3}, 2)
    assert dep[0] == {}
    assert set(dep[1]) == {1}


def test_total_existing_only_excludes_the_current_year_vintage():
    dep = model.depreciate({0: 600.0, 1: 300.0}, {0: 3}, 1)
    assert model.total(dep, 1) == pytest.approx(250)
    assert model.total(dep, 1, existing_only=True) == pytest.approx(200)
    assert model.total(dep, 99) == 0


def test_modeled_effect_of_a_life_change_matches_hand_calculation():
    # The validation in model.run compares depreciation in the change year under the
    # old and the new life. Fleet: 300 bought in each of years 0, 1, 2 on 3 years; the
    # life goes to 4 years in year 3 (the "existing" basis ignores year-3 purchases).
    adds = {0: 300.0, 1: 300.0, 2: 300.0, 3: 300.0}
    old = {0: 3, 1: 3, 2: 3, 3: 3}
    new = {0: 3, 1: 3, 2: 3, 3: 4}
    d_old = model.total(model.depreciate(adds, old, 3), 3, existing_only=True)
    d_new = model.total(model.depreciate(adds, new, 3), 3, existing_only=True)
    # Old: vintage 0 has 50 left (all goes), vintage 1 has 150 over 1.5 yrs = 100,
    # vintage 2 has 250 over 2.5 yrs = 100.
    assert d_old == pytest.approx(50 + 100 + 100)
    # New: 50 over 1.5 yrs, 150 over 2.5 yrs, 250 over 3.5 yrs.
    assert d_new == pytest.approx(50 / 1.5 + 150 / 2.5 + 250 / 3.5)


def test_quarter_year_convention():
    # 600 on 3 years with a quarter-year first year: 50, then 550 over the remaining 2.75 years.
    got = by_year_frac({0: 600.0}, {0: 3}, 4, 0.25)
    assert got == pytest.approx([50, 200, 200, 150, 0])


def test_life_change_with_quarter_year_convention():
    # 600 on 3 years (50, 200), then 5 years from year 2: 350 left, age 1.25 -> 3.75 years to go.
    got = by_year_frac({0: 600.0}, {0: 3, 1: 3, 2: 5}, 6, 0.25)
    per_year = 350 / 3.75
    assert got == pytest.approx([50, 200, per_year, per_year, per_year, per_year * 0.75, 0])


def test_new_assets_override_applies_only_to_later_vintages():
    # General life 6 years; assets bought from year 2 on are on 3 years.
    dep = model.depreciate({0: 600.0, 2: 600.0}, {0: 6}, 8, new_assets={2: 3})
    old = [dep[t].get(0, 0.0) for t in range(0, 9)]
    new = [dep[t].get(2, 0.0) for t in range(0, 9)]
    assert old == pytest.approx([50, 100, 100, 100, 100, 100, 50, 0, 0])
    assert new == pytest.approx([0, 0, 100, 200, 200, 100, 0, 0, 0])


def test_latest_new_assets_override_wins():
    dep = model.depreciate({0: 600.0, 1: 600.0, 3: 600.0}, {0: 6}, 3, new_assets={1: 3, 3: 2})
    assert dep[3] == pytest.approx({0: 100, 1: 200, 3: 150})


LIFE_PATHS = {
    "constant 3": {0: 3},
    "constant 2": {0: 2},
    "constant 8": {0: 8},
    "fractional 3.5": {0: 3.5},
    "fractional 4.5": {0: 4.5},
    "fractional 5.7": {0: 5.7},
    "life of one year": {0: 1},
    "life under one year": {0: 0.5},
    "life under half a year": {0: 0.25},
    "microsoft 3 -> 4 -> 6": {0: 3, 1: 3, 2: 4, 3: 4, 4: 6},
    "amazon 3 -> 4 -> 5 -> 6 -> 5.7": {0: 3, 1: 4, 2: 4, 3: 5, 4: 5, 5: 6, 6: 5.7},
    "meta 3 -> 3.5 -> 4 -> 4.5 -> 5.5": {0: 3, 1: 3.5, 2: 4, 3: 4.5, 4: 4.5, 5: 5.5},
    "shortened 6 -> 2": {0: 6, 1: 6, 2: 6, 3: 2},
    "shortened then lengthened": {0: 5, 1: 2, 2: 7},
    "lengthened in the final half year": {0: 3, 1: 3, 2: 3, 3: 8},
}


@pytest.mark.parametrize("fraction", [0.5, 0.25, 0.75, 1.0])
@pytest.mark.parametrize("name", LIFE_PATHS)
def test_total_depreciation_equals_cost(name, fraction):
    additions = {0: 600.0, 1: 0.0, 2: 250.0, 3: 1000.0, 5: 40.0}
    dep = model.depreciate(additions, LIFE_PATHS[name], 40, first_year_fraction=fraction)
    got: dict[int, float] = {}
    for year in dep.values():
        for v, d in year.items():
            assert d >= 0
            got[v] = got.get(v, 0.0) + d
    assert got == pytest.approx({v: a for v, a in additions.items() if a > 0})


def test_total_depreciation_equals_cost_for_random_life_paths():
    rng = random.Random(20261118)
    lives = [1, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 5.7, 6, 7, 8]
    for _ in range(300):
        life = {y: rng.choice(lives) for y in range(0, 12)}
        additions = {y: rng.choice([0.0, 10.0, 123.4, 5e9]) for y in range(0, 12)}
        additions[0] = 600.0
        fraction = rng.choice([0.5, 0.25])
        overrides = rng.choice([None, {rng.randrange(0, 12): rng.choice(lives)}, {3: 5.27, 7: 2}])
        dep = model.depreciate(additions, life, 30, first_year_fraction=fraction, new_assets=overrides)
        cumulative: dict[int, float] = {}
        for t in sorted(dep):
            for v, d in dep[t].items():
                assert d >= 0
                cumulative[v] = cumulative.get(v, 0.0) + d
                assert cumulative[v] <= additions[v] * (1 + 1e-9)  # book value never goes below zero
        assert cumulative == pytest.approx({v: a for v, a in additions.items() if a > 0})


# --------------------------------------------------------------------------- estimate_additions


def as_rows(df: pd.DataFrame) -> dict[int, tuple[float, float, bool]]:
    return {int(r.fiscal_year): (r.additions, r.retired, bool(r.seeded)) for r in df.itertuples()}


def flat_life(years, life=3.0):
    return {y: life for y in years}


def test_additions_without_retirement_equal_the_change_in_gross():
    gross = {2015: 300.0, 2016: 400.0, 2017: 550.0, 2018: 550.0}
    got = as_rows(model.estimate_additions(gross, flat_life(range(2010, 2019)), retire_lag=99))
    assert got[2016] == pytest.approx((100, 0, False))
    assert got[2017] == pytest.approx((150, 0, False))
    assert got[2018] == pytest.approx((0, 0, False))


def test_opening_balance_is_seeded_evenly_over_the_preceding_life():
    gross = {2015: 300.0, 2016: 400.0}
    df = model.estimate_additions(gross, flat_life(range(2010, 2017)), retire_lag=99)
    got = as_rows(df)
    assert list(df.fiscal_year) == [2013, 2014, 2015, 2016]
    for y in (2013, 2014, 2015):
        assert got[y] == pytest.approx((100, 0, True))
    assert got[2016][2] is False
    assert list(df.columns) == ["fiscal_year", "additions", "retired", "seeded"]


@pytest.mark.parametrize("life, n", [(3, 3), (3.5, 4), (4, 4), (5.7, 6), (0.5, 1)])
def test_opening_balance_uses_the_life_in_force_rounded_up(life, n):
    df = model.estimate_additions({2020: 1200.0, 2021: 1200.0}, flat_life(range(2005, 2022), life), retire_lag=99)
    seeded = df[df.seeded]
    assert list(seeded.fiscal_year) == list(range(2020 - n + 1, 2021))
    assert seeded.additions.tolist() == pytest.approx([1200.0 / n] * n)


def test_retired_assets_are_added_back():
    # 3-year life, no lag: a vintage leaves gross three years after purchase.
    gross = {2015: 300.0, 2016: 400.0, 2017: 550.0}
    got = as_rows(model.estimate_additions(gross, flat_life(range(2010, 2018)), retire_lag=0))
    # 2016: the 2013 seed (100) retires, so 200 must have been bought to end at 400.
    assert got[2016] == pytest.approx((200, 100, False))
    # 2017: the 2014 seed (100) retires -> 150 + 100.
    assert got[2017] == pytest.approx((250, 100, False))


def test_retirement_lag_delays_the_add_back():
    gross = {2015: 300.0, 2016: 400.0, 2017: 550.0, 2018: 600.0}
    got = as_rows(model.estimate_additions(gross, flat_life(range(2010, 2019)), retire_lag=2))
    assert got[2016] == pytest.approx((100, 0, False))
    assert got[2017] == pytest.approx((150, 0, False))
    assert got[2018] == pytest.approx((150, 100, False))  # 2013 seed is now 5 years old


@pytest.mark.parametrize("lag", [0, 1, 2, 6, 99])
def test_purchases_less_retirements_reconcile_to_gross(lag):
    gross = {2012: 500.0, 2013: 650.0, 2014: 900.0, 2015: 1400.0, 2016: 1500.0, 2017: 2400.0, 2018: 4000.0, 2019: 4100.0}
    life = {y: (3 if y < 2016 else 4.5) for y in range(2000, 2020)}
    df = model.estimate_additions(gross, life, lag).set_index("fiscal_year")
    balance = (df.additions - df.retired).cumsum()
    for year, g in gross.items():
        assert balance[year] == pytest.approx(g)


def test_gap_year_spreads_additions_evenly():
    # No balance for 2021: the 200 increase is split across 2021 and 2022.
    gross = {2020: 300.0, 2022: 500.0}
    df = model.estimate_additions(gross, flat_life(range(2010, 2023)), retire_lag=99)
    got = as_rows(df)
    assert sorted(got) == [2018, 2019, 2020, 2021, 2022]
    assert got[2021] == pytest.approx((100, 0, False))
    assert got[2022] == pytest.approx((100, 0, False))


def test_gap_year_with_retirement():
    # By 2022 the 2018 and 2019 seeds (100 each) are three years old and retire:
    # 200 + 200 bought over the two missing years. Retirement is booked once, in 2022.
    gross = {2020: 300.0, 2022: 500.0}
    got = as_rows(model.estimate_additions(gross, flat_life(range(2010, 2023)), retire_lag=0))
    assert got[2021] == pytest.approx((200, 0, False))
    assert got[2022] == pytest.approx((200, 200, False))


def test_three_year_gap():
    gross = {2018: 90.0, 2021: 390.0}
    got = as_rows(model.estimate_additions(gross, flat_life(range(2010, 2022)), retire_lag=99))
    for y in (2019, 2020, 2021):
        assert got[y] == pytest.approx((100, 0, False))


def test_a_fall_in_gross_never_produces_negative_purchases():
    gross = {2015: 300.0, 2016: 250.0, 2017: 400.0}
    df = model.estimate_additions(gross, flat_life(range(2010, 2018)), retire_lag=99)
    assert (df.additions >= 0).all()
    assert as_rows(df)[2016] == pytest.approx((0, 0, False))


# --------------------------------------------------------------------------- policy_by_year


@pytest.fixture
def policy() -> pd.DataFrame:
    # Deliberately unsorted, with a second company mixed in.
    return pd.DataFrame(
        [
            ("AAA", 2023, 6.0),
            ("BBB", 2012, 5.0),
            ("AAA", 2012, 3.0),
            ("AAA", 2021, 4.0),
            ("BBB", 2025, 5.7),
        ],
        columns=["ticker", "from_fiscal_year", "life_years"],
    )


def test_policy_by_year_steps_at_each_change(policy):
    got = model.policy_by_year(policy, "AAA", range(2012, 2026))
    assert [got[y] for y in range(2012, 2021)] == [3.0] * 9
    assert (got[2020], got[2021], got[2022], got[2023], got[2025]) == (3.0, 4.0, 4.0, 6.0, 6.0)
    assert list(got) == list(range(2012, 2026))
    assert all(isinstance(v, float) for v in got.values())


def test_policy_by_year_before_first_entry_uses_the_earliest_life(policy):
    got = model.policy_by_year(policy, "AAA", range(2002, 2013))
    assert set(got.values()) == {3.0}


def test_policy_by_year_keeps_companies_apart(policy):
    got = model.policy_by_year(policy, "BBB", range(2020, 2027))
    assert got == {2020: 5.0, 2021: 5.0, 2022: 5.0, 2023: 5.0, 2024: 5.0, 2025: 5.7, 2026: 5.7}


def test_policy_by_year_on_the_committed_policy_file(root):
    # Only lives stated outright in the filings are pinned here; calibrated rows may be re-fitted.
    policy = pd.read_csv(root / "inputs" / "useful_life_policy.csv")
    msft = model.policy_by_year(policy, "MSFT", range(2019, 2027))
    assert [msft[y] for y in range(2019, 2027)] == [3, 3, 4, 4, 6, 6, 6, 6]
    amzn = model.policy_by_year(policy, "AMZN", range(2019, 2025))
    assert [amzn[y] for y in range(2019, 2025)] == [3, 4, 4, 5, 5, 6]
    orcl = model.policy_by_year(policy, "ORCL", range(2022, 2027))
    assert [orcl[y] for y in range(2022, 2027)] == [4, 5, 5, 6, 6]
    googl = model.policy_by_year(policy, "GOOGL", range(2020, 2026))
    assert [googl[y] for y in range(2020, 2026)] == [3, 4, 4, 6, 6, 6]


def test_policy_by_year_ignores_rows_that_apply_to_new_assets_only():
    policy = pd.DataFrame(
        [
            ("AAA", 2012, 3.0, "all"),
            ("AAA", 2024, 6.0, "all"),
            ("AAA", 2025, 5.8, "all"),
            ("AAA", 2025, 5.0, "new_assets"),
            ("AAA", 2026, 4.0, "new_assets"),
            ("BBB", 2012, 4.0, None),  # blank means "all"
        ],
        columns=["ticker", "from_fiscal_year", "life_years", "applies_to"],
    )
    got = model.policy_by_year(policy, "AAA", range(2023, 2028))
    assert got == {2023: 3.0, 2024: 6.0, 2025: 5.8, 2026: 5.8, 2027: 5.8}
    assert model.policy_by_year(policy, "BBB", range(2020, 2022)) == {2020: 4.0, 2021: 4.0}
    assert model.new_asset_lives(policy, "AAA") == {2025: 5.0, 2026: 4.0}
    assert model.new_asset_lives(policy, "BBB") == {}


def test_new_asset_lives_without_the_column(policy):
    assert model.new_asset_lives(policy, "AAA") == {}
