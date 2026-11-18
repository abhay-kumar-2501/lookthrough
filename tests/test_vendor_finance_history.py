"""vendor_finance_history: the 1997-2003 telecom vendor-financing ratios, on hand-made rows and on the committed CSVs."""
from __future__ import annotations

import csv
import io

import pandas as pd
import pytest

import vendor_finance_history as vf

HEADER = ["company", "cik", "fiscal_period_end", "form", "item", "amount_usd_millions", "evidence", "url", "verified", "notes"]
URL = "https://www.sec.gov/Archives/edgar/data/1006240/0000950123-00-000001.txt"


def write_input(tmp_path, rows):
    path = tmp_path / "in.csv"
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({"company": "Lucent Technologies", "cik": "1006240", "fiscal_period_end": "2000-09-30", "form": "10-K", "url": URL,
                        "verified": "yes", "notes": "", "evidence": "Commitments to extend credit 1,898", **r})
    return path


def rec(company="Lucent Technologies", period="2000-09-30", **items):
    out = {"company": company, "cik": "1", "fiscal_period_end": period, "_missing": []}
    out.update(items)
    return out


# --------------------------------------------------------------------------- load / pivot


def test_load_accepts_a_good_row_and_an_empty_amount(tmp_path):
    path = write_input(tmp_path, [{"item": "revenue", "amount_usd_millions": "33,000".replace(",", "")},
                                  {"item": "guarantees", "amount_usd_millions": "", "evidence": "", "verified": "no"}])
    assert len(vf.load(path)) == 2


@pytest.mark.parametrize("bad", [
    {"item": "made_up_item", "amount_usd_millions": "1"},
    {"item": "revenue", "amount_usd_millions": "1", "company": "Enron"},
    {"item": "revenue", "amount_usd_millions": "1", "verified": "maybe"},
    {"item": "revenue", "amount_usd_millions": "1", "url": "https://example.com/x"},
    {"item": "revenue", "amount_usd_millions": "1", "verified": "no"},       # a number must be verified
    {"item": "revenue", "amount_usd_millions": "1", "evidence": "  "},       # and carry its sentence
    {"item": "revenue", "amount_usd_millions": "1,000"},                      # thousand separators are not numbers
    {"item": "revenue", "amount_usd_millions": "$1000"},
])
def test_load_refuses_rows_that_break_the_rules(tmp_path, bad):
    with pytest.raises(ValueError):
        vf.load(write_input(tmp_path, [bad]))


def test_pivot_groups_by_company_and_period_and_records_gaps():
    rows = [
        dict(company="Lucent Technologies", cik="1", fiscal_period_end="2000-09-30", item="revenue", amount_usd_millions="33.5"),
        dict(company="Lucent Technologies", cik="1", fiscal_period_end="2000-09-30", item="guarantees", amount_usd_millions=""),
        dict(company="Lucent Technologies", cik="1", fiscal_period_end="2001-09-30", item="revenue", amount_usd_millions="21"),
    ]
    out = vf.pivot(rows)
    a = out[("Lucent Technologies", "2000-09-30")]
    assert a["revenue"] == 33.5 and a["_missing"] == ["guarantees"] and "guarantees" not in a
    assert out[("Lucent Technologies", "2001-09-30")]["revenue"] == 21


def test_pivot_adds_current_and_non_current_lease_receivables():
    rows = [dict(company="Cisco Systems", cik="1", fiscal_period_end="2000-07-31", item="lease_receivables_net", amount_usd_millions=v)
            for v in ("300", "450")]
    assert vf.pivot(rows)[("Cisco Systems", "2000-07-31")]["lease_receivables_net"] == 750


def test_pivot_refuses_a_repeated_item_that_may_not_repeat():
    rows = [dict(company="Cisco Systems", cik="1", fiscal_period_end="2000-07-31", item="revenue", amount_usd_millions="1")] * 2
    with pytest.raises(ValueError):
        vf.pivot(rows)


# --------------------------------------------------------------------------- ratio helper


def test_ratio_handles_missing_and_non_positive_denominators():
    assert vf._ratio(1, 4) == 0.25
    assert vf._ratio(None, 4) is None
    assert vf._ratio(1, None) is None
    assert vf._ratio(1, 0) is None
    assert vf._ratio(1, -3) is None
    assert vf._ratio(0, 4) == 0.0


# --------------------------------------------------------------------------- derive: calendars


