"""leases.extract: one realistic sentence per company, plus the traps that have bitten before.

Sentences follow the wording (and the "$ 12.3 billion" spacing) that
text.filing_sentences produces from the real filings.
"""
from __future__ import annotations

import re

import pytest

import leases

BN = 1e9
MN = 1e6


def amount(ticker: str, text: str) -> float:
    hit = leases.extract(ticker, text)
    assert hit is not None, "expected a figure"
    return hit[0]


# --------------------------------------------------------------------------- Microsoft

MSFT_SINGLE = (
    "The weighted average discount rate was 4.1 %. As of September 30, 2026, we had additional leases, "
    "primarily for datacenters, that had not yet commenced of $ 364.6 billion, with some arrangements subject "
    "to certain contractual conditions being met. These leases will commence between fiscal year 2027 and "
    "fiscal year 2034 with lease terms of 1 year to 20 years."
)
MSFT_PAIR = (
    "As of June 30, 2023, we have additional operating and finance leases, primarily for datacenters, that "
    "have not yet commenced of $ 7.5 billion and $ 75.1 billion, respectively. These operating and finance "
    "leases will commence between fiscal year 2024 and fiscal year 2030 with lease terms of 1 year to 18 years."
)


def test_microsoft_single_amount():
    assert amount("MSFT", MSFT_SINGLE) == pytest.approx(364.6 * BN)


def test_microsoft_operating_and_finance_amounts_add():
    assert amount("MSFT", MSFT_PAIR) == pytest.approx(82.6 * BN)


# --------------------------------------------------------------------------- Alphabet

GOOGL_SINGLE = (
    "As of September 30, 2026, we have entered into leases, primarily related to data centers and energy "
    "infrastructure, that have not yet commenced with future lease payments of $ 130.5 billion that are not yet "
    "recorded. These leases will commence between 2026 and 2031 with non-cancelable lease terms between one "
    "and 26 years."
)
GOOGL_PAIR = (
    "As of December 31, 2023, we have entered into leases that have not yet commenced with future short-term "
    "and long-term lease payments of $657 million and $3.3 billion, that are not yet recorded on our "
    "Consolidated Balance Sheets. These leases will commence between 2024 and 2026."
)


def test_alphabet_single_amount():
    assert amount("GOOGL", GOOGL_SINGLE) == pytest.approx(130.5 * BN)


def test_alphabet_short_and_long_term_amounts_add():
    assert amount("GOOGL", GOOGL_PAIR) == pytest.approx(657 * MN + 3.3 * BN)


# --------------------------------------------------------------------------- Meta

META_TRAP = (
    "In addition to the above, which are included on our balance sheet, we have operating and finance leases "
    "that have not yet commenced as of June 30, 2025. These lease obligations were approximately $ 52.56 billion, "
    "mostly for data centers, certain network infrastructure, and colocations, which will commence between the "
    "remainder of 2025 and 2034. We also have $ 27.95 billion of non-cancelable contractual commitments as of "
    "June 30, 2025, which are primarily related to our investments in servers and network infrastructure."
)
META_PAIR = (
    "As of March 31, 2021, we have additional operating and finance leases, that have not yet commenced, with "
    "lease obligations of approximately $ 6.14 billion and $ 543 million, respectively, mostly for offices, "
    "data centers and network equipment."
)
META_10K = (
    "In addition to the lease liabilities included in our consolidated balance sheets, we have leases that have "
    "not yet commenced, with total lease obligations of approximately $103.77 billion, mostly for data centers, "
    "colocations, and network infrastructure, as of December 31, 2025."
)


def test_meta_only_the_first_amount_counts():
    # The sentence continues "We also have $ 27.95 billion of non-cancelable..." inside the
    # 260-character window. That is a different commitment and must not be picked or added.
    anchor = re.search(r"that have not yet commenced", META_TRAP)
    assert META_TRAP.index("27.95") - anchor.end() < 260, "the trap must sit inside the search window"
    assert amount("META", META_TRAP) == pytest.approx(52.56 * BN)


def test_meta_operating_and_finance_amounts_add():
    assert amount("META", META_PAIR) == pytest.approx(6.14 * BN + 543 * MN)


def test_meta_annual_report_wording():
    assert amount("META", META_10K) == pytest.approx(103.77 * BN)


# --------------------------------------------------------------------------- Amazon

AMZN_TABLE = (
    "Financing obligations, including interest 465 472 479 485 492 5,655 8,048 "
    "Leases not yet commenced 2,590 12,448 11,477 12,193 11,385 114,829 164,922 "
    "Unconditional purchase obligations (2) 13,049 12,160 9,781 8,254 6,571 21,480 71,295"
)


def test_amazon_table_row_last_number_in_millions():
    value, evidence = leases.extract("AMZN", AMZN_TABLE)
    assert value == pytest.approx(164_922 * MN)
    assert evidence == "Leases not yet commenced 2,590 12,448 11,477 12,193 11,385 114,829 164,922"


def test_amazon_bare_row():
    row = "Leases not yet commenced 2,590 12,448 11,477 12,193 11,385 114,829 164,922"
    assert amount("AMZN", row) == pytest.approx(164.922 * BN)


def test_amazon_does_not_use_the_sentence_patterns():
    # A sentence in another company's style is not Amazon's disclosure.
    assert leases.extract("AMZN", MSFT_SINGLE) is None


# --------------------------------------------------------------------------- Oracle

