"""make_spenders.calendar_quarter: Oracle's fiscal quarters end one month before everyone else's."""
from __future__ import annotations

import pytest

import make_spenders


@pytest.mark.parametrize(
    "period_end, quarter",
    [
        ("2026-03-31", "2026Q1"),
        ("2026-06-30", "2026Q2"),
        ("2026-09-30", "2026Q3"),
        ("2025-12-31", "2025Q4"),
        ("2022-12-31", "2022Q4"),
    ],
)
@pytest.mark.parametrize("ticker", ["MSFT", "GOOGL", "AMZN", "META", "CRWV"])
def test_calendar_quarter_for_calendar_quarter_ends(ticker, period_end, quarter):
    assert make_spenders.calendar_quarter(ticker, period_end) == quarter


@pytest.mark.parametrize(
    "period_end, quarter",
    [
        ("2026-08-31", "2026Q3"),  # lines up with everyone else's 30 September
        ("2025-11-30", "2025Q4"),
        ("2026-02-28", "2026Q1"),
        ("2024-02-29", "2024Q1"),  # leap year
        ("2026-05-31", "2026Q2"),  # Oracle's fiscal year-end
        ("2022-11-30", "2022Q4"),
    ],
)
def test_calendar_quarter_oracle_is_shifted_one_month(period_end, quarter):
    assert make_spenders.calendar_quarter("ORCL", period_end) == quarter


def test_oracle_shift_is_not_applied_to_other_companies():
    assert make_spenders.calendar_quarter("MSFT", "2026-08-31") == "2026Q3"
    assert make_spenders.calendar_quarter("MSFT", "2025-11-30") == "2025Q4"
    # Same date, different label only at a quarter boundary:
    assert make_spenders.calendar_quarter("ORCL", "2026-09-30") == "2026Q4"
    assert make_spenders.calendar_quarter("MSFT", "2026-09-30") == "2026Q3"


def test_quarter_labels_sort_chronologically():
    ends = ["2022-11-30", "2023-02-28", "2023-05-31", "2023-08-31", "2023-11-30", "2024-02-29"]
    labels = [make_spenders.calendar_quarter("ORCL", e) for e in ends]
    assert labels == sorted(labels)
    assert labels[0] >= make_spenders.FIRST_LEASE_QUARTER