@pytest.mark.parametrize("company, period, ptype, fy", [
    ("Lucent Technologies", "2000-09-30", "annual", 2000),
    ("Lucent Technologies", "2000-12-31", "quarter", 2001),   # first quarter of Lucent's fiscal 2001
    ("Lucent Technologies", "2001-03-31", "quarter", 2001),
    ("Cisco Systems", "2000-07-31", "annual", 2000),
    ("Cisco Systems", "2000-10-31", "quarter", 2001),
    ("Nortel Networks", "2000-12-31", "annual", 2000),
    ("Nortel Networks", "2000-09-30", "quarter", 2000),
    ("Motorola", "2001-12-31", "annual", 2001),
])
def test_period_type_and_fiscal_year(company, period, ptype, fy):
    out = vf.derive(rec(company=company, period=period))
    assert (out["period_type"], out["fiscal_year"]) == (ptype, fy)


# --------------------------------------------------------------------------- derive: loans and guarantees


def test_drawn_loans_basis_precedence():
    assert vf.derive(rec(drawn_outstanding=500.0, drawn_outstanding_net=400.0, reserves=100.0))["loans_drawn_gross"] == 500.0
    r = vf.derive(rec(drawn_outstanding_net=400.0, reserves=100.0))
    assert r["loans_drawn_gross"] == 500.0 and r["drawn_basis"] == "net figure plus reserve"
    r = vf.derive(rec(drawn_outstanding_net=400.0))
    assert r["loans_drawn_gross"] == 400.0 and "lower bound" in r["drawn_basis"]
    assert vf.derive(rec())["loans_drawn_gross"] is None


def test_drawn_plus_guarantees_adds_loans_leases_and_guarantees_once():
    r = vf.derive(rec(drawn_outstanding=500.0, lease_receivables_gross=300.0, guarantees=200.0, commitments_guarantees=900.0))
    assert r["drawn_plus_guarantees"] == 1000.0          # the 900 commitment is not added on top of the 200 outstanding
    assert r["guarantees_basis"] == "outstanding as stated"


def test_guarantee_commitment_is_used_only_when_nothing_outstanding_is_stated():
    r = vf.derive(rec(drawn_outstanding=500.0, commitments_guarantees=900.0))
    assert r["drawn_plus_guarantees"] == 1400.0 and "upper bound" in r["guarantees_basis"]


def test_gross_lease_receivables_win_over_net():
    r = vf.derive(rec(lease_receivables_gross=300.0, lease_receivables_net=250.0))
    assert r["drawn_plus_guarantees"] == 300.0


def test_net_lease_receivables_used_when_gross_missing():
    assert vf.derive(rec(lease_receivables_net=250.0))["drawn_plus_guarantees"] == 250.0


def test_guarantees_alone_do_not_make_a_drawn_figure():
    assert vf.derive(rec(guarantees=200.0))["drawn_plus_guarantees"] is None


# --------------------------------------------------------------------------- derive: financing made available


def test_made_available_total_as_stated():
    r = vf.derive(rec(commitments_total=7000.0, commitments_loans=1.0))
    assert (r["financing_made_available"], r["made_available_basis"]) == (7000.0, "total as stated")


def test_made_available_loans_plus_guarantee_commitments():
    r = vf.derive(rec(commitments_loans=6000.0, commitments_guarantees=1500.0))
    assert r["financing_made_available"] == 7500.0 and r["made_available_basis"] == "loan commitments + guarantee commitments"
    r = vf.derive(rec(commitments_loans=6000.0))
    assert r["financing_made_available"] == 6000.0 and r["made_available_basis"] == "loan commitments only"


def test_made_available_undrawn_plus_drawn_plus_guarantees():
    r = vf.derive(rec(commitments_undrawn=2000.0, drawn_outstanding=500.0, guarantees=300.0))
    assert r["financing_made_available"] == 2800.0
    assert r["made_available_basis"] == "undrawn + loans drawn + guarantees"
    assert vf.derive(rec(commitments_undrawn=2000.0))["made_available_basis"] == "undrawn only (lower bound)"


def test_finance_leases_are_added_to_whatever_was_made_available():
    r = vf.derive(rec(commitments_total=7000.0, lease_receivables_net=800.0))
    assert r["financing_made_available"] == 7800.0 and r["made_available_basis"].endswith("+ finance leases")
    assert vf.derive(rec(lease_receivables_net=800.0))["financing_made_available"] is None  # leases alone are not "made available"


# --------------------------------------------------------------------------- derive: ratios


def test_ratios_to_annual_revenue():
    r = vf.derive(rec(period="2000-09-30", commitments_total=7000.0, drawn_outstanding=1000.0, revenue=35000.0))
    assert r["revenue_annualized"] == 35000.0
    assert r["available_to_revenue"] == pytest.approx(0.2)
    assert r["drawn_plus_guarantees_to_revenue"] == pytest.approx(1000 / 35000)


