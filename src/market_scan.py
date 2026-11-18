"""Exploratory: who else is sitting on large leases that have not started yet?

The main project tracks "leases signed but not yet commenced" for six
companies. This script asks whether those six are most of the story, by
scanning every SEC registrant instead of a hand-picked list.

How it works, in plain English:

1. Ask EDGAR full-text search for every 10-Q and 10-K filed since 1 July 2026
   that contains "not yet commenced" or a close variant of that phrase.
2. Keep the most recent matching filing per company. Rank the companies
   cheaply (filings that also contain the word "billion" first, then by total
   assets) and read at most MAX_DOCS filings, slowly, one at a time.
3. In each filing, find the sentence (or table row) around the phrase, check
   that it is about leases, and pull the dollar amount next to it.
4. Keep companies at $1 billion or more and write them, with the sentence the
   number came from, to data/processed/market_scan.csv.
5. Blind-spot check. Many companies give this disclosure once a year, in the
   10-K, and say nothing in their 10-Qs. Those companies are invisible to
   steps 1-4, so the script also searches the 10-Ks filed January to June
   2026, lists the companies found only there, and reads the ANNUAL_SAMPLE
   largest. They go to a separate file, not the main one: their figures are
   as of the end of 2025, not autumn 2026.

This is a wide net, not a careful read: a general pattern picks the wrong
number in some filings. Rows are marked `verified = yes` only where a person
read the sentence and confirmed the figure (see REVIEWED below). Everything
else is a lead to check, not a finding.

Amounts are total undiscounted future payments over the life of the leases.
They are NOT debt and NOT one year's spending.

Output, all in data/processed/:
  market_scan.csv              lessees at $1bn or more, latest filing since 1 July 2026
  market_scan_annual_only.csv  the same, for companies that only disclose in the 10-K (sample)
  market_scan_removed.csv      rows of $1bn or more taken out on review, with the reason
  market_scan_lessor_side.csv  the landlord's side: leases to tenants that have not started

Run:  .venv/bin/python -W ignore src/market_scan.py
"""
from __future__ import annotations

import html
import re
import time
from urllib.parse import quote

import pandas as pd
import requests

import edgar
from universe import COMPANIES

# Other jobs share the same SEC allowance: stay at two requests a second.
edgar._MIN_INTERVAL = 0.5

OUT = edgar.ROOT / "data" / "processed"
START, END = "2026-07-01", "2026-11-18"
ANNUAL_START, ANNUAL_END = "2026-01-01", "2026-06-30"  # when most 10-Ks for 2025 were filed
THRESHOLD = 1e9
MAX_DOCS = 500  # hard cap on filings read in the main scan
ANNUAL_SAMPLE = 60  # extra 10-Ks read for the blind-spot check
SEARCH = (
    "https://efts.sec.gov/LATEST/search-index?q={q}&forms={forms}"
    "&dateRange=custom&startdt={start}&enddt={end}&from={start_at}"
)
# Phrases searched. The last two catch companies (Oracle among them) that
# describe the same thing without the words "not yet commenced".
QUERIES = [
    '"not yet commenced"',
    '"have not commenced"',
    '"has not yet commenced"',
    '"yet to commence"',
    '"not commenced"',
    '"additional lease commitments"',
    '"leases" "expected to commence"',
]
MAIN_DOC_TYPES = re.compile(r"^(10-[KQ](T|405)?(/A)?|EX-13(\.\d+)?)$")
ASSET_FRAMES = ["CY2026Q2I", "CY2026Q1I"]

