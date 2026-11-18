"""nvidia_financing: figure extraction from filing text, derived revenue, NARROW / BROAD sums, and the committed CSVs."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd
import pytest

import nvidia_financing as nf

SPEC = {s["item"]: s for s in nf.SPECS}
URL = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000075/nvda-20260726.htm"


def get(item, text):
    hit = nf.extract(SPEC[item], text)
    return None if hit is None else hit[0]


TABLE_HEAD = ("Future commitments by fiscal year as of July 26, 2026, were as follows: Remainder of 2027 2028 2029 2030 2031 "
              "2032 and thereafter Total (In billions)")


# --------------------------------------------------------------------------- _usd and the add-up check


def test_usd_scales_million_and_billion_and_ignores_case():
    assert nf._usd("1,234", "million") == 1_234_000_000
    assert nf._usd("4.5", "Billion") == 4_500_000_000


@pytest.mark.parametrize("cells, ok", [
    ("$ 18 $ 3 $ 2 $ 2 — — $ 25", True),
    ("18 3 2 2 — — 26", True),     # within the 3 allowed for rounding
    ("18 3 2 2 — — 99", False),
    ("25", False),
])
def test_row_adds_up(cells, ok):
    assert nf._row_adds_up(cells) is ok


# --------------------------------------------------------------------------- table rows in $ billions


def test_equity_investment_row_in_the_commitments_table():
    text = TABLE_HEAD + " Supply and capacity $92 $87 $88 $6 $5 $1 $279 Equity investments $ 18 $ 3 $ 2 $ 2 — — $ 25 Capital expenditures $7 $1 — — — — $8"
    assert get("equity_investment_commitments", text) == 25e9


def test_a_table_row_that_does_not_add_up_is_rejected():
    text = TABLE_HEAD + " Equity investments $ 18 $ 3 $ 2 $ 2 — — $ 99"
    assert get("equity_investment_commitments", text) is None


def test_equity_investment_sentence_takes_the_total_not_the_named_part():
    text = "Investment commitments are $3.0 billion as of April 26, 2026, including $2.0 billion in Intel Corporation."
    assert get("equity_investment_commitments", text) == 3.0e9


def test_cloud_service_agreements_wordings():
    row = TABLE_HEAD + " Cloud service agreements 3 8 7 6 4 1 29"
    assert get("cloud_service_agreements", row) == 29e9
    sentence = "Multi-year cloud service agreement commitments as of January 28, 2024, were $3.5 billion, for which most is due later."
    assert get("cloud_service_agreements", sentence) == 3.5e9
    old = "Other non-inventory purchase obligations of $4.31 billion include $3.50 billion of multi-year cloud service agreements."
    assert get("cloud_service_agreements", old) == 3.5e9  # the part, not the $4.31 billion around it


def test_leases_for_third_parties_is_not_confused_with_own_leases():
    text = TABLE_HEAD + " Data center leases not commenced for third party 0 1 1 2 1 15 20 Data center leases not commenced 5 5 5 5 5 5 30"
    assert get("leases_not_commenced_for_third_parties", text) == 20e9
    assert get("leases_not_commenced_own_or_unassigned", text) == 30e9


# --------------------------------------------------------------------------- guarantees


def test_guarantee_sentence_variant():
    text = ("In the third quarter of fiscal year 2026, we entered into a guarantee with a data center developer. The agreement allows draws "
            "until 2030. The maximum gross exposure under all agreements is $860 million. Revenue was $57.0 billion.")
    assert get("guarantees_land_power_shell", text) == 860e6


def test_guarantee_table_variant_is_in_billions():
    text = ("The following table summarizes the maximum gross exposure related to our guarantees as of July 26, 2026: July 26, 2026 (In billions) "
            "Land, power, and shell guarantees for neoclouds $ 3.5 SB Energy Corp. guarantees 105.0 Total 108.5")
    assert get("guarantees_land_power_shell", text) == 3.5e9
    assert get("guarantees_sb_energy_cap", text) == 105.0e9


def test_escrow_sentence():
    text = "The partners have placed $1.2 billion in escrow, which reduces our exposure. We repurchased $9.0 billion of shares."
    assert get("guarantees_escrow_placed_by_partners", text) == 1.2e9


# --------------------------------------------------------------------------- balance sheet items


def test_nonmarketable_equity_takes_the_closing_balance_not_the_opening_one():
    text = ("Adjustments to the carrying value of our non-marketable equity securities were as follows: (In millions) "
            "Beginning balance $ 1,000 Purchases 500 Balance at end of period $ 3,387 $ 2,000")
    assert get("nonmarketable_equity_securities", text) == 3_387e6


def test_accounts_receivable_takes_the_current_column():
    text = ("Condensed Consolidated Balance Sheets (In millions, except par value) (Unaudited) Jul 27, 2025 Jan 26, 2025 Assets "
            "Current assets: Cash 1,000 2,000 Accounts receivable, net 23,065 17,000")
    assert get("accounts_receivable", text) == 23_065e6


def test_reported_dso_is_a_count_of_days_not_dollars():
    text = "Accounts receivable was $ 33.4 billion with 53 days sales outstanding (DSO) at quarter end."
    assert get("days_sales_outstanding_reported", text) == 53.0


def test_customer_advances_first_amount_only():
    text = "The balance as of October 26, 2025, and January 26, 2025, included $1.6 billion and $0.4 billion of customer advances, respectively."
    assert get("customer_advances", text) == 1.6e9


def test_extended_payment_terms_has_no_amount():
    text = "In certain cases, for investment-grade customer purchases, we have and may in the future provide longer payment terms."
    amount, ev = nf.extract(SPEC["extended_payment_terms"], text)
    assert amount is None and "longer payment terms" in ev


def test_public_company_warrants_fair_value_not_the_notional():
    text = "As of January 25, 2026, the fair values of the equity derivatives, a Level 3 measurement, were $1.1 billion. Public company warrants $ 900 $ 1,000"
    assert get("public_company_warrants_fair_value", text) == 1.1e9
    assert get("public_company_warrants_notional", text) == 900e6


# --------------------------------------------------------------------------- income statement and securities tables


def test_revenue_10q_with_four_columns_picks_ytd_and_prior_ytd():
    text = ("Condensed Consolidated Statements of Income (In millions, except per share data) (Unaudited) Three Months Ended Six Months Ended "
            "Revenue $ 46,743 $ 30,040 $ 90,805 $ 56,084 Cost of revenue 10,000 9,000 20,000 18,000")
    got = {item: amount for item, amount, *_ in nf.revenue(text, annual=False)}
    assert got == {"revenue_quarter": 46_743e6, "revenue_year_to_date": 90_805e6, "revenue_prior_year_to_date": 56_084e6}


def test_revenue_first_quarter_ytd_equals_quarter():
    text = "Statements of Income (In millions, except per share data) Three Months Ended Revenue $ 44,062 $ 26,044 Cost of revenue 1,000 2,000"
    got = {item: amount for item, amount, *_ in nf.revenue(text, annual=False)}
    assert got["revenue_quarter"] == got["revenue_year_to_date"] == 44_062e6
    assert got["revenue_prior_year_to_date"] == 26_044e6


def test_revenue_10k_is_the_fiscal_year():
    text = "Consolidated Statements of Income (In millions, except per share data) Year Ended Revenue $ 130,497 $ 60,922 $ 26,974 Cost of revenue 32,000 16,000 11,000"
    assert nf.revenue(text, annual=True)[0][:2] == ("revenue_fiscal_year", 130_497e6)


def test_public_equity_adds_level_1_and_level_2_rows():
    text = "Publicly-held equity securities (1) Level 1 $ 29,887 $ 21,000 Publicly-held equity securities (1) Level 2 $ 9,214 — Other"
    (item, amount, unit, _), = nf.public_equity(text)
    assert (item, amount) == ("public_equity_securities", 39_101e6)


def test_public_equity_single_row():
    text = "Publicly-held equity securities (1) Level 1 $ 1,500 $ 1,000 Privately-held equity securities Level 3 $ 3,000 $ 2,000"
    assert nf.public_equity(text)[0][1] == 1_500e6


GAIN_HEAD = "Adjustments to reconcile net income to net cash provided by operating activities: Stock-based compensation 100 200 "


def test_equity_gains_bracket_means_gain_and_third_cell_is_year_to_date():
    text = GAIN_HEAD + "Gains on non-marketable equity securities and publicly-held equity securities, net (1,000) (500) (2,000) (800) Deferred taxes 5"
    (item, amount, *_), = nf.equity_gains(text)
    assert item == "equity_gains_year_to_date" and amount == 2_000e6


def test_equity_gains_without_brackets_is_a_loss():
    text = GAIN_HEAD + "Gains on non-marketable equity securities and publicly-held equity securities, net 175 (50) Deferred taxes 5"
    assert nf.equity_gains(text)[0][1] == -175e6


def test_equity_gains_dash_is_nothing():
    text = GAIN_HEAD + "Gains on non-marketable equity securities and publicly-held equity securities, net — (50) Deferred taxes 5"
    assert nf.equity_gains(text) == []


# --------------------------------------------------------------------------- concentration


def amounts(rows):
    return {item: amount for item, amount, *_ in rows}


def test_receivables_two_named_percentages():
    text = "Revenue was 30% higher. Two customers accounted for 14% and 11% of our accounts receivable balance as of July 27, 2025."
    got = amounts(nf.receivables_concentration(text))
    assert got == {"receivables_top_customers_share": 25.0, "receivables_top_customers_count": 2, "receivables_top_customers_largest": 14.0}


def test_receivables_each_repeats_the_percentage_by_the_count():
    text = "Three direct customers each accounted for 11% of our accounts receivable balance as of July 27, 2025."
    got = amounts(nf.receivables_concentration(text))
    assert got["receivables_top_customers_share"] == 33.0 and got["receivables_top_customers_count"] == 3


def test_receivables_five_customers_with_serial_comma():
    text = "Five direct customers accounted for 22%, 14%, 13%, 11%, and 10% of our accounts receivable balance as of July 26, 2026."
    got = amounts(nf.receivables_concentration(text))
    assert got["receivables_top_customers_share"] == 70.0 and got["receivables_top_customers_largest"] == 22.0


def test_receivables_single_customer_wording():
    text = "One direct customer accounted for 12% of our accounts receivable balance as of July 27, 2025."
    got = amounts(nf.receivables_concentration(text))
    assert got["receivables_top_customers_share"] == 12.0 and got["receivables_top_customers_count"] == 1


def test_receivables_none_when_wording_absent():
    assert nf.receivables_concentration("A customer accounted for 12% of revenue.") == []


def test_revenue_one_customer_sentence():
    text = "For the second quarter of fiscal year 2027, one direct customer represented 16% of total revenue, which was primarily attributable to Compute."
    got = amounts(nf.revenue_concentration(text, 2027))
    assert got["revenue_top_customers_share"] == 16.0 and got["revenue_top_customers_count"] == 1


def test_revenue_three_customers_sentence():
    text = "For the third quarter of fiscal year 2027, three direct customers represented 14%, 11%, and 11% of total revenue, all of which were primarily attributable to Compute."
    got = amounts(nf.revenue_concentration(text, 2027))
    assert got["revenue_top_customers_share"] == 36.0 and got["revenue_top_customers_largest"] == 14.0


def test_revenue_comparison_year_sentence_is_not_picked_up():
    text = "For the second quarter of fiscal year 2026, one direct customer represented 99% of total revenue."
    assert nf.revenue_concentration(text, 2027) == []


def test_revenue_customer_a_and_b_wording():
    text = ("For the second quarter of fiscal year 2026, sales to one direct customer, Customer A, represented 23% of total revenue; "
            "and sales to a second direct customer, Customer B, represented 16% of total revenue")
    got = amounts(nf.revenue_concentration(text, 2026))
    assert got["revenue_top_customers_share"] == 39.0


def test_revenue_table_asterisk_means_below_ten_percent():
    text = ("Sales to direct customers which represented 10% or more of total revenue, are as follows: Year Ended Jan 28, 2024 Jan 29, 2023 "
            "Customer A 13% * Customer B * 11% ")
    # fiscal year 2024 filing; pattern needs the "Year Ended" header form
    got = amounts(nf.revenue_concentration(text, 2024))
    assert got["revenue_top_customers_share"] == 13.0


def test_no_customer_over_ten_percent_is_zero_count():
    text = "No customer represented 10% or more of total revenue for fiscal year 2023."
    got = amounts(nf.revenue_concentration(text, 2023))
    assert got["revenue_top_customers_share"] == 0 and got["revenue_top_customers_count"] == 0


# --------------------------------------------------------------------------- loans and named


def test_loans_row_records_a_search_with_no_amount():
    (item, amount, unit, ev), = nf.loans("We sell GPUs to cloud providers.")
    assert amount is None and "no mention" in ev


def test_loans_row_lists_what_was_mentioned():
    (_, amount, _, ev), = nf.loans("We provide customer financing in limited cases and hold a Note receivable.")
    assert amount is None and "customer financing" in ev and "note receivable" in ev


def test_named_intel_takes_the_intel_part_not_the_total():
    text = "Investment commitments are $25.0 billion as of April 26, 2026, including $5.0 billion in Intel Corporation."
    rows = {item: amount for item, amount, *_ in nf.named(text)}
    assert rows["named: Intel - committed equity investment"] == 5.0e9


def test_named_openai_has_no_amount():
    text = "We are finalizing an investment and partnership agreement with OpenAI."
    ((item, amount, *_),) = nf.named(text)
    assert amount is None and "OpenAI" in item


# --------------------------------------------------------------------------- derived revenue rows


def long_rows():
    def r(period, form, item, amount):
        return dict(period_end=period, form=form, item=item, amount=amount, unit="USD", evidence="e", url=URL)

    return pd.DataFrame([
        r("2023-10-29", "10-Q", "revenue_quarter", 12.0), r("2023-10-29", "10-Q", "revenue_year_to_date", 33.0),
        r("2023-10-29", "10-Q", "revenue_prior_year_to_date", 26.0),
        r("2024-01-28", "10-K", "revenue_fiscal_year", 46.0),
        r("2024-04-28", "10-Q", "revenue_quarter", 14.0), r("2024-04-28", "10-Q", "revenue_year_to_date", 14.0),
        r("2024-04-28", "10-Q", "revenue_prior_year_to_date", 10.0),
        r("2024-07-28", "10-Q", "revenue_quarter", 15.0), r("2024-07-28", "10-Q", "revenue_year_to_date", 29.0),
        r("2024-07-28", "10-Q", "revenue_prior_year_to_date", 21.0),
        r("2024-07-28", "10-Q", "nonmarketable_securities_on_balance_sheet", 1000.0),
        r("2024-07-28", "10-Q", "nonmarketable_equity_securities", 700.0),
    ])


def test_derived_fourth_quarter_and_trailing_twelve_months():
    derived = pd.DataFrame(nf.derived_rows(long_rows()))
    by = {(r.period_end, r.item): r.amount for r in derived.itertuples()}
    assert by[("2024-01-28", "revenue_quarter")] == 46 - 33        # year less first nine months
    assert by[("2024-01-28", "revenue_trailing_twelve_months")] == 46
    assert by[("2024-04-28", "revenue_trailing_twelve_months")] == 46 + 14 - 10
    assert by[("2024-07-28", "revenue_trailing_twelve_months")] == 46 + 29 - 21
    assert ("2023-10-29", "revenue_trailing_twelve_months") not in by  # no full year known yet
    assert derived.evidence.str.startswith("derived:").all()


def test_derived_equity_method_is_balance_sheet_total_less_equity_securities():
    derived = pd.DataFrame(nf.derived_rows(long_rows()))
    em = derived[derived.item == "equity_method_investments"]
    assert em.amount.tolist() == [300.0]


def test_derived_equity_method_not_added_when_the_filing_states_it():
    df = pd.concat([long_rows(), pd.DataFrame([dict(period_end="2024-07-28", form="10-Q", item="equity_method_investments", amount=250.0,
                                                    unit="USD", evidence="e", url=URL)])])
    derived = pd.DataFrame(nf.derived_rows(df))
    assert "equity_method_investments" not in set(derived.item)


# --------------------------------------------------------------------------- verified marker


def test_mark_verified_requires_the_rows_to_be_unchanged(monkeypatch):
    df = pd.DataFrame([dict(period_end="2026-07-26", form="10-Q", item="accounts_receivable", amount=63_059e6, unit="USD", evidence="ar", url=URL)])
    key = "000104581026000075/nvda-20260726.htm"
    monkeypatch.setattr(nf, "READ_BY_HAND", {key: nf._fingerprint(df)})
    assert nf.mark_verified(df).verified.tolist() == ["yes"]
    changed = df.assign(amount=63_060e6)
    assert nf.mark_verified(changed).verified.tolist() == ["no"]
    monkeypatch.setattr(nf, "READ_BY_HAND", {})
    assert nf.mark_verified(df).verified.tolist() == ["no"]


# --------------------------------------------------------------------------- NARROW and BROAD


def leaves(name):
    parts = nf.SUM_PARTS.get(name)
    if parts is None:
        return [name]
    return [leaf for p in parts for leaf in leaves(p)]


def test_every_component_of_broad_is_counted_exactly_once():
    flat = leaves("broad_support")
    assert len(flat) == len(set(flat)), [x for x in flat if flat.count(x) > 1]
    assert set(flat) == {
        "guarantees_land_power_shell", "guarantees_power_and_systems", "guarantees_sb_energy_cap", "loans_to_customers",
        "equity_investment_commitments", "nonmarketable_equity_securities", "equity_method_investments", "public_equity_securities",
        "convertible_debt_in_public_companies", "public_company_warrants_fair_value", "cloud_service_agreements", "ai_cloud_agreements",
        "leases_not_commenced_for_third_parties",
    }


def test_narrow_is_a_subset_of_broad():
    assert set(leaves("narrow_support")) < set(leaves("broad_support"))


def test_own_leases_and_notional_amounts_stay_out_of_the_sums():
    flat = set(leaves("broad_support"))
    for excluded in ("leases_not_commenced_own_or_unassigned", "public_company_warrants_notional", "equity_forward_contract_notional",
                     "equity_method_maximum_loss_exposure", "guarantees_escrow_placed_by_partners", "customer_advances"):
        assert excluded not in flat


def quarters():
    def rows(period, form, **items):
        return [dict(period_end=period, form=form, item=k, amount=v, unit="USD", evidence="e", url=URL) for k, v in items.items()]

    q1 = rows("2026-04-26", "10-Q", revenue_quarter=80.0, revenue_trailing_twelve_months=300.0, accounts_receivable=40.0,
              guarantees_land_power_shell=3.0, guarantees_power_and_systems=1.0, equity_investment_commitments=10.0,
              nonmarketable_equity_securities=20.0, equity_method_investments=2.0, public_equity_securities=30.0,
              convertible_debt_in_public_companies=4.0, public_company_warrants_fair_value=1.0,
              cloud_service_agreements=5.0, ai_cloud_agreements=6.0, leases_not_commenced_for_third_parties=7.0,
              equity_gains_year_to_date=16.0, deferred_revenue_current=2.0, deferred_revenue_long_term=1.0, loans_or_notes_receivable_from_customers=np.nan)
    q2 = rows("2026-07-26", "10-Q", revenue_quarter=91.0, revenue_trailing_twelve_months=360.0, accounts_receivable=60.0,
              guarantees_land_power_shell=3.0, guarantees_power_and_systems=1.0, guarantees_sb_energy_cap=100.0,
              equity_investment_commitments=10.0, nonmarketable_equity_securities=20.0, public_equity_securities=35.0,
              cloud_service_agreements=5.0, equity_gains_year_to_date=24.0, deferred_revenue_current=2.0, deferred_revenue_long_term=1.0)
    return pd.DataFrame(q1 + q2)


@pytest.fixture()
def summary():
    return nf.summarise(quarters()).set_index("period_end")


def test_narrow_adds_guarantees_loans_and_equity_commitments(summary):
    # 3 + 1 guarantees, no loans disclosed (counts as nothing, flagged), 10 of equity commitments
    assert summary.loc["2026-04-26", "guarantees_max_exposure"] == 4.0
    assert summary.loc["2026-04-26", "narrow_support"] == 14.0


def test_broad_adds_narrow_stakes_capacity_and_third_party_leases(summary):
    q = summary.loc["2026-04-26"]
    assert q.equity_stakes_carrying_value == 20 + 2 + 30 + 4 + 1
    assert q.capacity_buyback_commitments == 5 + 6
    assert q.broad_support == 14 + 57 + 11 + 7


def test_guarantee_signed_after_the_balance_sheet_date_is_kept_out_of_the_period(summary):
    q = summary.loc["2026-07-26"]
    assert pd.isna(q.guarantees_sb_energy_cap)
    assert q.guarantees_signed_after_period_end == 100.0
    assert q.narrow_support == 3 + 1 + 10  # the 100 is not in force at 26 July 2026


def test_days_sales_outstanding_is_receivables_over_quarter_revenue_times_91(summary):
    assert summary.loc["2026-04-26", "days_sales_outstanding"] == round(40 / 80 * 91, 1)
    assert summary.loc["2026-07-26", "days_sales_outstanding"] == round(60 / 91 * 91, 1)


def test_receivables_stretch_is_receivables_above_45_days(summary):
    q = summary.loc["2026-04-26"]
    assert q.receivables_at_45_days == round(80 * 45 / 91)
    assert q.receivables_stretch == 40 - round(80 * 45 / 91)


def test_shares_of_trailing_revenue(summary):
    q = summary.loc["2026-04-26"]
    assert q.narrow_support_share_of_ttm_revenue == round(14 / 300, 4)
    assert q.broad_support_share_of_ttm_revenue == round(89 / 300, 4)


def test_equity_gains_quarter_is_year_to_date_difference_except_in_the_first_quarter(summary):
    assert summary.loc["2026-04-26", "equity_gains_quarter"] == 16.0   # a first quarter is its own year to date
    assert summary.loc["2026-07-26", "equity_gains_quarter"] == 24.0 - 16.0


def test_not_disclosed_names_the_missing_expected_items(summary):
    nd = summary.loc["2026-04-26", "not_disclosed"]
    assert "loans_to_customers" in nd and "cloud_service_agreements" not in nd
    assert "leases_not_commenced_for_third_parties" not in nd


def test_a_quarter_with_no_capacity_figure_is_flagged_not_silently_zero():
    df = quarters()
    df = df[~((df.period_end == "2026-07-26") & df.item.isin(["cloud_service_agreements"]))]
    s = nf.summarise(df).set_index("period_end")
    assert "cloud_service_agreements" in s.loc["2026-07-26", "not_disclosed"]


# --------------------------------------------------------------------------- committed CSVs


@pytest.fixture(scope="module")
def evidence(processed):
    return pd.read_csv(processed / "nvidia_customer_financing.csv")


@pytest.fixture(scope="module")
def fin(processed):
    return pd.read_csv(processed / "nvidia_financing_summary.csv").sort_values("period_end").reset_index(drop=True)


def test_no_duplicate_item_per_document(evidence):
    assert not evidence.duplicated(["period_end", "form", "item", "url"]).any()


def test_every_verified_row_has_evidence_and_an_sec_url(evidence):
    v = evidence[evidence.verified == "yes"]
    assert len(v) > 300
    assert (v.evidence.fillna("").str.strip().str.len() > 10).all()
    assert v.url.str.startswith("https://www.sec.gov/").all()


def test_dollar_amounts_are_positive_except_equity_gains(evidence):
    usd = evidence[(evidence.unit == "USD") & evidence.amount.notna() & (evidence.item != "equity_gains_year_to_date")]
    assert (usd.amount > 0).all()


def test_percentages_are_between_zero_and_one_hundred_and_counts_are_whole(evidence):
    pct = evidence[evidence.unit == "percent"]
    assert pct.amount.between(0, 100).all()
    cnt = evidence[evidence.item.str.endswith("_count")]
    assert (cnt.amount == cnt.amount.round()).all()


def test_each_amount_can_be_found_in_its_evidence(evidence):
    """The extracted number must appear in the sentence or row it was taken from (as $ millions or $ billions)."""
    skip = ("derived", "named:")
    bad = []
    for r in evidence[(evidence.unit == "USD") & evidence.amount.notna()].itertuples():
        if r.evidence.startswith(skip[0]) or r.item.startswith(skip[1]) or r.item == "public_equity_securities":
            continue
        tokens = {float(t.replace(",", "")) for t in re.findall(r"\d[\d,]*(?:\.\d+)?", r.evidence)}
        want = {abs(r.amount) / 1e6, abs(r.amount) / 1e9}
        if not any(abs(t - w) < 1e-6 for t in tokens for w in want):
            bad.append((r.period_end, r.item, r.amount))
    assert not bad, bad


def test_public_equity_is_the_sum_of_its_level_rows(evidence):
    for r in evidence[(evidence.item == "public_equity_securities") & evidence.evidence.str.contains(r"\|")].itertuples():
        firsts = [float(re.search(r"Level \d \$? ?([\d,]+)", part).group(1).replace(",", "")) for part in r.evidence.split("|")]
        assert r.amount == pytest.approx(sum(firsts) * 1e6)


def test_summary_has_one_row_per_quarter(fin):
    assert not fin.duplicated("period_end").any()
    assert len(fin) >= 15


def test_narrow_is_never_larger_than_broad(fin):
    assert (fin.narrow_support <= fin.broad_support).all()


def test_summary_narrow_and_broad_equal_the_sum_of_their_components(fin):
    z = fin.fillna(0)
    guarantees = z.guarantees_land_power_shell + z.guarantees_power_and_systems + z.guarantees_sb_energy_cap
    assert fin.guarantees_max_exposure.fillna(0).tolist() == pytest.approx(guarantees.tolist())
    narrow = z.guarantees_max_exposure + z.loans_to_customers + z.equity_investment_commitments
    assert fin.narrow_support.tolist() == pytest.approx(narrow.tolist())
    stakes = (z.nonmarketable_equity_securities + z.equity_method_investments + z.public_equity_securities
              + z.convertible_debt_in_public_companies + z.public_company_warrants_fair_value)
    assert fin.equity_stakes_carrying_value.fillna(0).tolist() == pytest.approx(stakes.tolist())
    capacity = z.cloud_service_agreements + z.ai_cloud_agreements
    assert fin.capacity_buyback_commitments.fillna(0).tolist() == pytest.approx(capacity.tolist())
    broad = z.narrow_support + z.equity_stakes_carrying_value + z.capacity_buyback_commitments + z.leases_not_commenced_for_third_parties
    assert fin.broad_support.tolist() == pytest.approx(broad.tolist())


def test_days_sales_outstanding_matches_receivables_and_revenue(fin):
    expected = (fin.accounts_receivable / fin.revenue_quarter * 91).round(1)
    assert fin.days_sales_outstanding.tolist() == pytest.approx(expected.tolist())
    assert fin.days_sales_outstanding.between(20, 120).all()


def test_ttm_revenue_is_the_sum_of_the_last_four_quarters(fin):
    rolled = fin.revenue_quarter.rolling(4).sum()
    ok = rolled.notna()
    assert ((rolled[ok] - fin.revenue_ttm[ok]).abs() <= 5e6).all()


def test_shares_of_ttm_revenue(fin):
    assert fin.narrow_support_share_of_ttm_revenue.tolist() == pytest.approx((fin.narrow_support / fin.revenue_ttm).round(4).tolist())
    assert fin.broad_support_share_of_ttm_revenue.tolist() == pytest.approx((fin.broad_support / fin.revenue_ttm).round(4).tolist())


def test_no_guarantee_is_counted_before_it_was_signed(fin):
    early = fin[fin.period_end < nf.SB_ENERGY_SIGNED]
    assert early.guarantees_sb_energy_cap.isna().all()


def test_customer_concentration_is_internally_consistent(fin):
    ok = fin.receivables_top_customers_count.notna()
    assert (fin.receivables_top_customers_largest[ok] <= fin.receivables_top_customers_share[ok]).all()
    assert (fin.receivables_top_customers_largest[ok] * fin.receivables_top_customers_count[ok] >= fin.receivables_top_customers_share[ok] - 1e-9).all()


def test_a_missing_capacity_figure_is_at_least_flagged(fin):
    for r in fin[fin.capacity_buyback_commitments.isna()].itertuples():
        if r.period_end >= "2023-01-29":
            assert "cloud_service_agreements" in r.not_disclosed, r.period_end


@pytest.mark.xfail(strict=True, reason="2025-07-27 has no cloud_service_agreements row, so BROAD drops from 15.1bn to 7.0bn for that quarter (nvidia_financing.py:170 cloud_service_agreements spec)")
def test_broad_has_no_hole_where_a_component_was_simply_not_found(fin):
    f = fin.set_index("period_end")
    holes = [c for p, c in zip(f.index[:-1], f.index[1:])
             if pd.isna(f.loc[c, "capacity_buyback_commitments"]) and f.loc[p, "capacity_buyback_commitments"] > 0]
    assert holes == []