def test_quarterly_revenue_is_multiplied_by_four():
    r = vf.derive(rec(period="2000-12-31", commitments_total=7000.0, revenue=8750.0))
    assert r["period_type"] == "quarter" and r["revenue_annualized"] == 35000.0
    assert r["available_to_revenue"] == pytest.approx(0.2)


def test_days_sales_outstanding_uses_365_for_a_year_and_91_for_a_quarter():
    annual = vf.derive(rec(period="2000-09-30", receivables=9125.0, revenue=36500.0))
    assert annual["dso_days"] == pytest.approx(9125 / 36500 * 365) == pytest.approx(91.25)
    quarter = vf.derive(rec(period="2000-12-31", receivables=2275.0, revenue=9100.0))
    assert quarter["dso_days"] == pytest.approx(2275 / 9100 * 91)


def test_no_revenue_means_no_ratios():
    r = vf.derive(rec(commitments_total=7000.0, receivables=100.0))
    assert r["available_to_revenue"] is None and r["dso_days"] is None


# --------------------------------------------------------------------------- derive: reserves


def test_reserve_share_of_drawn_loans():
    r = vf.derive(rec(drawn_outstanding=900.0, reserves=100.0))
    assert r["reserve_share_of_drawn"] == pytest.approx(100 / 900)


def test_lucent_reserve_also_covers_guarantees_but_others_do_not():
    kwargs = dict(drawn_outstanding=900.0, guarantees=100.0, reserves=100.0)
    assert vf.derive(rec(company="Lucent Technologies", **kwargs))["reserve_share_of_drawn"] == pytest.approx(100 / 1000)
    assert vf.derive(rec(company="Nortel Networks", period="2000-12-31", **kwargs))["reserve_share_of_drawn"] == pytest.approx(100 / 900)


def test_lease_reserves_pool_with_loan_reserves():
    r = vf.derive(rec(company="Cisco Systems", period="2000-07-31", drawn_outstanding=800.0, reserves=80.0,
                      lease_receivables_gross=200.0, lease_reserves=20.0))
    assert r["reserve_share_of_drawn"] == pytest.approx(100 / 1000)


def test_not_disclosed_is_sorted_and_unique():
    r = vf.derive(rec(_missing=["reserves", "guarantees", "reserves"]))
    assert r["not_disclosed"] == "guarantees, reserves"


# --------------------------------------------------------------------------- peaks


def test_peak_is_the_largest_financing_made_available_and_charges_run_from_there():
    a = vf.derive(rec(period="1999-09-30", commitments_total=1000.0, charges=1.0))
    b = vf.derive(rec(period="2000-09-30", commitments_total=5000.0, charges=50.0, charges_customer_financing=20.0, reserves=300.0))
    c = vf.derive(rec(period="2001-09-30", commitments_total=3000.0, charges=800.0, charges_customer_financing=300.0, reserves=700.0))
    d = vf.derive(rec(period="2002-09-30", commitments_total=1000.0, charges=1200.0, charges_customer_financing=500.0, reserves=400.0))
    e = vf.derive(rec(period="2004-09-30", commitments_total=500.0, charges=9999.0))   # fiscal 2004: after the window
    records = [a, b, c, d, e]
    vf.add_peaks(records)
    assert [r["is_peak"] for r in records] == ["", "yes", "", "", ""]
    assert b["charges_from_peak"] == 50 + 800 + 1200            # 1999 is before the peak, 2004 after the window
    assert b["charges_share_of_peak"] == pytest.approx(2050 / 5000)
    assert b["narrow_charges_from_peak"] == 20 + 300 + 500
    assert b["narrow_charges_share_of_peak"] == pytest.approx(820 / 5000)
    assert b["peak_reserve_balance"] == 700.0                    # the highest balance in any period, not at the peak
    assert b["peak_reserve_share_of_peak"] == pytest.approx(700 / 5000)


def test_quarters_never_count_as_charges_but_can_be_the_peak():
    q = vf.derive(rec(period="2000-12-31", commitments_total=9000.0, charges=500.0))
    y = vf.derive(rec(period="2001-09-30", commitments_total=1000.0, charges=40.0))
    vf.add_peaks([q, y])
    assert q["is_peak"] == "yes" and q["charges_from_peak"] == 40.0


def test_company_without_any_total_has_no_peak():
    r = vf.derive(rec(drawn_outstanding=1.0))
    vf.add_peaks([r])
    assert r["is_peak"] == ""


