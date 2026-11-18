"""Integrity checks on the CSVs committed under data/processed and inputs/."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import make_spenders
import model
from universe import COMPANIES

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
TICKERS = {c["ticker"] for c in COMPANIES}
MAX_VALIDATION_ERROR_PCT = 20.0

# Validation rows known to miss the 20% bar (strict: remove the entry once the model is fixed).
KNOWN_VALIDATION_MISSES = {
    ("MSFT", 2021, "existing"): "MSFT FY2021 3->4 yrs: model 2.11bn vs 2.7bn disclosed (-21.8%)",
}


def load(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / name)


# --------------------------------------------------------------------------- validation.csv


def _validation_params():
    v = load("validation.csv")
    params = []
    for r in v[v.in_validation].itertuples():
        key = (r.ticker, int(r.fiscal_year), r.basis)
        marks = [pytest.mark.xfail(strict=True, reason=KNOWN_VALIDATION_MISSES[key])] if key in KNOWN_VALIDATION_MISSES else []
        params.append(pytest.param(r.error_pct, id=f"{r.ticker}-{r.fiscal_year}-{r.basis}", marks=marks))
    return params


@pytest.mark.parametrize("error_pct", _validation_params())
def test_validation_error_is_under_20_percent(error_pct):
    assert abs(error_pct) < MAX_VALIDATION_ERROR_PCT


def test_validation_table_is_well_formed():
    v = load("validation.csv")
    used = v[v.in_validation]
    assert len(used) >= 9
    assert not v.duplicated(["ticker", "fiscal_year", "basis"]).any()
    assert v.retire_lag.nunique() == 1
    assert np.isfinite(v[["disclosed_bn", "modeled_bn", "error_pct"]].to_numpy()).all()
    # error_pct is what it says it is
    assert ((v.modeled_bn / v.disclosed_bn - 1) * 100).tolist() == pytest.approx(v.error_pct.tolist())
    # the model must at least get the direction of every disclosed effect right
    assert (np.sign(v.modeled_bn) == np.sign(v.disclosed_bn)).all()


def test_every_validation_row_comes_from_the_impacts_file():
    v = load("validation.csv")
    impacts = pd.read_csv(ROOT / "inputs" / "disclosed_impacts.csv")
    key = ["ticker", "fiscal_year", "basis"]
    assert not impacts.duplicated(key).any()
    merged = v.merge(impacts, on=key, how="left", indicator=True)
    assert (merged._merge == "both").all()
    assert merged.disclosed_bn.tolist() == pytest.approx(merged.disclosed_reduction_bn.tolist())
    assert (merged.in_validation_x == (merged.in_validation_y == "yes")).all()
    assert len(v) == len(impacts), "a disclosed impact was silently skipped (no asset balance for that year?)"


def test_chosen_retirement_lag_is_the_best_fit():
    v, fit = load("validation.csv"), load("retire_lag_fit.csv")
    best = fit.sort_values("mean_abs_error_pct").iloc[0]
    assert v.retire_lag.iloc[0] == best.retire_lag
    assert v[v.in_validation].error_pct.abs().mean() == pytest.approx(best.mean_abs_error_pct)


# --------------------------------------------------------------------------- uncommenced_leases.csv


@pytest.fixture(scope="module")
def leases() -> pd.DataFrame:
    return load("uncommenced_leases.csv")


def test_lease_values_are_positive(leases):
    have = leases.dropna(subset=["uncommenced_leases"])
    assert len(have) > 100
    assert (have.uncommenced_leases > 0).all()


def test_no_company_quarter_appears_twice(leases):
    assert not leases.duplicated(["ticker", "period_end"]).any()
    quarter = [make_spenders.calendar_quarter(t, p) for t, p in zip(leases.ticker, leases.period_end)]
    dup = leases.assign(quarter=quarter).duplicated(["ticker", "quarter"], keep=False)
    assert not dup.any(), leases[dup][["ticker", "period_end"]].to_string()


def test_lease_rows_are_complete(leases):
    assert set(leases.ticker) == TICKERS
    assert set(leases.form) <= {"10-K", "10-Q"}
    assert (leases.period_end >= "2021-01-01").all()
    assert (leases.filed > leases.period_end).all()
    assert leases.url.str.startswith("https://www.sec.gov/Archives/edgar/data/").all()
    have = leases.dropna(subset=["uncommenced_leases"])
    assert have.evidence.str.len().gt(20).all(), "every figure must carry the sentence it came from"


def test_newest_filing_of_every_company_has_a_figure(leases):
    # If the wording changes and the pattern stops matching, make_spenders carries the previous
    # quarter forward without saying so. Catch that here.
    newest = leases.sort_values("period_end").groupby("ticker").tail(1)
    assert newest.uncommenced_leases.notna().all(), newest[newest.uncommenced_leases.isna()].ticker.tolist()


def test_lease_figures_are_in_a_plausible_range(leases):
    # A million/billion mix-up or a neighbouring table cell shows up as a 1000x or 10x jump.
    have = leases.dropna(subset=["uncommenced_leases"]).sort_values(["ticker", "period_end"])
    assert have.uncommenced_leases.between(1e8, 2e12).all()
    ratio = have.groupby("ticker").uncommenced_leases.transform(lambda s: s / s.shift())
    assert ratio.dropna().between(0.1, 10).all(), have[~ratio.between(0.1, 10) & ratio.notna()][["ticker", "period_end"]].to_string()


def test_lease_evidence_contains_the_figure(leases):
    for r in leases.dropna(subset=["uncommenced_leases"]).itertuples():
        if r.ticker == "AMZN":
            shown = f"{r.uncommenced_leases / 1e6:,.0f}"
            assert r.evidence.rstrip().endswith(shown), (r.ticker, r.period_end)
        else:
            assert "$" in r.evidence, (r.ticker, r.period_end)


# --------------------------------------------------------------------------- financials / asset base


def test_financials_one_row_per_company_year():
    fin = load("financials.csv")
    assert not fin.duplicated(["ticker", "fiscal_year"]).any()
    assert (fin.fiscal_year == fin.period_end.str[:4].astype(int)).all()
    assert set(fin.ticker) == TICKERS


def test_eps_and_share_count_are_on_the_same_split_basis():
    # Alphabet and Amazon split 20-for-1 in 2022. A year whose EPS was restated but whose
    # share count was not (or the reverse) would be off by a factor of 20 here.
    fin = load("financials.csv").dropna(subset=["eps_diluted", "diluted_shares", "net_income"])
    fin = fin[fin.net_income.abs() >= 1e9]
    implied = fin.eps_diluted * fin.diluted_shares / fin.net_income
    bad = fin[(implied - 1).abs() > 0.06]
    assert bad.empty, bad[["ticker", "fiscal_year", "eps_diluted", "diluted_shares", "net_income"]].to_string()


def test_server_assets_one_positive_balance_per_company_year():
    assets = load("server_assets.csv")
    assert not assets.duplicated(["ticker", "fiscal_year"]).any()
    assert (assets.gross_server_assets > 0).all()
    assert (assets.fiscal_year == assets.period_end.str[:4].astype(int)).all()
    # `scale` is stored rounded to four decimals, hence the loose tolerance.
    assert np.allclose(assets.gross_server_assets, assets.reported_value * assets.scale, rtol=1e-3)
    assert set(assets.ticker) == TICKERS


def test_every_modeled_year_has_financials():
    scen, fin = load("scenarios.csv"), load("financials.csv")
    have = set(zip(fin.ticker, fin.fiscal_year))
    assert set(zip(scen.ticker, scen.fiscal_year)) <= have
    # ... and the headline (latest) year of each company is its latest asset balance.
    assets = load("server_assets.csv")
    assert scen.groupby("ticker").fiscal_year.max().to_dict() == assets.groupby("ticker").fiscal_year.max().to_dict()


def test_scenarios_one_row_per_company_year_life():
    scen = load("scenarios.csv")
    assert not scen.duplicated(["ticker", "fiscal_year", "life_years"]).any()
    assert set(scen.ticker) == TICKERS
    cols = ["modeled_server_depreciation", "counterfactual_server_depreciation", "extra_depreciation", "net_income_effect", "eps_restated"]
    assert np.isfinite(scen[cols].to_numpy()).all()
    assert (scen.modeled_server_depreciation > 0).all()
    # More depreciation always means less profit.
    assert (np.sign(scen.net_income_effect) == -np.sign(scen.extra_depreciation)).all()
    assert (np.sign(scen.eps_restated - scen.eps_reported) == -np.sign(scen.extra_depreciation)).all()


def test_additions_reconcile_to_the_asset_base():
    adds, assets = load("additions.csv"), load("server_assets.csv")
    assert (adds.additions >= 0).all() and (adds.retired >= 0).all()
    for ticker, a in adds.groupby("ticker"):
        a = a.sort_values("fiscal_year")
        balance = (a.additions - a.retired).cumsum()
        gross = assets[assets.ticker == ticker].set_index("fiscal_year").gross_server_assets
        modeled = pd.Series(balance.to_numpy(), index=a.fiscal_year.to_numpy()).reindex(gross.index)
        assert modeled.tolist() == pytest.approx(gross.tolist(), rel=1e-6), ticker


# --------------------------------------------------------------------------- outputs in step with inputs


def _same(run: pd.DataFrame, committed: pd.DataFrame, name: str) -> None:
    assert list(run.columns) == list(committed.columns), name
    assert len(run) == len(committed), name
    for col in run.columns:
        if pd.api.types.is_bool_dtype(run[col]) or pd.api.types.is_numeric_dtype(run[col]):
            np.testing.assert_allclose(
                run[col].to_numpy(dtype=float), committed[col].to_numpy(dtype=float), rtol=1e-9, atol=1e-6, equal_nan=True, err_msg=f"{name}.{col}"
            )
        else:
            assert run[col].astype(str).tolist() == committed[col].astype(str).tolist(), f"{name}.{col}"


def test_committed_model_outputs_match_a_fresh_run():
    # model.run only reads committed CSVs, so this needs no network. A failure means an input,
    # server_assets.csv or model.py changed without the outputs being regenerated.
    _, lag_table, validation, additions, scenarios = model.run()
    _same(validation, load("validation.csv"), "validation")
    _same(lag_table, load("retire_lag_fit.csv"), "retire_lag_fit")
    _same(additions, load("additions.csv"), "additions")
    _same(scenarios, load("scenarios.csv"), "scenarios")
