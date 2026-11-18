"""How much is NVIDIA helping to finance its own customers?

A supplier can support the companies that buy from it in several ways: it can
guarantee their debts or leases, lend to them, buy shares in them, promise to
buy their output back, sign leases on their behalf, or simply wait longer to
be paid. US accounting rules put most of these in footnotes, not on the
balance sheet. This script collects each one from every NVIDIA 10-K and 10-Q
since January 2023, with the sentence or table row it came from, so the same
measures can be built for other suppliers in other periods (Lucent and Cisco
in 1998-2002, for example).

Nothing here implies that any of these arrangements is improper. They are
disclosed by the company, and the figures are copied from its filings.

DEFINITIONS (every part is its own column in the summary, so a reader can
recombine them differently)

  NARROW support = guarantees + loans to customers + unfunded equity commitments
      guarantees     the most NVIDIA could have to pay if customers or partners
                     default on obligations it has guaranteed ("maximum gross
                     exposure"), before any escrow or recovery. Only guarantees
                     signed on or before the balance sheet date count; one
                     signed afterwards is shown in its own column.
      loans          loans or notes receivable from customers or partners.
                     NVIDIA discloses none in this period, so the column is
                     empty; longer payment terms show up in receivables below.
      unfunded equity commitments
                     amounts NVIDIA has agreed to invest in other companies but
                     has not yet paid ("investment commitments").

  BROAD support = NARROW + equity stakes + capacity buy-backs + leases for others
      equity stakes  carrying value of shares already owned: privately held
                     ("non-marketable") equity, equity-method investments,
                     publicly traded equity, debt convertible into public
                     equity, and warrants received from public companies.
      capacity buy-backs
                     agreements to buy computing capacity from cloud providers
                     that buy NVIDIA's products: "cloud service agreements"
                     (used for NVIDIA's own research) and "AI cloud" or
                     "neocloud" agreements (capacity NVIDIA commits to take if
                     the provider cannot sell it to others).
      leases for others
                     data center leases NVIDIA has signed and expects to
                     reassign to third parties.

  Receivables stretch = accounts receivable - 45 days of sales
      45 days of sales = quarterly revenue x 45 / 91. Days sales outstanding
      (DSO) = receivables / quarterly revenue x 91. A fourteen-week quarter
      (the fourth quarter of fiscal 2027 will be one) would need 98, not 91.

Each of the three is also shown as a share of trailing-twelve-month revenue.

HOW TO READ THE TOTALS

  * NARROW and BROAD add together different kinds of number: amounts already
    paid (equity stakes), amounts that may never be paid (guarantees), and
    undiscounted payments spread over many years (capacity and leases). They
    measure the size of the disclosed arrangements, not an expected loss.
  * The filings do not say which equity holdings are in customers, so the whole
    portfolio is counted. That makes the equity part an upper bound.
  * A guarantee counts at its full cap from the day it is signed, even where it
    only takes effect later. The SB Energy guarantees ($105 billion cap) take
    effect building by building from fiscal 2029; they have their own column,
    `guarantees_sb_energy_cap`, so NARROW can be read with or without them.
  * A part that a filing does not state is left empty and counted as zero; the
    `not_disclosed` column lists what was missing that quarter.
  * Fourth-quarter revenue is not stated in a 10-K. It is the fiscal year minus
    the first nine months. Trailing-twelve-month revenue is the last fiscal
    year plus this year to date minus the same months a year earlier.
  * Customer concentration in revenue is for the quarter in a 10-Q and for the
    whole fiscal year in a 10-K.

SOURCES

  Every 10-K and 10-Q with a period end from January 2023. If the newest
  quarter has been announced but its 10-Q is not yet on EDGAR, the earnings
  8-K exhibits (CFO commentary and supplemental financial information) are
  used and the `form` column says so. Other 8-Ks filed since the last 10-Q and
  the quarterly 13F-HR holdings reports are read only for rows that name a
  counterparty.

Outputs (data/processed/):
  nvidia_customer_financing.csv   one row per disclosed figure: period_end,
                                  form, item, amount, unit, evidence, url,
                                  verified
  nvidia_financing_summary.csv    one row per quarter with the measures above

`verified` is "yes" only where the evidence was read by a person against the
number. The check is a fingerprint of all rows from one document (READ_BY_HAND
below): if a pattern or a filing changes, every row from that document goes
back to "no" until it is read again.

Run: .venv/bin/python -W ignore src/nvidia_financing.py
"""
from __future__ import annotations

import hashlib
import re

import pandas as pd
from lxml import etree

import edgar
import text
import xbrl

edgar._MIN_INTERVAL = 0.4  # other processes share the SEC's rate allowance

CIK = 1045810
OUT = edgar.ROOT / "data" / "processed"
SINCE = "2023-01-01"
SB_ENERGY_SIGNED = "2026-08-17"  # date of the guarantees, from the 8-K filed that day

DATE = r"[A-Z][a-z]+ \d{1,2} ?, \d{4}"
AMT = r"\$ ?(?P<amount>[\d,]+(?:\.\d+)?) ?(?P<unit>billion|million)"
SENT = r"(?:[^.]|\.(?=\d))*\."  # the rest of the sentence, not stopping at the point in "$4.5 billion"
CELL = r"(?:\$ ?)?(?:[\d,]+|—)"
ROW = r"(?P<nums>(?:" + CELL + r" ){6}(?:\$ ?)?(?P<amount>[\d,]+))"  # six fiscal-year columns, then the total
TABLE = (r"(?P<head>[Ff]uture (?:additional )?commitments by fiscal year as of " + DATE
         + r", were as follows: .{0,90}?\(In billions\)) .{0,330}?")
