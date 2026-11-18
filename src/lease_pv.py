"""Step 4: what are the signed-but-not-started leases worth in today's money?

The "leases not yet commenced" figures collected by leases.py are totals of
every rent payment over lease terms of up to 30 years, simply added up. A
dollar of rent due in 2045 is not the same burden as a dollar of debt due
today, so the raw totals cannot be set next to debt. Accountants solve this
with a *present value* (PV): each future payment is divided by
(1 + rate) ^ years-until-paid, and the results are added. That is exactly how
a lease is measured when it finally reaches the balance sheet (ASC 842), so a
PV is the fair way to compare a signed lease with borrowings.

Part 1 - does the arithmetic work? (lease_method_check.csv)
    For leases already ON the balance sheet every company discloses three
    things: a year-by-year payment schedule, the weighted-average discount
    rate, and the recorded liability (which is the company's own PV). We
    discount the disclosed schedule at the disclosed rate and compare with the
    recorded liability. A small error means the method (mid-year payment
    timing, one average rate, the "thereafter" lump spread evenly at the last
    disclosed annual amount) can be trusted. Errors are reported as they come
    out, good or bad. `implied_rate` is the single rate that would make our PV
    equal the recorded liability.

Part 2 - PV of the leases not yet commenced (lease_pv.csv)
    Here the filings give only a total, a window in which the leases will
    start and a range of lease terms (inputs/lease_terms.csv). We assume:
      * the leases start evenly, month by month, across the disclosed window;
      * each one pays the same rent every year for its term;
      * rent is paid, on average, in the middle of each year.
    Three scenarios bracket what the filings do not say:
      base     term_base, rate = average of the company's disclosed operating
               and finance lease discount rates
      low PV   term_high, the same rate + 2 percentage points
      high PV  term_low, the disclosed rate
    The band is deliberately lopsided. The disclosed rate is a blend over
    leases signed years ago, when borrowing was cheaper. A lease that starts
    in 2028 will be discounted at the borrowing rate of 2028, which is
    probably above that legacy blend, so the true PV is more likely below the
    base case than above it.

    Amazon is the exception: it publishes a year-by-year schedule for its
    leases not yet commenced, so we discount that schedule directly. Only the
    final "thereafter" lump needs an assumption, and all three versions come
    from the schedule itself:
      base     paid at the last disclosed annual amount
      high PV  paid faster, at the largest disclosed annual amount
      low PV   starts at the last disclosed annual amount and tapers in a
               straight line to zero (leases expiring one by one), which takes
               twice as long; rate + 2 percentage points

Part 3 - history (lease_pv_history.csv)
    Base-case PV for every quarter since 2023. Amazon's rows use each
    quarter's own schedule. For the other five the terms file only holds the
    LATEST window and term range, so those are shifted back to each quarter's
    date; only the amount and the discount rate are that quarter's own. Older
    filings disclosed shorter windows and (Oracle) shorter terms, so early
    quarters are probably understated. See `method_note` in the file.

What a PV does not capture: variable rent, renewal options, the power and
service charges bundled into some data center leases, and the fact that some
of this capacity is rented on to a customer.
"""
from __future__ import annotations

import calendar
import math
import re
from datetime import date

import pandas as pd

import edgar
import xbrl
from fundamentals import instance_value
from universe import COMPANIES

OUT = edgar.ROOT / "data" / "processed"
TERMS = edgar.ROOT / "inputs" / "lease_terms.csv"
HISTORY_SINCE = "2023-01-01"
NEW_LEASE_PREMIUM = 0.02  # fallback for a company with no recent bond on file: new leases priced 2 points above its lease book
NOTES = edgar.ROOT / "inputs" / "ledger_notes.csv"  # hand-read figures, each with its sentence and link


