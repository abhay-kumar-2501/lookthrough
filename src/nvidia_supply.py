"""The supply pre-order test: how far ahead of its sales has NVIDIA ordered?

NVIDIA designs chips but does not make them. Wafers, memory, packaging and
factory capacity are bought from suppliers, and because those take a year or
more to arrive NVIDIA has to order long before it knows what customers will
buy. Three numbers in its filings track that bet:

  supply commitments   what NVIDIA has promised to pay suppliers for goods and
                       capacity not yet delivered. Nothing is on the balance
                       sheet yet; the figure sits in the commitments footnote.
  inventories          goods already delivered and paid for, waiting to be sold.
  excess purchase      a liability booked when NVIDIA decides it has ordered more
  obligation accrual   than it can sell. The cost goes through cost of revenue
                       at that moment, even though the goods have not arrived.

When demand falls short the pre-orders turn into "inventory provisions": a
write-down of stock on hand plus a charge for orders that cannot be cancelled.
Both lower gross margin in the quarter they are recognised. If reserved stock
is later sold after all, the reserve is released and gross margin benefits.

The test is to scale the commitments by the size of the business:

  years of cost of revenue = supply commitments / cost of revenue over the
                             last four quarters

Cost of revenue is what NVIDIA paid for the goods it sold in a year, so a
ratio of 1.0 means "a full year of purchases is already on order". The same
figure divided by revenue is also reported, and because a trailing year
understates a business that is doubling, so is a version scaled by the latest
quarter's cost of revenue times four. The script then finds each earlier
peak in the ratio and lists what revenue, gross margin and inventory charges
did over the next eight quarters. It describes what happened; it does not
claim the commitments caused it.

The wording of the commitments figure has changed four times, giving five
definitions. Each change is a break in the series (see SERIES below and
notes/nvidia_supply_notes.md):

  A  to May 2021    inventory purchase obligations only
  B  Aug 2021       adds the unpaid part of long-term supply agreements
  C  Apr 2023       adds capacity agreements
  D  Oct 2025       renamed "manufacturing, supply and capacity commitments"
  E  Jul 2026       one row, "supply and capacity", of a table in $ billions

Sources: every 10-K and 10-Q with a period end since January 2019. Amounts and
charges are read from the text, each kept with the sentence it came from;
revenue, cost of revenue, inventories and the accrual come from each filing's
XBRL data. If the newest quarter has only been announced on Form 8-K (the
10-Q follows a few weeks later) it is added from the 8-K and labelled so.

Outputs, in data/processed/:

  nvidia_supply.csv             one row per fiscal quarter
  nvidia_commitments_table.csv  every row and time bucket of each commitments
                                table or schedule the filings give
  nvidia_supply_peers.csv       the same ratio for AMD and Broadcom, for context

`verified` is "yes" only where the amounts in a row equal what a person read
in the evidence sentences (HAND_READ below). Anything new is "no" until read.

Amounts are totals over the life of the contracts. They are NOT debt and many
can be rescheduled or cancelled at a cost.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd
from bs4 import BeautifulSoup

import edgar
import text
import xbrl

CIK = 1045810
SINCE = "2019-01-01"
OUT = edgar.ROOT / "data" / "processed"
DATE = r"[A-Z][a-z]+ \d{1,2} ?, \d{4}"
REST = r"(?:[^.]|\.(?=\d))*?"  # the rest of a sentence, not stopping at the point in "$4.5 billion"
END = r"\.(?!\d)"  # the full stop that ends it
CELL = r"(?:\$ ?)?(?:[\d,]+(?:\.\d+)?|—)"  # one table cell: a number or a dash
_UNITS = {"billion": 1e9, "million": 1e6}


def _amt(name: str) -> str:
    """Regex for '$ 4.79 billion' that stores the number and unit under `name`."""
    return r"\$ ?(?P<" + name + r">[\d,]+(?:\.\d+)?) ?(?P<" + name + r"_unit>billion|million)"


# The five definitions of "supply commitments", oldest first. `includes` is written into the
# CSV so a reader can see what each number covers. Named groups: amount = the total,
# due12 = stated as falling in the next 12 months, unpaid = owed on long-term supply
# agreements (already inside the total), first = due in the rest of this fiscal year.
SERIES = [
    dict(id="A_inventory_purchase_obligations",
         includes="Open orders for wafers, components and finished goods (inventory purchase obligations) only",
         patterns=[r"As of " + DATE + r" ?, we had outstanding inventory purchase obligations totaling " + _amt("amount")
                   + r"(?P<all12> ?,? which are expected to occur over the next 12 months)?" + REST + END]),
    dict(id="B_plus_long_term_supply",
         includes="Inventory purchase obligations plus amounts still to be paid under long-term supply agreements "
                  "(money already prepaid is an asset and is not counted)",
         patterns=[r"As of " + DATE + r" ?, we had outstanding inventory purchase and long-term supply commitment obligations totaling " + _amt("amount")
                   + r" ?, of which " + _amt("due12") + r" is expected to occur over the next 12 months" + REST + END,
                   r"(?:We (?:have|recently) entered into several long-term supply agreements, under which we have made advance payments and have "
                   + _amt("unpaid") + r" remaining unpaid\. )?"
                   r"As of " + DATE + r" ?, we had outstanding inventory purchase and long-term supply obligations totaling " + _amt("amount") + REST + END]),
    dict(id="C_plus_capacity",
         includes="Inventory purchase obligations plus long-term supply and capacity agreements",
         patterns=[r"As of " + DATE + r" ?, we had outstanding inventory purchases? and long-term supply and capacity obligations totaling " + _amt("amount") + REST + END]),
    dict(id="D_manufacturing_supply_capacity",
         includes="Manufacturing, supply and capacity commitments (the auditor's report in the January 2026 10-K still calls the "
                  "same $95.2bn 'inventory purchase and long-term supply and capacity obligations')",
         patterns=[r"(?P<head>(?:Manufacturing production, long-term supply and capacity, and other related|Manufacturing, supply, and capacity) "
                   r"commitments reflect" + REST + END + r") .{0,500}?(?P<body>As of " + DATE + r" ?, these commitments were " + _amt("amount")
                   + r"(?: for which " + _amt("first") + r" will be paid in the remainder of fiscal year \d{4})?" + REST + END + r")"]),
    dict(id="E_supply_and_capacity_row",
         includes="'Supply and capacity' row of the commitments table, rounded to $ billions: data center systems supply, "
                  "primarily memory and manufacturing facilities",
         patterns=[r"(?P<head>Future commitments by fiscal year as of " + DATE + r" ?, were as follows: [^$]{0,120}?\(In billions\)) "
                   r"(?P<body>Supply and capacity (?P<cells>" + CELL + r"(?: " + CELL + r"){6}))"]),
]

REVENUE = ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]
COST = ["CostOfRevenue", "CostOfGoodsAndServicesSold"]
PREPAID = ["PrepaidSupplyAgreementsNoncurrent", "PrepaidSupplyAndCapacityAgreementsNoncurrent"]
ACCRUAL = ["ExcessInventoryPurchaseObligationsCurrent"]
PO_CHARGE_DIM = "NatureOfExpenseAxis=InventoryPurchaseObligationsInExcessOfProjectionsMember"
PO_CHARGE_OLD = "InventoryPurchaseObligationExceedingDemandProjectionsCancellationsAndPenaltiesExpense"

PROVISION = (r"(?:Inventory provisions(?: for excess inventory and purchase obligations)?"
             r"|(?:Reserves|Provisions) for inventory and excess inventory purchase obligations) totaled ")
RELEASE = (r"(?:Sales of inventory that was previously written[- ]off(?: or (?:written)?-? ?down)?"
           r"(?: ?, or settlements of excess inventory purchase obligations,)? totaled"
           r"|Sales of previously reserved inventory (?:or|and) settlements of excess inventory purchase obligations resulted in a provision release of) ")
SPAN = _amt("a") + r"(?: and " + _amt("b") + r")?" + REST + r"(?:for|in) (?:both )?(?:the )?(?P<span>(?:(?:first|second|third) quarter|first half|first nine months|fiscal year)" + REST + r")" + END

# Amounts read by eye in the evidence sentences, in $ millions:
#   (supply commitments, provisions for the quarter, releases for the quarter,
#    excess-purchase accrual in the liabilities table, first amount of the due split)
# None = the filing does not state it. Fourth-quarter charges were read as the full-year figure
# in the 10-K and the nine-month figure in the third-quarter 10-Q; the entry is the difference.
# The due split is the 12-month figure where one is given, otherwise the rest-of-fiscal-year bucket.
# A row is `verified = yes` only if it reproduces these, so a new filing starts as "no".
HAND_READ: dict[str, tuple] = {
    "2019-01-27": (912, None, None, None, 912),
    "2019-04-28": (782, 43, 12, None, None),
    "2019-07-28": (757, 28, 19, None, None),
    "2019-10-27": (980, 42, 78, None, None),
    "2020-01-26": (1160, 47, 36, None, 1156),
    "2020-04-26": (1760, 36, 39, None, None),
    "2020-07-26": (2040, 45, 49, None, None),
    "2020-10-25": (2570, 15, 29, None, None),
    "2021-01-31": (2540, 20, 29, None, 2540),
    "2021-05-02": (3460, 58, 21, None, 3460),
    "2021-08-01": (4790, 73, 20, None, 4590),
    "2021-10-31": (6900, 107, 48, None, 2944),
    "2022-01-30": (9000, 116, 22, 196, 9302),
    "2022-05-01": (9590, 90, 15, 258, 8344),
    "2022-07-31": (9220, 1220, 23, 866, 7108),
    "2022-10-30": (7020, 702, 21, 1181, 4234),
    "2023-01-29": (4920, 160, 78, 954, 5230),
    "2023-04-30": (7270, 134, 50, 786, 6667),
    "2023-07-30": (11150, 576, 84, 870, 8439),
    "2023-10-29": (17110, 681, 239, 1280, 6499),
    "2024-01-28": (16100, 810, 168, 1655, 17316),
    "2024-04-28": (18800, 393, 114, 1684, 19306),
    "2024-07-28": (27800, 908, 85, 2051, 21934),
    "2024-10-27": (28900, 865, 106, 1728, 14178),
    "2025-01-26": (30800, 1500, 384, 2095, 35727),
    "2025-04-27": (29800, 5300, 436, 4310, 31445),
    "2025-07-27": (None, 1000, 501, 3154, 30930),
    "2025-10-26": (50300, 410, 366, 2770, None),
    "2026-01-25": (95200, 500, 200, 2739, None),
    "2026-04-26": (119000, 1100, 103, 3121, 95000),
    "2026-07-26": (279000, 985, 177, 2138, 92000),
    "2026-10-25": (390000, None, None, None, 69000),  # Form 8-K CFO commentary, not a 10-Q
}


def _usd(num: str | None, unit: str | None) -> float | None:
    if num is None:
        return None
    return round(float(num.replace(",", "")) * _UNITS[unit.lower()])


def _tidy(passage: str) -> str:
    """Close the gaps the HTML leaves inside '$ 1.2 billion' and before commas."""
    return re.sub(r" ([,.])(?= |$)", r"\1", re.sub(r"\$ (?=[\d—])", "$", passage)).strip()


def fiscal(period_end: str) -> tuple[int, int]:
    """NVIDIA's fiscal year ends on the last Sunday of January and is named for that January."""
    d = date.fromisoformat(period_end)
    return (d.year if d.month == 1 else d.year + 1), {1: 4, 4: 1, 5: 1, 7: 2, 8: 2, 10: 3, 11: 3}[d.month]


