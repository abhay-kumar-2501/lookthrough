"""Back out the blended useful lives the filings do not state outright.

Three policy entries in inputs/useful_life_policy.csv are marked CALIBRATED:

  * Meta 2022-2024. The 10-K gives a range ("four to five years") because
    different server cohorts were on different lives. We solve for the single
    blended life at which the model reproduces the $2.92bn depreciation
    reduction Meta disclosed when it moved to 5.5 years in 2025.
  * Amazon 2025, assets already owned. Amazon cut "a subset" of servers from
    six to five years without sizing it, and said the change would cost about
    $0.7bn on assets held at the end of 2024. We solve for the blended life of
    those assets that reproduces $0.7bn.
  * Amazon 2025, new assets. The effect Amazon later reported, including assets
    bought during 2025, was $1.4bn. The extra $0.7bn must come from new
    equipment, so we solve for the blended life of 2025 purchases.

Because these disclosures are used to set inputs, they are excluded from the
validation table. Run this script to see where the numbers come from.
"""
from __future__ import annotations

import pandas as pd

import model


def modeled(policy: pd.DataFrame, impacts: pd.DataFrame, ticker: str, year: int, lag: float) -> float:
    _, _, v, _, _ = model.run(lag, policy=policy, impacts=impacts)
    return float(v[(v.ticker == ticker) & (v.fiscal_year == year)].modeled_bn.iloc[0])


def bisect(f, lo: float, hi: float, target: float, steps: int = 30) -> float:
    """Find x in [lo, hi] with f(x) = target, for monotonic f."""
    increasing = f(hi) > f(lo)
    for _ in range(steps):
        mid = (lo + hi) / 2
        if (f(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def main() -> None:
    policy = pd.read_csv(model.INPUTS / "useful_life_policy.csv")
    impacts = pd.read_csv(model.INPUTS / "disclosed_impacts.csv")
    lag, *_ = model.run()
    amzn_2025 = (policy.ticker == "AMZN") & (policy.from_fiscal_year == 2025)

    def meta(x: float) -> float:
        p, i = policy.copy(), impacts.copy()
        p.loc[(p.ticker == "META") & (p.from_fiscal_year == 2022), "life_years"] = x
        i.loc[(i.ticker == "META") & (i.fiscal_year == 2025), "old_life"] = x
        return modeled(p, i, "META", 2025, lag)

    def amzn(existing_life: float, new_life: float, basis: str) -> float:
        p, i = policy.copy(), impacts.copy()
        p.loc[amzn_2025 & (p.applies_to == "all"), "life_years"] = existing_life
        p.loc[amzn_2025 & (p.applies_to == "new_assets"), "life_years"] = new_life
        i.loc[(i.ticker == "AMZN") & (i.fiscal_year == 2025), "new_life"] = existing_life
        _, _, v, _, _ = model.run(lag, policy=p, impacts=i)
        row = v[(v.ticker == "AMZN") & (v.fiscal_year == 2025) & (v.basis == basis)]
        return float(row.modeled_bn.iloc[0])

    m = bisect(meta, 4.0, 5.0, 2.92)
    e = bisect(lambda x: amzn(x, 6.0, "existing"), 5.0, 5.999, -0.7)
    n = bisect(lambda x: amzn(e, x, "existing_and_new"), 3.0, 6.0, -1.4)
    print(f"Meta 2022-2024 blended life that reproduces $2.92bn:        {m:.2f} years (stated range 4-5)")
    print(f"Amazon 2025, assets owned at end-2024, reproduces -$0.7bn:   {e:.2f} years (about {(6 - e) * 100:.0f}% of them moved to five)")
    print(f"Amazon 2025, assets bought in 2025, reproduces -$1.4bn total: {n:.2f} years (about {(6 - n) * 100:.0f}% of them on five)")
    print("Compare with the values in inputs/useful_life_policy.csv and update that file if they differ.")


if __name__ == "__main__":
    main()