def discount_rates(ticker: str, f: pd.Series, notes: pd.DataFrame | None) -> dict:
    """The three discount rates for a company's signed leases, and where each comes from.

    A lease is recorded, on the day it starts, at what the company would pay to borrow THEN. The rate on a
    company's existing lease book is an average over leases signed years ago, when borrowing was cheaper, so
    it overvalues leases that have not started. The closest observable figure is what the company has just
    paid on its own bonds:
      base  the coupon on its most recent bond of about ten years (a fifteen-year lease paid in level
            instalments repays, on average, about as fast as a ten-year bond), but never below its lease book;
      low   the coupon on its recent bond of about twenty years (used with the longest lease term);
      high  the rate on its existing lease book, weighted by the size of each kind of lease (used with the
            shortest term). This was the base case before 18 November 2026.
    """
    op, fin = float(f["operating_lease_liability"] or 0), float(f["finance_lease_liability"] or 0)
    rates = [(float(f["operating_lease_rate"]), op), (float(f["finance_lease_rate"]), fin)]
    rates = [(r, w) for r, w in rates if r == r]  # drop a missing rate
    weight = sum(w for _, w in rates)
    book = sum(r * w for r, w in rates) / weight if weight else sum(r for r, _ in rates) / len(rates)
    bonds = None if notes is None else notes[(notes.ticker == ticker) & (notes["item"] == "current_borrowing_rate")]
    if bonds is None or bonds.empty:
        return {"base": book, "low": book + NEW_LEASE_PREMIUM, "high": book, "book": book,
                "source": "lease book rate (no recent bond on file); low case two points higher"}
    issued = pd.to_datetime(bonds.as_of)
    bonds = bonds.assign(years=bonds.maturity_year - issued.dt.year - (issued.dt.month - 1) / 12, issued=issued)
    bonds = bonds.sort_values("issued", ascending=False)  # so that, between equally close maturities, the newer issue wins
    ten = bonds.loc[(bonds.years - 10).abs().idxmin()]
    longest = bonds.loc[(bonds.years - 20).abs().idxmin()]
    if (pd.Timestamp(f["as_of"]) - bonds.issued.max()).days > 400:
        raise ValueError(f"{ticker}: its newest bond on file was issued {bonds.issued.max().date()}, over a year before {f['as_of']}; add a recent one to inputs/ledger_notes.csv")
    base, low = max(book, ten.rate_pct / 100), max(book, longest.rate_pct / 100)
    issued = pd.Timestamp(ten.as_of).strftime("%-d %B %Y")
    source = (f"the {ten.rate_pct:g}% notes due {int(ten.maturity_year)} it issued on {issued}" if ten.rate_pct / 100 >= book
              else f"the rate on its own lease book, which is above its {ten.rate_pct:g}% notes due {int(ten.maturity_year)}")
    return {"base": base, "low": low, "high": book, "book": book, "source": source}

# XBRL names for the payment schedule of leases already on the balance sheet.
LEASE_TYPES = {
    "operating": dict(
        stem="LesseeOperatingLeaseLiabilityPayments",
        liability="OperatingLeaseLiability",
        rate="OperatingLeaseWeightedAverageDiscountRatePercent",
    ),
    "finance": dict(
        stem="FinanceLeaseLiabilityPayments",
        liability="FinanceLeaseLiability",
        rate="FinanceLeaseWeightedAverageDiscountRatePercent",
    ),
}
YEAR_BUCKETS = ["DueNextTwelveMonths", "DueYearTwo", "DueYearThree", "DueYearFour", "DueYearFive"]
AFTER_BUCKETS = ["DueAfterYearFive", "DueAfterYearFour"]

# A payment stream is a list of blocks: (amount, start, years) = `amount` paid
# evenly over `years`, beginning `start` years after the valuation date.
Blocks = list


# --------------------------------------------------------------------------- discounting

def decimal_year(iso: str) -> float:
    """2026-09-30 -> 2026.75, the month-end convention used in inputs/lease_terms.csv."""
    d = date.fromisoformat(iso)
    return d.year + (d.month - 1 + d.day / calendar.monthrange(d.year, d.month)[1]) / 12


