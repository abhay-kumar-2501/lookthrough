# NVIDIA: support for customers and partners, from its filings

Written 18 November 2026. Code: `src/nvidia_financing.py`. Data: `data/processed/nvidia_customer_financing.csv` (409 rows, each with its evidence and link) and `data/processed/nvidia_financing_summary.csv` (one row per quarter, 16 quarters).

Everything here is copied from NVIDIA's own SEC filings. The arrangements are disclosed by the company; describing their size is not a claim that any of them is improper or will lead to a loss.

## What was read

- Every 10-K and 10-Q with a period end from 29 January 2023 to 26 July 2026 (15 filings).
- **The 10-Q for the quarter ended 25 October 2026 is not on EDGAR.** The filing list was refreshed on 18 November 2026; the newest items are the 8-K of 17 November (results) and a 13F-HR of 16 November. The CFO commentary says "We plan to file our 10-Q in the coming weeks." The October quarter therefore comes from two exhibits of that 8-K, the CFO commentary (99.2) and the supplemental financial information (99.3). Those rows carry `form` = "8-K CFO commentary" or "8-K supplemental financial information", and the summary row says "8-K (10-Q not yet filed)". They are unaudited and less detailed than a 10-Q.
- The 8-K of 17 August 2026 (the SB Energy guarantees), for the rows that name a counterparty.
- Twelve quarterly 13F-HR holdings reports (December 2023 to September 2026), for publicly traded shares held by issuer.

## Definitions

| Measure | What is added up |
|---|---|
| NARROW support | Guarantees at maximum gross exposure + loans to customers + equity investments committed but not yet paid |
| BROAD support | NARROW + carrying value of equity stakes + commitments to buy capacity from cloud providers + leases signed for third parties |
| Receivables stretch | Accounts receivable minus 45 days of sales (quarterly revenue x 45 / 91) |

Each is also divided by trailing-twelve-month revenue. Every component is its own column in the summary file. Days sales outstanding is receivables / quarterly revenue x 91.

## Per quarter ($ billion)

| Quarter end | Source | Revenue | TTM revenue | Receivables | DSO | Stretch | Guarantees | Unfunded equity | NARROW | Equity stakes | Capacity buy-backs | Leases for others | BROAD | NARROW / TTM | BROAD / TTM | Stretch / TTM |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2023-01-29 | 10-K | 6.1 | 27.0 | 3.8 | 58 | 0.8 |  |  | 0.0 | 0.3 | 2.2 |  | 2.5 | 0.0% | 9.4% | 3.1% |
| 2023-04-30 | 10-Q | 7.2 | 25.9 | 4.1 | 52 | 0.5 |  |  | 0.0 | 0.5 | 2.4 |  | 2.9 | 0.0% | 11.3% | 2.0% |
| 2023-07-30 | 10-Q | 13.5 | 32.7 | 7.1 | 48 | 0.4 |  |  | 0.0 | 0.8 | 3.5 |  | 4.3 | 0.0% | 13.2% | 1.2% |
| 2023-10-29 | 10-Q | 18.1 | 44.9 | 8.3 | 42 | -0.7 |  |  | 0.0 | 1.2 | 3.6 |  | 4.8 | 0.0% | 10.6% | -1.5% |
| 2024-01-28 | 10-K | 22.1 | 60.9 | 10.0 | 41 | -0.9 |  |  | 0.0 | 1.5 | 3.5 |  | 5.0 | 0.0% | 8.3% | -1.5% |
| 2024-04-28 | 10-Q | 26.0 | 79.8 | 12.4 | 43 | -0.5 |  |  | 0.0 | 1.8 | 8.8 |  | 10.6 | 0.0% | 13.2% | -0.6% |
| 2024-07-28 | 10-Q | 30.0 | 96.3 | 14.1 | 43 | -0.7 |  |  | 0.0 | 2.2 | 9.8 |  | 12.0 | 0.0% | 12.5% | -0.8% |
| 2024-10-27 | 10-Q | 35.1 | 113.3 | 17.7 | 46 | 0.3 |  |  | 0.0 | 2.7 | 11.3 |  | 14.0 | 0.0% | 12.4% | 0.3% |
| 2025-01-26 | 10-K | 39.3 | 130.5 | 23.1 | 53 | 3.6 |  |  | 0.0 | 3.8 | 10.9 |  | 14.7 | 0.0% | 11.2% | 2.8% |
| 2025-04-27 | 10-Q | 44.1 | 148.5 | 22.1 | 46 | 0.3 |  |  | 0.0 | 4.5 | 10.6 |  | 15.1 | 0.0% | 10.2% | 0.2% |
| 2025-07-27 | 10-Q | 46.7 | 165.2 | 27.8 | 54 | 4.7 |  |  | 0.0 | 7.0 |  |  | 7.0 | 0.0% | 4.2% | 2.8% |
| 2025-10-26 | 10-Q | 57.0 | 187.1 | 33.4 | 53 | 5.2 | 0.9 | 6.5 | 7.4 | 12.1 | 26.0 |  | 45.4 | 3.9% | 24.3% | 2.8% |
| 2026-01-25 | 10-K | 68.1 | 215.9 | 38.5 | 51 | 4.8 | 3.5 | 11.4 | 14.9 | 40.0 | 27.0 |  | 81.9 | 6.9% | 37.9% | 2.2% |
| 2026-04-26 | 10-Q | 81.6 | 253.5 | 40.7 | 45 | 0.4 | 3.5 | 27.0 | 30.5 | 82.4 | 30.0 |  | 142.9 | 12.0% | 56.4% | 0.1% |
| 2026-07-26 | 10-Q | 96.2 | 303.0 | 63.1 | 60 | 15.5 | 3.5 | 25.0 | 28.5 | 99.8 | 65.0 | 20.0 | 213.3 | 9.4% | 70.4% | 5.1% |
| 2026-10-25 | 8-K | 115.8 | 361.8 | 81.0 | 64 | 23.7 | 118.0 | 20.0 | 138.0 | 117.9 | 60.0 |  | 315.9 | 38.1% | 87.3% | 6.6% |

