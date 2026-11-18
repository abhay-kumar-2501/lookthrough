# NVIDIA supply pre-order test: notes

Written 18 November 2026. Code: `src/nvidia_supply.py`. Data: `data/processed/nvidia_supply.csv` (one row per fiscal quarter), `nvidia_commitments_table.csv` (every row and bucket of each commitments table or schedule) and `nvidia_supply_peers.csv` (AMD and Broadcom).

## The question

NVIDIA orders wafers, memory, packaging and capacity long before it sells the products. How large are those orders today relative to the business, compared with fiscal 2022-2023 (when large inventory charges followed) and with the rest of the record since January 2019?

The measure is supply commitments divided by cost of revenue over the last four quarters, read as "years of cost of revenue already on order". The same figure divided by revenue, and a version scaled by the latest quarter's cost times four, are alongside it in the CSV.

## Short answer

- **Today: 4.3 years of cost of revenue** ($390bn against $90.7bn), or 1.08 times a year's revenue, as of 25 October 2026. That quarter comes from the Form 8-K, not a 10-Q (see "Latest quarter"). The last figure in a 10-Q is 3.6 years ($279bn against $76.7bn) at 26 July 2026.
- **The fiscal 2022 peak was 0.95 years** ($9.0bn against $9.4bn) at 30 January 2022.
- **The highest reading before the present climb was 1.26 years** ($17.1bn against $13.5bn) at 29 October 2023, not fiscal 2022.
- Today's ratio is about 4.5 times the fiscal 2022 peak and 3.4 times the October 2023 peak. On the latest-quarter run rate, which is fairer to a business that has doubled in a year, it is 3.3 years against 0.85 and 0.91.
- The commitments are also longer-dated. In January 2022, 90% of purchase commitments fell due within 12 months. At 25 October 2026 only 18% of supply commitments fall in the remaining quarter of the fiscal year, 70% by the end of fiscal 2028, and $118bn (30%) in fiscal 2029 or later.

## Ratio table (fiscal year ends, then the last seven quarters)

| Quarter end | Source | Def. | Supply commitments | Cost of revenue, last 4 qtrs | Years of cost of revenue | x revenue, last 4 qtrs | Years at latest-quarter run rate | Inventories | Due: next 12m / rest of FY / through next FY |
|---|---|---|---|---|---|---|---|---|---|
| 2019-01-27 | 10-K | A | $0.9bn | $4.5bn | 0.20 | 0.08 | 0.23 | $1.6bn | 100% / n/d / 100% |
| 2020-01-26 | 10-K | A | $1.2bn | $4.2bn | 0.28 | 0.11 | 0.27 | $1.0bn | 100% / n/d / 100% |
| 2021-01-31 | 10-K | A | $2.5bn | $6.3bn | 0.40 | 0.15 | 0.34 | $1.8bn | 100% / n/d / 100% |
| 2022-01-30 | 10-K | B | $9.0bn | $9.4bn | 0.95 | 0.33 | 0.85 | $2.6bn | 90% / n/d / 90% |
| 2023-01-29 | 10-K | B | $4.9bn | $11.6bn | 0.42 | 0.18 | 0.55 | $5.2bn | 65% / n/d / 65% |
| 2024-01-28 | 10-K | C | $16.1bn | $16.6bn | 0.97 | 0.26 | 0.76 | $5.3bn | 84% / n/d / 84% |
| 2025-01-26 | 10-K | C | $30.8bn | $32.6bn | 0.94 | 0.24 | 0.73 | $10.1bn | 79% / n/d / 79% |
| 2025-04-27 | 10-Q | C | $29.8bn | $44.4bn | 0.67 | 0.20 | 0.43 | $11.3bn | n/d / 72% / 86% |
| 2025-07-27 | 10-Q | - | n/d | $49.8bn | n/d | n/d | n/d | $15.0bn | n/d / 68% / 82% |
| 2025-10-26 | 10-Q | D | $50.3bn | $56.0bn | 0.90 | 0.27 | 0.83 | $19.8bn | n/d / n/d / n/d |
| 2026-01-25 | 10-K | D | $95.2bn | $62.5bn | 1.52 | 0.44 | 1.40 | $21.4bn | n/d / n/d / n/d |
| 2026-04-26 | 10-Q | D | $119.0bn | $65.5bn | 1.82 | 0.47 | 1.45 | $25.8bn | n/d / 80% / n/d |
| 2026-07-26 | 10-Q | E | $279.0bn | $76.7bn | 3.64 | 0.92 | 2.90 | $31.6bn | n/d / 33% / 64% |
| 2026-10-25 | 8-K | E | $390.0bn | $90.7bn | 4.30 | 1.08 | 3.34 | $39.7bn | n/d / 18% / 70% |