# ---------------------------------------------------------------- supply commitments

def supply_commitment(full: str) -> dict | None:
    """The supply-side commitment a filing states, under whichever definition it uses."""
    for series in reversed(SERIES):  # newest wording first
        for pattern in series["patterns"]:
            m = re.search(pattern, full)
            if not m:
                continue
            g = m.groupdict()
            out = {"definition": series["id"], "includes": series["includes"], "due12": None, "first": None, "second": None, "unpaid": None}
            if g.get("cells"):  # table row in $ billions: buckets then the total
                cells = _cells(g["cells"])
                out.update(amount=cells[-1] * 1e9, first=cells[0] * 1e9, second=cells[1] * 1e9)
                said = re.search(r"(?:We have significantly increased our supply and capacity commitments from|Our supply commitments increased from)" + REST + END, full)
                evidence = f"{g['head']} ... {g['body']}" + (f" ... {said.group(0).strip()}" if said else "")
            else:
                out["amount"] = _usd(g["amount"], g["amount_unit"])
                out["due12"] = out["amount"] if g.get("all12") else _usd(g.get("due12"), g.get("due12_unit"))
                out["first"] = _usd(g.get("first"), g.get("first_unit"))
                out["unpaid"] = _usd(g.get("unpaid"), g.get("unpaid_unit"))
                evidence = f"{g['head']} ... {g['body']}" if g.get("head") else m.group(0)
            out["evidence"] = _tidy(evidence)
            return out
    return None


