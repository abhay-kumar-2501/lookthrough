# Vendor financing in 1997-2003: what the filings of the time say

Written 18 Nov 2026. Data: [`inputs/vendor_finance_2000.csv`](../inputs/vendor_finance_2000.csv) (419 rows, 54 filings). Ratios: [`src/vendor_finance_history.py`](../src/vendor_finance_history.py), which writes [`data/processed/vendor_finance_history.csv`](../data/processed/vendor_finance_history.csv).

## The question

Commentators compare NVIDIA's support for its customers (guarantees, equity stakes, capacity buy-backs) with telecom equipment makers lending to their customers around 2000. This file records what Lucent, Cisco, Nortel and Motorola actually disclosed then, so the same ratios can be computed for both periods. It makes no claim that the two periods are alike; the last section lists the reasons they may not be.

## Sources and method

| Company | CIK | Name on EDGAR | Filings read | Period covered |
|---|---|---|---|---|
| Lucent Technologies | 1006240 | ALCATEL-LUCENT USA INC. (formerly LUCENT TECHNOLOGIES INC) | 10-K / 10-K405 for fiscal 1997-2003; ten 10-Qs, Dec 1999 to Dec 2002 | Sep 1997 to Sep 2003 |
| Cisco Systems | 858877 | CISCO SYSTEMS, INC. | 10-K / 10-K405 for fiscal 1997-2003; nine 10-Qs, Jan 2000 to Oct 2002 | Jul 1997 to Jul 2003 |
| Nortel Networks | 72911 | NORTEL NETWORKS CORP (formerly NORTHERN TELECOM LTD) | 10-K405 / 10-K for 2000-2003; seven 10-Qs, Sep 2000 to Sep 2002 | Sep 2000 to Dec 2003 |
| Motorola | 68505 | Motorola Solutions, Inc. (formerly MOTOROLA INC) | 10-K for 2001-2003; seven 10-Qs, Sep 2000 to Sep 2002 | Sep 2000 to Dec 2003 (reserves from Dec 1999) |

- Every number was read in a filing fetched from sec.gov through `src/edgar.py`. Nothing comes from an article or from memory. No web search was used.
- Each row's evidence is the sentence or table row as it appears in the filing. The filings are plain text or simple HTML; the only change made is that runs of dots or dashes used as table rulers are collapsed to a space. Each evidence string was matched by program against the filing text before the row was written, and the amount was checked to appear in it.
- Old 10-Ks often put the annual report in an exhibit. Where they do, the URL is the complete submission text file (`<accession>.txt`), which contains every exhibit.
- Figures are as first reported in that period's own filing unless the notes column says otherwise. All four companies later restated (spin-offs of Avaya and Agere at Lucent, discontinued operations and two restatements at Nortel), so a later filing's comparative column can differ.
- Empty amount = the filing does not give the figure. 22 rows record a "not disclosed" after a search of the full filing text.
- Alcatel was not attempted (it filed Form 20-F under French accounting rules).

## Results