"n/d" = not disclosed. The due shares from October 2021 to July 2025 are shares of **all** purchase commitments (supply plus cloud services and other), because the filings only give a year-by-year schedule for the combined total in those years. Before and after that window they are shares of the supply figure itself. In a 10-Q "through next FY" covers 15 to 21 months; at a year end it is exactly the next 12 months.

## Definition changes (series breaks)

The label on the supply-side number changed four times. `commit_definition` and `series_break` in the CSV mark each one.

| From | Definition | What the number covers | Why it is a break |
|---|---|---|---|
| Jan 2019 | A: inventory purchase obligations | Open orders for wafers, components and finished goods. The fiscal 2019 and 2020 annual reports put all of it in the "less than 1 year" column. | Start of series. |
| Aug 2021 | B: inventory purchase and long-term supply obligations | A plus the unpaid part of new long-term supply agreements ($1.79bn of the $6.90bn at October 2021, falling to $0.81bn by January 2023). | Multi-year agreements enter. Prepayments already made are assets and are not in the number. |
| Apr 2023 | C: inventory purchase and long-term supply and capacity obligations | B plus capacity agreements. | The wording adds capacity. The unpaid supply-agreement amount stops being given. |
| Oct 2025 | D: manufacturing, supply and capacity commitments | Renamed and reworded. The July 2025 10-Q gave **no** separate supply figure at all. | New label after a one-quarter gap. The auditor's critical audit matter in the January 2026 10-K still describes the same $95.2bn under the definition C name, which suggests the scope is the same, but the company does not say so. |
| Jul 2026 | E: "supply and capacity" row of a commitments table | Rounded to whole $ billions, with payments by fiscal year. Described as supply for data center systems, primarily memory and manufacturing facilities, for several years of demand. | Table format, coarser rounding, explicitly multi-year. The 10-Q restates the prior quarter as $119bn, which matches definition D, so D and E join without a gap. |

Other things that changed around the number, recorded in `nvidia_commitments_table.csv`:

- **Other purchase obligations** (software, cloud services, long-lived assets) were always reported separately and are never in the supply figure: $0.3bn in 2020, $14.3bn by January 2025 (of which $10.9bn multi-year cloud service agreements).
- **The schedule by fiscal year** (October 2021 to July 2025) is one row for supply plus other. From October 2025 the cloud commitments get their own schedule in a sentence. From July 2026 there is a five-row table (supply and capacity, cloud service agreements, data center leases not commenced, equity investments, capital expenditures) plus a second table of "additional commitments".
- **Between the July 2026 10-Q and the October 2026 8-K the table was rearranged.** The $20bn of data center leases to be reassigned to third parties moved out of the additional-commitments table into the main "data center leases not commenced" row ($25bn to $74bn). The main-table total rose from $366bn to $518bn, of which roughly $20bn is that move. The supply row is not affected.
- **Guarantees** (maximum exposure $108.5bn in the July 2026 10-Q, $118.0bn in the October 2026 8-K, mostly the SB Energy lease guarantees) are contingent and are kept in the table file only.

## Prepaid supply agreements

Money already paid to suppliers in advance is an asset, separate from the commitments. Long-term balance from XBRL, short-term balance from a footnote sentence:

| Quarter end | Long-term | Short-term | Still unpaid on those agreements (inside the commitments) |
|---|---|---|---|
| 2021-10-31 | $1.6bn | n/d | $1.79bn |
| 2022-01-30 | $1.7bn | n/d | $1.58bn |
| 2023-01-29 | $3.0bn | $0.46bn (comparative in a later filing, not in the CSV) | $0.81bn |
| 2024-01-28 | $2.5bn | $2.5bn | n/d |
| 2025-01-26 | $1.7bn | $3.3bn | n/d |
| 2025-10-26 | $1.5bn | $2.0bn | n/d |

From the January 2026 10-K onward no prepaid supply balance is tagged or given as a separate line. The risk factors still say prepaid manufacturing and capacity agreements exist and have grown, so the asset has not gone away; it is no longer broken out.

## Peak 1: January 2022, and the eight quarters after

