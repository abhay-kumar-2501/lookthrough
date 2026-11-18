"""The README is written by hand. These tests fail when a number it quotes no longer matches the data."""
from __future__ import annotations

import math
import re

import pandas as pd
import pytest

import make_front


@pytest.fixture(scope="module")
def readme(root):
    return (root / "README.md").read_text()


@pytest.fixture(scope="module")
def a():
    return make_front.build_payload()["argument"]


def test_readme_is_short(readme):
    assert len(readme.split()) < 700


def test_finding_1_numbers(readme, a):
    su = a["sources_uses"]
    share = sum(r["capex"] for r in su) / sum(r["cfo"] for r in su)
    assert f"{share * 100:.0f} cents of every dollar of cash their operations generate" in readme
    assert f"${sum(r['raised'] for r in su) / 1e9:,.0f}bn of new debt" in readme
    assert f"${sum(r['shares'] or 0 for r in su) / 1e9:,.0f}bn of new shares" in readme
    over = sum(1 for r in a["funding"]["rows"] if r["capex_share"] > 1)
    assert {3: "Three"}.get(over, str(over)) + " of them spend more than they generate" in readme


def test_finding_2_numbers(readme, a):
    total = sum(r["value"] for r in a["leases"]["latest"])
    base = sum(r["base"] for r in a["pv"]["rows"])
    assert f"${total / 1e12:.2f} trillion" in readme and f"${base / 1e9:,.0f}bn in today's money" in readme
    assert base > sum(r["debt"] for r in a["pv"]["rows"]), "the README says the leases are worth more than everything the six have borrowed"


def test_finding_3_numbers(readme, a):
    lev = {r["ticker"]: r for r in a["leverage"]}
    for ticker, name in (("ORCL", "Oracle"), ("CRWV", "CoreWeave")):
        assert re.search(rf"{name} from {lev[ticker]['today']:.1f} to {lev[ticker]['pro_forma']:.1f}", readme), name
    rest = max(r["pro_forma"] for t, r in lev.items() if t not in ("ORCL", "CRWV"))
    ceiling = math.ceil(rest * 10) / 10
    assert f"stay under {ceiling:.1f}" in readme and rest < ceiling


def test_finding_4_numbers(readme, a):
    s = a["nvidia"]["summary"]
    assert f"${s['narrow'] / 1e9:,.0f}bn of guarantees and investments promised, {s['narrow_share'] * 100:.0f}% of its annual rate of sales" in readme
    assert f"Only {s['in_effect_share'] * 100:.1f}% is in force" in readme
    assert f"({s['dso']:.0f} days, against {s['dso_year_ago']:.0f} a year earlier)" in readme
    promised = [c["high_promised"] for c in a["nvidia"]["history"]]
    in_force = [c["peak_in_force_ratio"] for c in a["nvidia"]["history"]]
    assert f"{min(promised) * 100:.0f}% to {max(promised) * 100:.0f}% of sales and had {min(in_force) * 100:.0f}% to {max(in_force) * 100:.0f}% actually lent or in force" in readme
    # the README says NVIDIA sits inside the telecom range on promises and below it on what is in force
    assert min(promised) < s["narrow_share"] < max(promised) and s["in_effect_share"] < min(in_force)
    last = a["nvidia"]["financing"][-1]
    assert last["guarantee_2029"] > s["narrow"] / 2, "the README says most of the total is one guarantee"


def test_readme_points_at_files_that_exist(readme, root):
    for path in re.findall(r"\((charts/[^)]+|docs)\)", readme):
        assert (root / path).exists(), path
    for page in re.findall(r"`([a-z]+\.html)`", readme):
        assert (root / "docs" / page).exists(), page
    for folder in re.findall(r"^\| `([a-z/]+/)` \|", readme, flags=re.M):
        assert (root / folder).is_dir(), folder
    for module in re.findall(r"`([a-z_]+)`", readme):
        if module.startswith("make_"):
            continue
        assert (root / "src" / f"{module}.py").exists(), module


def test_readme_date_matches_the_latest_filing_read(readme, a):
    latest = pd.Timestamp(a["latest_filing"]).strftime("%-d %B %Y")
    assert f"up to {latest}" in readme


def test_checks_folder_has_as_many_figures_as_the_readme_says(readme, root):
    n = len(pd.read_csv(root / "checks" / "author_checks.csv"))
    assert f"The {n} headline figures" in readme
