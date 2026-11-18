"""Step 2: the vintage depreciation model.

Question: how much of each company's reported profit depends on the useful
life it assumes for servers and network equipment?

Method, in three moves:

1. ADDITIONS. Companies disclose the gross balance of server assets each year,
   not what they bought. We back out purchases ("vintages") from the change in
   the gross balance, adding back assets assumed retired:
       additions[t] = gross[t] - gross[t-1] + retired[t]
   A vintage is assumed retired once it has been in service for the useful
   life in force that year plus RETIRE_LAG years. The lag that fits company
   disclosures best is long (the fit is almost as good with no retirements at
   all), so in practice purchases are close to the change in the gross balance.
   Results are reported as a range across this setting.

2. DEPRECIATION. Each vintage is depreciated straight-line. Assets bought
   during a year get a part-year of depreciation: half a year in the base case,
   a quarter in the low case (when spending is ramping, more of it lands late
   in the year). When a company changes its useful life, the change is applied
   the way GAAP requires - prospectively: remaining book value is spread over
   the remaining NEW life.

3. COUNTERFACTUALS.
   * "Always L years" (the run-rate): re-run step 2 as if the company had used
     L years throughout. This is the steady earnings effect of the assumption.
   * "Switch to L years now": keep history as reported and change the life at
     the start of the latest fiscal year. Old book value is caught up in one
     year, so this one-year shock is larger than the run-rate.

The after-tax effect uses a flat 21% rate (the US statutory rate). Single-year
effective rates swing with one-off items, and the companies' own disclosures of
these effects imply 19-23%.

The model is tested against the dollar impacts the companies themselves
disclosed when they changed useful lives (inputs/disclosed_impacts.csv).
"""
from __future__ import annotations

import math

import pandas as pd

import edgar

OUT = edgar.ROOT / "data" / "processed"
INPUTS = edgar.ROOT / "inputs"
RETIRE_LAG_CHOICES = [0, 1, 2, 3, 4, 5, 6, 7, 8, 99]  # 99 = never retired
SCENARIO_LIVES = [2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 8]
FIRST_OUTPUT_YEAR = 2019
TAX_RATE = 0.21
BASE_FIRST_YEAR = 0.5  # half-year convention
LOW_FIRST_YEAR = 0.25  # quarter-year: purchases back-loaded in a ramp


def _all_assets(policy: pd.DataFrame) -> pd.DataFrame:
    if "applies_to" not in policy.columns:
        return policy
    return policy[policy.applies_to.fillna("all") == "all"]


def policy_by_year(policy: pd.DataFrame, ticker: str, years: range) -> dict[int, float]:
    """Useful life in force in each fiscal year (the life applied to assets generally)."""
    rows = _all_assets(policy)
    rows = rows[rows.ticker == ticker].sort_values("from_fiscal_year")
    out = {}
    for y in years:
        in_force = rows[rows.from_fiscal_year <= y]
        out[y] = float(in_force.iloc[-1].life_years if not in_force.empty else rows.iloc[0].life_years)
    return out


def new_asset_lives(policy: pd.DataFrame, ticker: str) -> dict[int, float]:
    """Lives that apply only to assets bought from a given year on: {first_vintage: life}.

    Used where a company shortened the life of new equipment but left most of
    the installed base alone (Amazon, 2025).
    """
    if "applies_to" not in policy.columns:
        return {}
    rows = policy[(policy.ticker == ticker) & (policy.applies_to == "new_assets")]
    return {int(r.from_fiscal_year): float(r.life_years) for r in rows.itertuples()}


def estimate_additions(gross: dict[int, float], life: dict[int, float], retire_lag: float) -> pd.DataFrame:
    """Back out yearly purchases from gross balances. Returns year, additions, retired."""
    years = sorted(gross)
    y0 = years[0]
    n = max(1, math.ceil(life[y0]))
    # Opening balance: assume it was bought evenly over the preceding n years.
    vintages = {y0 - k: gross[y0] / n for k in range(n)}
    in_gross = dict(vintages)
    rows = [{"fiscal_year": v, "additions": a, "retired": 0.0, "seeded": True} for v, a in sorted(vintages.items())]
    for prev, t in zip(years, years[1:]):
        retired = 0.0
        for v in list(in_gross):
            if t - v >= life[t] + retire_lag:
                retired += in_gross.pop(v)
        add = max(0.0, gross[t] - gross[prev] + retired)
        if t - prev > 1:  # a gap in the data: spread evenly over the missing years
            for k in range(prev + 1, t + 1):
                vintages[k] = in_gross[k] = add / (t - prev)
                rows.append({"fiscal_year": k, "additions": add / (t - prev), "retired": retired if k == t else 0.0, "seeded": False})
        else:
            vintages[t] = in_gross[t] = add
            rows.append({"fiscal_year": t, "additions": add, "retired": retired, "seeded": False})
    return pd.DataFrame(rows)