GUARANTEES = (r"(?P<head>summarizes the maximum gross exposure related to our guarantees[^:]*:(?: " + DATE
              + r" \(In billions\))?) .{0,140}?")
LOANS = r"\b[Ll]oans?\b|[Nn]otes? receivable|[Ff]inancing receivables?|[Vv]endor financing|[Cc]ustomer financing"


def _spec(item: str, patterns: list[str], unit: str = "USD", scale: str = "million") -> dict:
    return dict(item=item, patterns=patterns, unit=unit, scale=scale)


# Where each figure sits. Patterns are tried in order because the wording changes
# from year to year. Named groups: amount/unit = the figure; nums = a table row
# whose parts must add up to its total; head, body = evidence is "head ... body".
SPECS = [
    # 1. Guarantees
    _spec("guarantees_land_power_shell",
          [r"(?:In (?:the third quarter of )?fiscal year \d{4}, we|We) entered into [^.]{0,60}?guarantee[^.]*\. "
           r"(?:The agreement allows[^.]*\. )?The maximum gross exposure(?: under all agreements)? is " + AMT + SENT,
           GUARANTEES + r"(?P<body>Land, power, and shell guarantees for (?:AI clouds|neoclouds) \$ ?(?P<amount>[\d.]+))"],
          scale="billion"),
    _spec("guarantees_sb_energy_cap",
          [GUARANTEES + r"(?P<body>SB Energy Corp\. (?:credit support )?guarantees (?P<amount>[\d.]+))"], scale="billion"),
    _spec("guarantees_power_and_systems",
          [GUARANTEES + r"(?P<body>Power and systems credit support guarantees (?P<amount>[\d.]+))"], scale="billion"),
    _spec("guarantees_escrow_placed_by_partners", [r"The partners? ha(?:s|ve) placed " + AMT + r" in escrow" + SENT]),
    # 2. Equity
    _spec("nonmarketable_equity_securities",
          [r"(?P<head>[Aa]djustments to the carrying value of (?:our non-marketable equity securities|privately[- ]held securities)"
           r"[^$]{0,260}?\(In millions\)) .{0,420}?(?P<body>Balance at end of period \$ ?(?P<amount>[\d,]+)(?: \$ ?[\d,]+){0,3})",
           r"(?P<head>Adjustments to the carrying value of our non-marketable equity securities[^$]{0,200}?\(In millions\)) "
           r".{0,300}?(?P<body>Carrying amount as of " + DATE + r" \$ ?(?P<amount>[\d,]+)) In the",
           r"(?P<head>Other assets \(Investments? in non-affiliated entities\):) Publicly-held equity securities(?: \(\d\))? "
           r"Level 1 \$ ?[\d,]+ \$ ?[\d,]+ (?P<body>Privately-held equity securities Level 3 \$ ?(?P<amount>[\d,]+) \$ ?[\d,]+)"]),
    _spec("nonmarketable_securities_on_balance_sheet",
          [r"(?P<body>Non-marketable (?:equity )?securities (?P<amount>[\d,]+) [\d,]+) Other assets [\d,]+ [\d,]+ Total assets"]),
    _spec("equity_method_investments",
          [r"We (?:had|have) " + AMT + r" of investments in infrastructure (?:financiers|funds) accounted for using the equity method as of " + DATE + r"\."]),
    _spec("equity_method_maximum_loss_exposure",
          [r"(?:Those equity method investments[^.$]*?|Our )maximum loss exposure[^.$]*?" + AMT + r" as of " + DATE + r"\."]),
    _spec("convertible_debt_in_public_companies",
          [r"Debt securities convertible into publicly held equity securities(?: \(\d\))* Level 2 (?P<amount>[\d,]+)(?: (?:[\d,]+|—)){0,5}"]),
    _spec("public_company_warrants_fair_value",
          [r"(?:In the \w+ quarter of fiscal year \d{4}, we received warrants[^.]*\. .{0,260}?)?As of " + DATE
           + r", the fair values of the equity derivatives, a Level 3 measurement, were " + AMT]),
    _spec("public_company_warrants_notional", [r"Public company warrants \$ ?(?P<amount>[\d,]+) \$ ?(?:[\d,]+|—)"]),
    _spec("equity_forward_contract_notional", [r"Equity forward contract \$ ?(?P<amount>[\d,]+) \$ ?(?:[\d,]+|—)"]),
    _spec("equity_investment_commitments",
          [TABLE + r"(?P<body>Equity investments " + ROW + r")",
           r"(?:Total )?I ?nvestment commitments (?:are|were) " + AMT + r" as of " + DATE + SENT], scale="billion"),
    # 3. Capacity bought back from customers, and leases taken for others
    _spec("cloud_service_agreements",
          [TABLE + r"(?P<body>Cloud service agreements " + ROW + r")",
           r"Multi-year cloud service agreement commitments as of " + DATE + r", were " + AMT + SENT,
           r"Other non-inventory purchase obligations (?:of|were) \$ ?[\d,.]+ billion,? (?:include|including|which includes) "
           + AMT + r" of multi-year cloud service agreements" + SENT], scale="billion"),
    _spec("ai_cloud_agreements", [TABLE + r"(?P<body>(?:AI cloud|Neocloud) agreements (?:\(1\) )?" + ROW + r")"], scale="billion"),
    _spec("leases_not_commenced_for_third_parties",
          [TABLE + r"(?P<body>Data center leases not commenced for third party " + ROW + r")"], scale="billion"),
    _spec("leases_not_commenced_own_or_unassigned",
          [TABLE + r"(?P<body>Data center leases not commenced " + ROW + r")"], scale="billion"),
    # 4. Receivables and advances
    _spec("accounts_receivable",
          [r"(?i)(?P<head>Balance Sheets \(In millions[^)]*\)(?: \(Unaudited\))? .{5,60}? Assets) .{0,300}?"
           r"(?P<body>Accounts receivable, net (?P<amount>[\d,]+) [\d,]+)"]),
    _spec("deferred_revenue_current",
          [r"(?i)(?P<head>Accrued and Other Current Liabilities:).{0,400}?(?P<body>Deferred revenue \(\d\) (?P<amount>[\d,]+) [\d,]+)"]),
    _spec("deferred_revenue_long_term",
          [r"(?i)(?P<head>Other Long-Term Liabilities:).{0,200}?(?P<body>Deferred revenue \(\d\) (?P<amount>[\d,]+) [\d,]+)"]),
    _spec("customer_advances",
          [r"The balance as of " + DATE + r",? and " + DATE + r",? included " + AMT
           + r" and \$ ?[\d,.]+ (?:billion|million) of customer advances, respectively\.",
           AMT + r" and \$ ?[\d,.]+ (?:billion|million) of the balance in (?:the first quarter of fiscal year \d{4} and in "
           r"fiscal year \d{4}|fiscal \d{4} and \d{4}),? respectively,? (?:were )?related to customer advances\."]),
    _spec("days_sales_outstanding_reported",
          [r"Accounts receivable was \$ ?[\d.]+ billion with (?P<amount>\d+) days sales outstanding \(DSO\)" + SENT], unit="days"),
    _spec("extended_payment_terms",
          [r"In certain cases, for investment-grade customer purchases, we have and may in the future provide longer payment terms" + SENT],
          unit="text"),
]