def block_pv(amount: float, start: float, years: float, rate: float) -> float:
    """PV of one block, treating each year's slice as paid in the middle of that year."""
    if amount == 0 or years <= 0:
        return 0.0
    annual, pv, t = amount / years, 0.0, 0.0
    while t < years - 1e-9:
        span = min(1.0, years - t)  # the last slice may be part of a year
        pv += annual * span / (1 + rate) ** (start + t + span / 2)
        t += 1.0
    return pv


def pv(blocks: Blocks, rate: float) -> float:
    return sum(block_pv(a, s, y, rate) for a, s, y in blocks)


def implied_rate(blocks: Blocks, target: float) -> float | None:
    """The single discount rate at which the stream is worth `target` (bisection)."""
    lo, hi = 0.0, 1.0
    if not pv(blocks, hi) <= target <= pv(blocks, lo):
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pv(blocks, mid) > target else (lo, mid)
    return (lo + hi) / 2


def taper_blocks(total: float, start: float, first_annual: float) -> Blocks:
    """`total` paid as rent that starts at `first_annual` a year and falls in a straight line to zero."""
    years = 2 * total / first_annual
    blocks = []
    for j in range(int(math.ceil(years - 1e-9))):
        a, b = float(j), min(j + 1.0, years)
        blocks.append((first_annual * ((b - a) - (b * b - a * a) / (2 * years)), start + a, b - a))
    return blocks


# --------------------------------------------------------------------------- part 1: method check

def disclosed_schedule(inst: pd.DataFrame, stem: str, as_of: str, to_year_end: float) -> dict | None:
    """Payment schedule for leases on the books, from one filing's XBRL facts.

    `to_year_end` is the length in years of the "remainder of fiscal year"
    bucket that 10-Qs report first (0 in a 10-K).
    """
    def val(suffix):
        return instance_value(inst, stem + suffix, as_of)

    total = val("Due")
    annual = [v for v in (val(s) for s in YEAR_BUCKETS) if v is not None]
    if total is None or not annual:
        return None
    remainder = val("RemainderOfFiscalYear") or 0.0
    after = next((v for v in (val(s) for s in AFTER_BUCKETS) if v is not None), None)
    after_tagged = after is not None
    if after is None:  # untagged: whatever the other buckets do not explain
        after = total - remainder - sum(annual)
    first = to_year_end if remainder else 0.0
    blocks = [(remainder, 0.0, first)] + [(a, first + k, 1.0) for k, a in enumerate(annual)]
    # Spread "thereafter" at the last disclosed annual amount (the latest non-zero one).
    run_rate = next((a for a in reversed(annual) if a > 0), after)
    after_years = after / run_rate if after > 0 else 0.0
    blocks.append((after, first + len(annual), after_years))
    return dict(blocks=blocks, total=total, after=after, after_years=after_years, after_tagged=after_tagged)


def method_check_rows(c: dict) -> list[dict]:
    """Discount each disclosed schedule at the disclosed rate and compare with the recorded liability."""
    filings = edgar.filings(c["cik"], forms=("10-K", "10-Q"))
    last_10k = next(i for i, f in enumerate(filings) if f["form"] == "10-K")
    rows = []
    for kind, tags in LEASE_TYPES.items():
        # Newest filing that tags schedule, liability and rate together (Meta, Oracle: the 10-K).
        for i, f in enumerate(filings[: last_10k + 1]):
            inst, as_of = xbrl.filing_facts(c["cik"], f), f["period"]
            if inst.empty:
                continue
            prior_10k = next(k for k in filings[i:] if k["form"] == "10-K")
            year_end = decimal_year(prior_10k["period"]) + (1 if f["form"] == "10-Q" else 0)
            sched = disclosed_schedule(inst, tags["stem"], as_of, year_end - decimal_year(as_of))
            liability = instance_value(inst, tags["liability"], as_of)
            rate = instance_value(inst, tags["rate"], as_of)
            if sched is None or liability is None or rate is None:
                continue
            value = pv(sched["blocks"], rate)
            implied = implied_rate(sched["blocks"], liability)
            rows.append(
                {
                    "ticker": c["ticker"],
                    "lease_type": kind,
                    "form": f["form"],
                    "as_of": as_of,
                    "discount_rate": rate,
                    "undiscounted_payments": sched["total"],
                    "thereafter": sched["after"],
                    "thereafter_tagged": sched["after_tagged"],
                    "thereafter_years": round(sched["after_years"], 2),
                    "recorded_liability": liability,
                    "pv_of_schedule": round(value),
                    "error_pct": round(100 * (value / liability - 1), 2),
                    "implied_rate": round(implied, 4) if implied is not None else None,
                }
            )
            break
    return rows