An empty cell means the filing does not state the figure; it counts as zero in the totals. Three places where that matters:

- **July 2025.** The 10-Q gives one total for all commitments ($45.8bn) and does not split out cloud service agreements, which were $10.6bn a quarter earlier and $26bn a quarter later. BROAD for that quarter is understated; the dip is a disclosure gap.
- **July 2026.** The $105bn SB Energy guarantees were signed on 17 August 2026, after the quarter ended, so they are outside the totals and in `guarantees_signed_after_period_end`. With them, NARROW would be $133.5bn (44% of trailing revenue).
- **October 2026.** $105bn of the $118.0bn of guarantees is the SB Energy cap, which takes effect building by building from fiscal 2029. Without it NARROW is $33.0bn (9.1% of trailing revenue) and BROAD $210.9bn (58%). Also, the "leases not commenced for third party" row ($20bn in July) is gone: the commentary shows one row of $74bn and says "We may assign some of these leases to third parties in the future." Nothing is counted for leases for others that quarter, so BROAD is not like-for-like with July.

Concentration, advances and gains:

| Quarter end | Customers over 10% of receivables (number, combined share, largest) | Customers over 10% of revenue (number, combined share) | Customer advances ($bn) | Deferred revenue ($bn) | Equity gains in quarter ($bn) |
|---|---|---|---|---|---|
| 2023-01-29 | 2, 25%, 14% | 0, 0% |  | 0.6 |  |
| 2023-04-30 | 2, 22%, 12% | 0, 0% |  | 0.6 | -0.0 |
| 2023-07-30 | 2, 29%, 16% | 1, 17% |  | 0.7 | 0.1 |
| 2023-10-29 | 2, 22%, 11% | 1, 12% |  | 0.9 | -0.1 |
| 2024-01-28 | 2, 35%, 24% | 1, 13% | 0.2 | 1.3 | 0.3 |
| 2024-04-28 | 2, 31%, 16% | 2, 24% | 0.3 | 1.5 | 0.1 |
| 2024-07-28 | 3, 49%, 23% | 4, 46% | 0.3 | 1.7 | 0.2 |
| 2024-10-27 | 4, 53%, 18% | 3, 36% | 0.1 | 1.6 | 0.0 |
| 2025-01-26 | 2, 33%, 17% | 3, 34% | 0.1 | 1.8 | 0.7 |
| 2025-04-27 | 3, 57%, 27% | 2, 30% | 0.3 | 2.1 | -0.2 |
| 2025-07-27 | 3, 56%, 23% | 2, 39% | 0.1 | 2.0 | 2.2 |
| 2025-10-26 | 4, 65%, 22% | 4, 61% | 0.1 | 2.4 | 1.4 |
| 2026-01-25 | 3, 56%, 25% | 2, 36% | 0.2 | 2.6 | 5.5 |
| 2026-04-26 | 3, 64%, 30% | 3, 54% | 0.3 | 3.1 | 15.9 |
| 2026-07-26 | 5, 70%, 22% | 1, 16% | 2.8 | 6.4 | 7.8 |
| 2026-10-25 | 2, 35%, 18% | 3, 36% |  |  | 1.8 |

Revenue concentration is for the quarter in a 10-Q and for the fiscal year in a 10-K (the January rows). These are direct customers, which include distributors and system builders; the filings say separately that some end customers buy through them.

## The latest 10-Q quarter, 26 July 2026, piece by piece