def prepaid_short_term(full: str) -> tuple[float, str] | None:
    """Prepayments to suppliers due back as goods within a year (a footnote to the 'other assets' table)."""
    m = re.search(r"Prepaid supply and capacity agreements \(1\) " + CELL + r" " + CELL + r" .{0,260}?(?P<note>\(1\) " + REST
                  + _amt("amount") + REST + END + r")", full)
    return (_usd(m["amount"], m["amount_unit"]), _tidy(m["note"])) if m else None


def accrual_in_table(full: str) -> tuple[float, str] | None:
    """The excess-purchase accrual as printed in the 'accrued and other current liabilities' table ($ millions)."""
    m = re.search(r"Accrued and Other Current Liabilities: .{0,330}?(?P<row>Excess inventory purchase obligations (?:\(\d\) )?(?P<now>[\d,]+) (?P<then>[\d,]+))", full)
    return (float(m["now"].replace(",", "")) * 1e6, "Accrued and Other Current Liabilities (in millions; this period, then the last year end) ... " + m["row"]) if m else None


# ---------------------------------------------------------------- commitments tables

def _cells(cells: str) -> list[float]:
    return [0.0 if c == "—" else float(c.replace(",", "")) for c in re.findall(r"[\d,]+(?:\.\d+)?|—", cells)]


def _grid(table: str, head: str, body: str, columns: list[str], scale: float) -> list[dict]:
    """Rows of a label-then-numbers table. A row is a label followed by one cell per column."""
    rows = []
    row = r"(?P<label>[A-Z][A-Za-z,&.\- ]+?)(?: \(\d\))* (?P<cells>" + CELL + r"(?: " + CELL + r"){" + str(len(columns) - 1) + r"})(?= |$)"
    for m in re.finditer(row, body):
        for bucket, value in zip(columns, _cells(m["cells"])):
            rows.append(dict(table=table, row=m["label"].strip(), bucket=bucket, amount=value * scale,
                             evidence=_tidy(f"{head} ... {m.group(0)}")))
    return rows


def _buckets(n: int, period_end: str, form: str) -> list[str]:
    """Labels for n payment buckets: rest of this fiscal year (10-Q only), then one per year, then 'and thereafter'."""
    fy, _ = fiscal(period_end)
    years = list(range(fy, fy + n)) if form != "10-K" else list(range(fy + 1, fy + 1 + n))
    labels = [str(y) for y in years]
    if form != "10-K":
        labels[0] = f"Remainder of {fy}"
    labels[-1] += " and thereafter"
    return labels


def commitment_tables(full: str, period_end: str, form: str) -> list[dict]:
    """Every commitments table, schedule or itemised sentence in the filing, one row per cell."""
    rows: list[dict] = []
    # 1. The multi-row tables in $ billions (from July 2026) and the guarantees table beside them.
    names = iter(["commitments", "additional_commitments"])
    for m in re.finditer(r"(?P<head>Future (?P<extra>additional )?commitments by fiscal year as of " + DATE + r" ?, were as follows: "
                         r"(?P<cols>(?:Remainder of )?\d{4}(?: \d{4})+ and thereafter Total) \(In billions\)) (?P<body>.{0,700})", full):
        columns = re.findall(r"Remainder of \d{4}|\d{4} and thereafter|\d{4}|Total", m["cols"])
        name = "additional_commitments" if m["extra"] else next(names, "additional_commitments")
        rows += _grid(name, m["head"], m["body"], columns, 1e9)
    m = re.search(r"(?P<head>The following table summarizes the maximum gross exposure related to our guarantees[^:]*: "
                  r"(?:" + DATE + r" )?(?:\(In billions\))?) ?(?P<body>.{0,400}?Total " + CELL + r")", full)
    if m:
        rows += _grid("guarantees_maximum_exposure", m["head"], m["body"], ["Maximum gross exposure"], 1e9)
    # 2. The one-row schedule of all purchase commitments by fiscal year (October 2021 to July 2025).
    m = re.search(r"(?P<head>Total (?:gross )?future (?:unconditional )?(?:purchase )?commitments as of " + DATE + r" ?,? are as follows: "
                  r"(?:Purchase )?Commitments \(In millions\) Fiscal Year:) (?P<body>.{20,400}?Total \$ ?[\d,]+)", full)
    if m:
        cells = re.findall(r"(\d{4}(?: \([^)]*\))?(?: and thereafter)?|Total) \$? ?([\d,]+)", m["body"])
        for label, value in cells:
            rows.append(dict(table="purchase_commitments_schedule", row="All purchase commitments (supply plus other)", bucket=label,
                             amount=float(value.replace(",", "")) * 1e6, evidence=_tidy(f"{m['head']} {m['body']}")))
    # 3. The contractual obligations table of the fiscal 2019 and 2020 annual reports.
    m = re.search(r"(?P<head>The following table summarizes our contractual obligations as of " + DATE + r" ?: Payment Due By Period Contractual "
                  r"Obligations (?P<cols>Total Less than 1 Year 1-3 Years 4-5 Years More than 5 Years(?: All Other)?) \(In millions\)) "
                  r"(?P<body>.{0,700}?Total contractual obligations (?:" + CELL + r" ?)+)", full)
    if m:
        columns = re.findall(r"Total|Less than 1 Year|1-3 Years|4-5 Years|More than 5 Years|All Other", m["cols"])
        rows += _grid("contractual_obligations", m["head"], m["body"], columns, 1e6)
    # 4. Items stated in sentences next to the supply figure.
    rows += _sentence_items(full, period_end, form)
    return rows


