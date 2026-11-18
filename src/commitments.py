"""Step 4: what has been promised (other than leases) and what has been sold.

A balance sheet shows what a company owes today. It does not show what the
company has *contracted* to buy over the next several years: servers on order,
data centers under construction, take-or-pay power contracts, cloud capacity
rented from someone else. Under US GAAP those promises are disclosed in a
footnote or in the "liquidity" section of the 10-Q / 10-K, usually in one
sentence or one table row. This script collects them.

It also collects the other side of the ledger: contracted backlog, which the
accounting rules call "remaining performance obligations" (RPO) - revenue
customers have signed up for that has not been delivered yet.

Four kinds of row:

  purchase_commitments  non-cancelable orders and take-or-pay contracts
  construction          contracts to build data centers and other buildings
  backlog_rpo           signed customer contracts not yet recognised as revenue
  other                 funding promises to ventures, guarantees, backstops

Leases that have not started yet are a fifth kind of promise. They are handled
in leases.py and are deliberately not repeated here.

Output: data/processed/commitments.csv, one row per disclosed figure, from each
company's newest 10-Q or 10-K. If the newest filing does not state an item
(Microsoft only gives its purchase and construction commitments once a year)
the row comes from the most recent filing that does, back to the last 10-K,
and `as_of` says which date it describes.

Columns worth explaining:

  amount                the total, in dollars, over the whole life of the contracts
  due_within_12_months  only filled when the filing gives exactly a 12-month
                        figure. For backlog rows it is the revenue the company
                        expects to recognise in the next 12 months (its stated
                        percentage x the total).
  due_rest_of_fiscal_year / due_next_fiscal_year
                        used instead when a 10-Q splits payments by fiscal year
  in_total              True if funding_gap.py adds the row into "signed
                        commitments" or "backlog". False for a part of another
                        row, for anything contingent, and for anything that may
                        overlap another row, a recorded liability, or money
                        already paid in (`note` says which). The totals are
                        therefore a floor, not a ceiling.
  xbrl_tag              the XBRL concept that carries the same value on the same
                        date in the filing's own data file. Empty when the number
                        only appears in management's discussion, which is not tagged.

These are totals over many years (some energy contracts run past 2050). They
are NOT debt and NOT one year's spending.

Second output: data/processed/commitments_history.csv, the purchase,
construction and backlog rows from every 10-K and 10-Q since 2023. "Other" rows
are left out of the history because their wording changes too often to follow
reliably. A gap in the history means the filing did not state the figure (many
10-Qs only repeat annual tables when something material changed).
"""
from __future__ import annotations

import re

import pandas as pd

import edgar
import text
import xbrl
from universe import COMPANIES

OUT = edgar.ROOT / "data" / "processed"
SINCE = "2023-01-01"  # for the history file
DATE = r"[A-Z][a-z]+ \d{1,2} ?, \d{4}"
AMT = r"\$ ?(?P<amount>[\d,]+(?:\.\d+)?) ?(?P<unit>billion|million)"
ROW = r"(?P<nums>\$? ?\d[\d,]*(?: \$? ?\d[\d,]*){2,8})"  # a table row in $ millions; the last number is the total
SENT = r"(?:[^.]|\.(?=\d))*\."  # the rest of the sentence, not stopping at the point in "$4.5 billion"
SHORT = r" ?, of which \$ ?(?P<due12>[\d,.]+) (?P<due12_unit>billion|million) was short-term"
FIRST_TWO = (r"\$ ?(?P<first>[\d,.]+) (?P<first_unit>billion|million)"
             r"(?: and \$ ?(?P<second>[\d,.]+) (?P<second_unit>billion|million))? due in \d{4}(?: and \d{4}, respectively)?")

# Table and list headings, kept in the evidence so a row can be read on its own.
MSFT_TABLE = (r"(?P<head>The following table summarizes the payments due by fiscal year for our outstanding contractual obligations as of "
              + DATE + r": \(In millions\) .{0,80}?Total) .{0,500}?")
AMZN_TABLE = r"(?P<head>The following summarizes our principal contractual commitments,[^:]{0,160}? as of " + DATE + r" \(in millions\): .{0,140}?Total) .{0,1100}?"
META_TABLE = r"(?P<head>maximum exposure to loss in the unconsolidated data center ventures? \(in millions\): .{0,60}?)Carrying value.{0,200}?"
GOOGL_CASH = r"(?P<head>As of " + DATE + r", we have entered into future cash commitments that are not reflected on our balance sheet" + SENT + r" These future commitments comprise:).{0,1300}?"
GOOGL_CONTINGENT = r"(?P<head>As of " + DATE + r", we have entered into contingent commitments consisting of:).{0,700}?"
CRWV_LIST = r"(?P<head>Our significant contractual obligations as of " + DATE + r" consisted of:).{0,900}?"