# --------------------------------------------------------------------------- part 2: uncommenced leases

def window_blocks(amount: float, lead_from: float, lead_to: float, term: float) -> Blocks:
    """Equal tranches starting month by month across the window, each paying level rent for `term` years."""
    lead_from = max(0.0, lead_from)
    lead_to = max(lead_from, lead_to)
    n = max(1, round((lead_to - lead_from) * 12))
    step = (lead_to - lead_from) / n
    return [(amount / n, lead_from + (i + 0.5) * step, term) for i in range(n)]


def window_scenarios(amount: float, lead_from: float, lead_to: float, terms: dict, rate: float,
                     low_rate: float | None = None, high_rate: float | None = None) -> dict:
    """low / base / high PV for a company that discloses only a total, a window and a term range.

    `rate` is the base-case rate. The low case pairs the longest term with `low_rate`, the high case the
    shortest term with `high_rate`; left out, they default to two points above `rate` and to `rate`.
    """
    low_rate = rate + NEW_LEASE_PREMIUM if low_rate is None else low_rate
    high_rate = rate if high_rate is None else high_rate

    def value(term, r):
        return pv(window_blocks(amount, lead_from, lead_to, term), r)

    return {
        "pv_low": value(terms["term_high"], low_rate),
        "pv_base": value(terms["term_base"], rate),
        "pv_high": value(terms["term_low"], high_rate),
        "pv_base_at_book_rate": value(terms["term_base"], high_rate),
        "term_base": terms["term_base"],
        "annual_rent_base": amount / terms["term_base"],
        "method": (
            f"even commencement over disclosed window; level rent for "
            f"{terms['term_high']:g} / {terms['term_base']:g} / {terms['term_low']:g} years (low / base / high PV)"
        ),
    }


def amazon_schedule(evidence: str, as_of: str) -> dict:
    """Parse Amazon's commitments-table row: first bucket, full years, thereafter, total ($ millions)."""
    nums = [float(x.replace(",", "")) * 1e6 for x in re.findall(r"\d[\d,]*", evidence)]
    *buckets, after, total = nums
    if abs(sum(buckets) + after - total) > 2e6:
        raise ValueError(f"Amazon schedule does not add up: {evidence}")
    # 10-Q: the first bucket is the rest of the calendar year. 10-K (31 Dec): a full year.
    first = 1.0 - (decimal_year(as_of) % 1.0)
    head = [(buckets[0], 0.0, first)] + [(a, first + k, 1.0) for k, a in enumerate(buckets[1:])]
    full_years = buckets[1:] if first < 1 else buckets
    return dict(head=head, after=after, after_start=first + len(buckets) - 1, total=total,
                last=buckets[-1], peak=max(full_years))


def amazon_scenarios(evidence: str, as_of: str, rate: float, low_rate: float | None = None, high_rate: float | None = None) -> dict:
    """low / base / high PV from Amazon's own schedule; only "thereafter" needs an assumption."""
    low_rate = rate + NEW_LEASE_PREMIUM if low_rate is None else low_rate
    high_rate = rate if high_rate is None else high_rate
    s = amazon_schedule(evidence, as_of)
    after, start = s["after"], s["after_start"]
    base = s["head"] + [(after, start, after / s["last"])]
    high = s["head"] + [(after, start, after / s["peak"])]
    low = s["head"] + taper_blocks(after, start, s["last"])
    return {
        "pv_low": pv(low, low_rate),
        "pv_base": pv(base, rate),
        "pv_high": pv(high, high_rate),
        "pv_base_at_book_rate": pv(base, high_rate),
        # No term is disclosed: this is the total expressed in years of the largest annual amount.
        "term_base": round(s["total"] / s["peak"], 1),
        "annual_rent_base": s["peak"],
        "method": (
            f"disclosed year-by-year schedule; 'thereafter' paid over "
            f"{2 * after / s['last']:.1f} (tapering) / {after / s['last']:.1f} / {after / s['peak']:.1f} years "
            f"(low / base / high PV); term_base = total / largest annual amount"
        ),
    }


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    leases = pd.read_csv(OUT / "uncommenced_leases.csv").dropna(subset=["uncommenced_leases"])
    fund = pd.read_csv(OUT / "latest_fundamentals.csv").set_index("ticker")
    terms = pd.read_csv(TERMS).set_index("ticker")
    return leases.sort_values(["ticker", "period_end"]), fund, terms