ORCL_NEW = (
    "Total lease liability $ 34,621 $ 9,185 As of August 31, 2026 , we had $ 288 billion of additional lease "
    "commitments, substantially all related to data center arrangements, that are generally expected to "
    "commence between the second quarter of fiscal 2027 and fiscal 2029 and for terms of fifteen to nineteen years."
)
ORCL_OLD_10K = (
    "the weighted average discount rate used for calculating operating lease obligations was 2.8 %. As of "
    "May 31, 2021, we have $ 653 million of additional operating lease commitments, primarily for data centers."
)
ORCL_OLD_10Q = (
    "there have been no significant changes to our estimates of future payments under our fixed contractual "
    "obligations and commitments as presented in our Annual Report on Form 10-K for the fiscal year ended "
    "May 31, 2023, other than an increase in our operating lease commitments to $10.6 billion as of November 30, 2023."
)


def test_oracle_amount_before_the_anchor():
    assert amount("ORCL", ORCL_NEW) == pytest.approx(288 * BN)


def test_oracle_older_annual_wording_in_millions():
    assert amount("ORCL", ORCL_OLD_10K) == pytest.approx(653 * MN)


def test_oracle_older_quarterly_wording():
    assert amount("ORCL", ORCL_OLD_10Q) == pytest.approx(10.6 * BN)


def test_oracle_balance_first_then_subsequent_event():
    # The balance-sheet-date figure comes first in the note; a later "Subsequent to ..." sentence
    # with the same wording is new signings after the period end and must not replace it.
    text = (
        "As of August 31, 2025 , we had $ 99.8 billion of additional lease commitments, substantially all for "
        "data centers, that were not reflected on our condensed consolidated balance sheets. Subsequent to "
        "August 31, 2025, we entered into $ 6.6 billion of additional lease commitments for data centers."
    )
    assert amount("ORCL", text) == pytest.approx(99.8 * BN)


# --------------------------------------------------------------------------- CoreWeave

CRWV = (
    "As of September 30, 2026, the Company executed additional lease agreements, primarily for data centers, "
    "equipment, and office buildings, that had not yet commenced. The aggregate amount of estimated future "
    "undiscounted lease payments associated with such leases is $ 47.4 billion. These leases will commence "
    "between 2026 and 2029 with estimated lease terms of seven to seventeen years."
)


def test_coreweave():
    assert amount("CRWV", CRWV) == pytest.approx(47.4 * BN)


# --------------------------------------------------------------------------- no disclosure

NO_DISCLOSURE = (
    "We have entered into operating and finance leases for data centers and offices. Total operating lease "
    "liabilities were $ 12.3 billion. Rent expense was $ 2.1 billion and $ 1.9 billion for the periods presented."
)


@pytest.mark.parametrize("ticker", ["MSFT", "GOOGL", "AMZN", "META", "ORCL", "CRWV"])
def test_no_disclosure_returns_none(ticker):
    assert leases.extract(ticker, NO_DISCLOSURE) is None


@pytest.mark.parametrize("ticker", ["MSFT", "GOOGL", "AMZN", "META", "ORCL", "CRWV"])
def test_empty_text_returns_none(ticker):
    assert leases.extract(ticker, "") is None


def test_anchor_without_an_amount_returns_none():
    text = "we had additional leases that had not yet commenced of an amount that is not material."
    assert leases.extract("MSFT", text) is None


# --------------------------------------------------------------------------- shape of the result


@pytest.mark.parametrize(
    "ticker, text, figure",
    [
        ("MSFT", MSFT_SINGLE, "364.6"),
        ("GOOGL", GOOGL_SINGLE, "130.5"),
        ("META", META_TRAP, "52.56"),
        ("ORCL", ORCL_NEW, "288"),
        ("CRWV", CRWV, "47.4"),
    ],
)
def test_evidence_snippet_contains_the_figure(ticker, text, figure):
    value, evidence = leases.extract(ticker, text)
    assert isinstance(value, float)
    assert figure in evidence
    assert evidence in text


def test_anchor_match_is_case_insensitive():
    assert amount("MSFT", MSFT_SINGLE.upper().replace("BILLION", "billion")) == pytest.approx(364.6 * BN)


def test_dollar_sign_with_and_without_space_and_thousands_separator():
    tight = MSFT_SINGLE.replace("$ 364.6 billion", "$364.6 billion")
    assert amount("MSFT", tight) == pytest.approx(364.6 * BN)
    thousands = MSFT_SINGLE.replace("$ 364.6 billion", "$ 1,364.6 billion")
    assert amount("MSFT", thousands) == pytest.approx(1364.6 * BN)


def test_to_usd():
    assert leases._to_usd("7.5", "billion") == pytest.approx(7.5e9)
    assert leases._to_usd("543", "million") == pytest.approx(5.43e8)
    assert leases._to_usd("1,234.5", "Million") == pytest.approx(1.2345e9)


# --------------------------------------------------------------------------- known gaps (see report)


def test_a_later_pair_of_amounts_does_not_replace_the_lease_figure():
    text = (
        "we have operating and finance leases that have not yet commenced as of June 30, 2025. These lease "
        "obligations were approximately $ 52.56 billion, mostly for data centers. We also have $ 27.95 billion "
        "and $ 4.10 billion of non-cancelable contractual commitments and purchase obligations, respectively."
    )
    assert amount("META", text) == pytest.approx(52.56 * BN)


def test_trillion_is_understood():
    text = META_TRAP.replace("$ 52.56 billion", "$ 1.02 trillion")
    assert amount("META", text) == pytest.approx(1.02e12)