PHRASE = re.compile(
    r"not yet commenced|(?:have|has|had) not (?:yet )?commenced|not commenced|(?:have|has|had) yet to commence"
    r"|yet to commence|additional (?:operating |finance )?lease commitments"
    r"|leases?\b[^.;]{0,120}?(?:expected|scheduled) to commence",
    re.I,
)
NUM = r"[\d,]+(?:\.\d+)?"
MONEY = re.compile(r"\$ ?(" + NUM + r") ?(billion|million|thousand)?", re.I)
TABLE_ROW = re.compile(r"[A-Za-z ,()-]{0,40}?((?: \$? ?\(?" + NUM + r"\)?| [—–-]){3,10})")
SENTENCE_END = re.compile(r"(?<=[a-z0-9\)%”\"][.;])\s+(?=[A-Z(“\"$\d])")
# A table running straight into prose with no full stop: "... $ 3,705 As of September 30, 2026, we have ..."
TABLE_TO_PROSE = re.compile(
    r"(?<=[\d\)%—])\s+(?=(?:As of|At|In|We|The|Our|Additionally|Future|During|Leases?|Excludes?|Operating|Total) [A-Za-z])"
    r"|\s+(?=\(\d\) [A-Z][a-z])"
)
BELONGS_TO_PHRASE = re.compile(r"\s*\)?\s*(?:of|in|for|under|related to|relating to|associated with|pertaining to)\b", re.I)
# A sentence after the phrase gives the size of those leases if it points back at them ("these leases",
# "such agreements", "lease payments") and names a payment before the first dollar sign.
FOLLOW_ON = re.compile(r"([^$]{0,260}?)" + MONEY.pattern)
POINTS_BACK = re.compile(
    r"\b(?:these|those|such|the) (?:\w+ )?(?:leases?|agreements?|arrangements?)\b|\blease (?:payments?|obligations|commitments?)",
    re.I,
)
PAYMENT_WORD = re.compile(r"\b(?:payments?|obligations|commitments?|consideration|rent)\b", re.I)
NOT_OURS = re.compile(r"purchase|guarantee|as follows|right-of-use|sublease|\d[\d,.]* +\(?\d", re.I)
FOLLOW_ON_SENTENCES = 3
NOT_MATERIAL = re.compile(r"not (?:material|significant)|immaterial|no (?:material|significant)", re.I)
UNIT = {"billion": 1e9, "million": 1e6, "thousand": 1e3}
LESSOR_WORDS = re.compile(
    r"\bas (?:a |the )?lessor\b|\btenants?\b|\bcustomers?\b|rental (?:revenue|income)|lease (?:revenue|income)"
    r"|base rents?\b|to be received|annualized|\bABR\b|\boccupancy\b|\bleased to\b|leasing activity|backlog"
    r"|square f(?:ee|oo)t|signed leases not commenced",
    re.I,
)
PURPOSES = [
    ("data centers", r"data ?cent(?:er|re)s?"),
    ("aircraft", r"aircraft|engines?\b"),
    ("vessels", r"vessels?|ships?\b|charters?\b"),
    ("stores", r"stores?\b|retail|restaurants?|clubs?\b|studios?\b|theat(?:er|re)s?"),
    ("warehouses and logistics", r"warehouses?|fulfil+ment|distribution|logistics|delivery stations?"),
    ("offices", r"offices?\b|headquarters|campus"),
    ("labs and manufacturing", r"laborator(?:y|ies)|manufacturing|plants?\b|fabs?\b"),
    ("towers and network", r"towers?\b|network|fiber|satellites?"),
    ("power", r"power|energy|solar|turbines?"),
    ("equipment", r"equipment|vehicles?|fleet|rail ?cars?|servers?"),
    ("real estate", r"real estate|buildings?|facilit(?:y|ies)|land\b|hotels?|hospitals?|clinics?"),
]