| Component | $bn | Evidence (10-Q filed 26 August 2026) |
|---|---|---|
| Guarantees | 3.5 | "We entered into land, power, and shell guarantees for select AI cloud partners' data center lease obligations in the event of their default. The maximum gross exposure under all agreements is $3.5 billion." Partners "have placed $712 million in escrow". |
| Loans to customers | none disclosed | No mention of a loan or note receivable in any 10-K or 10-Q read. |
| Unfunded equity commitments | 25 | Commitments table: "Equity investments 18 3 2 2 — — 25"; "We committed to make certain equity investments in AI model makers, infrastructure financiers, and other private companies, subject to certain contingencies." |
| **NARROW** | **28.5** | 9.4% of trailing revenue of $303.0bn |
| Non-marketable equity securities | 47.9 | Roll-forward: "Balance at end of period $47,898" |
| Equity-method investments | 3.3 | "We had $3.3 billion of investments in infrastructure financiers accounted for using the equity method" |
| Publicly held equity securities | 47.7 | Two table rows: Level 1 36,934 and Level 2 10,806 (the second "included investments in unregistered warrants and preferred stock convertible to common stock in public companies") |
| Warrants in public companies | 0.8 | "the fair values of the equity derivatives, a Level 3 measurement, were $824 million" (notional $4,800m; an equity forward contract has notional $1,000m) |
| Cloud service agreements | 29 | Commitments table: "Cloud service agreements 3 8 7 6 4 1 29" |
| AI cloud agreements | 36 | Additional commitments table: "AI cloud agreements $ — $6 $8 $7 $6 $9 $36" |
| Leases for third parties | 20 | "Data center leases not commenced for third party — — 1 1 1 17 20"; "We expect to reassign these data center leases to third parties." |
| **BROAD** | **213.3** | 70.4% of trailing revenue |
| Receivables | 63.1 | "Accounts receivable, net 63,059"; quarterly revenue $96,221m gives 59.6 days and a stretch of $15.5bn over the 45-day level |

The company's own total, "equity investments of $99 billion and equity investment commitments of $25 billion as of July 26, 2026" (MD&A), matches the three equity lines above ($98.9bn) without the warrants.

On receivables the 10-Q says: "In certain cases, for investment-grade customer purchases, we have and may in the future provide longer payment terms ranging from 90 days up to one year to assist customers with large data center builds", and attributes the increase in receivables to "extended payment terms on large multi-quarter agreements with certain investment-grade customers."

## Named counterparties

From 10-Ks, 10-Qs and 8-Ks:

| Date | Counterparty | Amount | Statement |
|---|---|---|---|
| 27 Apr 2025 | CoreWeave | $1bn fair value | Investment reclassified to marketable securities after its listing |
| 26 Oct 2025 | Intel | $5bn | Part of $6.5bn of investment commitments, "subject to regulatory approval" |
| 26 Oct 2025 | Anthropic | up to $10bn | Agreement signed November 2025, after the period end, "subject to certain closing conditions" |
| 26 Oct 2025 | OpenAI | not stated | "a letter of intent with an opportunity to invest" |
| 25 Jan 2026 | OpenAI | not stated | "We are finalizing an investment and partnership agreement with OpenAI." |
| 17 Aug 2026 | SB Energy (lessor), OpenAI (tenant) | $105bn cap | Residual value guarantees on leases for about 4.25 gigawatts in Pike County, Ohio; "OpenAI has agreed to reimburse and indemnify NVIDIA for any and all amounts actually paid" |

Later filings give totals without names: the $25bn of equity commitments at July 2026 and the $9.5bn of "power and systems credit support guarantees" at October 2026 are not attributed to anyone.

The 13F-HR for 30 September 2026 lists eight public holdings worth $48.3bn: Space Exploration Technologies $19.7bn, Intel $19.4bn, CoreWeave $4.1bn, Coherent $2.2bn, Synopsys $1.9bn, Nokia $0.7bn, Nebius $0.3bn and Generate Biomedicines $0.01bn. A year earlier the list came to $3.8bn, of which CoreWeave was $3.3bn. All twelve quarters are in the long file under `form` = 13F-HR. A 13F covers listed shares only and is dated at calendar quarter ends, so it does not tie exactly to the fiscal-quarter balance sheet.

xAI and Nscale are not named with an amount in any document read. (The 17 November press release mentions Nscale, Nebius, CoreWeave, OpenAI and Anthropic as users of NVIDIA products, without financing terms.)

## What stands out