def pv_row(ticker: str, latest: pd.Series, f: pd.Series, terms: pd.DataFrame, notes: pd.DataFrame | None = None) -> dict:
    """One company's row of lease_pv.csv."""
    as_of, amount = latest["period_end"], float(latest["uncommenced_leases"])
    if as_of != f["as_of"]:
        raise ValueError(f"{ticker}: lease figure is for {as_of} but fundamentals are for {f['as_of']}")
    rates = discount_rates(ticker, f, notes)
    rate = rates["base"]
    if ticker == "AMZN":
        s = amazon_scenarios(latest["evidence"], as_of, rate, rates["low"], rates["high"])
    else:
        t = terms.loc[ticker]
        if t["as_of"] != as_of:
            raise ValueError(f"{ticker}: inputs/lease_terms.csv is for {t['as_of']}, lease figure for {as_of}")
        now = decimal_year(as_of)
        s = window_scenarios(amount, t["commence_from"] - now, t["commence_to"] - now, t.to_dict(), rate, rates["low"], rates["high"])
    leases_on_books = f["operating_lease_liability"] + f["finance_lease_liability"]
    today = f["debt"] + leases_on_books
    op_income = f["ttm_operating_income"]
    return {
        "ticker": ticker,
        "as_of": as_of,
        "undiscounted": amount,
        "pv_low": round(s["pv_low"]),
        "pv_base": round(s["pv_base"]),
        "pv_high": round(s["pv_high"]),
        "pv_base_ratio": round(s["pv_base"] / amount, 4),
        "discount_rate_base": round(rate, 5),
        "discount_rate_low_case": round(rates["low"], 5),
        "discount_rate_book": round(rates["book"], 5),
        "discount_rate_source": rates["source"],
        "pv_base_at_book_rate": round(s["pv_base_at_book_rate"]),
        "term_base": s["term_base"],
        "annual_rent_base": round(s["annual_rent_base"]),
        "debt": f["debt"],
        "existing_lease_liabilities": leases_on_books,
        "cash_and_securities": f["cash_and_securities"],
        "pv_base_vs_debt": round(s["pv_base"] / f["debt"], 3),
        "total_obligations_today": today,
        "total_with_signed_leases": round(today + s["pv_base"]),
        "ttm_operating_income": op_income,
        "ttm_cash_from_operations": f["ttm_cash_from_operations"],
        # A share of a loss means nothing, so it is left blank when operating income is not positive.
        "annual_rent_pct_of_ttm_operating_income": round(100 * s["annual_rent_base"] / op_income, 1) if op_income > 0 else None,
        "discount_rate_as_of": f["lease_rate_as_of"],
        "method": s["method"],
    }


# --------------------------------------------------------------------------- part 3: history

def rate_history(cik: int) -> pd.Series:
    """Average of the disclosed operating and finance lease discount rates, by balance sheet date."""
    facts = edgar.companyfacts(cik)["facts"].get("us-gaap", {})
    cols = {}
    for kind, tags in LEASE_TYPES.items():
        cols[kind] = {f["end"]: f["val"] for vals in facts.get(tags["rate"], {}).get("units", {}).values() for f in vals}
    return pd.DataFrame(cols).sort_index().ffill().mean(axis=1)  # one type alone if the other is not tagged yet