# 5. Statements that name a counterparty. No amount group = the filing gives none.
NAMED = [
    ("named: CoreWeave - fair value of shares held",
     r"The balance as of the first quarter of fiscal year 2026 includes an investment in CoreWeave, Inc\., or CoreWeave, which was "
     r"reclassified[^.]*\. The fair value of the investment as of " + DATE + r" was " + AMT + SENT),
    ("named: Intel - committed equity investment",
     r"I ?nvestment commitments are \$ ?[\d.]+ billion as of " + DATE + r", including " + AMT + r" in Intel Corporation" + SENT),
    ("named: Anthropic - agreement to invest up to (signed after the period end)",
     r"In November 2025, we entered into an agreement, subject to certain closing conditions, to invest up to " + AMT + r" in Anthropic\."),
    ("named: OpenAI - letter of intent to invest, no amount stated",
     r"In the third quarter of fiscal year 2026, we entered into a letter of intent with an opportunity to invest in OpenAI\."),
    ("named: OpenAI - investment and partnership agreement being finalised, no amount stated",
     r"We are finalizing an investment and partnership agreement with OpenAI\."),
    ("named: SB Energy and OpenAI - cap on lease guarantees",
     r"SB Energy Corp\. guarantees – In August 2026, we entered into guarantees, capped at a total of " + AMT + r",.{0,400}?Pike County, Ohio\."),
    ("named: SB Energy and OpenAI - cap on lease guarantees",
     r"NVIDIA’s aggregate payment obligation is cumulatively capped at " + AMT + r" for its initial commitment under the Agreements\."),
    ("named: SB Energy and OpenAI - cap on lease guarantees",
     r"In August 2026, we entered into guarantees to provide credit support.{0,700}?up to a maximum of " + AMT
     + r", and then declines over each 20-year lease term as OpenAI makes lease payments\."),
    ("named: OpenAI - agreed to reimburse NVIDIA for guarantee payments, no amount stated",
     r"OpenAI has agreed to reimburse and indemnify NVIDIA for any and all amounts actually paid by NVIDIA to the Lessor under the Agreements\."),
]

# Revenue from customers above 10% of the total: one wording per era. {fy} is the
# filing's fiscal year, so a sentence about the comparison period cannot match.
# `pcts` holds the current period's percentages; a table gives them in its first column.
REVENUE_SHARE = [
    r"Sales to direct customers which represented 10% or more of total revenue,[^:]*: (?:Three Months Ended \w+ Months Ended|Year Ended) "
    r"[A-Z][a-z]{2} \d+, \d{4} [A-Z][a-z]{2} \d+, \d{4} (?P<table>(?:(?:Direct )?Customer [A-E] (?:\d+ ?%|\*) (?:\d+ ?%|\*) )+)",
    r"For the \w+ quarter of fiscal year {fy}, \w+ direct customers with sales greater than 10% of total revenue included: (?P<pcts>[^.]*?), which were" + SENT,
    r"For the \w+ quarter of fiscal year {fy}, sales to one direct customer, Customer A, represented (?P<pcts>\d+ ?% of total revenue; "
    r"and sales to a second direct customer, Customer B, represented \d+ ?%) of total revenue",
    r"For the \w+ quarter of fiscal year {fy}, \w+ direct customers? represented (?P<pcts>[\d %,and]+?) of total revenue" + SENT,
    r"For fiscal year {fy}, sales to one direct customer represented (?P<pcts>\d+ ?% of total revenue and sales to another direct "
    r"customer represented \d+ ?%) of total revenue" + SENT,
    r"Sales to one (?:direct )?customer, (?:or )?Customer A, represented (?P<pcts>\d+ ?% of total revenue(?: and sales to a second direct "
    r"customer, Customer B, represented \d+ ?% of total revenue)?) for (?:the \w+ quarter of )?fiscal year {fy}" + SENT,
    r"One data center distributor customer represented approximately (?P<pcts>\d+ ?%) and \d+ ?% of total revenue for the second quarter "
    r"and first half of fiscal year {fy}, respectively" + SENT,
    r"No customer represented 10% or more of total revenue for (?:the \w+ quarter of )?fiscal years? {fy}" + SENT,
]