def _sentence_items(full: str, period_end: str, form: str) -> list[dict]:
    """Other purchase obligations, cloud service agreements and investment commitments given in prose."""
    rows = []
    singles = [
        ("Capital purchase obligations", r"we had outstanding capital purchase obligations totaling " + _amt("amount")),
        ("Other purchase obligations (non-inventory)", r"[Oo]ther (?:non-inventory )?purchase obligations (?:totaling|of|were) " + _amt("amount") + REST + END),
        ("Multi-year cloud service agreements (part of other purchase obligations)",
         r"[Oo]ther non-inventory purchase obligations (?:of|were) \$ ?[\d.]+ billion,? (?:which )?includ(?:e|es|ing) " + _amt("amount")
         + r" of multi-year cloud service agreements" + REST + END),
        ("Investment commitments", r"I ?nvestment commitments are " + _amt("amount") + REST + END),
        ("Other commitments", r"Other (?:vendor )?commitments were " + _amt("amount") + REST + END),
    ]
    for label, pattern in singles:
        m = re.search(pattern, full)
        if m:
            rows.append(dict(table="commitments_note", row=label, bucket="Total", amount=_usd(m["amount"], m["amount_unit"]), evidence=_tidy(m.group(0))))
    hit = supply_commitment(full)
    if hit and not hit["definition"].startswith("E_"):
        rows.append(dict(table="commitments_note", row="Supply commitments (" + hit["definition"] + ")", bucket="Total", amount=hit["amount"], evidence=hit["evidence"]))
        if hit["first"] is not None:
            rows.append(dict(table="commitments_note", row="Supply commitments (" + hit["definition"] + ")", bucket=_buckets(2, period_end, form)[0],
                             amount=hit["first"], evidence=hit["evidence"]))
    m = re.search(r"Multi-year cloud service agreement commitments as of " + DATE + r" ?, were " + _amt("amount")
                  + r",? for which (?P<parts>(?:(?:and )?\$ ?[\d.]+ billion,? ){2,8})will be paid in" + REST + END, full)
    if m:
        parts = [float(x) * 1e9 for x in re.findall(r"\$ ?([\d.]+) billion", m["parts"])]
        for bucket, value in zip(_buckets(len(parts), period_end, form) + ["Total"], parts + [_usd(m["amount"], m["amount_unit"])]):
            rows.append(dict(table="commitments_note", row="Multi-year cloud service agreements", bucket=bucket, amount=value, evidence=_tidy(m.group(0))))
    return rows


def schedule_total(tables: list[dict]) -> float | None:
    """Total of the filing's main commitments table or schedule (supply plus everything else in it)."""
    for r in tables:
        if r["bucket"] == "Total" and (r["table"] == "purchase_commitments_schedule" or (r["table"] == "commitments" and r["row"] == "Total")):
            return r["amount"]
    return None


def due_split(hit: dict | None, tables: list[dict], form: str) -> dict:
    """How much falls due soon, and against which total: the supply figure itself where the filing
    says, otherwise the schedule of all purchase commitments (supply plus other)."""
    out = dict(due_next_12_months=None, due_rest_of_fiscal_year=None, due_next_fiscal_year=None, due_total=None, due_basis="")
    schedule = [r for r in tables if r["table"] == "purchase_commitments_schedule"]
    old_table = [r for r in tables if r["table"] == "contractual_obligations" and r["row"] == "Inventory purchase obligations"]
    if hit and hit["due12"] is not None:
        out.update(due_next_12_months=hit["due12"], due_total=hit["amount"], due_basis="supply commitments, stated in the sentence")
    elif hit and hit["first"] is not None and form == "10-K":
        out.update(due_next_12_months=hit["first"], due_total=hit["amount"], due_basis="supply commitments")
    elif hit and hit["first"] is not None:
        out.update(due_rest_of_fiscal_year=hit["first"], due_next_fiscal_year=hit["second"], due_total=hit["amount"],
                   due_basis="supply commitments")
    elif old_table:
        cells = {r["bucket"]: r["amount"] for r in old_table}
        out.update(due_next_12_months=cells["Less than 1 Year"], due_total=cells["Total"], due_basis="supply commitments, contractual obligations table")
    elif schedule:
        values = [r["amount"] for r in schedule]
        out.update(due_total=values[-1], due_basis="all purchase commitments (supply plus other)")
        if form == "10-K":
            out["due_next_12_months"] = values[0]
        else:
            out.update(due_rest_of_fiscal_year=values[0], due_next_fiscal_year=values[1])
    elif hit and "substantially all will be paid through" in hit["evidence"]:
        out["due_basis"] = "supply commitments: 'substantially all' by the end of the next fiscal year, no figure given"
    return out


# ---------------------------------------------------------------- statements (XBRL)

def _flow(df: pd.DataFrame, names: list[str], end: str, dims: str = "") -> dict:
    """Quarter and fiscal-year-to-date values of an income-statement item for the period ending `end`."""
    d = df[df.concept.isin(names) & (df.dims == dims) & (df.end == end) & df.start.notna()].copy()
    d["days"] = (pd.to_datetime(d.end) - pd.to_datetime(d.start)).dt.days
    quarter = d[d.days.between(80, 100)]
    ytd = d[(d.days - 91 * fiscal(end)[1]).abs() < 25]  # some items are tagged for the quarter only
    return {"quarter": quarter.value.iloc[0] if len(quarter) else None, "ytd": ytd.value.iloc[0] if len(ytd) else None}


def _year_earlier(df: pd.DataFrame, names: list[str], end: str) -> float | None:
    """The comparative year-to-date figure a 10-Q prints beside the current one."""
    ends = pd.to_datetime(df.end, errors="coerce")
    gap = (pd.Timestamp(end) - ends).dt.days
    d = df[df.concept.isin(names) & (df.dims == "") & df.start.notna() & gap.between(350, 380)].copy()
    if d.empty:
        return None
    d["days"] = (pd.to_datetime(d.end) - pd.to_datetime(d.start)).dt.days
    return d.sort_values("days").value.iloc[-1]


def _instant(df: pd.DataFrame, names: list[str], end: str) -> float | None:
    d = df[df.concept.isin(names) & (df.dims == "") & (df.end == end) & df.start.isna()]
    return d.value.iloc[0] if len(d) else None


_facts: dict[str, pd.DataFrame] = {}


def facts(filing: dict) -> pd.DataFrame:
    if filing["accession"] not in _facts:
        _facts[filing["accession"]] = xbrl.numeric(xbrl.filing_facts(CIK, filing))
    return _facts[filing["accession"]]


def statement_facts(filing: dict) -> dict:
    """Revenue, cost of revenue, inventories and the excess-purchase accrual from the filing's XBRL."""
    df = facts(filing)
    end = filing["period"]
    revenue, cost, gross = _flow(df, REVENUE, end), _flow(df, COST, end), _flow(df, ["GrossProfit"], end)
    po = _flow(df, COST, end, PO_CHARGE_DIM)
    if po["ytd"] is None:
        po = _flow(df, [PO_CHARGE_OLD], end)
    writedown = _flow(df, ["InventoryWriteDown"], end)
    return {
        "revenue": revenue["quarter"], "revenue_ytd": revenue["ytd"], "revenue_ytd_year_earlier": _year_earlier(df, REVENUE, end),
        "cost_of_revenue": cost["quarter"], "cost_ytd": cost["ytd"], "cost_ytd_year_earlier": _year_earlier(df, COST, end),
        "gross_profit": gross["quarter"], "gross_ytd": gross["ytd"],
        "inventories": _instant(df, ["InventoryNet"], end),
        "excess_purchase_accrual": _instant(df, ACCRUAL, end),
        "prepaid_supply_long_term": _instant(df, PREPAID, end),
        "purchase_obligation_charge": po["quarter"], "po_charge_ytd": po["ytd"],
        "inventory_writedown": writedown["quarter"], "writedown_ytd": writedown["ytd"],
    }


