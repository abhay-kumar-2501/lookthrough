"""Build docs/method.html: how the project was built, how each number can be checked, and its limits.

Counts on the page are read from the data, so they stay true as the project changes.
The author's own re-checks come from checks/author_checks.csv and are mentioned only
once some have been recorded.
"""
from __future__ import annotations

import html as html_lib

import pandas as pd

import edgar
import make_checklist
import make_spenders
import site_shell

OUT = edgar.ROOT / "data" / "processed"
INPUTS = edgar.ROOT / "inputs"
CHECKS = edgar.ROOT / "checks"


def counts() -> dict:
    site = make_spenders.build_payload()
    vendor = pd.read_csv(INPUTS / "vendor_finance_2000.csv")
    fin = pd.read_csv(OUT / "nvidia_customer_financing.csv")
    supply = pd.read_csv(OUT / "nvidia_supply.csv")
    recheck = pd.read_csv(CHECKS / "machine_recheck.csv") if (CHECKS / "machine_recheck.csv").exists() else pd.DataFrame(columns=["machine_result"])
    return {
        "lease_figures": site["leases"]["n_figures"],
        "nvidia_rows": int(fin.amount.notna().sum()),
        "supply_quarters": int(supply.supply_commitments.notna().sum()),
        "vendor_rows": int(vendor.amount_usd_millions.notna().sum()),
        "vendor_filings": int(vendor.url.nunique()),
        "dep_n": site["validation"]["fit"]["n"],
        "dep_err": site["validation"]["fit"]["mean_abs_error"],
        "dep_max": site["validation"]["fit"]["max_abs_error"],
        "pv_n": site["pv"]["check"]["n"],
        "pv_err": site["pv"]["check"]["mean_abs"],
        "counterparties": len(site["counterparties"]),
        "counterparties_primary": sum(1 for r in site["counterparties"] if r["confidence"] == "primary_read"),
        "recheck_total": int(len(recheck)),
        "recheck_pass": int((recheck.machine_result == "pass").sum()),
        "latest_filing": max(site["latest_filing"], str(supply.filed.dropna().max())),
        "shares": sum(r["shares"] or 0 for r in site["sources_uses"]),
    }


def prior_rows() -> str:
    prior = pd.read_csv(INPUTS / "prior_work.csv").fillna("")
    e = html_lib.escape
    return "".join(
        f"<tr><td>{e(str(r.date))}</td><td><a href='{e(str(r.url))}'>{e(str(r.who))}</a></td><td class='wrap'>{e(str(r.what))}</td><td class='wrap'>{e(str(r.checked))}</td></tr>"
        for r in prior.itertuples()
    )