# Documents whose evidence has been read by a person against the amounts, with the fingerprint
# of their rows at the time (see _fingerprint). Read on 18 November 2026.
READ_BY_HAND: dict[str, str] = {
    "000104581023000017/nvda-20230129.htm": "b90e91476e",
    "000104581023000093/nvda-20230430.htm": "4b5eba9ed0",
    "000104581023000175/nvda-20230730.htm": "ab5a96bf2b",
    "000104581023000227/nvda-20231029.htm": "e89335dffb",
    "000104581024000029/nvda-20240128.htm": "717ade1059",
    "000104581024000124/nvda-20240428.htm": "6940900d1a",
    "000104581024000264/nvda-20240728.htm": "ab90585725",
    "000104581024000316/nvda-20241027.htm": "7d730237e5",
    "000104581025000023/nvda-20250126.htm": "b4bf1a41ab",
    "000104581025000116/nvda-20250427.htm": "08bb989c28",
    "000104581025000209/nvda-20250727.htm": "1513721e5c",
    "000104581025000230/nvda-20251026.htm": "192fb8168e",
    "000104581026000021/nvda-20260125.htm": "a6a22ecf1d",
    "000104581026000052/nvda-20260426.htm": "9364d2485c",
    "000104581026000075/nvda-20260726.htm": "fe061ebc65",
    "000104581026000069/nvda-20260817.htm": "87cfdfc4b6",
    "000104581026000088/q3fy27cfocommentary.htm": "c5c1eafb81",
    "000104581026000088/supplementalfinancialinfor.htm": "4c080b6ea4",
    # 13F-HR holdings tables
    "000104581024000021/information_table.xml": "b521a92165",
    "000104581024000108/information_table.xml": "72832ebaa2",
    "000104581024000256/information_table.xml": "8a4d24b137",
    "000104581024000305/information_table.xml": "39dfdbd6a4",
    "000104581025000013/information_table.xml": "042aa2df65",
    "000104581025000102/information_table.xml": "2e617fda06",
    "000104581025000199/information_table.xml": "bee2a7e70f",
    "000104581025000219/information_table.xml": "df239d5302",
    "000104581026000011/information_table.xml": "f2461b4e21",
    "000104581026000042/information_table.xml": "474bec19d5",
    "000104581026000065/information_table.xml": "c6968a4639",
    "000104581026000084/information_table.xml": "907764f675",
}


def _usd(num: str, unit: str) -> float:
    return round(float(num.replace(",", "")) * {"billion": 1e9, "million": 1e6}[unit.lower()])


def _row_adds_up(cells: str) -> bool:
    """A commitments row in whole $ billions: the six years must add up to the total, within rounding."""
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", cells)]
    return len(nums) >= 2 and abs(sum(nums[:-1]) - nums[-1]) <= 3


def _tidy(passage: str) -> str:
    """Close the gaps the HTML leaves inside '$ 1.2 billion' and '30 %'."""
    return re.sub(r"(?<=\d) %", "%", re.sub(r"\$ (?=\d)", "$", passage)).strip()


def extract(spec: dict, full: str) -> tuple[float | None, str] | None:
    """First passage that matches the spec: (amount, evidence)."""
    for pattern in spec["patterns"]:
        for m in re.finditer(pattern, full):
            g = m.groupdict()
            if g.get("nums") and not _row_adds_up(g["nums"]):
                continue
            if spec["unit"] == "USD":
                amount = _usd(g["amount"], g.get("unit") or spec["scale"])
            else:
                amount = float(g["amount"]) if g.get("amount") else None
            passage = f"{g['head']} ... {g['body']}" if g.get("head") else g.get("body") or m.group(0)
            return amount, _tidy(passage)
    return None


def revenue(full: str, annual: bool) -> list[tuple]:
    """Revenue from the income statement: the fiscal year in a 10-K; the quarter and year to date in a 10-Q."""
    m = re.search(r"(?i)Statements of Income \(In millions, except per share data\).{0,220}?Revenue (?P<nums>\$ ?[\d,]+(?: \$ ?[\d,]+){1,3})", full)
    if not m:
        return []
    nums = [_usd(x, "million") for x in re.findall(r"[\d,]+", m.group("nums"))]
    evidence = _tidy(m.group(0))
    if annual:
        return [("revenue_fiscal_year", nums[0], "USD", evidence)]
    year_to_date, a_year_earlier = (nums[2], nums[3]) if len(nums) == 4 else (nums[0], nums[1])
    return [("revenue_quarter", nums[0], "USD", evidence),
            ("revenue_year_to_date", year_to_date, "USD", evidence),
            ("revenue_prior_year_to_date", a_year_earlier, "USD", evidence)]