| Quarter end | Qtrs after | Commitments | Years of cost | Revenue | Revenue y/y | Gross margin | Provisions | % of revenue | Releases | Accrual |
|---|---|---|---|---|---|---|---|---|---|---|
| 2022-01-30 | 0 | $9.0bn | 0.95 | $7.6bn | 53% | 65.4% | $116m | 1.5% | $22m | $196m |
| 2022-05-01 | 1 | $9.6bn | 0.93 | $8.3bn | 46% | 65.5% | $90m | 1.1% | $15m | $258m |
| 2022-07-31 | 2 | $9.2bn | 0.78 | $6.7bn | 3% | 43.5% | $1,220m | 18.2% | $23m | $866m |
| 2022-10-30 | 3 | $7.0bn | 0.58 | $5.9bn | -17% | 53.6% | $702m | 11.8% | $21m | $1,181m |
| 2023-01-29 | 4 | $4.9bn | 0.42 | $6.1bn | -21% | 63.3% | $160m | 2.6% | $78m | $954m |
| 2023-04-30 | 5 | $7.3bn | 0.64 | $7.2bn | -13% | 64.6% | $134m | 1.9% | $50m | $786m |
| 2023-07-30 | 6 | $11.2bn | 0.96 | $13.5bn | 101% | 70.1% | $576m | 4.3% | $84m | $870m |
| 2023-10-29 | 7 | $17.1bn | 1.26 | $18.1bn | 206% | 74.0% | $681m | 3.8% | $239m | $1,280m |
| 2024-01-28 | 8 | $16.1bn | 0.97 | $22.1bn | 265% | 76.0% | $810m | 3.7% | $168m | $1,655m |

What happened: revenue peaked one quarter after the ratio did, then fell 28% in two quarters. Provisions in fiscal 2023 were $2.17bn, 8.1% of that year's revenue, against 1.1% over the eight quarters up to and including the peak. The filings split the fiscal 2023 charge into $1.04bn for stock on hand and $1.13bn for purchase obligations above demand, and attribute it to excess supply of the then-current gaming and data center products, particularly expected demand in China. Gross margin fell 22 points in the quarter of the largest charge and was back within two quarters. The accrual for excess purchase obligations went from $196m to $1,181m in three quarters. Commitments were cut from $9.6bn to $4.9bn, then rebuilt above the old level within two more quarters as data center demand turned.

Cross-check: the filings give the net effect of provisions and releases on gross margin as 17.8 points in the July 2022 quarter, 11.5 in the October 2022 quarter and 7.5 for fiscal 2023. The CSV's net charge divided by revenue gives 17.9, 11.5 and 7.5.

## Peak 2: October 2023, and the eight quarters after

| Quarter end | Qtrs after | Commitments | Years of cost | Revenue | Revenue y/y | Gross margin | Provisions | % of revenue | Releases | Accrual |
|---|---|---|---|---|---|---|---|---|---|---|
| 2023-10-29 | 0 | $17.1bn | 1.26 | $18.1bn | 206% | 74.0% | $681m | 3.8% | $239m | $1,280m |
| 2024-01-28 | 1 | $16.1bn | 0.97 | $22.1bn | 265% | 76.0% | $810m | 3.7% | $168m | $1,655m |
| 2024-04-28 | 2 | $18.8bn | 0.95 | $26.0bn | 262% | 78.4% | $393m | 1.5% | $114m | $1,684m |
| 2024-07-28 | 3 | $27.8bn | 1.20 | $30.0bn | 122% | 75.1% | $908m | 3.0% | $85m | $2,051m |
| 2024-10-27 | 4 | $28.9bn | 1.06 | $35.1bn | 94% | 74.6% | $865m | 2.5% | $106m | $1,728m |
| 2025-01-26 | 5 | $30.8bn | 0.94 | $39.3bn | 78% | 73.0% | $1,500m | 3.8% | $384m | $2,095m |
| 2025-04-27 | 6 | $29.8bn | 0.67 | $44.1bn | 69% | 60.5% | $5,300m | 12.0% | $436m | $4,310m |
| 2025-07-27 | 7 | n/d | n/d | $46.7bn | 56% | 72.4% | $1,000m | 2.1% | $501m | $3,154m |
| 2025-10-26 | 8 | $50.3bn | 0.90 | $57.0bn | 62% | 73.4% | $410m | 0.7% | $366m | $2,770m |

What happened: the opposite path. Revenue tripled, so the ratio fell although commitments nearly tripled too. Provisions over the eight quarters were $11.2bn, 3.7% of revenue. One quarter stands out: $5.3bn in April 2025, of which the filing attributes $4.5bn to H20 products after a new export licence requirement. That is a charge on pre-ordered product, but the filing's stated reason is regulation, not a general shortfall in demand. A higher ratio than fiscal 2022 was therefore followed by a very different outcome, which is the main reason not to read the ratio as a forecast.

## Today