def depreciate(
    additions: dict[int, float],
    life: dict[int, float],
    through: int,
    first_year_fraction: float = BASE_FIRST_YEAR,
    new_assets: dict[int, float] | None = None,
) -> dict[int, dict[int, float]]:
    """Depreciation by year and vintage: result[year][vintage].

    Straight-line; assets get `first_year_fraction` of a year's depreciation in
    the year they are bought; life changes are applied prospectively.
    `new_assets` = {first_vintage: life} overrides the life for assets bought in
    or after that year.
    """
    new_assets = new_assets or {}

    def life_for(t: int, v: int) -> float:
        starts = [k for k in new_assets if k <= v and k <= t]
        if starts:
            return new_assets[max(starts)]
        return life.get(t, life[max(life)] if t > max(life) else life[min(life)])

    nbv: dict[int, float] = {}
    out: dict[int, dict[int, float]] = {}
    first = min(additions)
    for t in range(first, through + 1):
        out[t] = {}
        for v in list(nbv):
            age = (t - v - 1) + first_year_fraction  # years in service at the start of year t
            remaining = life_for(t, v) - age
            dep = nbv[v] if remaining <= 1 else nbv[v] / remaining
            out[t][v] = dep
            nbv[v] -= dep
            if nbv[v] <= 1e-9:
                del nbv[v]
        if t in additions and additions[t] > 0:
            dep = min(additions[t], additions[t] * first_year_fraction / life_for(t, t))
            out[t][t] = dep
            nbv[t] = additions[t] - dep
    return out


def total(dep: dict[int, dict[int, float]], year: int, existing_only: bool = False) -> float:
    return sum(d for v, d in dep.get(year, {}).items() if not (existing_only and v == year))


