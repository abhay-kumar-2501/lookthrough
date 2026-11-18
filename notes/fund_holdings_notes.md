# Fund holdings: notes (run 18 November 2026)

Code: `src/fund_holdings.py`. Inputs: `inputs/funds.csv`, `inputs/ai_names.csv`. Outputs: `data/processed/fund_ai_exposure.csv`, `data/processed/fund_top_holdings.csv`.

## Sources
Every number comes from the newest public Form NPORT-P for each fund series, read from `primary_doc.xml` in the filing folder on sec.gov. The filing was located with EDGAR's per-series filing feed (`cgi-bin/browse-edgar?CIK=<series id>&type=NPORT-P&output=atom`). Registrant CIK, series ID and class ID come from SEC's `files/company_tickers_mf.json`; each series ID was then checked against the `seriesId` and `seriesName` inside the filing (the script stops if they differ). Exact filing URLs are in the `source_urls` column.

| Fund | Series name in filing | As-of | Filed | Weights sum |
|---|---|---|---|---|
| S&P 500 index fund | Vanguard 500 Index Fund | 2026-06-30 | 2026-08-28 | 100.09% |
| Total US stock market | Vanguard Total Stock Market Index Fund | 2026-06-30 | 2026-08-28 | 100.47% |
| Nasdaq-100 (QQQ) | Invesco QQQ Trust, Series 1 | 2026-06-30 | 2026-08-28 | 100.28% |
| Equal-weight S&P 500 (RSP) | Invesco S&P 500 Equal Weight ETF | 2026-07-31 | 2026-09-29 | 104.69% |
| Total world (VT) | Vanguard Total World Stock Index Fund | 2026-07-31 | 2026-09-28 | 100.24% |
| Technology (VGT) | Vanguard Information Technology Index Fund | 2026-08-31 | 2026-10-29 | 100.16% |
| Semiconductors (SMH) | VanEck Semiconductor ETF | 2026-09-30 | 2026-11-17 | 100.13% |
| Target-date 2060 | Vanguard Target Retirement 2060 Fund | 2026-06-30 | 2026-08-28 | 100.71% |
| Target-date 2030 | Vanguard Target Retirement 2030 Fund | 2026-06-30 | 2026-08-28 | 100.35% |

Target-date look-through used two more filings: Vanguard Total Stock Market Index Fund (as-of 2026-06-30) and Vanguard Total International Stock Index Fund (series S000002932, as-of 2026-07-31). The target-date holdings are therefore a blend of dates, one month apart. The oldest filing used is 141 days old on 18 Nov 2026, under the five-month threshold.

## Method
- Weight = `pctVal` (percent of net assets) as filed. Dollar value = `valUSD`.
- Weights sum slightly above 100% everywhere because of securities-lending cash collateral and cash-like holdings, which the fund reports as assets while net assets are after liabilities. The `pct_sum_check` column shows the sum. RSP is the outlier (104.69%, of which 4.23% is cash collateral held in Invesco private money-market funds).
- `pct_stocks` = lines with asset category EC or EP. `pct_bonds_and_other` = every other line as filed (cash, collateral, bond funds, futures). The two can add to more than 100% for the reason above.
- Target-date funds own about seven lines: four Vanguard funds, a money-market fund and two tiny derivative lines. Each underlying stock fund's weight is multiplied by that fund's own holdings. The Total Bond Market II and Total International Bond II funds (and Short-Term Inflation-Protected in the 2030 fund) are kept as single "BOND_FUND" lines and are not opened. The international stock fund is opened, so TSMC and SK hynix held through it count in tier 3. `n_holdings` for target-date funds is the number of lines the fund itself files.
- `pct_top10` and `effective_number_of_holdings` (1 / sum of squared weights) are computed on all lines, including cash and bond-fund lines, with weights as fractions of net assets. For the 2030 fund the bond funds are single big lines, so these two figures describe fund-level concentration and not stock concentration.
- Alphabet Class A and Class C are separate securities; they are summed into one Alphabet figure. Securities with the same ISIN or CUSIP are merged.