def xbrl_check(filing: dict, amount: float) -> str:
    """Concept(s) in the filing's XBRL that carry the supply figure on the period-end date."""
    df = facts(filing)
    hit = df[(df.end == filing["period"]) & ((df.value - amount).abs() < 1) & df.concept.str.contains("Purchase|Commitment")]
    members = hit.dims.str.extract(r"OtherCommitmentsAxis=(\w+)")[0].fillna("")
    return "; ".join(sorted(set(hit.concept + members.map(lambda x: f" [{x}]" if x else ""))))


# ---------------------------------------------------------------- inventory charges

def _charge(full: str, lead: str, fy: int) -> dict:
    """Quarter, year-to-date and full-year amounts of a provision or release for fiscal year `fy`."""
    out = {"quarter": None, "ytd": None, "annual": None, "evidence": []}
    for m in re.finditer(lead + SPAN, full):
        span, a, b = m["span"], _usd(m["a"], m["a_unit"]), _usd(m["b"], m["b_unit"])
        years = re.findall(r"fiscal years? (\d{4})", span)
        if not years or int(years[0]) != fy:
            continue  # the comparative sentence about the year before
        if re.match(r"(first|second|third) quarter and first (half|nine months)", span):
            found = {"quarter": a, "ytd": b}
        elif re.match(r"(first|second|third) quarter", span):
            found = {"quarter": a}
        elif re.match(r"first (half|nine months)", span):
            found = {"ytd": a}
        else:
            found = {"annual": a}
        new = {k: v for k, v in found.items() if out[k] is None and v is not None}
        if new:
            out.update(new)
            out["evidence"].append(_tidy(m.group(0)))
    out["evidence"] = " ... ".join(out["evidence"])
    return out


def inventory_charges(full: str, period_end: str) -> dict:
    """Provisions for inventory and excess purchase obligations, and releases of earlier reserves."""
    fy, _ = fiscal(period_end)
    return {"provision": _charge(full, PROVISION, fy), "release": _charge(full, RELEASE, fy)}


# ---------------------------------------------------------------- one row per filing

def filing_row(filing: dict) -> tuple[dict, list[dict]]:
    full = " ".join(text.filing_sentences(CIK, filing))
    fy, quarter = fiscal(filing["period"])
    url = edgar.primary_doc_url(CIK, filing)
    hit = supply_commitment(full)
    tables = commitment_tables(full, filing["period"], filing["form"])
    charges = inventory_charges(full, filing["period"])
    prepaid = prepaid_short_term(full)
    accrual = accrual_in_table(full)
    row = {
        "period_end": filing["period"], "fiscal_year": fy, "fiscal_quarter": quarter, "form": filing["form"], "filed": filing["filed"],
        "source": filing["form"],
        "supply_commitments": hit["amount"] if hit else None,
        "commit_definition": hit["definition"] if hit else "",
        "commit_includes": hit["includes"] if hit else "not stated separately in this filing",
        "of_which_unpaid_on_supply_agreements": hit["unpaid"] if hit else None,
        **due_split(hit, tables, filing["form"]),
        "all_commitments_in_schedule": schedule_total(tables),
        "prepaid_supply_short_term": prepaid[0] if prepaid else None,
        **statement_facts(filing),
        "provision_raw": charges["provision"], "release_raw": charges["release"],
        "commit_xbrl_tag": xbrl_check(filing, hit["amount"]) if hit else "",
        "commit_evidence": hit["evidence"] if hit else "",
        "prepaid_evidence": prepaid[1] if prepaid else "",
        "accrual_in_text": accrual[0] if accrual else None,
        "accrual_evidence": accrual[1] if accrual else "",
        "url": url,
    }
    for r in tables:
        r.update(period_end=filing["period"], form=filing["form"], source=filing["form"], url=url)
    return row, tables


# ---------------------------------------------------------------- newest quarter from Form 8-K

def _page_text(url: str) -> str:
    soup = BeautifulSoup(edgar.get(url), "lxml")
    return re.sub(r"\s+", " ", soup.get_text(" ").replace("\xa0", " "))


def announced_quarter(last_period: str, last_filed: str) -> tuple[dict, list[dict]] | None:
    """Results announced on Form 8-K for a quarter whose 10-Q is not on EDGAR yet.

    NVIDIA furnishes a CFO commentary (commitments table) and supplemental statements with its
    earnings release, then files the 10-Q some weeks later. These are unaudited and "furnished",
    so the row is labelled as coming from the 8-K and is replaced once the 10-Q is in the list.
    """
    for f in edgar.filings(CIK, forms=("8-K",)):
        if f["filed"] <= last_filed:
            break
        names = edgar.filing_files(CIK, f["accession"])
        commentary = next((n for n in names if "cfocommentary" in n.lower()), None)
        supplement = next((n for n in names if n.lower().startswith("supplementalfinancial")), None)
        if not commentary:
            continue
        base = edgar.filing_base(CIK, f["accession"])
        url, cfo = f"{base}/{commentary}", _page_text(f"{base}/{commentary}")
        as_of = re.search(r"Future commitments by fiscal year as of (" + DATE + r")", cfo)
        if not as_of:
            continue
        period = pd.to_datetime(as_of.group(1)).strftime("%Y-%m-%d")
        if period <= last_period:
            return None
        fy, quarter = fiscal(period)
        hit = supply_commitment(cfo)
        tables = commitment_tables(cfo, period, "10-Q")
        row = {"period_end": period, "fiscal_year": fy, "fiscal_quarter": quarter, "form": "8-K", "filed": f["filed"],
               "source": "8-K CFO commentary and supplemental statements (unaudited; 10-Q not yet filed)",
               "supply_commitments": hit["amount"] if hit else None, "commit_definition": hit["definition"] if hit else "",
               "commit_includes": hit["includes"] if hit else "", **due_split(hit, tables, "10-Q"),
               "all_commitments_in_schedule": schedule_total(tables),
               "provision_raw": {"quarter": None, "ytd": None, "annual": None, "evidence": ""},
               "release_raw": {"quarter": None, "ytd": None, "annual": None, "evidence": ""},
               "commit_xbrl_tag": "", "commit_evidence": hit["evidence"] if hit else "", "prepaid_evidence": "", "url": url}
        if supplement:
            row.update(_supplement_facts(_page_text(f"{base}/{supplement}")))
        for r in tables:
            r.update(period_end=period, form="8-K", source=row["source"], url=url)
        return row, tables
    return None


