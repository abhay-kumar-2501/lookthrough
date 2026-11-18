"""recheck.figure_in: a figure must be in the filing text as a number of the right size."""
from __future__ import annotations

import recheck


def test_a_billion_figure_needs_the_word_or_a_table_in_millions():
    assert recheck.figure_in("we had additional leases that had not yet commenced of $ 364.6 billion", "$364.6bn")
    assert recheck.figure_in("Leases not yet commenced 2,590 12,448 11,477 12,193 11,385 114,829 164,922", "$164.9bn")
    assert not recheck.figure_in("we had additional leases of $ 364.6 million", "$364.6bn")
    assert not recheck.figure_in("we had 3 leases and 4 offices", "$364.6bn")


def test_a_table_headed_in_billions_carries_no_unit_word():
    assert not recheck.figure_in("Supply and capacity $69 $203 $92 $10 $8 $8 $390", "$390.0bn")
    assert recheck.figure_in("Supply and capacity $69 $203 $92 $10 $8 $8 $390", "$390.0bn", in_billions=True)


def test_millions_percent_and_days():
    assert recheck.figure_in("commitments of approximately $8.4 billion", "$8,400m") and recheck.figure_in("reserves of $2,100 million", "$2,100m")
    assert not recheck.figure_in("reserves of $2,100 billion", "$2,100m")
    assert recheck.figure_in("pctVal 7.51", "7.51%") and not recheck.figure_in("pctVal 7.15", "7.51%")
    assert recheck.figure_in("with 64 days sales outstanding", "64 days")


def test_rounding_follows_the_decimals_shown():
    assert recheck.figure_in("a reduction of $3.7 billion", "$3.70bn") and not recheck.figure_in("a reduction of $3.8 billion", "$3.70bn")