def run(retire_lag: float | None = None, policy: pd.DataFrame | None = None, impacts: pd.DataFrame | None = None):
    """Run the whole model. `policy` / `impacts` override the input files (used by calibrate.py)."""
    policy = pd.read_csv(INPUTS / "useful_life_policy.csv") if policy is None else policy
    impacts = pd.read_csv(INPUTS / "disclosed_impacts.csv") if impacts is None else impacts
    assets = pd.read_csv(OUT / "server_assets.csv")
    fin = pd.read_csv(OUT / "financials.csv")

    def company_setup(ticker: str, lag: float):
        g = assets[assets.ticker == ticker].set_index("fiscal_year")["gross_server_assets"].to_dict()
        yrs = range(min(g) - 10, max(g) + 1)
        life = policy_by_year(policy, ticker, yrs)
        adds = estimate_additions(g, life, lag)
        return g, life, adds, adds.set_index("fiscal_year")["additions"].to_dict()

    # --- Validation: can the model reproduce what the companies disclosed? ---
    def validate(lag: float) -> pd.DataFrame:
        rows = []
        for r in impacts.itertuples():
            g, life, _, adds = company_setup(r.ticker, lag)
            if r.fiscal_year not in g or r.fiscal_year - 1 not in g:
                continue
            overrides = new_asset_lives(policy, r.ticker)
            before = {k: v for k, v in overrides.items() if k < r.fiscal_year}
            old = dict(life)
            old[r.fiscal_year] = r.old_life
            new = dict(life)
            new[r.fiscal_year] = r.new_life
            existing = r.basis == "existing"
            modeled = total(depreciate(adds, old, r.fiscal_year, new_assets=before), r.fiscal_year, existing) - total(
                depreciate(adds, new, r.fiscal_year, new_assets=overrides), r.fiscal_year, existing
            )
            rows.append(
                {
                    "ticker": r.ticker,
                    "fiscal_year": r.fiscal_year,
                    "change": f"{r.old_life:g} -> {r.new_life:g} yrs",
                    "basis": r.basis,
                    "disclosed_bn": r.disclosed_reduction_bn,
                    "modeled_bn": modeled / 1e9,
                    "error_pct": (modeled / 1e9 / r.disclosed_reduction_bn - 1) * 100,
                    "in_validation": r.in_validation == "yes",
                    "retire_lag": lag,
                }
            )
        return pd.DataFrame(rows)

    lag_table = []
    for lag in RETIRE_LAG_CHOICES:
        v = validate(lag)
        used = v[v.in_validation]
        lag_table.append({"retire_lag": lag, "mean_abs_error_pct": used.error_pct.abs().mean(), "median_error_pct": used.error_pct.median()})
    lag_table = pd.DataFrame(lag_table)
    if retire_lag is None:
        retire_lag = float(lag_table.sort_values("mean_abs_error_pct").iloc[0].retire_lag)
    validation = validate(retire_lag)

    # --- Scenarios ---
    # Each headline number is computed under the base settings and then under the
    # alternative retirement and first-year settings, to report a range.
    variants = [(retire_lag, BASE_FIRST_YEAR), (retire_lag, LOW_FIRST_YEAR), (0, BASE_FIRST_YEAR), (99, BASE_FIRST_YEAR)]
    add_rows, scen_rows = [], []
    for ticker in assets.ticker.unique():
        g, life, adds_df, adds = company_setup(ticker, retire_lag)
        adds_df.insert(0, "ticker", ticker)
        adds_df["gross_server_assets"] = adds_df.fiscal_year.map(g)
        add_rows.append(adds_df)
        last = max(g)
        overrides = new_asset_lives(policy, ticker)
        general = _all_assets(policy)
        pre_ext_life = float(general[general.ticker == ticker].sort_values("from_fiscal_year").iloc[0].life_years)
        f = fin[fin.ticker == ticker].set_index("fiscal_year")
        adds_by_lag = {retire_lag: adds}

        def gap(L: float, y: int, lag: float, frac: float) -> tuple[float, float, float]:
            """(reported-policy depreciation, always-L depreciation, share of the gap from this year's purchases)."""
            if lag not in adds_by_lag:
                adds_by_lag[lag] = company_setup(ticker, lag)[3]
            a = adds_by_lag[lag]
            base = depreciate(a, life, y, frac, overrides)
            alt = depreciate(a, {k: L for k in life}, y, frac)
            diff = total(alt, y) - total(base, y)
            this_year = alt[y].get(y, 0.0) - base[y].get(y, 0.0)
            return total(base, y), total(alt, y), (this_year / diff if abs(diff) > 1e-6 else float("nan"))

        for L in SCENARIO_LIVES:
            for y in range(max(FIRST_OUTPUT_YEAR, min(g) + 1), last + 1):
                if y not in f.index:
                    continue
                d_policy, d_alt, share_new = gap(L, y, retire_lag, BASE_FIRST_YEAR)
                delta = d_alt - d_policy
                band, switch = [delta], float("nan")
                if y == last:  # the range and the switch-now shock are only needed for the headline year
                    for lag, frac in variants[1:]:
                        p, a, _ = gap(L, y, lag, frac)
                        band.append(a - p)
                    now = dict(life)
                    now[y] = L
                    switch = total(depreciate(adds, now, y, BASE_FIRST_YEAR, overrides), y) - d_policy
                # A company with a loss gets no tax saving from extra depreciation.
                tax = TAX_RATE if f.loc[y, "net_income"] > 0 else 0.0
                ni_hit = delta * (1 - tax)
                scen_rows.append(
                    {
                        "ticker": ticker,
                        "fiscal_year": y,
                        "life_years": float(L),
                        "policy_life": life[y],
                        "pre_extension_life": pre_ext_life,
                        "modeled_server_depreciation": d_policy,
                        "counterfactual_server_depreciation": d_alt,
                        "extra_depreciation": delta,
                        "extra_depreciation_low": min(band),
                        "extra_depreciation_high": max(band),
                        "current_year_share": share_new,
                        "switch_now_extra_depreciation": switch,
                        "operating_income_reported": f.loc[y, "operating_income"],
                        "pct_of_operating_income": -delta / abs(f.loc[y, "operating_income"]) * 100,
                        "net_income_effect": -ni_hit,
                        "net_income_reported": f.loc[y, "net_income"],
                        "pct_of_net_income": -ni_hit / abs(f.loc[y, "net_income"]) * 100,
                        "eps_reported": f.loc[y, "eps_diluted"],
                        "eps_restated": f.loc[y, "eps_diluted"] - ni_hit / f.loc[y, "diluted_shares"],
                        "reported_total_depreciation": f.loc[y, "depreciation"],
                    }
                )
    additions = pd.concat(add_rows, ignore_index=True)
    scenarios = pd.DataFrame(scen_rows)
    return retire_lag, lag_table, validation, additions, scenarios


def main() -> None:
    lag, lag_table, validation, additions, scenarios = run()
    lag_table.to_csv(OUT / "retire_lag_fit.csv", index=False)
    validation.to_csv(OUT / "validation.csv", index=False)
    additions.to_csv(OUT / "additions.csv", index=False)
    scenarios.to_csv(OUT / "scenarios.csv", index=False)
    pd.set_option("display.width", 220)
    print("Retirement-lag fit:\n", lag_table.round(1).to_string(index=False))
    print(f"\nUsing retire_lag = {lag:g}\n\nValidation vs company disclosures:\n", validation.round(2).to_string(index=False))
    used = validation[validation.in_validation]
    print(f"\nMean absolute error on {len(used)} test rows: {used.error_pct.abs().mean():.1f}%  (worst {used.error_pct.abs().max():.1f}%)")


if __name__ == "__main__":
    main()