def test_peaks_are_found_per_company():
    a = vf.derive(rec(company="Lucent Technologies", period="2000-09-30", commitments_total=5000.0))
    b = vf.derive(rec(company="Motorola", period="2000-12-31", commitments_total=700.0))
    vf.add_peaks([a, b])
    assert a["is_peak"] == b["is_peak"] == "yes"


# --------------------------------------------------------------------------- writing


def test_cell_formatting_keeps_four_decimals_for_ratios_and_one_for_big_numbers():
    assert vf._cell(None) == ""
    assert vf._cell(0.123456) == "0.1235"
    assert vf._cell(0.5) == "0.5"
    assert vf._cell(12345.678) == "12345.7"
    assert vf._cell(7000.0) == "7000"
    assert vf._cell("annual") == "annual"


def test_write_round_trips_through_csv(tmp_path):
    r = vf.derive(rec(commitments_total=7000.0, revenue=35000.0))
    path = tmp_path / "out.csv"
    vf.write([r], path)
    back = pd.read_csv(path)
    assert list(back.columns) == vf.OUT_COLUMNS
    assert back.financing_made_available[0] == 7000 and back.available_to_revenue[0] == pytest.approx(0.2)


# --------------------------------------------------------------------------- the committed input file


@pytest.fixture(scope="module")
def raw_rows(root):
    with open(root / "inputs" / "vendor_finance_2000.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def test_input_passes_the_modules_own_validation():
    assert len(vf.load()) > 100


def test_every_amount_is_numeric_or_empty(raw_rows):
    for n, r in enumerate(raw_rows, start=2):
        a = r["amount_usd_millions"]
        if a != "":
            float(a)
            assert a == a.strip() and "," not in a and "$" not in a, f"line {n}: {a!r}"


def test_every_filled_row_has_evidence_a_sec_url_and_is_verified(raw_rows):
    for n, r in enumerate(raw_rows, start=2):
        if r["amount_usd_millions"] != "":
            assert len(r["evidence"].strip()) > 15, f"line {n}"
            assert r["url"].startswith("https://www.sec.gov/Archives/edgar/data/"), f"line {n}"
            assert r["verified"] == "yes", f"line {n}"


def test_no_item_is_entered_twice_for_the_same_company_and_period(raw_rows):
    seen = {}
    for n, r in enumerate(raw_rows, start=2):
        key = (r["company"], r["fiscal_period_end"], r["item"])
        if key in seen and r["item"] not in vf.MAY_REPEAT:
            pytest.fail(f"line {n} repeats line {seen[key]}: {key}")
        seen.setdefault(key, n)


def test_cik_is_constant_for_each_company_and_dates_are_iso(raw_rows):
    ciks = {}
    for r in raw_rows:
        ciks.setdefault(r["company"], set()).add(r["cik"])
        assert len(r["fiscal_period_end"]) == 10 and r["fiscal_period_end"][4] == "-"
    assert all(len(v) == 1 for v in ciks.values()), ciks


def test_money_amounts_are_non_negative_and_not_absurd(raw_rows):
    for n, r in enumerate(raw_rows, start=2):
        if r["amount_usd_millions"] != "" and r["item"] != "net_income":
            v = float(r["amount_usd_millions"])
            if r["item"] == "charges":
                assert v >= 0 or "Negative" in r["notes"], f"line {n}: a negative charge must say it is a recovery"
            else:
                assert v >= 0, f"line {n} {r['item']}"
            assert v < 100_000, f"line {n} {r['item']} = {v} million"   # no vendor had $100bn of anything


# --------------------------------------------------------------------------- the committed output file


@pytest.fixture(scope="module")
def history(processed):
    return pd.read_csv(processed / "vendor_finance_history.csv")


def test_output_has_the_documented_columns_and_unique_keys(history):
    assert list(history.columns) == vf.OUT_COLUMNS
    assert not history.duplicated(["company", "fiscal_period_end"]).any()


def test_committed_output_is_what_the_code_produces_from_the_committed_input(history):
    built = pd.DataFrame(vf.build())
    for col in ["financing_made_available", "available_to_revenue", "drawn_plus_guarantees", "dso_days", "reserve_share_of_drawn", "charges_share_of_peak"]:
        got = history.set_index(["company", "fiscal_period_end"])[col]
        want = built.set_index(["company", "fiscal_period_end"])[col].astype(float)
        assert got.index.equals(want.index) or set(got.index) == set(want.index)
        # the file keeps 4 decimals below 10 and 1 decimal above
        assert got.sort_index().tolist() == pytest.approx(want.sort_index().tolist(), rel=1e-3, abs=0.06, nan_ok=True), col


def test_each_company_has_exactly_one_peak_and_it_is_the_maximum(history):
    for name, g in history.groupby("company"):
        if g.financing_made_available.notna().any():
            peaks = g[g.is_peak == "yes"]
            assert len(peaks) == 1, name
            assert peaks.financing_made_available.iloc[0] == g.financing_made_available.max()


def test_ratios_equal_their_numerators_over_denominators(history):
    ok = history.available_to_revenue.notna()
    assert (history.financing_made_available / history.revenue_annualized)[ok].tolist() == pytest.approx(history.available_to_revenue[ok].tolist(), abs=6e-5)
    ok = history.drawn_plus_guarantees_to_revenue.notna()
    assert (history.drawn_plus_guarantees / history.revenue_annualized)[ok].tolist() == pytest.approx(history.drawn_plus_guarantees_to_revenue[ok].tolist(), abs=6e-5)


def test_annualized_revenue_follows_the_period_type(history):
    """Every company on one yardstick: the latest quarter's sales times four, the same as NVIDIA."""
    for r in history.itertuples():
        if r.period_type == "quarter" and pd.notna(r.revenue):
            assert r.revenue_annualized == pytest.approx(r.revenue * 4) and r.sales_basis == "latest quarter x 4"
        elif r.period_type == "annual" and pd.notna(r.revenue_q4):
            assert r.revenue_annualized == pytest.approx(r.revenue_q4 * 4) and r.sales_basis == "latest quarter x 4"
        elif r.period_type == "annual" and pd.notna(r.revenue):
            assert r.revenue_annualized == pytest.approx(r.revenue) and r.sales_basis.startswith("fiscal year")
    assert (history.sales_basis == "latest quarter x 4").mean() > 0.9, "almost every period should have a quarterly figure"


def test_the_highest_readings_on_both_yardsticks(history):
    """Rebuilt independently from the filings during the November 2026 audit."""
    want = {"Lucent Technologies": (0.321, 0.1455, 0.2776, 0.1409), "Nortel Networks": (0.2697, 0.1283, 0.2331, 0.1056),
            "Cisco Systems": (0.2009, 0.0953, 0.1549, 0.0800), "Motorola": (0.1308, 0.1230, 0.1172, 0.1109)}
    for company, (promised, in_force, promised_ttm, in_force_ttm) in want.items():
        g = history[history.company == company]
        assert g.available_to_revenue.max() == pytest.approx(promised, abs=6e-4), company
        assert g.drawn_plus_guarantees_to_revenue.max() == pytest.approx(in_force, abs=6e-4), company
        assert g.available_to_revenue_trailing.max() == pytest.approx(promised_ttm, abs=6e-4), company
        assert g.drawn_plus_guarantees_to_revenue_trailing.max() == pytest.approx(in_force_ttm, abs=6e-4), company


def test_trailing_sales_need_four_quarters_or_a_fiscal_year(history):
    r = history[(history.company == "Nortel Networks") & (history.fiscal_period_end == "2002-06-30")].iloc[0]
    assert r.revenue_trailing == pytest.approx(3694 + 3456 + 2912 + 2773)
    annual = history[(history.period_type == "annual") & history.revenue.notna()]
    assert annual.revenue_trailing.notna().all()


def test_ratios_are_plausible_fractions_of_revenue(history):
    assert history.available_to_revenue.dropna().between(0, 1.5).all()
    assert history.dso_days.dropna().between(10, 250).all()
    assert history.reserve_share_of_drawn.dropna().between(0, 1).all()
    assert history.charges_share_of_peak.dropna().between(0, 1.5).all()
    assert (history.narrow_charges_share_of_peak.dropna() <= history.charges_share_of_peak.max() + 1e-9).all()


def test_narrow_charges_are_never_more_than_all_charges(history):
    both = history[history.narrow_charges_from_peak.notna() & history.charges_from_peak.notna()]
    assert (both.narrow_charges_from_peak <= both.charges_from_peak + 1e-9).all()


def test_lucents_trailing_year_never_mixes_quarters_with_and_without_a_separated_business(history):
    """June 2000 is the first quarter reported without Avaya; March 2001 the first without Agere."""
    g = history[history.company == "Lucent Technologies"].set_index("fiscal_period_end")
    assert g.loc["2000-06-30", "revenue_trailing"] == pytest.approx(8713 + 8355 + 8065 + 8347)   # the three earlier quarters as restated without Avaya
    assert g.loc["2001-03-31", "revenue_trailing"] == pytest.approx(5915 + 4354 + 7172 + 7412)   # ... and without Agere
    assert g.loc["1999-12-31", "revenue_trailing"] == pytest.approx(8672 + 9315 + 10575 + 9905)  # before either separation: as first reported