Fiscal years, $ millions. "Available" = all financing promised, drawn or not. "Drawn" = loans (and Cisco's finance leases) before reserves. n/d = not disclosed.

| Company | Year end | Available | Drawn | Guarantees | Revenue | Available ÷ revenue | (Drawn + guarantees) ÷ revenue | DSO (days) | Reserves ÷ drawn |
|---|---|---|---|---|---|---|---|---|---|
| Lucent | Sep 1997 | 2,207 | 25 | 118 | 26,360 | 8.4% | 0.5% | 74 | n/d |
| Lucent | Sep 1998 | 2,604 | 399 | 205 | 30,147 | 8.6% | 2.0% | 84 | n/d |
| Lucent | Sep 1999 | 7,520 | 1,574 | 310 | 38,303 | 19.6% | 4.9% | 99 | n/d |
| Lucent | Sep 2000 | 8,100 | 1,300 | 770 | 33,813 | 24.0% | 6.1% | 103 | n/d |
| Lucent | Sep 2001 | 5,300 | 2,600 | 400 | 21,294 | 24.9% | 14.1% | 79 | 70.0% |
| Lucent | Sep 2002 | 1,342 | 909 | 189 | 12,321 | 10.9% | 8.9% | 49 | 86.6% |
| Lucent | Sep 2003 | 505 | 354 | 88 | 8,470 | 6.0% | 5.2% | 65 | 93.9% |
| Cisco | Jul 1997 | n/d | n/d | n/d | 6,440 | n/d | n/d | 66 | n/d |
| Cisco | Jul 1998 | n/d | n/d | n/d | 8,459 | n/d | n/d | 56 | n/d |
| Cisco | Jul 1999 | n/d | 663 | n/d | 12,154 | n/d | 5.5% | 37 | 12.5% |
| Cisco | Jul 2000 | n/d | 1,515 | n/d | 18,928 | n/d | 8.0% | 44 | 14.9% |
| Cisco | Jul 2001 | 3,454 | 1,638 | n/d | 22,293 | 15.5% | 7.3% | 24 | 57.7% |
| Cisco | Jul 2002 | 2,162 | 1,275 | n/d | 18,915 | 11.4% | 6.7% | 21 | 77.1% |
| Cisco | Jul 2003 | 844 | 789 | n/d | 18,878 | 4.5% | 4.2% | 26 | 70.1% |
| Nortel | Dec 2000 | 5,614 | 1,514 | n/d | 30,275 | 18.5% | 5.0% | 99 | 28.6% |
| Nortel | Dec 2001 | 2,962 | 1,351 | n/d | 17,511 | 16.9% | 7.7% | 61 | 65.7% |
| Nortel | Dec 2002 | 1,892 | 1,091 | n/d | 10,560 | 17.9% | 10.3% | 66 | 73.2% |
| Nortel | Dec 2003 | 581 | 401 | n/d | 10,193 | 5.7% | 3.9% | 90 | 70.1% |
| Motorola | Dec 2000 | 3,398 | 2,907 | n/d | 38,136 | 8.9% | 7.6% | 68 | 8.0% |
| Motorola | Dec 2001 | 3,199 | 2,762 | 275 | 30,486 | 10.5% | 10.0% | 55 | 59.6% |
| Motorola | Dec 2002 | 2,943 | 2,718 | 50 | 27,279 | 10.8% | 10.1% | 59 | 82.8% |
| Motorola | Dec 2003 | 2,555 | 2,396 | 10 | 27,058 | 9.4% | 8.9% | 60 | 87.4% |

Quarterly rows for 2000-2002 are in the processed CSV. The patterns worth knowing:

- **Lucent's promises peaked eighteen months before its loans did.** Commitments were highest at 31 Dec 1999 ($8.4bn of loans plus $1.4bn of guarantees = $9.8bn, 25% of annualized revenue) when only $1.1bn was drawn. Drawn loans plus guarantees peaked at $2.9bn in June 2001 to $3.0bn in September 2001, when quarterly revenue was $5.8bn against $7.4bn a year earlier.
- **Reserves arrived late and all at once.** At the end of 2000 Motorola had reserved 8% of its finance receivables and Nortel 29% of its drawn financing; Lucent states no reserve against customer financing before March 2001. By the end of fiscal 2001 Lucent had reserved 70% of drawn commitments, Nortel 66%, Motorola 60%.
- **Days sales outstanding rose before the write-offs.** Lucent went from 74 days (1997) to 103 (2000); Nortel was at 99 days at the end of 2000.

### Peaks and what followed

| Company | Peak financing available | Date | Share of annualized revenue | Charges, peak fiscal year to 2003 | Share of peak | Of which tied to customer financing or a named borrower | Share of peak | Largest reserve balance | Share of peak |
|---|---|---|---|---|---|---|---|---|---|
| Lucent | $9,800m | 31 Dec 1999 | 24.7% | $3,831m | 39% | $2,065m | 21% | $2,100m (Sep 2001) | 21% |
| Nortel | $5,614m | 31 Dec 2000 | 18.5% | $1,902m | 34% | n/d | n/d | $895m (Sep 2002) | 16% |
| Motorola | $3,776m | 31 Mar 2001 | 12.2% | $2,176m | 58% | $1,926m (Telsim) | 51% | $2,251m (Dec 2002) | 60% |
| Cisco | $3,454m | 28 Jul 2001 | 15.5% | $300m | 9% | n/d | n/d | $936m (Jul 2002) | 27% |

How to read the charge columns:

- Lucent's and Nortel's charges are the income-statement provision for bad debts **and** customer financing together, so they are an upper bound on financing losses. Lucent gives two partial splits: about $1.3bn of the fiscal 2001 provision of $2.2bn "was related to three customer finance projects, including Winstar and One.Tel", and $765m of the fiscal 2002 provision of $1.3bn was customer financing. Those two add to $2,065m, a floor. Nortel gives no split. Against the amounts actually drawn the losses look heavier: Lucent's reserves reached 70-94% of drawn commitments.
- Motorola's charge is specific to finance receivables. $1.4bn of the 2001 charge and $526m of the 2002 charge were one borrower, Telsim of Turkey.
- Cisco's 9% is a lower bound: it booked reserves on leases and structured loans as reductions of revenue ("sales adjustments") and never quantified them. Its "unearned income and other reserves" on leases rose from $195m to $896m in fiscal 2001.
- Most undrawn commitments were never lent. They expired or were cancelled when borrowers missed milestones, so a share of peak *commitments* understates the loss rate on money that actually went out.

## The most striking sentences

1. Lucent, 10-Q for 31 Dec 1999: "As of December 31, 1999, Lucent had made commitments or entered into agreements to extend credit to certain customers, including PCS and wireless operators, for an aggregate of approximately $8.4 billion." The same filing: "Network operators worldwide are requiring their suppliers to arrange or provide long-term financing for them as a condition of obtaining or bidding on infrastructure projects."
2. Lucent, 10-K for fiscal 2001: "Reserves associated with total drawn commitments were $2.1 billion, reflecting a net exposure of approximately $900 million."
3. Lucent, 10-K for fiscal 1998: "Lucent entered into a credit agreement with WinStar to provide up to $2,000 million in equipment financing to fund the buildout of this network." (The fiscal 2001 10-K: "On April 18, 2001, Winstar filed for Chapter 11 protection"; Lucent booked "a $700 million provision ... for amounts due from Winstar".)
4. Motorola, 10-K for 2003: "a $1.5 billion charge for potentially uncollectible finance receivables, of which $1.4 billion related to the $2.0 billion loan to Telsim".
5. Lucent, 10-K for fiscal 1998, on why it could book revenue on financed sales: "Lucent has determined that the receivables under the contract are reasonably assured of collection based on various factors among which was the ability of Lucent to sell the loans and commitments without recourse." And the 10-K for fiscal 2003, looking back: "We were unable to sell or transfer significant amounts of the drawn and undrawn commitments to financial institutions or other investors on reasonable terms or at all."
6. Cisco, 10-K for fiscal 2000: "Our loan financing arrangements may include not only financing the acquisition of our products but also providing additional funds for soft costs associated with network installation and integration of our products and for working capital purposes."

## Mapping to the NVIDIA measures

`src/nvidia_financing.py` defines "narrow support" as guarantees + loans to customers + unfunded equity commitments, and shows it as a share of trailing-twelve-month revenue. The closest historical counterpart is `financing_made_available` ÷ revenue here (loans and guarantees, drawn and undrawn). `drawn_plus_guarantees_to_revenue` is the stricter version: money actually out plus guarantees actually in use. Days sales outstanding uses the same formula in both scripts.

Two differences in construction: quarterly ratios here use the quarter's revenue times four, not a trailing twelve months (restatements make the old quarters hard to chain); and amounts here are in $ millions.

## Limits of the comparison

**Who the customers were.** The filings name them: Sprint PCS (a new wireless network, $1.8bn facility from Lucent in 1996), WinStar (fixed wireless broadband, $2bn facility), One.Tel (liquidated in 2001), Telsim ("a wireless service provider in Turkey", $2bn from Motorola, in default from April 2001). Cisco's 1999 10-K says demand for financing came "particularly [from] competitive local exchange carriers"; Nortel's 2000 10-K says it would keep financing "strategic start-up customers and ... turnkey construction of new networks, particularly 3G wireless operators". These were newly formed carriers building networks ahead of their revenue, dependent on capital markets staying open, and each vendor's exposure was concentrated in a handful of them. The losses came from that kind of borrower, not from customer financing as such: Lucent's first large facility was repaid in full ("In November 1998, Sprint PCS repaid the entire outstanding loan balance and canceled the remaining undrawn commitments"). Who the borrowers are now is a question for today's filings, covered in `research/nvidia_financing_notes.md`, not for these. As background only (not read in a filing for this file): most AI hardware is bought by large, profitable companies that need no vendor credit, and the support suppliers disclose is directed at a smaller group of newer cloud providers and AI developers. That smaller group is where the analogy applies, if it applies anywhere.

**Loans then; equity, guarantees and buy-backs now.** The 1990s instrument was a senior loan or a guarantee of the customer's bank debt: a fixed claim with a repayment date, which either performs or is reserved. An equity stake has no repayment date and is marked up or down; a capacity buy-back or a lease guarantee is a contingent obligation over many years and is not an asset at all. So "reserves ÷ drawn" has no clean modern counterpart, and modern totals that add equity stakes to guarantees are not measuring the same thing as `financing_made_available`. The like-for-like items are guarantees, loans and unfunded commitments.

**Financing more than the product.** Cisco and Nortel both say their loans could fund installation costs, working capital and (Nortel) "equity financing", not just their own equipment. The vendor was partly acting as the customer's bank.

**Revenue recognition leaned on selling the loans.** Lucent booked revenue on financed sales partly because it expected to sell the loans on to banks without recourse. When that market closed in 2001 the loans stayed with Lucent. (Background, not from these filings: the accounting rules for revenue and for transfers of financial assets have both been rewritten since.)

**Disclosures with no modern equivalent.**
- Commitments split into "drawn", "available but not drawn" and "not available" (conditions precedent not yet met). At Lucent's peak, $4.9bn of the $8.4bn was in the last bucket. Modern guarantee notes give a maximum exposure but no such split.
- Sales of customer loans to off-balance-sheet trusts with limited recourse (Lucent's September 2000 trust, capacity $970m, $579m sold), and receivables "sold with recourse" kept on the balance sheet as secured borrowings ($1,037m at Lucent in 1999). (Background: the rules for such vehicles were tightened after 2001.)
- Guarantees "backed by amounts held in trust ... or assigned to a third-party reinsurer" (Lucent, 1997-1999).
- Reserves booked as a deduction from revenue (Cisco) and so invisible as an expense.

**Things that exist now and did not then.** Standardized disclosure of guarantees (the FIN 45 rule took effect at the end of 2002, after the losses) and machine-readable tagging. The old numbers are therefore more dependent on what each company chose to say, and definitions differ between the four companies.

**Scale and timing.** Peak financing available was 12-25% of annualized revenue, but the amount actually lent plus guaranteed never exceeded about 14% of annual revenue at any of the four, and that maximum came after revenue had already collapsed (the denominator fell faster than the loans were repaid). A ratio taken at one date can mislead in either direction.

## What could not be found

- **Cisco:** any total for loan commitments before 28 Jul 2001; the gross amount of structured loans and the reserve against them (only a net figure, $205m at its highest); guarantees of customer debt (the fiscal 2003 10-K says they "were not material"); charges specific to customer financing. It is unclear whether "outstanding loan commitments" includes amounts already funded; it is treated here as the commitment total and finance leases are added to it.
- **Nortel:** nothing before the 10-Q for September 2000. As a foreign issuer it was not on EDGAR in 10-K form for 1997-1999. Drawn balances are missing for the quarters before December 2001 (only undrawn commitments are stated). No customer guarantees are quantified. The charge for 2000 is described but not given.
- **Motorola:** financing balances for 1997-1999; guarantees at 31 Dec 2000, so the true peak may be at that date and somewhat above $3.8bn; the 10-Ks for 2000-2002 incorporate their financial statements from the proxy statement, which was not read, so sales and earnings for 2000-2002 are the restated figures in the 2003 10-K. Its guarantee totals in 2000-2001 are "third-party financial guarantees" and may include non-customers.
- **Lucent:** reserves against customer financing before March 2001; a split of the provision between trade receivables and customer financing in any year but fiscal 2002. Its 1997-1999 guarantee figures include debt of joint ventures.
- **Sold with recourse** is thin everywhere: seven rows, and not always customer loans as opposed to trade receivables.

## Confidence

| Company | Confidence | Why |
|---|---|---|
| Lucent | High | A consistent table or paragraph in every filing from 1997; quarterly from Dec 1999; totals reconcile across filings (for example 5,544 undrawn + 1,574 drawn = the $7,100m in MD&A). |
| Nortel | Medium to high for 2001-2003, medium for 2000 | Clear tables from Dec 2001. Earlier quarters give undrawn only. Figures were restated twice; original filings are used except 2003. |
| Motorola | Medium | Finance receivables and allowances are clear from the 10-Qs. Revenue for 2000-2001 is restated, guarantees are broadly defined, and nothing is available before 2000. |
| Cisco | Medium for what is there, low for completeness | Leases and loan commitments are stated plainly, but commitments start only in 2001, loans are net, and reserves mix unearned income with credit reserves. |