# Hand review, keyed by accession number so a verdict never carries over to a
# later filing. verdict "yes" = sentence read, figure confirmed as the lessee's
# leases not yet commenced; anything else is the reason the row was removed.
# `amount` / `evidence` / `what_for` replace what the pattern found, and are
# only used where the filing splits the total over two lines or says what the
# leases are for in a neighbouring sentence.
# Reviewed on 18 November 2026: every row of $1bn or more in both lessee files.
YES = {"verdict": "yes"}
REVIEWED: dict[str, dict] = {
    # --- latest filing since 1 July 2026
    "0001193125-26-436133": YES,  # Microsoft
    "0001628280-26-066773": YES,  # Meta
    "0001193125-26-389274": YES,  # Oracle
    "0001018724-26-000040": YES,  # Amazon: "Leases not yet commenced" row of the commitments table, in millions
    "0001652044-26-000084": YES,  # Alphabet
    "0001769628-26-000465": YES,  # CoreWeave
    "0001045810-26-000075": {  # Nvidia: two rows in two commitments tables, both in billions
        "verdict": "yes",
        "amount": 45e9,
        "what_for": "data centers ($25bn for its own engineering and testing, $20bn to be reassigned to third parties)",
        "evidence": "Data center leases not commenced — 1 1 2 1 20 25 [...] Data center leases not commenced for third "
                    "party — — 1 1 1 17 20 [both rows in billions, last figure is the total; added by hand] [...] We "
                    "expect to reassign these data center leases to third parties.",
    },
    "0000002488-26-000191": {  # AMD: own leases plus leases it expects to hand on
        "verdict": "yes",
        "amount": 13.5e9,
        "what_for": "data centers ($13.3bn to be assigned or subleased to partners; $0.2bn for its own operations)",
        "evidence": "We had future payments of $0.2 billion under leases for our operations that have not yet commenced "
                    "[...] Future payments under data center leases not yet commenced that we expect to assign or "
                    "sublease to commercial partners were $13.3 billion [added by hand]",
    },
    "0001628280-26-073494": {"verdict": "yes", "what_for": "data centers"},  # Cerebras
    "0000764622-26-000050": {  # Pinnacle West
        "verdict": "yes",
        "what_for": "power (energy storage agreements; the total includes non-lease payments)",
    },
    "0001108524-26-000190": {"verdict": "no: total lease commitments, including leases already on the balance sheet"},  # Salesforce
    "0001628280-26-069141": {"verdict": "yes", "what_for": "data centers (co-location space)"},  # DigitalOcean
    "0000936340-26-000169": {"verdict": "yes", "what_for": "power (energy storage agreements)"},  # DTE
    "0001086222-26-000100": {"verdict": "yes", "what_for": "data centers (co-location)"},  # Akamai
    "0001099590-26-000029": YES,  # MercadoLibre
    "0001376986-26-000041": {  # TVA: capacity payments under agreements that contain a lease, not lease payments alone
        "verdict": "yes",
        "what_for": "power (battery storage agreements that include a lease component)",
        "evidence": "During 2026, TVA signed three battery energy storage system agreements which are expected to "
                    "commence in or before the summer of 2029. The terms of the agreements are 20 years, and capacity "
                    "payments over the terms of the agreements are expected to total over $ 1.8 billion. All "
                    "agreements include a lease component.",
    },
    "0000909832-26-000093": YES,  # Costco: footnote to the lease maturity table, in millions
    "0001628280-26-070246": {"verdict": "yes", "what_for": "aircraft (primarily)"},  # UPS: stated in the next sentence
    "0000886982-26-000532": YES,  # Goldman Sachs
    "0001048911-26-000131": {"verdict": "yes", "what_for": "build-to-suit facilities"},  # FedEx
    # --- companies that only disclose in the 10-K (figures as of their 2025 year end)
    "0000100517-26-000023": {  # United Airlines: the table has no total column
        "verdict": "yes",
        "amount": 6.6e9,
        "evidence": "(in billions): 2026 2027 2028 2029 2030 After 2030 [...] Leases not yet commenced (c) 0.2 0.3 0.5 "
                    "0.5 0.5 4.6 [no total column; row added by hand] (c) Represents future payments under leases that "
                    "have not yet commenced and are not included in the consolidated balance sheet.",
    },
    "0000034088-26-000045": {  # Exxon Mobil: operating plus finance
        "verdict": "yes",
        "amount": 3.8e9,
        "what_for": "vessels (LNG transportation, primarily)",
    },
    "0000821189-26-000054": {"verdict": "no: took the total of a cash-requirements table; the leases row is $30 million"},  # EOG
    "0000732712-26-000007": YES,  # Verizon
    "0001628280-26-008131": YES,  # JPMorgan
    "0000027419-26-000016": {"verdict": "no: figure also covers purchase, construction and remodeling commitments"},  # Target
    "0001133421-26-000003": YES,  # Northrop Grumman
    "0001163165-26-000009": YES,  # ConocoPhillips
}

# The same for the landlord-side file.
LESSOR_REVIEWED: dict[str, str] = {
    "0001482512-26-000085": "no: a leasing-statistics table (square feet and rent per foot), not a payment total",  # Hudson Pacific
    "0001839341-26-000030": "yes: landlord to CoreWeave",  # Core Scientific
}


# ---------------------------------------------------------------- search