def body(c: dict, checks: dict) -> str:
    mine = ""
    if checks["checked"]:
        scope = "each of the" if checks["checked"] == checks["total"] else f"{checks['checked']} of the"
        mine = f" I then opened the filing behind {scope} {checks['total']} headline figures and confirmed the number myself (latest check {checks['last']})."
        if checks["mismatches"]:
            mine += f" {checks['mismatches']} did not match and are noted in the checklist."
    rows = [
        ("Leases signed but not started",
         f"{c['lease_figures']} figures, each stored with its sentence and link. Every one was read against its sentence in a separate pass, and the five-company total for the end of 2025 matches the figure Moody's published."),
        ("What the leases are worth today",
         f"The method was run first on {c['pv_n']} lease portfolios whose recorded value is known: average miss {c['pv_err']:.1f}%. That confirms the discounting, not the assumed start dates and terms, so the result is shown as a range and the middle estimate is probably high."),
        ("Cash, borrowing and debt ratios",
         "Taken from the machine-readable financial statements each company files. Twelve-month figures are the latest fiscal year plus the year to date, less the same period a year earlier. A missing item is left blank, never set to zero. New shares sold uses the year-to-date figure where a company had sold none in earlier years."),
        ("NVIDIA's support for customers",
         f"{c['nvidia_rows']} disclosed amounts across {c['supply_quarters']} quarters. Most were also matched to the machine-readable version of the same filing."),
        ("The telecom makers, 1997 to 2003",
         f"{c['vendor_rows']} amounts from {c['vendor_filings']} filings by Lucent, Nortel, Cisco and Motorola. Each recorded sentence was matched by program against the text of the filing it cites. Where a company did not disclose an item the cell is empty."),
        ("Fund holdings",
         "Read from each fund's latest holdings report to the regulator. Funds that hold other funds are looked through to the underlying shares."),
        ("Landlords and lenders table",
         f"{c['counterparties_primary']} of {c['counterparties']} rows rest on a filing or company release. The rest are press reports and are labelled."),
        ("Server-life model (appendix)",
         f"Tested against {c['dep_n']} effects the companies themselves disclosed: average miss {c['dep_err']:.1f}%, worst {c['dep_max']:.0f}%. One setting was tuned to those same disclosures, so this is a fit, not an independent test."),
    ]
    table = "".join(f"<tr><td style='min-width:170px'><b>{a}</b></td><td class='wrap'>{b}</td></tr>" for a, b in rows)
    return f"""  <p class="kicker" style="margin-top:34px">Method and checks</p>
  <h1>How this was built, and how far to trust it</h1>
  <p class="lede">Almost every figure on this site comes from a filing with the US securities regulator and can be traced to the sentence it came from. This page says who did what, how to check any number yourself, which calls were judgment, and what changed after the work was reviewed.</p>

  <section>
    <h2>Who did what</h2>
    <p>I built this with Claude Code, an AI coding tool. I chose the subject and the questions, directed the work, and decided what stayed and what was cut. The tool wrote the code, did the first reading of the filings and proposed several of the measures.{mine}</p>
    <p>Because a tool did the first reading, each number is set up to be checked without relying on it:</p>
    <ul>
      <li><b>A source for every number.</b> Each figure is saved with the sentence it came from and a link to the filing, so it can be checked against the source directly.</li>
      <li><b>A second pass that shares no code with the first.</b> A separate program downloads a fresh copy of each cited filing and confirms the sentence and the figure are there. Result: {c['recheck_pass']} of {c['recheck_total']} headline figures confirmed.</li>
      <li><b>Tests against known answers.</b> Where a company has disclosed the answer itself, the calculation is run on the same question and compared.</li>
      <li><b>Two hostile reviews.</b> I had the project critiqued twice by separate AI sessions instructed to find what was wrong, not to approve it. What changed as a result is listed below.</li>
    </ul>
  </section>

  <section>
    <h2>Part by part</h2>
    <div class="scroll"><table><thead><tr><th>Part</th><th style="text-align:left">Where it comes from and how it was checked</th></tr></thead><tbody>{table}</tbody></table></div>
  </section>

  <section>
    <h2>Judgment calls</h2>
    <p>These are choices, not facts. Each could reasonably have been made differently.</p>
    <ul>
      <li><b>Which six companies.</b> Microsoft, Alphabet, Amazon, Meta, Oracle and CoreWeave. A scan of every other filer found they hold nearly all of the signed-but-not-started leases, which is why the list stops there.</li>
      <li><b>Which companies count as AI hardware</b> in the fund tool. The list is mine and is printed in full beside the tool.</li>
      <li><b>Counting each company whole.</b> The tool counts all of Microsoft or Amazon, although most of their business is not AI. It measures who is on each side of the spending, not how much of each company depends on it.</li>
      <li><b>The discount rate for leases.</b> Each company's own reported lease rate. Those were set when borrowing was cheaper, so the value shown is more likely too high than too low.</li>
      <li><b>Lease terms and start dates.</b> Taken from each filing; where a filing gives a wide range, 15 years.</li>
      <li><b>Debt ratios hold earnings still.</b> The "with signed leases" ratio assumes today's earnings, as if the new data centers earned nothing, and ignores signed customer contracts. It is a stress reading.</li>
      <li><b>NVIDIA measured against the latest quarter's sales times four,</b> not the last twelve months, because it is growing fast and the older figure would make every ratio look larger (38% promised instead of 30%). The six spenders' earnings are the last twelve months, which is harsher on the fastest grower, CoreWeave. The two choices are not the same and that is a weakness.</li>
      <li><b>The telecom comparison uses each company's highest reading,</b> whenever it came, against NVIDIA's latest. Sales are measured on the latest quarter times four for Lucent and Motorola and on the fiscal year for Nortel and Cisco, as their filings allow.</li>
    </ul>
  </section>

  <section>
    <h2>What changed after review</h2>
    <ul>
      <li><b>The conclusion moved from the supplier to the buyers.</b> Earlier versions had no view on which companies were stretched. Adding the debt ratios showed the load is heaviest at two of the six.</li>
      <li><b>"The difference is being borrowed" was too simple.</b> The six also sold ${c['shares'] / 1e9:,.0f}bn of new shares in the same twelve months. The page now shows both.</li>
      <li><b>A claim about 2000 was wrong.</b> An earlier draft said NVIDIA had promised its customers more than any telecom maker did. Lucent reached 32% of sales against NVIDIA's 30%. The comparison now uses each company's highest reading and says NVIDIA is inside their range on promises and below all of them on what is in force.</li>
      <li><b>Part of the telecom story was sales falling, not lending rising.</b> Lucent's lending kept growing after its promises peaked; Nortel's did not, and its ratio rose only because its sales fell. The page now says which is which.</li>
      <li><b>NVIDIA's support goes to newer builders, not to the six.</b> Its largest guarantee is for a campus leased to OpenAI. An earlier draft implied it was helping its large customers pay.</li>
      <li><b>NVIDIA's orders from its own suppliers were restated</b> at the current pace of production (3.3 years, not 4.3) and moved to an appendix, since they are not part of the argument.</li>
      <li><b>The fund tool separates sellers from buyers.</b> Adding them into one number hid that the two groups carry different risks.</li>
    </ul>
  </section>

  <section>
    <h2>Where to be careful</h2>
    <ul>
      <li>The latest NVIDIA quarter comes from its results release. The full quarterly report had not been filed when this was built.</li>
      <li>Fund holdings are reported a few months late. The tool shows the date.</li>
      <li>Commitments run for up to 30 years. A large total is not one year's bill.</li>
      <li>If a number looks wrong, the sentence it came from is one click away. Tell me and I will correct it.</li>
    </ul>
    <details class="ev"><summary>Earlier work by others on the same questions</summary><div class="ev-body">
      <p>The lease total and the server-life question have both been reported widely. What this project adds is the source sentence for every figure, the value in today's money, the debt ratios, and the telecom makers' figures set beside NVIDIA's on matched definitions.</p>
      <div class="scroll"><table><thead><tr><th>Date</th><th>Who</th><th style="text-align:left">What they reported</th><th style="text-align:left">How far it could be checked</th></tr></thead><tbody>{prior_rows()}</tbody></table></div>
    </div></details>
  </section>
"""


def main() -> None:
    make_checklist.main()
    c = counts()
    asof = pd.Timestamp(c["latest_filing"]).strftime("%-d %B %Y")
    html = site_shell.render(
        "method.html",
        "Method and checks",
        "Who did what, where every figure comes from, how to check it, which calls were judgment, and what changed after review.",
        f"Latest filing read: {asof}",
        body=body(c, make_checklist.status()),
    )
    site_shell.write("method.html", html)


if __name__ == "__main__":
    main()