def _spec(kind: str, item: str, patterns: list[str], in_total: bool = True, note: str = "") -> dict:
    return dict(kind=kind, item=item, patterns=patterns, in_total=in_total, note=note)


def _with_heading(heading: str, body: str) -> list[str]:
    """Try the row together with its table heading first, then the bare row."""
    return [heading + r"(?P<body>" + body + r")", body]


# Where each company puts each number. Patterns are tried in order (wording
# drifts from year to year); named groups pick out the figures:
#   amount/unit    the total             due12/due12_unit  due within 12 months
#   first, second  the first two periods of a payment schedule
#   pct12          share of backlog expected to become revenue within 12 months
#   nums           a table row in $ millions (first = nearest period, last = total)
#   head, body     evidence is "head ... body" instead of the whole match
SPECS = {
    "MSFT": [
        _spec("purchase_commitments", "Purchase commitments (open purchase orders and take-or-pay contracts, primarily datacenters)",
              _with_heading(MSFT_TABLE, r"Purchase commitments (?:\(\w\) )?" + ROW)),
        _spec("construction", "Construction commitments (new buildings, building and leasehold improvements, primarily datacenters)",
              _with_heading(MSFT_TABLE, r"Construction commitments (?:\(\w\) )?" + ROW)),
        _spec("backlog_rpo", "Remaining performance obligations, total company",
              [r"Revenue allocated to remaining performance obligations, which includes unearned revenue and amounts[^.$]*?, was " + AMT
               + r" as of " + DATE + r"(?:.{0,800}?We expect to recognize approximately (?P<pct12>\d+) ?% of [^.]{0,220}?over the next 12 months)?"]),
        _spec("backlog_rpo", "Remaining performance obligations, commercial portion", in_total=False, note="part of the total-company row",
              patterns=[r"Revenue allocated to remaining performance obligations related to the commercial portion of revenue was " + AMT + r" as of " + DATE,
                        r"Revenue allocated to remaining performance obligations, which includes[^.$]*?, was \$ ?[\d,.]+ billion as of " + DATE
                        + r", of which " + AMT + r" is related to the commercial portion of revenue"]),
        _spec("other", "Funding commitments to OpenAI (total, mostly already funded)", in_total=False, note="total commitment including the part already paid in",
              patterns=[r"We have made total funding commitments of " + AMT + r" related to our investment, of which \$ ?[\d.]+ billion has been funded as of " + DATE]),
    ],
    "GOOGL": [
        _spec("purchase_commitments", "Material purchase commitments (technical infrastructure and inventory, energy take-or-pay, content, open purchase orders)",
              [r"Of the total material purchase commitments of " + AMT + r", \$ ?(?P<due12>[\d,.]+) (?P<due12_unit>billion|million) is due within 12 months",
               r"As of " + DATE + r", we had material (?:purchase commitments and other )?contractual obliga ?tions (?:of|totaling) " + AMT + SHORT,
               r"We have material purchase commitments and other contractual obligations[^.]*\. As of " + DATE + r", the total for these commitments was " + AMT + SHORT]),
        _spec("purchase_commitments", "Contracts with remaining terms over one year (long-term supply, energy, content)", in_total=False,
              note="part of material purchase commitments; stated at maximum contractual price and volume",
              patterns=[r"We have significant contractual obligations from contracts with remaining terms greater than one year\. As of " + DATE
                        + r", total commitments under these obligations were " + AMT + SENT]),
        _spec("other", "Future funding commitments for investments in equity securities",
              [GOOGL_CASH + r"(?P<body>" + AMT + r" of future funding commitments related to our investments in equity securities)"],
              note="listed by the company as a cash commitment; its Note 5 says $20.0bn of it depends on an investee reaching milestones"),
        _spec("other", "Contingent: data center backstop obligations", in_total=False, note="contingent, only paid if a counterparty fails",
              patterns=[GOOGL_CONTINGENT + r"(?P<body>" + AMT + r" of financial support in the form of backstop obligations relating to data centers" + SENT + r")"]),
        _spec("other", "Contingent: financial guarantees", in_total=False, note="contingent, maximum potential payments",
              patterns=[GOOGL_CONTINGENT + r"(?P<body>" + AMT + r" of financial guarantees, primarily to support counterparty procurement" + SENT + r")"]),
        _spec("backlog_rpo", "Revenue backlog, total",
              [r"As of " + DATE + r", we had " + AMT + r" of remaining performance obligations \(.revenue backlog.\)" + SENT]),
        _spec("backlog_rpo", "Revenue backlog, Google Cloud", in_total=False, note="part of the total row",
              patterns=[r"As of " + DATE + r", we had \$ ?[\d,.]+ billion of remaining performance obligations \(.revenue backlog.\), of which "
                        + AMT + r" related to Google Cloud"]),
    ],
    "AMZN": [
        _spec("purchase_commitments", "Property and equipment (unconditional purchase obligations to acquire property and equipment)",
              _with_heading(AMZN_TABLE, r"Property and equipment \(\d\) " + ROW)),
        _spec("purchase_commitments", "Unconditional purchase obligations (energy, digital media content, software licences)",
              _with_heading(AMZN_TABLE, r"Unconditional purchase obligations \(\d\) " + ROW),
              note="before the September 2026 10-Q this row also held the property and equipment agreements"),
        _spec("other", "Other commitments (asset retirement obligations, content liabilities, build-to-suit rent)", in_total=False,
              note="includes liabilities already on the balance sheet",
              patterns=_with_heading(AMZN_TABLE, r"Other commitments \(\d\)(?: ?\(\d\))? " + ROW)),
        _spec("backlog_rpo", "Customer commitments not yet recognised, contracts over one year (primarily AWS)",
              [r"Additionally, we have performance obligations, primarily related to AWS,.{0,330}?commitments not yet recognized were (?:estimated to be )?(?:approximately )?"
               + AMT + r" as of " + DATE]),
    ],
    "META": [
        _spec("purchase_commitments", "Non-cancelable contractual commitments (third-party cloud capacity, servers and network, energy, Reality Labs hardware)",
              [r"As of " + DATE + r", we had " + AMT + r" of non-cancelable contractual commitments[^.]*\. These commitments[^.]*? with approximately " + FIRST_TWO,
               r"We (?:also )?have " + AMT + r" of non-cancelable contractual commitments as of " + DATE + r"(?:\. These commitments|, which)[^.]*?,? with (?:approximately )?" + FIRST_TWO,
               r"We have " + AMT + r" of non-cancelable contractual commitments as of " + DATE + r".{0,400}?The following is a schedule, by years, of non-cancelable "
               r"contractual commitments as of " + DATE + r" \(in millions\): (?:The remainder of )?\d{4} \$ ?(?P<first>[\d,]+) \d{4} (?P<second>[\d,]+)"]),
        _spec("other", "Future funding commitments to data center joint ventures", in_total=False,
              note="firm, but the filing does not say whether it is already inside the contractual commitments row",
              patterns=[META_TABLE + r"(?P<body>Future funding commitments (?P<amount>[\d,]+))"]),
        _spec("other", "Contingent: obligation to purchase cloud capacity", in_total=False, note="contingent, falls if the provider resells the capacity",
              patterns=[r"as of " + DATE + r", we have contingent obligations to purchase up to " + AMT + r" of cloud capacity" + SENT]),
        _spec("other", "Contingent: maximum residual value guarantees to data center joint ventures", in_total=False,
              note="contingent, company says payment is not probable",
              patterns=[META_TABLE + r"(?P<body>Maximum residual value guarantees (?P<amount>[\d,]+))"]),
    ],
    "ORCL": [
        _spec("purchase_commitments", "Unconditional purchase and certain other obligations (cloud infrastructure components, data center power)",
              [r"As of " + DATE + r" ?, our unconditional purchase and certain other obligations[^:.$]*?were as follows \(in millions\): (?P<nums>.{20,400}?Total \$ ?[\d,]+)",
               r"As of " + DATE + r" ?, our unconditional purchase and certain other obligations[^:.$]*?were " + AMT + r"\."]),
        _spec("backlog_rpo", "Remaining performance obligations",
              [r"(?:Remaining performance obligations(?:, as defined in Note 1 [^$]{0,200}?,)? were " + AMT + r" as of " + DATE
               + r"|As of " + DATE + r" ?, our remaining performance obligations were \$ ?(?P<amount2>[\d,.]+) (?P<unit2>billion|million))"
               r" ?, (?:of which we expect to recognize )?approximately (?P<pct12>\d+) ?% (?:of which we expect to recognize )?as revenues over the next twelve months" + SENT]),
    ],
    "CRWV": [
        _spec("construction", "Contractual commitments for future construction of data centers and related technical infrastructure",
              [r"As of " + DATE + r", the Company ha[sd] contractual commitments of approximately " + AMT + r" for future construction costs" + SENT]),
        _spec("purchase_commitments", "Other enforceable commitments (technology equipment, enterprise software and services)",
              [CRWV_LIST + r"(?P<body>other contractual commitments of approximately " + AMT + r" associated with agreements that are enforceable and legally binding" + SENT + r")"]),
        _spec("other", "Equipment to procure and install at leased data centers (high end of a stated range)", in_total=False,
              note="a range; the amount is its upper end, and it may overlap the purchase row",
              patterns=[r"the Company has contractual obligations to procure and install equipment at the leased premises\..{0,200}?As of " + DATE
                        + r", the Company estimated that it would incur between \$ ?[\d,.]+ (?:million|billion) and " + AMT + r" to fulfill these commitments" + SENT]),
        _spec("other", "Funding commitments to unconsolidated data center entities (total, partly funded)", in_total=False,
              note="total commitment including the part already paid in",
              patterns=[r"the Company committed to provide funding up to " + AMT + r" to certain VIEs for data center development projects, of which" + SENT]),
        _spec("backlog_rpo", "Remaining performance obligations",
              [r"As of " + DATE + r", the Company had " + AMT + r" of unsatisfied RPO" + SENT]),
    ],
}