def search_page(query: str, window: tuple[str, str, str], start_at: int) -> dict:
    forms, start, end = window
    url = SEARCH.format(q=quote(query), forms=forms, start=start, end=end, start_at=start_at)
    for attempt in range(4):
        try:
            return edgar.get_json(url)["hits"]
        except requests.HTTPError as err:  # the search service throws the odd 500; wait and ask again
            print(f"  search hiccup ({err.response.status_code}), retrying", flush=True)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"EDGAR search kept failing for {query} from {start_at}")


def search_all(query: str, window: tuple[str, str, str]) -> list[dict]:
    """Every hit for one query (the API serves 100 per page)."""
    hits, start_at = [], 0
    while True:
        page = search_page(query, window, start_at)
        hits.extend(page["hits"])
        start_at += 100
        if not page["hits"] or start_at >= min(page["total"]["value"], 10000):
            return hits


def split_display_name(display: str) -> tuple[str, str]:
    """'AMAZON COM INC  (AMZN)  (CIK 0001018724)' -> ('AMAZON COM INC', 'AMZN')."""
    name = re.sub(r"\s*\(CIK \d+\)\s*$", "", display).strip()
    m = re.search(r"\s*\(([A-Z0-9., -]+)\)$", name)
    if not m:
        return name, ""
    return name[: m.start()].strip(), m.group(1).split(",")[0].strip()


def hit_to_filing(hit: dict) -> dict | None:
    """One search hit as a flat record, or None if it is an exhibit such as a lease contract."""
    src = hit["_source"]
    if not MAIN_DOC_TYPES.match(src.get("file_type") or ""):
        return None
    adsh, _, doc = hit["_id"].partition(":")
    company, ticker = split_display_name(src["display_names"][0])
    cik = int(src["ciks"][0])
    return {
        "cik": cik,
        "company": company,
        "ticker": ticker,
        "form": src["form"],
        "period_end": src.get("period_ending") or "",
        "filed": src["file_date"],
        "adsh": adsh,
        "url": f"{edgar.filing_base(cik, adsh)}/{doc}",
    }


def candidates(
    window: tuple[str, str, str] = ("10-Q,10-K", START, END), billion_only: bool = False
) -> tuple[pd.DataFrame, dict]:
    """Most recent matching filing per company, plus counts for the coverage note.

    `window` is (form types, first filing date, last filing date). Each phrase is searched twice: on its own, and together with the word "billion" (a cheap sign
    that the company is large). `billion_only` skips the first search.
    """
    filings, with_billion, n_hits = {}, set(), 0
    for query in QUERIES:
        for q, flag in ((query, False), (query + " billion", True)):
            if billion_only and not flag:
                continue
            for hit in search_all(q, window):
                n_hits += not flag
                f = hit_to_filing(hit)
                if f is None:
                    continue
                if flag:
                    with_billion.add(f["url"])
                filings[f["url"]] = f
    df = pd.DataFrame(filings.values())
    stats = {"search_hits": n_hits, "filings_matched": len(df)}
    df["says_billion"] = df.url.isin(with_billion)
    df = df.sort_values(["filed", "period_end", "form"]).groupby("cik").tail(1)
    stats["companies_matched"] = len(df)
    return df, stats


def total_assets() -> dict[int, float]:
    """Total assets for every XBRL filer, from two bulk calls. Used only to rank who gets read first."""
    assets: dict[int, float] = {}
    for frame in ASSET_FRAMES:
        try:
            data = edgar.get_json(f"https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/{frame}.json")
        except Exception as err:  # the ranking is a convenience; carry on without it
            print(f"  (no asset data for {frame}: {err})")
            continue
        for row in data["data"]:
            assets.setdefault(int(row["cik"]), float(row["val"]))
    return assets