def history_rows(ticker: str, cik: int, leases: pd.DataFrame, latest_as_of: str, terms: pd.DataFrame) -> list[dict]:
    """Base-case PV for each quarter since HISTORY_SINCE, at the rate disclosed on or before that quarter."""
    rates, rows = rate_history(cik), []
    for q in leases[(leases.ticker == ticker) & (leases.period_end >= HISTORY_SINCE)].itertuples():
        known = rates[rates.index <= q.period_end]
        if known.empty:
            continue
        rate, rate_date = float(known.iloc[-1]), known.index[-1]
        if ticker == "AMZN":
            s = amazon_schedule(q.evidence, q.period_end)
            value = pv(s["head"] + [(s["after"], s["after_start"], s["after"] / s["last"])], rate)
            note = "that quarter's disclosed payment schedule"
        else:
            t, now = terms.loc[ticker], decimal_year(latest_as_of)
            value = pv(window_blocks(q.uncommenced_leases, t["commence_from"] - now, t["commence_to"] - now, t["term_base"]), rate)
            note = (
                f"that quarter's amount; commencement window and {t['term_base']:g}-year term are the {latest_as_of} "
                f"disclosures shifted to this date, not this quarter's own"
            )
        rows.append(
            {
                "ticker": ticker,
                "period_end": q.period_end,
                "undiscounted": q.uncommenced_leases,
                "discount_rate": round(rate, 5),
                "pv_base": round(value),
                "pv_base_ratio": round(value / q.uncommenced_leases, 4),
                "method_note": note + f"; discount rate disclosed as of {rate_date}",
            }
        )
    return rows


# --------------------------------------------------------------------------- output

def main() -> None:
    leases, fund, terms = load_inputs()
    notes = pd.read_csv(NOTES)
    check, rows, history = [], [], []
    for c in COMPANIES:
        t = c["ticker"]
        latest = leases[leases.ticker == t].iloc[-1]
        check += method_check_rows(c)
        rows.append(pv_row(t, latest, fund.loc[t], terms, notes))
        history += history_rows(t, c["cik"], leases, latest["period_end"], terms)
    check, out, hist = pd.DataFrame(check), pd.DataFrame(rows), pd.DataFrame(history)
    OUT.mkdir(parents=True, exist_ok=True)
    check.to_csv(OUT / "lease_method_check.csv", index=False)
    out.to_csv(OUT / "lease_pv.csv", index=False)
    hist.to_csv(OUT / "lease_pv_history.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    print("Method check: disclosed schedule discounted at the disclosed rate vs recorded liability ($bn)")
    show = check[["ticker", "lease_type", "form", "as_of", "discount_rate", "thereafter_years", "recorded_liability", "pv_of_schedule", "error_pct", "implied_rate"]].copy()
    show[["recorded_liability", "pv_of_schedule"]] = (show[["recorded_liability", "pv_of_schedule"]] / 1e9).round(2)
    print(show.to_string(index=False))
    print(f"average absolute error {check.error_pct.abs().mean():.1f}%, worst {check.error_pct.abs().max():.1f}%")

    print("\nLeases not yet commenced: present value ($bn)")
    show = out.set_index("ticker")[["as_of", "undiscounted", "pv_low", "pv_base", "pv_high", "pv_base_ratio", "discount_rate_base",
                                    "term_base", "annual_rent_base", "debt", "pv_base_vs_debt", "annual_rent_pct_of_ttm_operating_income"]].copy()
    money = ["undiscounted", "pv_low", "pv_base", "pv_high", "annual_rent_base", "debt"]
    show[money] = (show[money] / 1e9).round(1)
    print(show.rename(columns={"annual_rent_pct_of_ttm_operating_income": "rent_pct_op_income"}).to_string())

    print("\nBase-case PV by quarter ($bn); see method_note in lease_pv_history.csv before using")
    print(hist.pivot_table(index="period_end", columns="ticker", values="pv_base").div(1e9).round(1).to_string())


if __name__ == "__main__":
    main()