def _supplement_facts(page: str) -> dict:
    """Income statement lines (quarter, year-ago quarter, year to date, year-ago year to date) and inventories, in $ millions."""
    def line(label: str) -> list[float]:
        m = re.search(label + r" \$? ?([\d,]+) \$? ?([\d,]+) \$? ?([\d,]+) \$? ?([\d,]+)", page)
        return [float(x.replace(",", "")) * 1e6 for x in m.groups()]
    revenue, cost, gross = line("Revenue"), line("Cost of revenue"), line("Gross profit")
    inventories = re.search(r"Inventories ([\d,]+) [\d,]+", page)
    return {"revenue": revenue[0], "revenue_ytd": revenue[2], "revenue_ytd_year_earlier": revenue[3],
            "cost_of_revenue": cost[0], "cost_ytd": cost[2], "cost_ytd_year_earlier": cost[3],
            "gross_profit": gross[0], "gross_ytd": gross[2],
            "inventories": float(inventories.group(1).replace(",", "")) * 1e6}


# ---------------------------------------------------------------- ratios and what followed

def assemble(rows: list[dict]) -> pd.DataFrame:
    """One row per quarter with fourth quarters filled in, trailing-year sums, charges and ratios."""
    df = pd.DataFrame(rows).sort_values("period_end").reset_index(drop=True)
    annual = {r.fiscal_year: r for r in df[df.form == "10-K"].itertuples()}
    nine_months = {r.fiscal_year: r for r in df[df.fiscal_quarter == 3].itertuples()}
    for col in ("revenue_ttm", "cost_of_revenue_ttm", "inventory_provisions", "provision_releases",
                "inventory_provisions_fiscal_year_to_date", "provision_releases_fiscal_year_to_date"):
        df[col] = float("nan")
    df["provision_evidence"], df["release_evidence"], df["charges_basis"] = "", "", ""
    for i, r in df.iterrows():
        _fill_statements(df, i, r, nine_months.get(r.fiscal_year), annual.get(r.fiscal_year - 1))
        _fill_charges(df, i, r, nine_months.get(r.fiscal_year))
    _ratios(df)
    df["verified"] = [verified(r) for r in df.itertuples()]
    return df


def _fill_statements(df: pd.DataFrame, i: int, r: pd.Series, nine, last_year) -> None:
    """A 10-K only gives the year, so the fourth quarter is the year less the first nine months.
    Trailing four quarters = this year to date + last full year - the same months a year ago."""
    if r.form == "10-K":
        for col, ytd in (("revenue", "revenue_ytd"), ("cost_of_revenue", "cost_ytd"), ("gross_profit", "gross_ytd"),
                         ("purchase_obligation_charge", "po_charge_ytd"), ("inventory_writedown", "writedown_ytd")):
            if nine is not None and pd.notna(r[ytd]) and pd.notna(getattr(nine, ytd)):
                df.at[i, col] = r[ytd] - getattr(nine, ytd)
        df.at[i, "revenue_ttm"], df.at[i, "cost_of_revenue_ttm"] = r.revenue_ytd, r.cost_ytd
    elif last_year is not None:
        df.at[i, "revenue_ttm"] = r.revenue_ytd + last_year.revenue_ytd - r.revenue_ytd_year_earlier
        df.at[i, "cost_of_revenue_ttm"] = r.cost_ytd + last_year.cost_ytd - r.cost_ytd_year_earlier


def _fill_charges(df: pd.DataFrame, i: int, r: pd.Series, nine) -> None:
    """Provisions and releases for the quarter. The 10-K states the year only, so the fourth
    quarter is derived, and is only as precise as the rounding of the two figures it comes from."""
    how = "as stated for the quarter"
    for raw, col, evidence in (("provision_raw", "inventory_provisions", "provision_evidence"), ("release_raw", "provision_releases", "release_evidence")):
        c = r[raw]
        value, text_ = c["quarter"], c["evidence"]
        if value is None and r.form == "10-K" and c["annual"] is not None and nine is not None and getattr(nine, raw)["ytd"] is not None:
            value, how = c["annual"] - getattr(nine, raw)["ytd"], "fiscal year less first nine months (derived, subject to rounding in the filings)"
            text_ += " ... [nine months, from the third-quarter 10-Q] " + getattr(nine, raw)["evidence"]
        df.at[i, col] = value
        df.at[i, col + "_fiscal_year_to_date"] = c["annual"] if r.form == "10-K" else c["ytd"] if c["ytd"] is not None else value
        df.at[i, evidence] = text_
    if pd.notna(df.at[i, "inventory_provisions"]):
        df.at[i, "charges_basis"] = how


def _ratios(df: pd.DataFrame) -> None:
    df["gross_margin"] = df.gross_profit / df.revenue
    df["net_inventory_charge"] = df.inventory_provisions - df.provision_releases
    df["provisions_share_of_revenue"] = df.inventory_provisions / df.revenue
    df["net_charge_share_of_revenue"] = df.net_inventory_charge / df.revenue
    df["revenue_growth_year_on_year"] = df.revenue / df.revenue.shift(4) - 1
    df["commitments_years_of_cost_of_revenue"] = df.supply_commitments / df.cost_of_revenue_ttm
    df["commitments_to_revenue_ttm"] = df.supply_commitments / df.revenue_ttm
    # A trailing year understates a business that is doubling, so also scale by the latest quarter x 4.
    df["commitments_years_of_latest_quarter_cost"] = df.supply_commitments / (4 * df.cost_of_revenue)
    df["share_due_next_12_months"] = df.due_next_12_months / df.due_total
    df["share_due_rest_of_fiscal_year"] = df.due_rest_of_fiscal_year / df.due_total
    # At a year end "through next fiscal year" is the next 12 months; in a 10-Q it is 15 to 21 months.
    through = df.due_next_12_months.where(df.form == "10-K", df.due_rest_of_fiscal_year + df.due_next_fiscal_year)
    df["share_due_through_next_fiscal_year"] = through / df.due_total
    stated = df.commit_definition.where(df.commit_definition != "").ffill()
    changed = (df.commit_definition != "") & stated.shift().notna() & (df.commit_definition != stated.shift())
    df["series_break"] = [f"definition changed from {old} to {new}" if flag else "" for flag, old, new in zip(changed, stated.shift(), df.commit_definition)]


