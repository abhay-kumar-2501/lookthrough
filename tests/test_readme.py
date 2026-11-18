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
    assert len(readme.split()) < 1050  # the ledger table alone is about 130 of these


def test_headline_and_ledger_rows(readme, a):
    t = make_front.ledger_totals(a)
    assert "Microsoft, Alphabet, Amazon, Meta, Oracle and CoreWeave have borrowed" in readme and "OpenAI and Anthropic are not on this list" in readme
    assert f"have borrowed ${t['debt'] / 1e9:,.0f}bn. Count their leases and they have promised ${t['total'] / 1e12:.1f} trillion" in readme
    bn = lambda v: f"${v / 1e9:,.0f}bn"
    for r in a["leverage"]:
        row = f"| {a['names'][r['ticker']]} | {bn(r['debt'])} | {bn(r['leases'])} | {bn(r['signed'])} | {bn(r['debt'] + r['leases'] + r['signed'])} | {r['pro_forma']:.1f} ({r['today']:.1f}) |"
        assert row in readme, row
    assert f"| **Six together** | {bn(t['debt'])} | {bn(t['leases'])} | {bn(t['signed'])} | {bn(t['total'])} | {t['total'] / t['ebitda']:.1f} ({(t['debt'] + t['leases']) / t['ebitda']:.1f}) |" in readme
    order = [readme.index(f"| {a['names'][r['ticker']]} |") for r in sorted(a["leverage"], key=lambda r: -r["pro_forma"])]
    assert order == sorted(order), "the ledger is listed from the longest bill to the shortest"


def test_lease_and_ratio_sentences(readme, a):
    total = sum(r["value"] for r in a["leases"]["latest"])
    t = make_front.ledger_totals(a)
    assert f"${total / 1e12:.2f} trillion; the ledger counts them at ${t['signed'] / 1e9:,.0f}bn" in readme
    lev = {r["ticker"]: r for r in a["leverage"]}
    for ticker, name in (("ORCL", "Oracle"), ("CRWV", "CoreWeave")):
        assert re.search(rf"{name} from {lev[ticker]['today']:.1f} to {lev[ticker]['pro_forma']:.1f}", readme), name
    rest = [r["pro_forma"] for tk, r in lev.items() if tk not in ("ORCL", "CRWV")]
    ceiling = math.ceil(max(rest) * 10) / 10
    assert len(rest) == 4 and f"four of the six have promised under {ceiling:.1f} years" in readme and max(rest) < ceiling


def test_fund_and_cash_numbers(readme, a):
    sp = next(f for f in make_front.funds_payload() if f["key"] == "sp500")
    assert f"{sp['customers']:.0f} cents of every dollar in the six companies building AI's data centers and {sp['nvidia'] + sp['other_ai']:.0f} in the companies that sell them the equipment" in readme
    su = a["sources_uses"]
    share = sum(r["capex"] for r in su) / sum(r["cfo"] for r in su)
    assert f"{share * 100:.0f} cents of every dollar of cash their operations generate" in readme
    assert f"${sum(r['raised'] or 0 for r in su) / 1e9:,.0f}bn of new long-term debt" in readme
    assert f"${sum(r['shares'] or 0 for r in su) / 1e9:,.0f}bn of new shares" in readme


def test_fund_and_read_sentences(readme, a):
    funds = {f["key"]: f for f in make_front.funds_payload()}
    tot = lambda f: f["nvidia"] + f["customers"] + f["other_ai"]
    assert f"A 2060 target-date fund has {tot(funds['target_2060']):.0f} cents in both together, a 2030 one {tot(funds['target_2030']):.0f}." in readme
    small = sum(funds["sp500"]["by_customer"][n] for n in ("Oracle", "CoreWeave"))
    assert f"({small:.1f} cents of each dollar in an S&P 500 fund)" in readme
    t = make_front.ledger_totals(a)
    assert f"{make_front.rent_share_in_words(t)} of it rent" in readme
    assert readme.startswith("# Lookthrough\n")


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
    assert f"{n} source figures" in readme