1. **The mix changed in about a year.** Until July 2025 the only items were small equity stakes and cloud contracts for NVIDIA's own research and cloud offerings. The first guarantee ($0.86bn) and the first separately disclosed investment commitment ($6.5bn) appear in the October 2025 10-Q. By October 2026 guarantees were $118bn at their caps and BROAD support was 87% of trailing revenue, against 12% two years earlier.
2. **Equity stakes grew from $7.0bn to $117.9bn in five quarters** (July 2025 to October 2026). Gains recognised on them were $15.9bn in the April 2026 quarter and $25.5bn over the first nine months of fiscal 2027.
3. **Receivables moved late.** DSO stayed between 41 and 58 days for fourteen quarters, then went to 60 and 64 in the last two. The stretch over 45 days went from $0.4bn in April 2026 to $23.7bn in October 2026. The company's own figure for October is 64 days, the same as computed here.
4. **In July 2026 five customers each held over 10% of receivables (70% together) while only one exceeded 10% of the quarter's revenue (16%).** In October it was two customers and 35%.
5. **Customer advances rose from $0.3bn to $2.8bn** between April and July 2026, a movement in the opposite direction: some customers are paying ahead.

## Judgment calls

- **Guarantees are counted at the stated maximum**, before the $712m of escrow and before any recovery from re-letting a site. The SB Energy cap is counted in full from the signing date although no guarantee is yet in effect.
- **All equity holdings count as stakes in customers or partners.** The filings do not separate customers from other investees, and the 13F list includes companies (Intel, Synopsys, Nokia, Coherent) that the filings read here do not describe as customers. The equity part of BROAD is an upper bound.
- **"Cloud service agreements" are included in BROAD** although NVIDIA describes them as infrastructure for its own research. They are bought from cloud providers that buy NVIDIA products; the fiscal 2023 10-K says data center revenue "reflects purchases made by several CSP partners to support multi-year cloud service agreements". They are kept apart from "AI cloud" (later "neocloud") agreements, where the provider "can unilaterally stop providing to us and sell to third-party customers".
- **Debt convertible into public equity** ($3.5bn, first shown October 2026) is treated as an equity stake, not a loan, because the company presents it with its equity securities.
- **Leases NVIDIA will use itself** ($25bn in July 2026) are recorded but left out of BROAD.
- **The equity-method "maximum loss exposure"** ($4.7bn) is recorded but not added, since it overlaps the carrying value and possibly the investment commitments.
- **Fourth-quarter revenue** is the fiscal year minus nine months. Every quarter uses 91 days; the fourth quarter of fiscal 2027 will have fourteen weeks and will need 98.
- **Gains** come from the cash flow statement line for equity securities, which is cumulative for the year; quarterly gains are differences.

BROAD adds amounts already paid, amounts that may never be paid, and undiscounted payments over up to twenty years. It measures the scale of disclosed arrangements against sales and is not an estimate of loss.

## Verification

- All 409 rows had their evidence read against their amounts on 18 November 2026 and are marked `verified` = yes. The mark is tied to a fingerprint of each document's rows, so any later change to a pattern or filing resets that document to "no".
- As a second check, 163 of 167 dollar figures from the 10-Ks and 10-Qs also appear as an XBRL fact dated at the same period end. Two of the four exceptions are sums of two table rows (public equity, April and July 2026).
- 21 rows are arithmetic on other rows and say "derived" in their evidence. 16 rows record that a search for loans found nothing; their amount is empty.

## Unverified or inconsistent

- **April 2026 guarantees.** The 10-Q for 26 April 2026 states the $3.5bn maximum exposure and $712m escrow in the present tense, but its XBRL tags date both facts 25 January 2026. The July 10-Q shows notional values of $3,530m at 25 January and $3,529m at 26 July, so the April figure is very probably right, but the filing does not date it in words.
- **October 2026 is from an earnings release.** No deferred revenue, customer advances, warrant values or equity-method figure are given. Equity-method investments ($3.9bn) are derived as the balance sheet line "Non-marketable securities" minus the roll-forward balance. The 10-Q may change or add detail, in particular on which leases are for third parties and what the $9.5bn "power and systems" guarantees cover.
- **Rounding.** From October 2025 most commitments are stated in whole billions of dollars, so each can differ from its exact value by up to $0.5bn.
- **Loans.** "None disclosed" means the words loan, note receivable, financing receivable, vendor financing and customer financing do not appear in the documents read. It does not show that no such balance exists below the disclosure threshold.

## Using the same measures for Lucent and Cisco, 1998-2002

| Here | Likely equivalent then |
|---|---|
| Guarantees, maximum exposure | Guarantees of customer borrowings (commitments and contingencies note) |
| Loans to customers | Customer financing loans and notes receivable drawn; undrawn commitments would sit with "unfunded equity commitments" as a separate column |
| Equity stakes | Investments in customers and partners, public and private |
| Capacity buy-backs | Purchase commitments to customers, if any |
| Receivables stretch | Same formula; use 91 days and the quarter's revenue |

For NVIDIA the loan column is empty and guarantees and equity carry the weight; for the equipment makers of that period the reverse is likely, which is why the components are kept apart.
