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
        "nvidia_quarters": int(fin[fin.amount.notna()].period_end.nunique()),
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
        "signed": sum(r["signed"] for r in site["leverage"]),
        "signed_at_book": sum(r["signed_at_book_rate"] for r in site["leverage"]),
        "rates": ", ".join(f"{site['names'][r['ticker']]} {r['rate'] * 100:.2f}%" for r in site["leverage"]),
        "book_rates": ", ".join(f"{r['rate_book'] * 100:.1f}%" for r in site["leverage"]),
        "locked": sum(r["cash_locked"] for r in site["leverage"]),
        "prepaid": sum(r["prepaid"] or 0 for r in site["sources_uses"]),
        "leased": sum(r["leased"] or 0 for r in site["sources_uses"]),
        "audit_rows": int(len(pd.read_csv(INPUTS / "ledger_notes.csv"))),
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
        mine = f" I then opened the filing behind {scope} {checks['total']} source figures and confirmed the number myself (latest check {checks['last']})."
        if checks["mismatches"]:
            mine += f" {checks['mismatches']} did not match and are noted in the checklist."
    rows = [
        ("Leases signed but not started",
         f"{c['lease_figures']} figures, each stored with its sentence and link. When the data was built, every one was read against its sentence in a separate pass by Claude Code; in the November audit 26 were read again independently. The five-company total for the end of 2025 matches the figure Moody's published."),
        ("What the leases are worth today",
         f"The method was run first on {c['pv_n']} lease portfolios whose recorded value is known: average miss {c['pv_err']:.1f}%, nearly always on the high side. That confirms the discounting arithmetic. It cannot confirm the interest rate, the start dates or the terms, which are assumptions listed below, so the result is shown as a range."),
        ("Cash, borrowing and debt ratios",
         "Taken from the machine-readable financial statements each company files. Twelve-month figures are the latest fiscal year plus the year to date, less the same period a year earlier as it stood when the annual report was filed. A missing item is left blank, never set to zero. In the November 2026 audit each company's borrowings, lease liabilities, cash, operating income and twelve-month cash figures were read again from the printed statements, and the project's own checks now fail if it drifts from those printed lines."),
        ("NVIDIA's support for customers",
         f"{c['nvidia_rows']} disclosed amounts across {c['nvidia_quarters']} period-ends. Most were also matched to the machine-readable version of the same filing."),
        ("The telecom makers, 1997 to 2003",
         f"{c['vendor_rows']} amounts from {c['vendor_filings']} filings by Lucent, Nortel, Cisco and Motorola. Each recorded sentence was matched by program against the text of the filing it cites. Where a company did not disclose an item the cell is empty."),
        ("Fund holdings",
         "Read from each fund's latest holdings report to the regulator. Funds that hold other funds are looked through to the underlying shares. In the audit the nine funds then on the page were rebuilt from the raw reports with separate code and matched to two decimals, and the S&P 500 figure was also matched against a second manager's S&P 500 fund. The 2040 and 2050 target-date funds were added afterwards with the same code and have not had that separate rebuild; their figures are in line with the audited 2030 and 2060 funds (the same share of each fund's stocks)."),
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
    <h2>What Lookthrough is</h2>
    <p>Two things, kept apart on purpose.</p>
    <div class="parts wide">
      <div><span class="ptag">Part 1 · The tool</span><b>What is in your fund</b>
        <ul>
          <li><b>Where.</b> The top of the first page.</li>
          <li><b>What it does.</b> Shows how much of a fund is in the six companies building AI's data centers and in the companies selling them equipment.</li>
          <li><b>Made of.</b> The fund's own holdings report and arithmetic. The only judgment is which companies are on the two lists, and the lists are shown.</li>
          <li><b>What it is not.</b> A forecast, a rating of a fund, or advice on what to hold.</li>
        </ul></div>
      <div><span class="ptag">Part 2 · The research</span><b>What those companies owe</b>
        <ul>
          <li><b>Where.</b> The rest of the first page, the workings and the NVIDIA note.</li>
          <li><b>What it does.</b> Adds up what the six have borrowed and promised to pay, and compares it with what they earn.</li>
          <li><b>Made of.</b> Figures read from company filings, calculations with stated assumptions, and at the end my own reading, which is labelled as opinion.</li>
          <li><b>What it is not.</b> Advice, a prediction that anything will go wrong, or a claim that any company has acted improperly.</li>
        </ul></div>
    </div>
  </section>

  <section>
    <h2>Who did what</h2>
    <p>I built this with Claude Code, an AI coding tool. I chose the subject and the questions, directed the work, and decided what stayed and what was cut. Claude Code wrote the code, did the first reading of the filings and proposed several of the measures.{mine}</p>
    <p>Because a program did the first reading, each number is set up to be checked without relying on it:</p>
    <ul>
      <li><b>One topic.</b> Lookthrough asks one thing: what a retirement fund has riding on AI's data centers. The fund tool answers the first half and the ledger of company bills the second. A related question, what NVIDIA has promised on behalf of some builders, is kept as a separate companion note.</li>
      <li><b>A source for every number.</b> Each figure is saved with the sentence it came from and a link to the filing, so it can be checked against the source directly.</li>
      <li><b>A second pass on fresh downloads.</b> A separate program downloads each cited filing again and confirms that the whole quoted sentence is there and that the figure is in it at the right size (a billion is not accepted for a million). Result: {c['recheck_pass']} of {c['recheck_total']} source figures confirmed. This covers figures read from a filing, not calculated ones.</li>
      <li><b>Tests against known answers.</b> Where a company has disclosed the answer itself, the calculation is run on the same question and compared.</li>
      <li><b>Two hostile reviews.</b> I had the project critiqued twice by separate AI sessions instructed to find what was wrong, not to approve it.</li>
      <li><b>A line-by-line audit.</b> Those reviews read the argument and missed an error in a calculation. So on 18 November 2026 six separate AI sessions each rebuilt one part of the project from the filings themselves, without using this project's choice of lines, and compared. Every figure read from a filing matched. Several calculations and labels did not survive, and are listed under "What changed after review". The audit's sourced corrections ({c['audit_rows']} figures, each with its sentence and link) are in the repository.</li>
    </ul>
  </section>

  <section>
    <h2>Part by part</h2>
    <div class="scroll"><table><thead><tr><th>Part</th><th style="text-align:left">Where it comes from and how it was checked</th></tr></thead><tbody>{table}</tbody></table></div>
  </section>

  <section>
    <h2>Assumptions and judgment calls</h2>
    <p>Every one of these is a choice, not a fact. Each is the choice I think is closest to what is true; where a different choice would change a headline number, the size of the change is given.</p>
    <h3>The ledger</h3>
    <ul>
      <li><b>Which six companies.</b> Microsoft, Alphabet, Amazon, Meta, Oracle and CoreWeave. A scan of other filers found they hold nearly all of the signed-but-not-started leases, which is why the list stops there. OpenAI is private and publishes no accounts. Anthropic went public in November 2026, as this version was being finished. <a href="https://www.sec.gov/Archives/edgar/data/2130357/000162828026074338/anthropicpbc-sx1ax3.htm">Its prospectus</a> reports about $901bn of commitments for computing and data centers, including leases that have not started. It is not in the ledger because it has not yet filed a quarterly report, and it is not in the fund tool because it listed after the fund reports the tool reads. It is the first company to add.</li>
      <li><b>The interest rate for signed leases.</b> A lease is recorded, the day it starts, at what the company would pay to borrow then. Nobody discloses that in advance. The ledger uses the coupon on each company's most recent US dollar bond of about ten years (a fifteen-year lease paid in level instalments is repaid, on average, about as fast as a ten-year bond): {c['rates']}. CoreWeave's is the rate on its own leases, which is higher than its latest bond. This gives ${c['signed'] / 1e9:,.0f}bn. At the rates on the companies' existing leases ({c['book_rates']}), most of them signed when borrowing was cheaper, it would be ${c['signed_at_book'] / 1e9:,.0f}bn. That older basis was this site's headline until the audit. The accounting rule asks for a secured borrowing rate, which would be a little below an unsecured bond coupon, so the choice made here leans toward the lower figure.</li>
      <li><b>Lease terms and start dates.</b> Taken from each filing. Where a filing gives a wide range the middle term is 15 years; the low case uses the longest term stated. Leases are assumed to start evenly across the window given, and rent is assumed level with no yearly increases. Amazon gives a year-by-year schedule; its payments after 2030 are assumed to continue at the 2030 pace.</li>
      <li><b>What counts as borrowed.</b> Loans, bonds and notes at the value carried on the balance sheet. Amazon's also includes its short-term borrowings and the obligations it records for buildings it is treated as owning. Purchase orders, customer prepayments and money borrowed after the quarter ended are not included; the last is listed on each bill.</li>
      <li><b>Leases running.</b> Operating and finance lease liabilities on the balance sheet. Meta does not give its finance leases in quarterly reports, so that part is from December 2025.</li>
      <li><b>Cash profit.</b> Operating income plus depreciation and amortization of property, equipment and intangible assets, over the last twelve months (EBITDA). Amazon's own cash-flow line also adds back leased assets and video content, so its narrower property-and-equipment figure is used to keep the six on one footing. Alphabet gives its amortization of intangibles only for the year to date, so part of its $1bn is estimated; Amazon gives its once a year, so last year's $0.8bn stands in. Microsoft's is built from two figures in its notes, which come within 1% of its cash-flow line. One-off items are not removed; where one is large (Meta's legal charge) the bill shows the ratio without it.</li>
      <li><b>Profit is held still.</b> The last column assumes today's profit, as if the new data centers earned nothing, and ignores signed customer contracts. It sets tomorrow's rent against today's earnings, a mismatch in timing by design. It also divides by profit after operating-lease rent; adding that rent back, as a rating agency would, lowers every ratio.</li>
      <li><b>Cash.</b> Not subtracted in the main column, because cash can be spent on other things. Each bill gives the ratio with cash subtracted, leaving out ${c['locked'] / 1e9:,.1f}bn of shares Alphabet holds but may not yet sell.</li>
      <li><b>Dates.</b> Each company's figures are at its latest quarter-end: 31 August 2026 for Oracle, 30 September for the others. The "six together" row adds figures a month apart.</li>
    </ul>
    <h3>Cash in and out</h3>
    <ul>
      <li><b>Spending on buildings and equipment</b> is cash paid, before any proceeds from sales. It leaves out ${c['leased'] / 1e9:,.0f}bn of assets taken on under finance leases, where no cash is paid up front.</li>
      <li><b>Cash from operations</b> is as each company reports it. Oracle's includes ${c['prepaid'] / 1e9:,.0f}bn that customers paid in advance.</li>
      <li><b>Debt raised and repaid</b> are the long-term lines of each cash-flow statement. Short-term borrowing drawn and repaid within the year is left out.</li>
    </ul>
    <h3>NVIDIA and the telecom makers</h3>
    <ul>
      <li><b>NVIDIA is measured against the latest quarter's sales times four,</b> not the last twelve months, because it is growing fast. On the last twelve months its promised share would be 38% instead of 30%.</li>
      <li><b>"Promised"</b> is guarantees at their maximum plus investments pledged and not yet paid. It leaves out agreements to take capacity from AI cloud companies, which take effect only if they secure financing, and data center leases NVIDIA has signed itself.</li>
      <li><b>"In force"</b> is every guarantee except the one NVIDIA says has not started. NVIDIA confirms part of that as outstanding and does not say when the rest takes effect, so the figure is an upper limit.</li>
      <li><b>The telecom comparison uses each company's highest disclosed reading,</b> whenever it came, against NVIDIA's latest. All five are measured against the latest quarter's sales times four. Sales are as first reported. Where a company did not report a component its figure is a minimum. On trailing sales the telecom makers look smaller and NVIDIA larger, so the site gives both and claims no ranking.</li>
      <li><b>The latest NVIDIA quarter</b> comes from its results release and the commentary filed with it. Its full quarterly report had not been filed when this was built.</li>
    </ul>
    <h3>The fund tool</h3>
    <ul>
      <li><b>Which companies count as AI hardware.</b> The list is mine and is printed beside the tool. It leaves out Intel, Samsung, the storage makers and the makers of chip-manufacturing equipment; counting those would add about 4.6 cents per dollar in an S&P 500 fund.</li>
      <li><b>Each company is counted whole,</b> although most of Microsoft's or Amazon's business is not AI. The tool measures who is on each side of the spending, not how much of each company depends on it.</li>
      <li><b>Funds are read at different dates,</b> between June and September 2026, as their reports allow. A ticker marked as similar borrows another fund's figures and says how it differs.</li>
    </ul>
    <h3>The appendices</h3>
    <ul>
      <li><b>Equipment life.</b> The model treats servers and network gear as one group with one life, and one setting was tuned to the companies' own disclosures. Meta's life for 2022 to 2024 is set at 4.5 years, the middle of the range it gives. Earnings per share assume a 21% tax rate.</li>
      <li><b>What a year of spending has to earn.</b> The middle of the assumptions tested: 60% of spending on equipment lasting four years, a 10% return, and 40 cents of each new revenue dollar left after running costs.</li>
    </ul>
  </section>

  <section>
    <h2>What changed after review</h2>
    <p>The first seven came from the two reviews of the argument. The rest came from the line-by-line audit of 18 November 2026, in which every figure read from a filing matched and the items below did not.</p>
    <ul>
      <li><b>The conclusion moved from the supplier to the buyers.</b> Earlier versions had no view on which companies were stretched. Adding the debt ratios showed the load is heaviest at two of the six.</li>
      <li><b>"The difference is being borrowed" was too simple.</b> The six also sold ${c['shares'] / 1e9:,.0f}bn of new shares in the same twelve months. The page now shows both.</li>
      <li><b>A claim about 2000 was wrong.</b> An earlier draft said NVIDIA had promised its customers more than any telecom maker did. Lucent reached 32% of sales against NVIDIA's 30%. The comparison now uses each company's highest reading and says NVIDIA is inside their range on promises and below all of them on what is in force.</li>
      <li><b>Part of the telecom story was sales falling, not lending rising.</b> Lucent's lending kept growing after its promises peaked; Nortel's did not, and its ratio rose only because its sales fell. The page now says which is which.</li>
      <li><b>Whom NVIDIA is backing.</b> Its largest guarantee is for a campus leased to OpenAI, and it names no one else. An earlier draft implied it was helping its large customers pay; a later one said the rest went to "newer builders, not the six", which the filings do not support either way.</li>
      <li><b>NVIDIA's orders from its own suppliers were restated</b> at the current pace of production (3.3 years, not 4.3) and moved to an appendix, since they are not part of the argument.</li>
      <li><b>The fund tool separates sellers from buyers.</b> Adding them into one number hid that the two groups carry different risks.</li>
      <li><b>The signed leases were valued at an out-of-date interest rate.</b> CoreWeave apart, the rates on the companies' existing leases are about 4% to 6%; they now borrow at about 5.3% to 8%. On current rates the signed leases are worth ${c['signed'] / 1e9:,.0f}bn, not $862bn, and the six-company total is $1.7 trillion, not $1.8 trillion. Oracle's ratio fell from 10.1 to 9.2.</li>
      <li><b>Amazon's cash profit was not comparable with the others'.</b> Its add-back included leased assets and video content. On the same footing as the other five its ratio is 2.6, not 2.3. Its borrowings also left out $10bn of short-term and building-related obligations.</li>
      <li><b>"Its cash covers the whole total" was wrong for Alphabet.</b> $75.2bn of what was counted as cash is shares it may not yet sell.</li>
      <li><b>New shares sold was $1bn too high,</b> because Oracle moved its employee share plans to a new line and the old one was counted for the wrong period. The total is ${c['shares'] / 1e9:,.0f}bn. "Debt raised" is now labelled as long-term debt, which is what it was.</li>
      <li><b>The telecom comparison did not use one yardstick.</b> The site said which sales figure each company was measured against, and was wrong for two of them. All are now on the latest quarter times four. The claim that NVIDIA's promises were "above three of the four" is gone: the ranking changes with the yardstick.</li>
      <li><b>"In force" claimed more than NVIDIA's documents say.</b> Only $3.5bn of the $13bn is confirmed as outstanding. The figure is now called an upper limit.</li>
      <li><b>Two columns in the fund tool were wrong.</b> "Ten largest holdings" and "counts like" included cash collateral and unopened bond funds and split Alphabet's two share classes. They now look at stocks, by company.</li>
      <li><b>One appendix table was labelled "middle assumptions"</b> and was really the most lenient case tested. It now uses the middle.</li>
      <li><b>The automated re-check proved less than this page said.</b> It matched only the opening words of each sentence. It now matches the whole sentence and the size of the number.</li>
      <li><b>Cash profit left out a line for four companies.</b> For Microsoft, Meta, Oracle and CoreWeave the program added back depreciation but not the amortization of intangible assets, which understated their cash profit and overstated their ratios. I was working through Oracle's figures by hand, and setting them out line by line showed the gap. Oracle's ratio with signed leases counted went from 10.5 to 10.1 and CoreWeave's from 17.8 to 17.6; the others moved by less than 0.1.</li>
    </ul>
  </section>

  <section>
    <h2>Where to be careful</h2>
    <ul>
      <li>The latest NVIDIA quarter comes from its results release. The full quarterly report had not been filed when this was built.</li>
      <li>The audit was done by AI sessions working from the filings. It is far stronger than a read-through, and it is still not the same as a person rebuilding a number by hand.</li>
      <li>Not read again in the audit: most rows of the landlords table that rest on press reports, and 88 of the 114 quarterly lease figures (the 26 that were read again all matched their sentences).</li>
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