def public_equity(full: str) -> list[tuple]:
    """Fair value of publicly traded shares held: one table row, or two (Level 1 and Level 2) from April 2026."""
    row = r"Publicly[- ]held equity securities(?: \(\d\))*(?: Level \d)? \$? ?(?P<amount>[\d,]+)(?: \$? ?(?:[\d,]+|—)){0,4}"
    first = re.search(row, full)
    if not first:
        return []
    rows = [first]
    second = re.match(" " + row, full[first.end():])
    if second:
        rows.append(second)
    total = sum(_usd(r.group("amount"), "million") for r in rows)
    return [("public_equity_securities", total, "USD", _tidy(" | ".join(r.group(0).strip() for r in rows)))]


def equity_gains(full: str) -> list[tuple]:
    """Gains (+) or losses (-) on equity holdings for the year to date, from the cash flow statement."""
    cell = r"(?:\( ?[\d,]+ ?\)|[\d,]+|—)"
    m = re.search(r"(?P<head>Adjustments to reconcile net income to net cash provided by operating activities:) .{0,260}?"
                  r"(?P<body>(?:Realized and unrealized )?\(?(?:[Gg]ains|[Ll]osses)\)? ?(?:\(?(?:gains|losses)\)? )?(?:on|from) "
                  r"(?:investments in non-affiliate[sd]?(?: entities)?(?: and publicly-held equity securities)?|non-marketable equity "
                  r"securities and publicly-held equity securities|equity securities)(?:, net)? (?P<cells>" + cell + r"(?: " + cell + r"){0,3}))", full)
    if not m:
        return []
    cells = re.findall(cell, m.group("cells"))
    pick = cells[2] if len(cells) == 4 else cells[0]  # quarter, quarter, year to date, year to date: take the third
    if pick == "—":
        return []
    value = _usd(re.sub(r"[^\d,]", "", pick), "million")
    gain = value if "(" in pick else -value  # the statement subtracts gains from net income, so brackets mean a gain
    return [("equity_gains_year_to_date", gain, "USD", _tidy(f"{m.group('head')} ... {m.group('body')}"))]


def _shares(item: str, pcts: list[float], evidence: str) -> list[tuple]:
    return [(f"{item}_share", sum(pcts), "percent", evidence),
            (f"{item}_count", len(pcts), "count", evidence),
            (f"{item}_largest", max(pcts) if pcts else 0, "percent", evidence)]


def receivables_concentration(full: str) -> list[tuple]:
    """Customers above 10% of receivables: their combined share, how many, and the largest."""
    m = re.search(r"\w+ (?:direct )?customers? (?P<each>each )?accounted for (?P<pcts>[\d %,and]+?) of our accounts receivable balance as of "
                  + DATE + r"\.", full)
    if not m:
        return []
    pcts = [float(x) for x in re.findall(r"\d+", m.group("pcts"))]
    if m.group("each"):  # "Two customers each accounted for 11%"
        pcts = pcts * {"two": 2, "three": 3, "four": 4, "five": 5}[m.group(0).split()[0].lower()]
    return _shares("receivables_top_customers", pcts, _tidy(m.group(0)))


def revenue_concentration(full: str, fiscal_year: int) -> list[tuple]:
    """Direct customers above 10% of revenue, for the quarter (10-Q) or the fiscal year (10-K)."""
    for pattern in REVENUE_SHARE:
        m = re.search(pattern.replace("{fy}", str(fiscal_year)), full)
        if not m:
            continue
        g = m.groupdict()
        if g.get("table"):
            first_column = re.findall(r"Customer [A-E] (\d+ ?%|\*)", g["table"])
            pcts = [float(x.rstrip(" %")) for x in first_column if x != "*"]
        else:
            pcts = [float(x) for x in re.findall(r"(\d+) ?%", g.get("pcts") or "")]
        return _shares("revenue_top_customers", pcts, _tidy(m.group(0)))
    return []


def loans(full: str) -> list[tuple]:
    """Loans or notes receivable from customers. None is disclosed; the row records that the search was made."""
    hits = sorted({m.group(0).lower() for m in re.finditer(LOANS, full)})
    found = f"mentions found: {', '.join(hits)}" if hits else "no mention of a loan, note receivable or customer financing in this document"
    return [("loans_or_notes_receivable_from_customers", None, "USD", f"not disclosed ({found})")]


def named(full: str) -> list[tuple]:
    rows = []
    for item, pattern in NAMED:
        m = re.search(pattern, full)
        if m:
            g = m.groupdict()
            rows.append((item, _usd(g["amount"], g["unit"]) if g.get("amount") else None, "USD", _tidy(m.group(0))))
    return rows


def document_rows(doc: dict, names_only: bool = False) -> list[dict]:
    """Every figure one document discloses. `doc` is an EDGAR filing dict; an 8-K exhibit carries a
    `label` that replaces its form in the output."""
    full = " ".join(text.filing_sentences(CIK, doc))
    found = named(full)
    if not names_only:
        annual = doc["form"] == "10-K"
        year, month = int(doc["period"][:4]), int(doc["period"][5:7])
        for spec in SPECS:
            hit = extract(spec, full)
            if hit:
                found.append((spec["item"], hit[0], spec["unit"], hit[1]))
        found += revenue(full, annual) + public_equity(full) + equity_gains(full) + receivables_concentration(full)
        found += revenue_concentration(full, year + 1 if month >= 2 else year)
        if doc.get("search_loans", True):
            found += loans(full)
    url = edgar.primary_doc_url(CIK, doc)
    return [dict(period_end=doc["period"], form=doc.get("label", doc["form"]), item=item, amount=amount, unit=unit,
                 evidence=evidence, url=url) for item, amount, unit, evidence in found]