def _usd(num: str | None, unit: str | None) -> float | None:
    """'454.52', 'billion' -> 454,520,000,000. No unit means a table in $ millions."""
    if num is None:
        return None
    scale = {"billion": 1e9, "million": 1e6}[(unit or "million").lower()]
    return round(float(num.replace(",", "")) * scale)


def _row_numbers(cell: str) -> list[float] | None:
    """Numbers in a table row, or None unless the parts add up to the final total."""
    cell = re.sub(r"[Ff]iscal \d{4}", " ", cell)  # Oracle labels each column inline
    nums = [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", cell)]
    if len(nums) < 3 or abs(sum(nums[:-1]) - nums[-1]) > 2:
        return None
    return nums


def _tidy(passage: str) -> str:
    """Close the gaps the HTML leaves inside '$ 1.2 billion' and '30 %'."""
    return re.sub(r"(?<=\d) %", "%", re.sub(r"\$ (?=\d)", "$", passage)).strip()


def extract(spec: dict, full_text: str, form: str) -> dict | None:
    """First passage in the filing that matches the spec, as figures plus evidence."""
    for pattern in spec["patterns"]:
        for m in re.finditer(pattern, full_text):
            g = m.groupdict()
            out = {"due_within_12_months": None, "due_rest_of_fiscal_year": None, "due_next_fiscal_year": None}
            if g.get("nums"):
                nums = _row_numbers(g["nums"])
                if nums is None:
                    continue  # same label elsewhere in the filing, not the commitments table
                out["amount"], first, second = nums[-1] * 1e6, nums[0] * 1e6, nums[1] * 1e6
            else:
                out["amount"] = _usd(g.get("amount") or g.get("amount2"), g.get("unit") or g.get("unit2"))
                first, second = _usd(g.get("first"), g.get("first_unit")), _usd(g.get("second"), g.get("second_unit"))
                out["due_within_12_months"] = _usd(g.get("due12"), g.get("due12_unit"))
                if g.get("pct12"):
                    out["due_within_12_months"] = round(out["amount"] * int(g["pct12"]) / 100)
            if first is not None and form == "10-K":  # at year-end the first period is exactly the next 12 months
                out["due_within_12_months"] = first
            elif first is not None:
                out["due_rest_of_fiscal_year"], out["due_next_fiscal_year"] = first, second
            passage = f"{g['head']} ... {g['body']}" if g.get("head") else g.get("body") or m.group(0)
            out["evidence"] = _tidy(passage)
            return out
    return None


_facts: dict[str, pd.DataFrame] = {}
# Only concepts that could describe a commitment or backlog count as a cross-check;
# a round number such as "$4 billion" can equal an unrelated fact by coincidence.
_RELEVANT = r"RemainingPerformanceObligation|PurchaseObligation|PurchaseCommitment|ContractualObligation|OtherCommitment|FundingCommitment|Guarantee"


def xbrl_tag(cik: int, filing: dict, amount: float) -> str:
    """Concept(s) in the filing's XBRL instance with this exact value at the period end."""
    key = filing["accession"]
    if key not in _facts:
        _facts[key] = xbrl.numeric(xbrl.filing_facts(cik, filing))
    df = _facts[key]
    if df.empty:
        return ""
    hit = df[(df.end == filing["period"]) & ((df.value - amount).abs() < 1) & df.concept.str.contains(_RELEVANT)]
    return "; ".join(sorted(set(hit.concept)))


def filing_rows(company: dict, filing: dict, specs: list[dict], check_xbrl: bool = True) -> list[dict]:
    """One row for every spec this filing discloses."""
    full = " ".join(text.filing_sentences(company["cik"], filing))
    rows = []
    for spec in specs:
        hit = extract(spec, full, filing["form"])
        if hit is None:
            continue
        rows.append(
            {
                "ticker": company["ticker"],
                "as_of": filing["period"],
                "kind": spec["kind"],
                "item": spec["item"],
                "amount": hit["amount"],
                "due_within_12_months": hit["due_within_12_months"],
                "due_rest_of_fiscal_year": hit["due_rest_of_fiscal_year"],
                "due_next_fiscal_year": hit["due_next_fiscal_year"],
                "in_total": spec["in_total"],
                "note": spec["note"],
                "xbrl_tag": xbrl_tag(company["cik"], filing, hit["amount"]) if check_xbrl else "",
                "form": filing["form"],
                "filed": filing["filed"],
                "evidence": hit["evidence"],
                "url": edgar.primary_doc_url(company["cik"], filing),
            }
        )
    return rows


def latest(company: dict) -> list[dict]:
    """Newest disclosure of each item: the latest filing, else back to the last 10-K."""
    remaining = list(SPECS[company["ticker"]])
    rows = []
    for filing in edgar.filings(company["cik"], forms=("10-K", "10-Q")):
        found = filing_rows(company, filing, remaining)
        rows += found
        got = {r["item"] for r in found}
        remaining = [s for s in remaining if s["item"] not in got]
        if not remaining or filing["form"] == "10-K":
            break
    return rows


def history(company: dict) -> list[dict]:
    """Purchase, construction and backlog rows in every 10-K and 10-Q since SINCE."""
    specs = [s for s in SPECS[company["ticker"]] if s["kind"] != "other"]
    rows = []
    for filing in edgar.filings(company["cik"], forms=("10-K", "10-Q")):
        if filing["period"] >= SINCE:
            rows += filing_rows(company, filing, specs, check_xbrl=False)  # no XBRL check, to stay fast
    return rows


def main() -> None:
    now = pd.DataFrame([r for c in COMPANIES for r in latest(c)])
    past = pd.DataFrame([r for c in COMPANIES for r in history(c)]).sort_values(["ticker", "item", "as_of"])
    OUT.mkdir(parents=True, exist_ok=True)
    now.to_csv(OUT / "commitments.csv", index=False)
    past.drop(columns=["xbrl_tag"]).to_csv(OUT / "commitments_history.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 200)
    pd.set_option("display.max_colwidth", 62)
    show = now[["ticker", "as_of", "kind", "item", "amount", "due_within_12_months", "in_total", "xbrl_tag"]].copy()
    show["item"] = show["item"].str.slice(0, 58)
    show[["amount", "due_within_12_months"]] = (show[["amount", "due_within_12_months"]] / 1e9).round(1)
    print("Latest disclosed commitments and backlog, $bn\n")
    print(show.to_string(index=False))

    counted = now[now.in_total]
    signed = counted[counted.kind != "backlog_rpo"].groupby("ticker").amount.sum()
    backlog = counted[counted.kind == "backlog_rpo"].groupby("ticker").amount.sum()
    totals = pd.DataFrame({"signed_non_lease_commitments": signed, "backlog": backlog}).div(1e9).round(1)
    print("\nRows with in_total = True, $bn (empty = not disclosed)\n")
    print(totals.reindex([c["ticker"] for c in COMPANIES]).to_string())

    wide = past[past.in_total].pivot_table(index="as_of", columns=["ticker", "kind"], values="amount", aggfunc="sum").div(1e9).round(1)
    print(f"\nHistory since {SINCE[:4]}: {len(past)} rows from {past.url.nunique()} filings, in_total rows by kind, $bn\n")
    print(wide.to_string())


if __name__ == "__main__":
    main()