def verified(r) -> str:
    """yes only if the text-derived amounts in the row equal what was read by eye (HAND_READ)."""
    if r.period_end not in HAND_READ:
        return "no"
    due = r.due_rest_of_fiscal_year if pd.notna(r.due_rest_of_fiscal_year) else r.due_next_12_months
    accrual_agrees = pd.isna(r.accrual_in_text) or abs(r.accrual_in_text - r.excess_purchase_accrual) < 1
    got = (r.supply_commitments, r.inventory_provisions, r.provision_releases, r.accrual_in_text, due)
    same = all((pd.isna(g) and h is None) or (h is not None and pd.notna(g) and abs(g - h * 1e6) < 1) for g, h in zip(got, HAND_READ[r.period_end]))
    return "yes" if same and accrual_agrees else "no"


def peaks(df: pd.DataFrame, stood_for: int = 4) -> list[int]:
    """Quarters where the ratio set a new high that then stood for at least `stood_for` quarters."""
    ratio = df.commitments_years_of_cost_of_revenue
    out = []
    for i in range(len(df) - stood_for):
        if pd.notna(ratio[i]) and ratio[i] >= ratio[: i + 1].max() and not (ratio[i + 1: i + 1 + stood_for] > ratio[i]).any():
            out.append(i)
    return out


def aftermath(df: pd.DataFrame, peak: int, quarters: int = 8) -> pd.DataFrame:
    """The peak quarter and the eight after it: what revenue, margin and inventory charges did."""
    w = df.iloc[peak: peak + quarters + 1]
    return pd.DataFrame({
        "period_end": w.period_end.values,
        "quarters_after_peak": range(len(w)),
        "commit_$bn": (w.supply_commitments / 1e9).round(2).values,
        "years_of_cost": w.commitments_years_of_cost_of_revenue.round(2).values,
        "revenue_$bn": (w.revenue / 1e9).round(2).values,
        "revenue_vs_peak_qtr_%": ((w.revenue / w.revenue.iloc[0] - 1) * 100).round(0).values,
        "revenue_yoy_%": (w.revenue_growth_year_on_year * 100).round(0).values,
        "gross_margin_%": (w.gross_margin * 100).round(1).values,
        "provisions_$m": (w.inventory_provisions / 1e6).round(0).values,
        "provisions_%_revenue": (w.provisions_share_of_revenue * 100).round(1).values,
        "releases_$m": (w.provision_releases / 1e6).round(0).values,
        "accrual_$m": (w.excess_purchase_accrual / 1e6).round(0).values,
    })


# ---------------------------------------------------------------- AMD and Broadcom, for context

# Peers are read from the SEC's companyfacts file (every tagged number, one download per company)
# rather than from each filing's text, so most rows have no sentence behind them and are
# `verified = no`. PEER_READ holds the few figures that were read in the filing itself.
PEERS = [
    dict(ticker="AMD", cik=2488,
         tags=["UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount", "RecordedUnconditionalPurchaseObligation", "PurchaseObligation"],
         includes="Unconditional purchase commitments: wafers and substrates, plus multi-year cloud, software and technology licences "
                  "(broader than NVIDIA's supply-only figure)"),
    dict(ticker="AVGO", cik=1730168, tags=["UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount"],
         includes="Unconditional purchase commitments, primarily inventory, EXCLUDING any with a remaining term of one year or less "
                  "(ordinary purchase orders are left out, so the level is not comparable with NVIDIA's)"),
]
PEER_READ = {  # (ticker, period end): ($ millions, the table row as printed)
    ("AMD", "2022-06-25"): (10685, "Total future unconditional purchase commitments as of June 25, 2022 were as follows: ... Total unconditional purchase commitments $10,685"),
    ("AMD", "2025-12-27"): (12166, "Fiscal Year 2026 2027 2028 2029 2030 2031 and thereafter Total (In millions) Unconditional commitments $8,498 $1,099 $1,216 $1,197 $156 $— $12,166"),
    ("AMD", "2026-09-26"): (48761, "Future purchase commitments related to the Company's operations as of September 26, 2026 were as follows (in millions): "
                                   "Fiscal Year Remainder of 2026 2027 2028 2029 2030 2031 and thereafter Total Purchase commitments $11,218 $22,206 $4,959 $3,786 $4,231 $2,361 $48,761"),
    ("AVGO", "2025-11-02"): (132, "contractual obligations and commitments as of November 2, 2025: Fiscal Year: Purchase Commitments ... 2026 $106 ... Total $132"),
    ("AVGO", "2026-02-01"): (54, "contractual obligations and commitments as of February 1, 2026: Fiscal Year: Purchase Commitments ... 2026 (remainder) $28 2027 12 2028 10 2029 4 ... Total $54"),
    ("AVGO", "2026-05-03"): (128110, "contractual commitments as of May 3, 2026: Fiscal Year: Purchase Commitments ... 2026 (remainder) $22 2027 55,214 2028 72,870 2029 4 ... Total $128,110"),
    ("AVGO", "2026-08-02"): (126821, "contractual commitments as of August 2, 2026: Fiscal Year: Purchase Commitments ... 2026 (remainder) $1,110 2027 52,674 2028 72,952 2029 85 ... Total $126,821"),
}


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _trailing_year(facts: dict, tags: list[str], end: str) -> float | None:
    """Four quarters ending `end` from companyfacts: a full-year fact, or year to date + last year - last year to date."""
    spans = {}
    for tag in tags:
        for v in facts.get(tag, {}).get("units", {}).get("USD", []):
            if "start" in v:
                spans.setdefault((v["start"], v["end"]), v["val"])
    years = {k: v for k, v in spans.items() if 350 <= _days(*k) <= 380}
    for (start, stop), value in years.items():
        if stop == end:
            return value
    to_date = max(((_days(a, b), a, v) for (a, b), v in spans.items() if b == end and _days(a, b) < 300), default=None)
    if to_date is None:
        return None
    length, year_start, value = to_date
    for (start, stop), last_year in years.items():
        if _days(stop, year_start) == 1:
            earlier = [v for (a, b), v in spans.items() if a == start and abs(_days(a, b) - length) <= 10]
            return value + last_year - earlier[0] if earlier else None
    return None