def periodic_filings() -> list[dict]:
    return sorted((f for f in edgar.filings(CIK, forms=("10-K", "10-Q")) if f["period"] >= SINCE), key=lambda f: f["period"])


def current_reports(after: str) -> list[dict]:
    """Documents from 8-Ks filed after the latest 10-Q or 10-K period: the 8-K itself and, for a
    quarter with no 10-Q yet, the earnings exhibits."""
    docs = []
    for f in edgar.filings(CIK, forms=("8-K",)):
        if f["filed"] <= after:
            continue
        body = " ".join(text.filing_sentences(CIK, f))
        docs.append(dict(f, names_only=True))
        quarter = re.search(r"results for the quarter ended (" + DATE + r")", body)
        period = pd.to_datetime(quarter.group(1)).strftime("%Y-%m-%d") if quarter else ""
        if period <= after:
            continue  # not an earnings release, or the quarter already has a 10-Q
        for name in edgar.filing_files(CIK, f["accession"]):
            kind = ("CFO commentary" if "cfocommentary" in name else
                    "supplemental financial information" if "supplementalfinancial" in name else None)
            if kind:
                docs.append(dict(f, primary_doc=name, period=period, form="10-Q", label=f"8-K {kind}",
                                 search_loans=kind == "CFO commentary", names_only=False))
    return docs


def holdings_13f() -> list[dict]:
    """Publicly traded shares NVIDIA reports holding, by issuer, from each quarterly 13F-HR."""
    rows = []
    for f in edgar.filings(CIK, forms=("13F-HR",)):
        if f["period"] < SINCE:
            continue
        table = [n for n in edgar.filing_files(CIK, f["accession"]) if n.endswith(".xml") and n != "primary_doc.xml"]
        if not table:
            continue
        url = f"{edgar.filing_base(CIK, f['accession'])}/{table[0]}"
        root = etree.fromstring(edgar.get(url))
        for entry in root.iter("{*}infoTable"):
            cell = {tag: (entry.findtext(f".//{{*}}{tag}") or "").strip()
                    for tag in ("nameOfIssuer", "titleOfClass", "value", "sshPrnamt", "sshPrnamtType")}
            rows.append(dict(period_end=f["period"], form="13F-HR", item=f"named: {cell['nameOfIssuer'].title()} - reported value of shares held",
                             amount=float(cell["value"]), unit="USD",
                             evidence=f"nameOfIssuer {cell['nameOfIssuer']}; titleOfClass {cell['titleOfClass']}; value {cell['value']}; "
                                      f"sshPrnamt {cell['sshPrnamt']} {cell['sshPrnamtType']}", url=url))
    return rows


def derived_rows(df: pd.DataFrame) -> list[dict]:
    """Figures the filings imply but do not state: fourth-quarter and trailing-twelve-month revenue,
    and equity-method investments where only the balance sheet total is given."""
    def value(period: str, item: str) -> float | None:
        hit = df[(df.period_end == period) & (df.item == item)].amount
        return None if hit.empty else hit.iloc[0]

    quarters = df[df.item.isin(["revenue_fiscal_year", "revenue_quarter"])].drop_duplicates("period_end")
    periods = list(quarters.period_end)
    rows, last_year = [], None
    for i, q in enumerate(quarters.itertuples()):
        def add(item: str, amount: float, how: str) -> None:
            rows.append(dict(period_end=q.period_end, form=q.form, item=item, amount=amount, unit="USD", evidence=f"derived: {how}", url=q.url))

        if q.form == "10-K":
            last_year = value(q.period_end, "revenue_fiscal_year")
            nine, source = (value(periods[i - 1], "revenue_year_to_date"), f"10-Q for {periods[i - 1]}") if i else (None, "")
            if nine is None and i + 3 < len(periods):  # first year in the file: next year's third-quarter 10-Q shows it as a comparison
                nine, source = value(periods[i + 3], "revenue_prior_year_to_date"), f"comparison column of the 10-Q for {periods[i + 3]}"
            if nine is not None:
                add("revenue_quarter", last_year - nine,
                    f"fiscal-year revenue ${last_year / 1e6:,.0f}m (this 10-K) minus nine-month revenue ${nine / 1e6:,.0f}m ({source})")
            add("revenue_trailing_twelve_months", last_year, f"fiscal-year revenue ${last_year / 1e6:,.0f}m (this 10-K)")
        elif last_year is not None:
            ytd, before = value(q.period_end, "revenue_year_to_date"), value(q.period_end, "revenue_prior_year_to_date")
            add("revenue_trailing_twelve_months", last_year + ytd - before,
                f"last fiscal year ${last_year / 1e6:,.0f}m plus year to date ${ytd / 1e6:,.0f}m minus the same months a year earlier ${before / 1e6:,.0f}m")
        on_sheet, equity = value(q.period_end, "nonmarketable_securities_on_balance_sheet"), value(q.period_end, "nonmarketable_equity_securities")
        if value(q.period_end, "equity_method_investments") is None and on_sheet and equity and on_sheet > equity:
            add("equity_method_investments", on_sheet - equity,
                f"non-marketable securities on the balance sheet ${on_sheet / 1e6:,.0f}m minus non-marketable equity securities ${equity / 1e6:,.0f}m")
    return rows


