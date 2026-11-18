"""fundamentals.ttm and fundamentals.instance_value on small synthetic inputs."""
from __future__ import annotations

import pandas as pd
import pytest

import fundamentals as fu


def fact(start, end, val, filed, form="10-Q"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def companyfacts(**tags) -> dict:
    """A minimal companyfacts payload: tag -> list of facts (all in USD)."""
    return {"facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in tags.items()}}}


# A calendar-year company, latest filing is the Q3 2026 10-Q.
CALENDAR = [
    fact("2024-01-01", "2024-12-31", 800, "2025-02-01", "10-K"),
    fact("2025-01-01", "2025-03-31", 200, "2025-04-30"),
    fact("2025-01-01", "2025-06-30", 430, "2025-07-30"),
    fact("2025-04-01", "2025-06-30", 230, "2025-07-30"),
    fact("2025-01-01", "2025-09-30", 700, "2025-10-30"),
    fact("2025-07-01", "2025-09-30", 270, "2025-10-30"),
    fact("2025-01-01", "2025-12-31", 1000, "2026-02-01", "10-K"),
    fact("2026-01-01", "2026-03-31", 280, "2026-04-30"),
    fact("2026-01-01", "2026-06-30", 590, "2026-07-30"),
    fact("2026-04-01", "2026-06-30", 310, "2026-07-30"),
    fact("2026-01-01", "2026-09-30", 900, "2026-10-30"),
    fact("2026-07-01", "2026-09-30", 310, "2026-10-30"),
    # balance-sheet style fact with no start date: must be ignored
    {"end": "2026-09-30", "val": 123456, "filed": "2026-10-30", "form": "10-Q"},
]


def test_ttm_at_fiscal_year_end_is_the_annual_figure():
    facts = companyfacts(Revenues=CALENDAR)
    assert fu.ttm(facts, ["Revenues"], "2025-12-31") == 1000
    assert fu.ttm(facts, ["Revenues"], "2024-12-31") == 800


def test_ttm_mid_year_is_last_year_plus_ytd_minus_prior_ytd():
    facts = companyfacts(Revenues=CALENDAR)
    # 1000 (FY25) + 900 (9M 2026) - 700 (9M 2025); the 3-month Q3 figure must not be used as the YTD.
    assert fu.ttm(facts, ["Revenues"], "2026-09-30") == 1200
    # Half year: 1000 + 590 - 430.
    assert fu.ttm(facts, ["Revenues"], "2026-06-30") == 1160
    # First quarter: year-to-date and the quarter are the same span.
    assert fu.ttm(facts, ["Revenues"], "2026-03-31") == 1080


def test_ttm_june_fiscal_year_company():
    # Microsoft-style: FY2026 ends 30 June 2026, the latest 10-Q is Q1 of FY2027.
    rows = [
        fact("2024-07-01", "2025-06-30", 2800, "2025-07-30", "10-K"),
        fact("2025-07-01", "2025-09-30", 770, "2025-10-29"),
        fact("2025-07-01", "2026-06-30", 3300, "2026-07-29", "10-K"),
        fact("2026-07-01", "2026-09-30", 920, "2026-10-28"),
    ]
    assert fu.ttm(companyfacts(Revenues=rows), ["Revenues"], "2026-09-30") == 3300 + 920 - 770


def test_ttm_may_fiscal_year_company_across_a_leap_day():
    # Oracle-style: FY ends 31 May; the prior-year span contains 29 Feb 2024.
    rows = [
        fact("2023-06-01", "2024-05-31", 530, "2024-06-20", "10-K"),
        fact("2023-06-01", "2024-02-29", 390, "2024-03-12"),
        fact("2024-06-01", "2025-02-28", 420, "2025-03-11"),
    ]
    assert fu.ttm(companyfacts(Revenues=rows), ["Revenues"], "2025-02-28") == 530 + 420 - 390


def test_ttm_reads_the_prior_year_to_date_as_it_stood_when_the_annual_report_was_filed():
    """(year - prior nine months) is last year's fourth quarter, so both must be on the annual report's basis.
    Here the nine-month comparative was re-presented (700 -> 650) in the Q3 2026 report, after the annual report."""
    restated = CALENDAR + [fact("2025-01-01", "2025-09-30", 650, "2026-10-30")]
    assert fu.ttm(companyfacts(Revenues=restated), ["Revenues"], "2026-09-30") == 1000 + 900 - 700


def test_ttm_uses_a_restatement_made_before_the_annual_report():
    early = CALENDAR + [fact("2025-01-01", "2025-09-30", 690, "2026-01-15")]  # corrected before the 10-K of 1 Feb 2026
    assert fu.ttm(companyfacts(Revenues=early), ["Revenues"], "2026-09-30") == 1000 + 900 - 690


def test_ttm_missing_tag_returns_none():
    facts = companyfacts(Revenues=CALENDAR)
    assert fu.ttm(facts, ["PaymentsOfDividends"], "2026-09-30") is None
    assert fu.ttm({"facts": {}}, ["Revenues"], "2026-09-30") is None
    assert fu.ttm(facts, [], "2026-09-30") is None


def test_ttm_no_fact_for_the_as_of_date_returns_none():
    facts = companyfacts(Revenues=CALENDAR)
    assert fu.ttm(facts, ["Revenues"], "2026-12-31") is None


def test_ttm_falls_back_to_the_next_tag():
    facts = companyfacts(Revenues=CALENDAR)
    assert fu.ttm(facts, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"], "2026-09-30") == 1200


def test_ttm_prefers_the_first_tag_that_works():
    other = [fact(f["start"], f["end"], f["val"] * 10, f["filed"]) for f in CALENDAR if "start" in f]
    facts = companyfacts(Revenues=CALENDAR, SalesRevenueNet=other)
    assert fu.ttm(facts, ["Revenues", "SalesRevenueNet"], "2026-09-30") == 1200
    assert fu.ttm(facts, ["SalesRevenueNet", "Revenues"], "2026-09-30") == 12000


def test_ttm_without_the_prior_year_comparative_is_none_not_a_partial_sum():
    rows = [f for f in CALENDAR if f.get("start") and not (f["start"] == "2025-01-01" and f["end"] == "2025-09-30")]
    assert fu.ttm(companyfacts(Revenues=rows), ["Revenues"], "2026-09-30") is None


def test_ttm_when_the_company_switches_tag_mid_year():
    # Alphabet's dividends, in $bn, as they sit in companyfacts on 18 Nov 2026: the 2025 annual
    # figure is tagged PaymentsOfDividends, the 2026 year-to-date PaymentsOfOrdinaryDividends.
    facts = companyfacts(
        PaymentsOfDividends=[
            fact("2025-01-01", "2025-09-30", 7.513, "2025-10-30"),
            fact("2025-01-01", "2025-12-31", 10.049, "2026-02-05", "10-K"),
            fact("2026-01-01", "2026-03-31", 2.542, "2026-04-30"),
        ],
        PaymentsOfOrdinaryDividends=[
            fact("2025-01-01", "2025-09-30", 7.513, "2026-10-29"),
            fact("2026-01-01", "2026-09-30", 8.167, "2026-10-29"),
        ],
    )
    got = fu.ttm(facts, ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock", "PaymentsOfOrdinaryDividends"], "2026-09-30")
    assert got == pytest.approx(10.049 + 8.167 - 7.513)


def test_ttm_when_nothing_happened_in_the_current_year_to_date():
    # Oracle's debt issuance, in $bn, as it sits in companyfacts on 18 Nov 2026: $46.1bn in the
    # year to 31 May 2026, none in the first quarter of either fiscal year (so no fact is tagged
    # for June-August 2026). Twelve months to 31 August 2026 is therefore 46.093, not "missing".
    facts = companyfacts(
        ProceedsFromIssuanceOfSeniorLongTermDebt=[
            fact("2024-06-01", "2025-05-31", 19.548, "2025-06-18", "10-K"),
            fact("2025-06-01", "2025-11-30", 17.880, "2025-12-11"),
            fact("2025-06-01", "2026-02-28", 44.544, "2026-03-11"),
            fact("2025-06-01", "2026-05-31", 46.093, "2026-06-22", "10-K"),
        ]
    )
    # Financing flows are "sparse": a missing year-to-date piece means nothing happened.
    assert fu.ttm(facts, ["ProceedsFromIssuanceOfSeniorLongTermDebt"], "2026-08-31", sparse=True) == pytest.approx(46.093)
    # Without the flag a missing piece is treated as a data gap.
    assert fu.ttm(facts, ["ProceedsFromIssuanceOfSeniorLongTermDebt"], "2026-08-31") is None


# --------------------------------------------------------------------------- instance_value


def instance(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["concept", "value", "start", "end", "dims"])


INSTANCE = instance(
    [
        ("LongTermDebt", "35481000000", None, "2026-09-30", ""),
        ("LongTermDebt", "40152000000", None, "2026-06-30", ""),
        ("LongTermDebt", "9000000000", None, "2026-09-30", "DebtInstrumentAxis=SeniorNotesMember"),
        ("InterestExpense", "500000000", "2026-07-01", "2026-09-30", ""),
        ("OperatingLeaseLiability", "5758000000", None, "2026-09-30", ""),
        ("OperatingLeaseLiability", "27477000000", None, "2026-09-30", ""),
        ("OperatingLeaseLiability", "21719000000", None, "2026-09-30", ""),
        ("OperatingLeaseWeightedAverageDiscountRatePercent", "0.041", None, "2026-09-30", ""),
    ]
)


def test_instance_value_takes_the_plain_instant_fact_at_the_date():
    assert fu.instance_value(INSTANCE, "LongTermDebt", "2026-09-30") == 35_481_000_000
    assert fu.instance_value(INSTANCE, "LongTermDebt", "2026-06-30") == 40_152_000_000
    assert fu.instance_value(INSTANCE, "OperatingLeaseWeightedAverageDiscountRatePercent", "2026-09-30") == pytest.approx(0.041)


def test_instance_value_missing_returns_none():
    assert fu.instance_value(INSTANCE, "LongTermDebt", "2025-09-30") is None
    assert fu.instance_value(INSTANCE, "FinanceLeaseLiability", "2026-09-30") is None
    # A duration fact is not a balance.
    assert fu.instance_value(INSTANCE, "InterestExpense", "2026-09-30") is None


def test_instance_value_takes_the_total_when_parts_carry_the_same_concept():
    # Microsoft tags the current and non-current parts with the same concept as the total.
    assert fu.instance_value(INSTANCE, "OperatingLeaseLiability", "2026-09-30") == 27_477_000_000


# --------------------------------------------------------------------------- depreciation and amortization


def _year_and_quarters(annual, new_q, old_q):
    """A May year-end company: the last full year, the first quarter of the new year, and the same quarter a year before."""
    return [fact("2025-06-01", "2026-05-31", annual, "2026-06-22", "10-K"), fact("2026-06-01", "2026-08-31", new_q, "2026-09-11"),
            fact("2025-06-01", "2025-08-31", old_q, "2025-09-10")]


def test_depreciation_and_amortization_adds_the_two_lines_when_the_company_gives_no_total():
    """Oracle's shape: depreciation and amortization of intangible assets on separate lines of the cash-flow statement."""
    facts = companyfacts(Depreciation=_year_and_quarters(7623, 3156, 1351), AmortizationOfIntangibleAssets=_year_and_quarters(1671, 202, 420))
    assert fu.depreciation_and_amortization(facts, "2026-08-31")[0] == (7623 + 3156 - 1351) + (1671 + 202 - 420)


def test_depreciation_and_amortization_uses_the_companys_total_line_and_does_not_add_to_it():
    facts = companyfacts(DepreciationDepletionAndAmortization=_year_and_quarters(1000, 300, 200), Depreciation=_year_and_quarters(900, 280, 190),
                         AmortizationOfIntangibleAssets=_year_and_quarters(100, 20, 10))
    assert fu.depreciation_and_amortization(facts, "2026-08-31")[0] == 1100


def test_depreciation_alone_when_there_is_nothing_to_amortize():
    assert fu.depreciation_and_amortization(companyfacts(Depreciation=_year_and_quarters(500, 150, 100)), "2026-08-31")[0] == 550


def test_no_depreciation_at_all_is_a_gap_not_zero():
    assert fu.depreciation_and_amortization(companyfacts(AmortizationOfIntangibleAssets=_year_and_quarters(100, 20, 10)), "2026-08-31")[0] is None


def test_a_listed_company_adds_exactly_its_own_lines_even_when_a_broader_total_exists():
    """Amazon's cash-flow total also covers leased assets and video content; only its property-and-equipment line is added back."""
    facts = companyfacts(DepreciationDepletionAndAmortization=_year_and_quarters(1000, 300, 200), Depreciation=_year_and_quarters(600, 200, 150))
    value, how = fu.depreciation_and_amortization(facts, "2026-08-31", "AMZN")
    assert value == 650 and how.startswith("Depreciation + AmortizationOfIntangibleAssets") and "not reported" in how


def test_a_line_given_only_for_the_year_to_date_is_estimated_and_says_so():
    """Alphabet's shape: depreciation has a full year, amortization of intangibles only nine-month figures."""
    nine_now, nine_before = fact("2026-01-01", "2026-09-30", 920, "2026-10-30"), fact("2025-01-01", "2025-09-30", 375, "2025-10-30")
    dep = [fact("2025-01-01", "2025-12-31", 21136, "2026-02-01", "10-K"), fact("2026-01-01", "2026-09-30", 21955, "2026-10-30"), fact("2025-01-01", "2025-09-30", 15096, "2025-10-30")]
    value, how = fu.depreciation_and_amortization(companyfacts(Depreciation=dep, AmortizationOfIntangibleAssets=[nine_now, nine_before]), "2026-09-30", "GOOGL")
    assert value == pytest.approx((21136 + 21955 - 15096) + 920 + 375 * 3 / 9) and "estimated" in how


# --------------------------------------------------------------------------- a re-presented prior-year figure


def _re_presented(scale=1):
    """FY 1,000 in the annual report; nine months first filed as 700, later re-presented as 650."""
    rows = [dict(f, val=f["val"] * scale) for f in CALENDAR] + [fact("2025-01-01", "2025-09-30", 650 * scale, "2026-10-30")]
    return companyfacts(Revenues=rows)


def test_a_re_presented_line_can_be_read_either_way_when_told():
    facts = _re_presented()
    assert fu.ttm(facts, ["Revenues"], "2026-09-30") == 1000 + 900 - 700
    assert fu.ttm(facts, ["Revenues"], "2026-09-30", restated={"Revenues"}) == 1000 + 900 - 650
    assert fu.prior_versions(facts, "Revenues", "2026-09-30") == (700, 650)


def test_a_re_presentation_nobody_has_looked_at_stops_the_build():
    with pytest.raises(ValueError, match="PRIOR_BASIS"):
        fu.restated_tags("XYZ", _re_presented(1e9), ["Revenues"], "2026-09-30")       # $700bn against $650bn: far beyond rounding
    assert fu.restated_tags("XYZ", _re_presented(), ["Revenues"], "2026-09-30") == set()  # a $50 difference is rounding
    assert fu.restated_tags("XYZ", companyfacts(Revenues=CALENDAR), ["Revenues"], "2026-09-30") == set()   # nothing re-presented


def test_proxy_statements_are_not_read_as_financial_statements():
    proxy = fact("2025-01-01", "2025-12-31", 950, "2026-04-01", "DEF 14A")   # filed after the 10-K, on another basis
    assert fu.ttm(companyfacts(Revenues=CALENDAR + [proxy]), ["Revenues"], "2025-12-31") == 1000


def test_a_line_given_once_a_year_uses_the_last_fiscal_year():
    """Amazon's shape: amortization of intangibles appears only in the annual report."""
    dep = [fact("2025-01-01", "2025-12-31", 41860, "2026-02-06", "10-K"), fact("2026-01-01", "2026-09-30", 41845, "2026-10-30"), fact("2025-01-01", "2025-09-30", 29747, "2025-10-31")]
    amort = [fact("2025-01-01", "2025-12-31", 817, "2026-02-06", "10-K")]
    value, how = fu.depreciation_and_amortization(companyfacts(Depreciation=dep, AmortizationOfIntangibleAssets=amort), "2026-09-30", "AMZN")
    assert value == (41860 + 41845 - 29747) + 817 and "last fiscal year" in how


def test_share_sales_ignore_a_stale_interim_figure_for_a_line_that_was_folded_into_another():
    """CoreWeave's shape: 67.7 on its own line in the third-quarter report, zero in the annual report (it is inside the offering line there)."""
    folded = [fact("2025-01-01", "2025-09-30", 67.7, "2025-11-13"), fact("2025-01-01", "2025-12-31", 0.0, "2026-03-02", "10-K")]
    offering = [fact("2025-01-01", "2025-09-30", 1422.6, "2025-11-13"), fact("2025-01-01", "2025-09-30", 1491.0, "2026-11-12"),
                fact("2025-01-01", "2025-12-31", 1491.0, "2026-03-02", "10-K"), fact("2026-01-01", "2026-09-30", 0.0, "2026-11-12")]
    placement = [fact("2026-01-01", "2026-09-30", 2982.0, "2026-11-12")]
    facts = companyfacts(ProceedsFromIssuanceOfCommonStock=folded, ProceedsFromIssuanceInitialPublicOffering=offering, ProceedsFromIssuanceOfPrivatePlacement=placement)
    assert fu.shares_sold(facts, "2026-09-30", {"ProceedsFromIssuanceInitialPublicOffering"}) == 2982.0