def rank_and_cap(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Order companies so the likely-large ones are read first; return (to read, left out)."""
    assets = total_assets()
    df = df.assign(assets=df.cik.map(assets).fillna(0.0))
    df = df.sort_values(["says_billion", "assets"], ascending=False).reset_index(drop=True)
    return df.iloc[:MAX_DOCS], df.iloc[MAX_DOCS:]


# ---------------------------------------------------------------- reading one filing


def plain_text(raw: bytes) -> str:
    """Filing HTML as one line of text. A regex strip, because parsing 500 large filings properly is slow."""
    doc = raw.decode("utf-8", "replace")
    doc = re.sub(r"(?is)<(script|style|ix:header)\b.*?</\1>", " ", doc)
    doc = re.sub(r"<[^>]+>", " ", doc)
    doc = html.unescape(doc).replace("\xa0", " ")
    return re.sub(r"\s+", " ", doc)


def table_scale(text: str, pos: int) -> float:
    """What a bare number means at this point in the filing: the nearest '(in millions)' style note above it."""
    notes = re.findall(r"\bin (billions|millions|thousands)\b", text[max(0, pos - 2500): pos], re.I)
    if not notes:
        notes = re.findall(r"\bin (millions|thousands)\b", text[:pos], re.I)[-1:]
    return UNIT[notes[-1].lower().rstrip("s")] if notes else 1.0


def sentence_around(text: str, start: int, end: int, reach: int = 450) -> tuple[int, int]:
    """Start and end positions of the sentence containing text[start:end]."""
    floor = max(0, start - reach)
    cuts = [m.end() for rx in (SENTENCE_END, TABLE_TO_PROSE) for m in rx.finditer(text, floor, start)]
    stop = SENTENCE_END.search(text, end, end + reach)
    return (max(cuts) if cuts else floor), (stop.start() if stop else min(len(text), end + reach))


def to_usd(num: str, unit: str, scale: float) -> float:
    value = float(num.replace(",", ""))
    if unit:
        return value * UNIT[unit.lower()]
    # No unit word: a figure written out in full dollars, or one in the filing's table units.
    return value if value >= 1e6 else value * scale


def amount_in_sentence(sentence: str, at: int, phrase_end: int, scale: float) -> float | None:
    """The dollar amount that belongs to the phrase sitting at sentence[at:phrase_end].

    Two wordings cover most filings:
      "we had $1.5 billion of additional leases which had not commenced"   (amount before)
      "leases that have not yet commenced of $7.5 billion"                (amount after)
    """
    found = [(m.start(), m.end(), to_usd(m.group(1), m.group(2) or "", scale)) for m in MONEY.finditer(sentence)]
    before = [f for f in found if f[1] <= at and at - f[1] < 220]
    after = [f for f in found if f[0] >= phrase_end]
    if before and BELONGS_TO_PHRASE.match(sentence[before[-1][1]: at]):
        return before[-1][2]
    if after:
        pos, _, value = after[0]
        # "of $7.5 billion and $75.1 billion, respectively" for operating and finance leases:
        # two parts of one total. The same wording for two dates is NOT added.
        pair = re.match(MONEY.pattern + r",? and " + MONEY.pattern + r",? respectively", sentence[pos:], re.I)
        lead = sentence[:pos].lower()
        if pair and "operating" in lead and "finance" in lead and len(set(re.findall(r"\b20\d\d\b", sentence))) < 2:
            value += to_usd(pair.group(3), pair.group(4) or "", scale)
        return value
    # Otherwise accept an amount before the phrase only if prose runs on from it ("$94 million of minimum ...").
    # A table total followed by a heading ("$ 48,761 Other Commitments Leases not yet commenced.") is not ours.
    if before and re.match(r"\s*\)?\s*,?\s*[a-z]", sentence[before[-1][1]: at]):
        return before[-1][2]
    return None


def amount_in_next_sentences(text: str, finish: int, scale: float) -> tuple[float, str] | None:
    """Meta-style: '... have not yet commenced. These lease obligations were approximately $355 billion'."""
    for _ in range(FOLLOW_ON_SENTENCES):
        start = finish
        _, finish = sentence_around(text, start + 2, start + 2, reach=450)
        m = FOLLOW_ON.match(text[start:finish].strip())
        lead = m.group(1) if m else ""
        if POINTS_BACK.search(lead) and PAYMENT_WORD.search(lead) and not NOT_OURS.search(lead):
            return to_usd(m.group(2), m.group(3) or "", scale), text[start:finish].strip()
    return None


def amount_in_table_row(text: str, end: int, scale: float) -> tuple[float, str] | None:
    """Amazon-style: a commitments-table row 'Leases not yet commenced 950 2,149 ... 38,407'."""
    m = TABLE_ROW.match(text[end: end + 200])
    if not m:
        return None
    nums = [float(n.replace(",", "")) for n in re.findall(NUM, m.group(1)) if re.search(r"\d", n)]
    if len(nums) < 3:
        return None
    return max(nums) * scale, m.group(0)


def what_for(sentence: str) -> str:
    found = [label for label, rx in PURPOSES if re.search(rx, sentence, re.I)]
    return ", ".join(found[:3]) if found else "not stated"


def read_filing(url: str) -> list[dict]:
    """Every lease-related mention of the phrase in one filing, with the amount beside it."""
    text = plain_text(edgar.get(url))
    out, seen = [], set()
    for m in PHRASE.finditer(text):
        begin, finish = sentence_around(text, m.start(), m.end())
        sentence = text[begin:finish]
        if not re.search(r"leas", sentence, re.I) or NOT_MATERIAL.search(sentence) or sentence in seen:
            continue
        seen.add(sentence)
        scale = table_scale(text, m.start())
        row = amount_in_table_row(text, m.end(), scale)
        if row:
            amount, evidence = row[0], text[max(begin, m.start() - 60): m.end()] + row[1]
        else:
            amount, evidence = amount_in_sentence(sentence, m.start() - begin, m.end() - begin, scale), sentence
            later = amount_in_next_sentences(text, finish, scale) if amount is None else None
            if later:
                amount, evidence = later[0], f"{sentence.strip()} [...] {later[1]}"
        if amount is None:
            continue
        out.append(
            {
                "amount": amount,
                "evidence": evidence.strip()[:1200],
                "side": "lessor" if LESSOR_WORDS.search(evidence) else "lessee",
                "what_for": what_for(evidence),
            }
        )
    return out


def best_mention(mentions: list[dict]) -> dict | None:
    """The lessee-side mention with the largest amount (the total, when parts are also given)."""
    own = [m for m in mentions if m["side"] == "lessee"]
    return max(own, key=lambda m: (m["amount"], -len(m["evidence"]))) if own else None


# ---------------------------------------------------------------- the scan


def scan(to_read: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Read each filing. Returns (lessee rows, lessor-side mentions, counts)."""
    rows, lessor_rows, stats = [], [], {"fetched": 0, "fetch_failed": 0, "with_amount": 0}
    for i, f in enumerate(to_read.to_dict("records")):
        if i % 50 == 0:
            print(f"  reading filing {i + 1} of {len(to_read)}", flush=True)
        try:
            mentions = read_filing(f["url"])
        except Exception as err:
            stats["fetch_failed"] += 1
            print(f"  skipped {f['company']}: {err}")
            continue
        stats["fetched"] += 1
        best = best_mention(mentions)
        if best:
            stats["with_amount"] += 1
            rows.append({**f, **best})
        for m in mentions:
            if m["side"] == "lessor" and m["amount"] >= THRESHOLD:
                lessor_rows.append({**f, **m})
    return pd.DataFrame(rows), pd.DataFrame(lessor_rows), stats


COLUMNS = ["rank", "company", "ticker", "cik", "form", "period_end", "filed", "uncommenced_leases_usd",
           "what_for", "evidence", "url", "verified"]


def apply_review(rows: pd.DataFrame) -> pd.DataFrame:
    """Attach the hand-review verdict to each row, with any correction read from the filing."""
    rows = rows.assign(review="")
    for i, adsh in rows.adsh.items():
        note = REVIEWED.get(adsh, {})
        rows.at[i, "review"] = note.get("verdict", "")
        for field in ("amount", "evidence", "what_for"):
            if field in note:
                rows.at[i, field] = note[field]
    return rows


def finish(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply the hand review and the $1bn floor; return (kept, removed)."""
    if rows.empty:
        return pd.DataFrame(columns=COLUMNS), pd.DataFrame()
    big = apply_review(rows)
    big = big[big.amount >= THRESHOLD]
    removed = big[~big.review.isin(["", "yes"])]
    kept = big[big.review.isin(["", "yes"])].sort_values("amount", ascending=False).reset_index(drop=True)
    kept["rank"] = kept.index + 1
    kept["verified"] = kept.review.map({"yes": "yes"}).fillna("no")
    kept = kept.rename(columns={"amount": "uncommenced_leases_usd"})
    return kept[COLUMNS], removed


def annual_only(found: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Blind-spot check: companies whose 10-K has the phrase but whose filings since July do not.

    Returns (rows read from the ANNUAL_SAMPLE largest, the companies not read, counts).
    """
    earlier, _ = candidates(("10-K", ANNUAL_START, ANNUAL_END), billion_only=True)
    only = earlier[~earlier.cik.isin(found.cik)]
    assets = total_assets()
    only = only.assign(assets=only.cik.map(assets).fillna(0.0)).sort_values("assets", ascending=False)
    rows, _, stats = scan(only.head(ANNUAL_SAMPLE))
    stats["companies"] = len(only)
    return rows, only.iloc[ANNUAL_SAMPLE:], stats


def show(table: pd.DataFrame, n: int = 25) -> None:
    view = table.head(n).assign(usd_bn=(table.uncommenced_leases_usd / 1e9).round(1))
    print(view[["rank", "company", "ticker", "form", "period_end", "usd_bn", "what_for", "verified"]].to_string(index=False))


def billions(table: pd.DataFrame) -> str:
    return f"${table.uncommenced_leases_usd.sum() / 1e9:,.1f}bn"


def main() -> None:
    print("searching EDGAR full text ...", flush=True)
    found, stats = candidates()
    to_read, left_out = rank_and_cap(found)
    rows, lessor_rows, scan_stats = scan(to_read)
    kept, removed = finish(rows)
    print("blind-spot check: companies that only disclose in the 10-K ...", flush=True)
    annual_rows, annual_unread, annual_stats = annual_only(found)
    annual_kept, annual_removed = finish(annual_rows)
    if not lessor_rows.empty:
        lessor_rows["review"] = lessor_rows.adsh.map(LESSOR_REVIEWED).fillna("")

    OUT.mkdir(parents=True, exist_ok=True)
    kept.to_csv(OUT / "market_scan.csv", index=False)
    annual_kept.to_csv(OUT / "market_scan_annual_only.csv", index=False)
    pd.concat([removed, annual_removed]).to_csv(OUT / "market_scan_removed.csv", index=False)
    lessor_rows.to_csv(OUT / "market_scan_lessor_side.csv", index=False)

    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 44)
    show(kept)
    print(f"\nsearch hits {stats['search_hits']}, main-document filings {stats['filings_matched']}, "
          f"companies {stats['companies_matched']}")
    print(f"read {scan_stats['fetched']} (cap {MAX_DOCS}), failed {scan_stats['fetch_failed']}, "
          f"not read because of the cap {len(left_out)} "
          f"(largest by assets: {', '.join(left_out.company.head(5))})")
    print(f"filings with a lease amount beside the phrase: {scan_stats['with_amount']}")
    print(f"at or above $1bn: {len(kept) + len(removed)}, removed on review: {len(removed)}, "
          f"kept: {len(kept)} of which verified: {int((kept.verified == 'yes').sum())}")
    print(f"total kept {billions(kept)}, verified only {billions(kept[kept.verified == 'yes'])}")
    tracked = [c["cik"] for c in COMPANIES]
    six, everyone = kept[kept.cik.isin(tracked)], pd.concat([kept, annual_kept])
    print(f"the {len(six)} tracked companies: {billions(six)} = "
          f"{six.uncommenced_leases_usd.sum() / kept.uncommenced_leases_usd.sum():.1%} of this file, "
          f"{six.uncommenced_leases_usd.sum() / everyone.uncommenced_leases_usd.sum():.1%} with the annual-only sample added")

    print(f"\nBLIND SPOT: {annual_stats['companies']} companies have the phrase in a 10-K filed {ANNUAL_START} to "
          f"{ANNUAL_END} but in nothing filed since. Read the {annual_stats['fetched']} largest by assets; "
          f"{annual_stats['with_amount']} gave a lease amount, {len(annual_kept)} at $1bn or more "
          f"({billions(annual_kept)}, as of their 2025 year end):")
    show(annual_kept)
    print(f"not read: {len(annual_unread)} (largest: {', '.join(annual_unread.company.head(8))})")
    if not lessor_rows.empty:
        print("\nLANDLORD SIDE (leases to tenants not yet commenced, $1bn or more):")
        for r in lessor_rows.to_dict("records"):
            print(f"  {r['company']}: ${r['amount'] / 1e9:,.1f}bn [{r['review'] or 'not reviewed'}] {r['evidence'][:160]}")


if __name__ == "__main__":
    main()