def _fingerprint(rows: pd.DataFrame) -> str:
    """Short hash of everything taken from one document, so a changed row cannot stay marked as read."""
    lines = [f"{r.item}|{r.amount}|{r.evidence}" for r in rows.sort_values(["item", "evidence"]).itertuples()]
    return hashlib.sha1("\n".join(lines).encode()).hexdigest()[:10]


def mark_verified(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["verified"] = "no"
    for url, rows in df.groupby("url"):
        if READ_BY_HAND.get(url.rsplit("/", 2)[-2] + "/" + url.rsplit("/", 1)[-1]) == _fingerprint(rows):
            df.loc[rows.index, "verified"] = "yes"
    return df


SUM_PARTS = {
    "guarantees_max_exposure": ["guarantees_land_power_shell", "guarantees_power_and_systems", "guarantees_sb_energy_cap"],
    "narrow_support": ["guarantees_max_exposure", "loans_to_customers", "equity_investment_commitments"],
    "equity_stakes_carrying_value": ["nonmarketable_equity_securities", "equity_method_investments", "public_equity_securities",
                                     "convertible_debt_in_public_companies", "public_company_warrants_fair_value"],
    "capacity_buyback_commitments": ["cloud_service_agreements", "ai_cloud_agreements"],
    "broad_support": ["narrow_support", "equity_stakes_carrying_value", "capacity_buyback_commitments",
                      "leases_not_commenced_for_third_parties"],
}
EXPECTED = ["guarantees_land_power_shell", "loans_to_customers", "equity_investment_commitments", "nonmarketable_equity_securities",
            "public_equity_securities", "cloud_service_agreements", "leases_not_commenced_for_third_parties"]


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """One row per quarter: the components, the three measures, and each measure over trailing revenue."""
    quarterly = df[~df.item.str.startswith("named:") & df.form.str.contains("10-|8-K ")]
    s = quarterly.pivot_table(index="period_end", columns="item", values="amount", aggfunc="first")
    s.insert(0, "form", quarterly.groupby("period_end").form.agg(lambda x: "10-K" if "10-K" in set(x) else "10-Q" if "10-Q" in set(x)
                                                                  else "8-K (10-Q not yet filed)"))
    s = s.rename(columns={"loans_or_notes_receivable_from_customers": "loans_to_customers",
                          "revenue_trailing_twelve_months": "revenue_ttm"})
    for column in {c for parts in SUM_PARTS.values() for c in parts} | {"customer_advances", "guarantees_escrow_placed_by_partners",
                                                                         "leases_not_commenced_own_or_unassigned", "loans_to_customers"}:
        if column not in s:
            s[column] = float("nan")
    # A guarantee signed after the balance sheet date is reported with that quarter but was not yet in force.
    early = s.index < SB_ENERGY_SIGNED
    s["guarantees_signed_after_period_end"] = s["guarantees_sb_energy_cap"].where(early)
    s.loc[early, "guarantees_sb_energy_cap"] = float("nan")
    s["not_disclosed"] = [", ".join(c for c in EXPECTED if pd.isna(row[c])) for _, row in s.iterrows()]
    for total, parts in SUM_PARTS.items():
        s[total] = s[parts].sum(axis=1, min_count=1)
    s[["narrow_support", "broad_support"]] = s[["narrow_support", "broad_support"]].fillna(0)
    s["deferred_revenue"] = s[["deferred_revenue_current", "deferred_revenue_long_term"]].sum(axis=1, min_count=1)
    s["days_sales_outstanding"] = (s.accounts_receivable / s.revenue_quarter * 91).round(1)
    s["receivables_at_45_days"] = (s.revenue_quarter * 45 / 91).round()
    s["receivables_stretch"] = s.accounts_receivable - s.receivables_at_45_days
    gains = s.equity_gains_year_to_date
    first_quarter = s.index.str[5:7].isin(["04", "05"])
    s["equity_gains_quarter"] = gains.where(first_quarter, gains - gains.shift(1))
    for measure in ("narrow_support", "broad_support", "receivables_stretch"):
        s[f"{measure}_share_of_ttm_revenue"] = (s[measure] / s.revenue_ttm).round(4)
    columns = ["form", "revenue_quarter", "revenue_ttm", "accounts_receivable", "days_sales_outstanding", "days_sales_outstanding_reported",
               "receivables_at_45_days", "receivables_stretch", "receivables_stretch_share_of_ttm_revenue",
               "receivables_top_customers_share", "receivables_top_customers_count", "receivables_top_customers_largest",
               "revenue_top_customers_share", "revenue_top_customers_count", "revenue_top_customers_largest",
               "deferred_revenue", "customer_advances",
               "guarantees_land_power_shell", "guarantees_power_and_systems", "guarantees_sb_energy_cap", "guarantees_max_exposure",
               "guarantees_signed_after_period_end", "guarantees_escrow_placed_by_partners", "loans_to_customers",
               "equity_investment_commitments", "narrow_support", "narrow_support_share_of_ttm_revenue",
               "nonmarketable_equity_securities", "equity_method_investments", "public_equity_securities",
               "convertible_debt_in_public_companies", "public_company_warrants_fair_value", "equity_stakes_carrying_value",
               "cloud_service_agreements", "ai_cloud_agreements", "capacity_buyback_commitments",
               "leases_not_commenced_for_third_parties", "leases_not_commenced_own_or_unassigned",
               "broad_support", "broad_support_share_of_ttm_revenue", "equity_gains_year_to_date", "equity_gains_quarter", "not_disclosed"]
    return s.reindex(columns=columns).reset_index()


def xbrl_matches(df: pd.DataFrame, filings: list[dict]) -> tuple[int, int, list[str]]:
    """How many dollar figures from 10-Ks and 10-Qs also appear in the same filing as a tagged fact dated at the
    period end. A figure that adds two table rows will not match; anything else unmatched deserves a second look."""
    found = total = 0
    missing = []
    for f in filings:
        facts = xbrl.numeric(xbrl.filing_facts(CIK, f))
        rows = df[(df.url == edgar.primary_doc_url(CIK, f)) & (df.unit == "USD") & df.amount.notna() & ~df.evidence.str.startswith("derived")
                  & ~df.item.str.startswith("named:") & (df.item != "revenue_prior_year_to_date")]  # those describe another date
        for r in rows.itertuples():
            total += 1
            if not facts.empty and ((facts.end == f["period"]) & ((facts.value.abs() - abs(r.amount)).abs() < 1)).any():
                found += 1
            else:
                missing.append(f"{r.period_end} {r.item}")
    return found, total, missing


def main() -> None:
    filings = periodic_filings()
    latest = filings[-1]["period"]
    docs = filings + current_reports(after=latest)
    rows = [r for d in docs for r in document_rows(d, names_only=d.get("names_only", False))]
    df = pd.DataFrame(rows + holdings_13f())
    df = pd.concat([df, pd.DataFrame(derived_rows(df))], ignore_index=True)
    df = mark_verified(df).sort_values(["period_end", "form", "item"]).reset_index(drop=True)
    summary = summarise(df)
    OUT.mkdir(parents=True, exist_ok=True)
    df[["period_end", "form", "item", "amount", "unit", "evidence", "url", "verified"]].to_csv(OUT / "nvidia_customer_financing.csv", index=False)
    summary.to_csv(OUT / "nvidia_financing_summary.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    pd.set_option("display.max_colwidth", 90)
    newest = summary.period_end.max()
    print(f"NVIDIA customer financing: {len(df)} rows from {df.url.nunique()} documents; latest 10-Q or 10-K period {latest}; "
          f"latest quarter covered {newest}" + (" (from the earnings 8-K: its 10-Q is not on EDGAR yet)" if newest > latest else ""))
    show = summary.set_index("period_end")[["revenue_quarter", "revenue_ttm", "accounts_receivable", "receivables_stretch",
                                             "guarantees_max_exposure", "equity_investment_commitments", "narrow_support",
                                             "equity_stakes_carrying_value", "capacity_buyback_commitments",
                                             "leases_not_commenced_for_third_parties", "broad_support"]].div(1e9).round(1)
    show.columns = ["rev_qtr", "rev_ttm", "receivables", "stretch", "guarantees", "equity_commit", "NARROW", "equity_stakes",
                    "capacity", "leases_3rd", "BROAD"]
    show.insert(3, "dso", summary.days_sales_outstanding.values)
    for measure, label in (("narrow_support", "narrow_%ttm"), ("broad_support", "broad_%ttm"), ("receivables_stretch", "stretch_%ttm")):
        show[label] = (summary[f"{measure}_share_of_ttm_revenue"].values * 100).round(1)
    print("\nPer quarter, $bn (empty = not disclosed; shares are of trailing-twelve-month revenue)\n")
    print(show.to_string())
    after = summary[summary.guarantees_signed_after_period_end.notna()]
    for r in after.itertuples():
        print(f"\nNot in the {r.period_end} totals: ${r.guarantees_signed_after_period_end / 1e9:.0f}bn of guarantees signed after that date.")
    names = df[df.item.str.startswith("named:") & (df.form != "13F-HR")]
    print("\nStatements naming a counterparty (10-K, 10-Q, 8-K)\n")
    print(names.assign(amount=(names.amount / 1e9).round(2))[["period_end", "form", "item", "amount"]].to_string(index=False))
    last_13f = df[(df.form == "13F-HR") & (df.period_end == df[df.form == "13F-HR"].period_end.max())]
    print(f"\nPublic holdings in the latest 13F-HR ({last_13f.period_end.max()}), $bn\n")
    print(last_13f.assign(amount=(last_13f.amount / 1e9).round(2), item=last_13f.item.str[7:])[["item", "amount"]]
          .sort_values("amount", ascending=False).to_string(index=False))
    found, total, missing = xbrl_matches(df, filings)
    print(f"\nDollar figures from 10-Ks and 10-Qs that also appear as an XBRL fact for the same period end: {found} of {total}")
    if missing:
        print("  not tagged with the same value: " + "; ".join(missing))
    unread = df[df.verified == "no"]
    print(f"\nEvidence read by hand: {int((df.verified == 'yes').sum())} of {len(df)} rows")
    for url, rows in unread.groupby("url"):
        print(f'  unread: "{url.rsplit("/", 2)[-2]}/{url.rsplit("/", 1)[-1]}": "{_fingerprint(df[df.url == url])}",')


if __name__ == "__main__":
    main()