def peers() -> pd.DataFrame:
    """Purchase commitments against trailing cost of revenue for AMD and Broadcom."""
    rows = []
    for peer in PEERS:
        facts = edgar.companyfacts(peer["cik"])["facts"]["us-gaap"]
        seen = {}
        for tag in reversed(peer["tags"]):  # the first tag listed wins where two overlap
            for v in facts.get(tag, {}).get("units", {}).get("USD", []):
                if v["end"] >= SINCE and v["form"] in ("10-K", "10-Q"):
                    seen[v["end"]] = (v["val"], tag, v["form"], v["accn"])
        for end, (value, tag, form, accession) in sorted(seen.items()):
            cost = _trailing_year(facts, COST, end)
            revenue = _trailing_year(facts, list(reversed(REVENUE)), end)
            read = PEER_READ.get((peer["ticker"], end))
            rows.append({
                "ticker": peer["ticker"], "period_end": end, "form": form, "purchase_commitments": value, "xbrl_tag": tag,
                "cost_of_revenue_ttm": cost, "revenue_ttm": revenue,
                "commitments_years_of_cost_of_revenue": value / cost if cost else None,
                "commitments_to_revenue_ttm": value / revenue if revenue else None,
                "includes": peer["includes"],
                "verified": "yes" if read and abs(read[0] * 1e6 - value) < 1 else "no",
                "evidence": read[1] if read else "",
                "url": edgar.filing_base(peer["cik"], accession) + "/",
            })
    return pd.DataFrame(rows)


COLUMNS = [
    "period_end", "fiscal_year", "fiscal_quarter", "form", "filed", "source",
    "supply_commitments", "commit_definition", "series_break", "commit_includes", "of_which_unpaid_on_supply_agreements",
    "cost_of_revenue_ttm", "revenue_ttm", "commitments_years_of_cost_of_revenue", "commitments_to_revenue_ttm",
    "commitments_years_of_latest_quarter_cost",
    "due_basis", "due_total", "due_next_12_months", "due_rest_of_fiscal_year", "due_next_fiscal_year",
    "share_due_next_12_months", "share_due_rest_of_fiscal_year", "share_due_through_next_fiscal_year",
    "all_commitments_in_schedule", "prepaid_supply_long_term", "prepaid_supply_short_term",
    "revenue", "cost_of_revenue", "gross_profit", "gross_margin", "revenue_growth_year_on_year", "inventories", "excess_purchase_accrual",
    "inventory_provisions", "provision_releases", "net_inventory_charge", "provisions_share_of_revenue", "net_charge_share_of_revenue",
    "inventory_provisions_fiscal_year_to_date", "provision_releases_fiscal_year_to_date", "charges_basis",
    "purchase_obligation_charge", "inventory_writedown",
    "verified", "commit_xbrl_tag", "commit_evidence", "provision_evidence", "release_evidence", "accrual_evidence", "prepaid_evidence", "url",
]
TABLE_COLUMNS = ["period_end", "form", "source", "table", "row", "bucket", "amount", "evidence", "url"]


def main() -> None:
    edgar._MIN_INTERVAL = 0.4  # other processes share the SEC allowance
    filings = sorted((f for f in edgar.filings(CIK, forms=("10-K", "10-Q")) if f["period"] >= SINCE), key=lambda f: f["period"])
    rows, table_rows = [], []
    for f in filings:
        row, tables = filing_row(f)
        rows.append(row)
        table_rows += tables
    extra = announced_quarter(filings[-1]["period"], filings[-1]["filed"])
    if extra:
        rows.append(extra[0])
        table_rows += extra[1]
    df = assemble(rows)
    tables = pd.DataFrame(table_rows)[TABLE_COLUMNS].sort_values(["period_end", "table"], kind="stable")
    OUT.mkdir(parents=True, exist_ok=True)
    df[COLUMNS].to_csv(OUT / "nvidia_supply.csv", index=False)
    tables.to_csv(OUT / "nvidia_commitments_table.csv", index=False)
    context = peers()
    context.to_csv(OUT / "nvidia_supply_peers.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    pd.set_option("display.max_colwidth", 60)
    show = pd.DataFrame({
        "period_end": df.period_end, "src": df.form, "def": df.commit_definition.str.slice(0, 1),
        "commit_$bn": (df.supply_commitments / 1e9).round(2),
        "cost_ttm_$bn": (df.cost_of_revenue_ttm / 1e9).round(1),
        "yrs_of_cost": df.commitments_years_of_cost_of_revenue.round(2),
        "x_revenue": df.commitments_to_revenue_ttm.round(2),
        "due_12m_%": (df.share_due_next_12_months * 100).round(0),
        "due_rest_fy_%": (df.share_due_rest_of_fiscal_year * 100).round(0),
        "due_thru_next_fy_%": (df.share_due_through_next_fiscal_year * 100).round(0),
        "rev_$bn": (df.revenue / 1e9).round(2), "gm_%": (df.gross_margin * 100).round(1),
        "inventory_$bn": (df.inventories / 1e9).round(2), "accrual_$m": (df.excess_purchase_accrual / 1e6).round(0),
        "provisions_$m": (df.inventory_provisions / 1e6).round(0), "prov_%_rev": (df.provisions_share_of_revenue * 100).round(1),
        "releases_$m": (df.provision_releases / 1e6).round(0), "verified": df.verified,
    })
    print("NVIDIA supply commitments against the size of the business\n")
    print(show.to_string(index=False))
    print("\nSeries breaks:")
    for r in df[df.series_break != ""].itertuples():
        print(f"  {r.period_end}: {r.series_break}")
    missing = df[df.supply_commitments.isna()].period_end.tolist()
    print(f"\nquarters with no separate supply figure: {missing or 'none'}")
    newest = df.iloc[-1]
    print(f"newest quarter {newest.period_end} comes from: {newest.source}")
    for i in peaks(df):
        print(f"\nPeak of the ratio at {df.period_end[i]} ({df.commitments_years_of_cost_of_revenue[i]:.2f} years of cost of revenue) and the eight quarters after:\n")
        print(aftermath(df, i).to_string(index=False))
    wide = context.pivot(index="period_end", columns="ticker", values="commitments_years_of_cost_of_revenue").round(2)
    print("\nPeers, purchase commitments in years of cost of revenue (definitions differ, see the CSV; last eight period ends each):\n")
    print(pd.concat([wide[t].dropna().tail(8).rename(t).reset_index() for t in wide.columns], axis=1).to_string(index=False))
    print(f"peer rows verified by eye: {int((context.verified == 'yes').sum())} of {len(context)}")
    print(f"\n{len(df)} quarters, {int((df.verified == 'yes').sum())} verified by eye; {len(tables)} table cells from {tables.period_end.nunique()} filings")


if __name__ == "__main__":
    main()