## Matching to AI names
Order: CUSIP, then ISIN, then exact name (case and punctuation ignored, against `filing_name`). Result of this run: every AI-name match among the top-25 rows was by CUSIP (71 rows) or ISIN (6 rows, the Taiwan and Korea local-share lines of TSMC and SK hynix which carry no CUSIP). No holding was matched by name only (`name_only_matches` is empty for all funds). Identifiers in `ai_names.csv` were read from the filings, not typed from memory; the ticker column was typed by hand and is for display only.

## Tier 3 is a judgment call
Tier 3 is my own short list of listed companies whose revenue leans heavily on AI data center hardware. Another analyst would draw it differently. Included, with the reason:
- Broadcom: custom AI chips and AI networking silicon.
- Taiwan Semiconductor Manufacturing (ADR and Taiwan shares): makes most leading AI chips.
- Advanced Micro Devices: data center GPUs.
- Micron Technology: high-bandwidth memory.
- SK hynix (ADR and Korea shares): high-bandwidth memory leader.
- Marvell Technology: custom AI chips, data center networking.
- Arista Networks: AI cluster Ethernet switches.
- Dell Technologies: AI servers.
- Super Micro Computer: servers built around NVIDIA GPUs.
- Vertiv: data center power and cooling.
- Celestica: hyperscale networking and server hardware.
- Credo Technology: connectivity cables and chips for AI servers.
- Astera Labs: connectivity chips inside AI servers.

Deliberately left out: chip equipment makers (ASML, Applied Materials, Lam Research, which sell to the whole chip industry), storage firms (Sandisk, Western Digital, Seagate), Samsung, Intel, Amphenol, Coherent, Lumentum, and power utilities (Vistra, Constellation Energy). Some of these arguably belong. Adding them would raise every tier 3 figure, most for the semiconductor and technology funds. Tier 3 here is not a claim that these companies buy NVIDIA chips or depend on NVIDIA.

Tier 2 is the six customers named in the project (Microsoft, Meta, Amazon, Alphabet, Oracle, CoreWeave). Those companies are also huge non-AI businesses; the percentage counts the whole company, not just the AI part. Likewise NVIDIA's 7.5% in the S&P 500 fund is a share of the fund, not a measure of AI revenue.

## Checks and oddities
- S&P 500 fund top 10 (by weight): NVIDIA 7.51, Apple 6.59, Microsoft 4.30, Amazon 3.62, Alphabet 3.25 (Class C line), Broadcom 2.77, Alphabet 2.59 (Class A line), Micron 2.02, Meta 1.92, Tesla 1.84. These are large US companies. Micron in the top 10 is surprising to me; it matches the 5.64% weight in the Nasdaq-100 fund and the high weight in the chip funds, so it is a feature of the mid-2026 filings and not a parsing error, but I could not check it against an S&P index weight file. Berkshire Hathaway, JPMorgan and Eli Lilly follow just below. Alphabet appears twice because its two share classes are two lines.
- Securities-lending cash collateral is present in all 9 funds (a trace in the S&P 500 fund; 0.2% to 4.2% elsewhere; target-date funds inherit it from their underlying funds). Futures and similar derivative lines exist in most Vanguard funds but net to less than 0.01%. Cash-like holdings (money-market funds, repo) are 0.2% to 4.4%.
- No fund's latest N-PORT is older than five months. The oldest is 141 days (30 June 2026 holdings read on 18 November 2026).
- The equal-weight fund's low AI share (2.7%) reflects equal weighting of 500 companies, not low AI exposure of the companies themselves.
- VOO/VTI share classes: VFIAX and VTSAX are the same series as VOO and VTI, so the percentages apply to them. SPY, IVV and FXAIX are different funds tracking the same index; they were not read, so "essentially the same" is an assumption, not a measurement.

## Limits
- Holdings are a snapshot 1.5 to 4.6 months old; the stock market has moved since, and NVIDIA's weight in particular can change quickly.
- Only the third month of each fiscal quarter is public, so each fund's latest date differs.
- Percentages are of net assets, so they show how many of each dollar sit in the name, not how much that dollar is "AI".
- Bond funds inside target-date funds are not opened, so any corporate-bond exposure to AI companies is not counted.
- Target-date funds change their mix each year toward bonds; the 2060 and 2030 figures are for funds as they stood on 30 June 2026.
- Share classes with different expense ratios hold the same portfolio; fees are ignored.
- This is data for education, not investment advice.