- 26 July 2026 (10-Q): supply and capacity $279bn, up from $119bn a quarter earlier. $92bn falls in the rest of fiscal 2027, $87bn in fiscal 2028, $88bn in fiscal 2029, $12bn later.
- 25 October 2026 (8-K): $390bn. $69bn in the remaining quarter, $203bn in fiscal 2028, $92bn in fiscal 2029, $26bn later. The commentary attributes the increase mainly to multi-year memory procurement.
- Inventories were $39.7bn, 0.44 years of trailing cost of revenue (0.28 at the January 2022 peak). Inventories plus commitments were 4.7 years (1.2 then).
- The accrual for excess purchase obligations was $2.1bn at July 2026, 0.8% of commitments (2.2% at January 2022, 7.5% at October 2023). It is not given in the 8-K.
- Provisions in the first half of fiscal 2027 were $2.1bn, 1.2% of revenue; the July 2026 10-Q mentions a $0.4bn charge on H200 products within that.
- Scale against the next year rather than the last: commitments due through fiscal 2028 are $272bn. Trailing cost of revenue is $90.7bn and the latest quarter annualised is $116.7bn, so the amounts due in the next five quarters alone are 2.3 to 3.0 times a year of current cost of revenue.

## Latest quarter: 10-Q not yet filed

The filing list was refreshed on 18 November 2026. The newest 10-Q is for the quarter ended 26 July 2026 (filed 26 August 2026). There is no 10-Q for the quarter ended 25 October 2026. The row for that quarter comes from the Form 8-K furnished on 17 November 2026 (accession 0001045810-26-000088): the commitments table from the CFO commentary (exhibit 99.2), and revenue, cost of revenue, gross profit and inventories from the supplemental statements (exhibit 99.3). It is unaudited and "furnished" rather than "filed". The row is labelled `form = 8-K` with the source spelled out, has no XBRL cross-check, and has no inventory charges or accrual because the 8-K does not give them. The script replaces it automatically once the 10-Q appears in the list. The 8-K says the 10-Q will follow in the coming weeks.

## AMD and Broadcom (context only)

| | Latest | Purchase commitments | Years of cost of revenue | A year earlier |
|---|---|---|---|---|
| AMD | 26 Sep 2026 | $48.8bn | 2.3 | 0.7 |
| Broadcom | 2 Aug 2026 | $126.8bn | 4.6 | 0.01 |

The climb is not NVIDIA's alone, but the levels are not comparable. AMD's figure also covers cloud, software and technology licences. Broadcom's excludes any commitment with a remaining term of one year or less, so its history is near zero and then jumps from $54m to $128bn in one quarter (May 2026). Peer rows come from the SEC's companyfacts file; only seven of 55 were read in the filing and are `verified = yes` (AMD June 2022, December 2025, September 2026; Broadcom November 2025 to August 2026).

## Judgment calls

1. **Trailing-year denominator.** Trailing four quarters = year to date + last full year - same period a year earlier, all from XBRL. Fourth quarters = full year less nine months.
2. **Which number is "the" commitment.** The supply-side figure only. Cloud services, leases, equity investments, capital expenditure and guarantees are in the table file but not in the ratio.
3. **July 2025 gap.** Neither the 10-Q nor that quarter's CFO commentary gives a supply figure, only total purchase commitments of $45.8bn. Left blank, not interpolated.
4. **Fourth-quarter charges are derived** (full year in the 10-K less nine months in the third-quarter 10-Q). From fiscal 2024 the filings round these to $0.1bn, so the derived quarters (January 2024, 2025, 2026) can be out by up to about $0.1bn. `charges_basis` marks them.
5. **What counts as a peak.** A quarter where the ratio set a new high that then stood for at least four quarters. That rule finds January 2022 and October 2023.
6. **Due-date shares** use the combined schedule in the years when no supply-only split exists (see the table note).
7. **Charges before April 2023** are labelled "inventory provisions" in the filings; from April 2023 "provisions for inventory and excess inventory purchase obligations". The earlier label already included purchase-obligation charges (the July 2022 figure is the sum of the two parts) and the restated comparatives are identical, so it is treated as one series.

## Unverified or inconsistent

- **Verified by eye:** all 32 quarters for supply commitments, the first due amount, provisions, releases and the accrual as printed in the liabilities table (which equals the XBRL value in every quarter from January 2022).
- **Not read sentence by sentence:** revenue, cost of revenue, gross profit and inventories (XBRL facts; gross profit equals revenue less cost in every row, and the margins match the percentages the filings state where checked). The `purchase_obligation_charge` and `inventory_writedown` columns are XBRL-only and should be treated as unverified. The long-term prepaid balance is XBRL-only.
- **Peers:** 48 of 55 rows unverified.
- **Fiscal 2019 fourth quarter** has no quarterly charge because the fiscal 2019 third-quarter 10-Q is before the start date. The year's figure ($270m of provisions) is in the year-to-date column.
- **Rounding:** the January 2020 note says $1.16bn; the table in the same filing says $1,156m. The CSV carries the note figure.
- **Table rearrangement** between July and October 2026 (above) makes the "all commitments" totals of those two quarters not comparable.
- **The October 2026 quarter is 8-K data** and may differ from the 10-Q when filed.
- No causal claim is made anywhere. Two peaks, with opposite outcomes, is not a sample.
