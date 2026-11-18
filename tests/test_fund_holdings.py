"""fund_holdings: N-PORT parsing, matching holdings to AI names, fund-of-funds look-through, and the committed tables."""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

import fund_holdings as fh

# --------------------------------------------------------------------------- helpers


def holding(name, pct, cusip="", isin="", cat="EC", payoff="Long", collateral=False):
    return dict(name=name, cusip=cusip, isin=isin, value_usd=pct * 10.0, pct=pct, asset_cat=cat, payoff=payoff, country="US",
                cash_collateral=collateral)


def ai_names():
    return pd.DataFrame(
        [
            dict(tier="1", company="NVIDIA", ticker="NVDA", cusip="67066G104", isin="US67066G1040", filing_name="NVIDIA Corp", reason="chips"),
            dict(tier="2", company="Microsoft", ticker="MSFT", cusip="594918104", isin="US5949181045", filing_name="Microsoft Corp", reason="buyer"),
            dict(tier="2", company="Alphabet", ticker="GOOGL", cusip="02079K305", isin="US02079K3059", filing_name="Alphabet Inc", reason="buyer"),
            dict(tier="2", company="Alphabet", ticker="GOOG", cusip="02079K107", isin="US02079K1079", filing_name="Alphabet Inc", reason="buyer"),
            dict(tier="3", company="Broadcom", ticker="AVGO", cusip="11135F101", isin="US11135F1012", filing_name="Broadcom Inc", reason="chips"),
            dict(tier="3", company="SK hynix (Korea shares)", ticker="000660.KS", cusip="", isin="KR7000660001", filing_name="SK hynix Inc", reason="memory"),
        ]
    ).astype(str)


# --------------------------------------------------------------------------- normalising


def test_norm_lowercases_and_collapses_punctuation():
    assert fh._norm("NVIDIA Corp.") == fh._norm("Nvidia  CORP") == "nvidia corp"
    assert fh._norm("Amazon.com, Inc.") == "amazon com inc"


def test_clean_id_blanks_placeholders():
    for junk in (None, "", "  ", "N/A", "na", "000000000"):
        assert fh._clean_id(junk) == ""
    assert fh._clean_id(" us67066g1040 ") == "US67066G1040"


def test_slug():
    assert fh._slug("Meta Platforms") == "pct_meta_platforms"
    assert fh._slug("CoreWeave") == "pct_coreweave"


# --------------------------------------------------------------------------- parse_nport


def nport_xml(holdings: str, net_assets="1000000000.00") -> bytes:
    return f"""<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/nport">
 <formData>
  <genInfo><seriesName>VANGUARD TEST INDEX FUND</seriesName><seriesId>S000000001</seriesId><repPdDate>2026-06-30</repPdDate></genInfo>
  <fundInfo><netAssets>{net_assets}</netAssets></fundInfo>
  <invstOrSecs>{holdings}</invstOrSecs>
 </formData>
</edgarSubmission>""".encode()


STOCK = """<invstOrSec><name>NVIDIA Corp</name><cusip>67066G104</cusip><identifiers><isin value="US67066G1040"/></identifiers>
 <valUSD>75140000.50</valUSD><pctVal>7.514</pctVal><assetCat>EC</assetCat><payoffProfile>Long</payoffProfile><invCountry>US</invCountry>
 <securityLending><isCashCollateral>N</isCashCollateral></securityLending></invstOrSec>"""
COLLATERAL = """<invstOrSec><name>Repo collateral</name><cusip>000000000</cusip><valUSD>4000000</valUSD><pctVal>0.4</pctVal><assetCat>RA</assetCat>
 <payoffProfile>Long</payoffProfile><invCountry>US</invCountry>
 <securityLending><cashCollateralCondition isCashCollateral="Y"/></securityLending></invstOrSec>"""
FLAG_STYLE = """<invstOrSec><name>Money market</name><valUSD>1000</valUSD><pctVal>0.001</pctVal><assetCat>STIV</assetCat>
 <payoffProfile>Long</payoffProfile><invCountry>US</invCountry><securityLending><isCashCollateral>Y</isCashCollateral></securityLending></invstOrSec>"""


def test_parse_nport_header_and_holdings():
    fund = fh.parse_nport(nport_xml(STOCK + COLLATERAL + FLAG_STYLE))
    assert fund["series_id"] == "S000000001" and fund["as_of"] == "2026-06-30" and fund["net_assets"] == 1e9
    assert len(fund["holdings"]) == 3
    nv = fund["holdings"][0]
    assert (nv["name"], nv["cusip"], nv["isin"], nv["pct"], nv["asset_cat"]) == ("NVIDIA Corp", "67066G104", "US67066G1040", 7.514, "EC")
    assert nv["value_usd"] == pytest.approx(75140000.50) and nv["cash_collateral"] is False


def test_parse_nport_reads_both_cash_collateral_styles_and_blanks_placeholder_ids():
    _, coll, flag = fh.parse_nport(nport_xml(STOCK + COLLATERAL + FLAG_STYLE))["holdings"]
    assert coll["cash_collateral"] is True and coll["cusip"] == "" and coll["isin"] == ""
    assert flag["cash_collateral"] is True


def test_parse_nport_missing_numbers_are_zero():
    odd = "<invstOrSec><name>Odd</name><assetCat>EC</assetCat></invstOrSec>"
    h = fh.parse_nport(nport_xml(odd))["holdings"][0]
    assert h["value_usd"] == 0.0 and h["pct"] == 0.0


def test_latest_nport_picks_the_newest_filing(monkeypatch):
    feed = (b"<feed><entry><filing-date>2025-11-27</filing-date><filing-href>https://www.sec.gov/Archives/edgar/data/36405/000011111125000001/0000111111-25-000001-index.htm</filing-href></entry>"
            b"<entry><filing-date>2026-02-26</filing-date><filing-href>https://www.sec.gov/Archives/edgar/data/36405/000022222226000002/0000222222-26-000002-index.htm</filing-href></entry></feed>")
    seen = {}
    monkeypatch.setattr(fh.edgar, "get", lambda url, refresh=False: seen.setdefault("url", url) and feed)
    ref = fh.latest_nport("S000002839")
    assert ref == {"filed": "2026-02-26", "url": "https://www.sec.gov/Archives/edgar/data/36405/000022222226000002/primary_doc.xml"}
    assert "S000002839" in seen["url"]


def test_latest_nport_with_no_filings_raises(monkeypatch):
    monkeypatch.setattr(fh.edgar, "get", lambda url, refresh=False: b"<feed></feed>")
    with pytest.raises(RuntimeError):
        fh.latest_nport("S000000000")


def test_load_fund_refuses_a_filing_for_the_wrong_series(monkeypatch):
    monkeypatch.setattr(fh, "latest_nport", lambda s: {"filed": "2026-01-01", "url": "u"})
    monkeypatch.setattr(fh.edgar, "get", lambda url, refresh=False: nport_xml(STOCK))
    with pytest.raises(RuntimeError):
        fh.load_fund("S000009999")
    fund = fh.load_fund("S000000001")
    assert fund["filed"] == "2026-01-01" and fund["url"] == "u"


# --------------------------------------------------------------------------- the matcher


@pytest.fixture()
def match():
    return fh.build_matcher(ai_names())


def test_cusip_match_comes_first(match):
    hit, method = match(holding("anything", 1, cusip="67066G104", isin="US5949181045"))
    assert (hit.company, method) == ("NVIDIA", "cusip")


def test_isin_when_cusip_is_unknown(match):
    hit, method = match(holding("SK Hynix", 1, cusip="", isin="KR7000660001"))
    assert (hit.company, method) == ("SK hynix (Korea shares)", "isin")


def test_exact_normalised_name_is_the_last_resort(match):
    hit, method = match(holding("NVIDIA CORP.", 1))
    assert (hit.company, method) == ("NVIDIA", "name")


def test_blank_identifiers_do_not_match_blank_table_entries(match):
    # the SK hynix row has an empty cusip in the names table; a holding with no cusip must not hit it
    assert match(holding("Unrelated Co", 1, cusip="", isin="")) is None


def test_near_names_do_not_match(match):
    assert match(holding("NVIDIA Corp Class A", 1)) is None
    assert match(holding("Microsoft Corp 2030 Notes", 1)) is None


def test_non_stock_lines_never_match_even_with_the_right_name(match):
    assert match(holding("NVIDIA Corp", 0.2, cusip="67066G104", cat="DBT")) is None   # a bond
    assert match(holding("NVIDIA Corp", 0.2, cat="DE")) is None                         # a derivative
    assert match(holding("Microsoft Corp", 0.2, cusip="594918104", cat="EP")) is not None  # preferred stock counts


# --------------------------------------------------------------------------- merge and weights


def test_merge_lines_adds_the_same_security_and_keeps_distinct_ones():
    a = holding("Microsoft Corp", 2.0, cusip="594918104")
    b = holding("Microsoft Corp", 3.0, cusip="594918104")
    c = holding("Microsoft Corp", 1.0, cusip="")           # a different key (the name), so not merged
    merged = fh.merge_lines([a, b, c])
    assert len(merged) == 2
    assert merged[0]["pct"] == 5.0 and merged[0]["value_usd"] == 50.0
    assert a["pct"] == 2.0                                  # inputs are not changed


def test_ai_weights_sum_by_tier_and_company(match):
    lines = [holding("NVIDIA Corp", 6.0, cusip="67066G104"), holding("Microsoft Corp", 5.0, cusip="594918104"),
             holding("Alphabet Inc", 2.0, cusip="02079K305"), holding("Alphabet Inc", 1.5, cusip="02079K107"),
             holding("Broadcom Inc", 2.5, cusip="11135F101"), holding("Boring Co", 80.0, cusip="123")]
    by_company, by_tier, name_only = fh.ai_weights(lines, match)
    assert by_tier == {"1": 6.0, "2": 8.5, "3": 2.5}
    assert by_company["Alphabet"] == 3.5                    # both share classes are one company
    assert name_only == []
    assert lines[0]["ai_tier"] == "1" and lines[-1]["ai_tier"] == ""


def test_name_only_matches_are_reported(match):
    _, _, name_only = fh.ai_weights([holding("Broadcom Inc", 1.0)], match)
    assert name_only == ["Broadcom Inc"]


# --------------------------------------------------------------------------- fund of funds


TOTAL_STOCK = dict(series_name="VANGUARD TOTAL STOCK MARKET INDEX FUND", series_id="S000002848", as_of="2026-06-30", net_assets=500e9,
                   filed="2026-08-29", url="u1",
                   holdings=[holding("NVIDIA Corp", 6.0, cusip="67066G104"), holding("Microsoft Corp", 5.0, cusip="594918104"),
                             holding("Rest of market", 89.0, cusip="999")])
TOTAL_INTL = dict(series_name="VANGUARD TOTAL INTERNATIONAL STOCK INDEX FUND", series_id="S000002932", as_of="2026-06-30", net_assets=300e9,
                  filed="2026-08-29", url="u2",
                  holdings=[holding("Broadcom Inc", 1.0, cusip="11135F101"), holding("SK Hynix", 2.0, isin="KR7000660001"),
                            holding("Rest of world", 97.0, cusip="888")])


def target_date_fund():
    return dict(series_name="VANGUARD TARGET RETIREMENT 2060", series_id="S000035453", as_of="2026-06-30", net_assets=1000.0,
                filed="2026-08-29", url="u0",
                holdings=[holding("Vanguard Total Stock Market Index Fund", 54.0, cusip="922908355"),
                          holding("Vanguard Total International Stock Index Fund", 36.0, cusip="921909602"),
                          holding("Vanguard Total Bond Market II Index Fund", 6.0, cusip="92203C105"),
                          holding("Vanguard Total International Bond II Index Fund", 4.0, cusip="92211J308")])


@pytest.fixture()
def expanded():
    cache = {"S000002848": TOTAL_STOCK, "S000002932": TOTAL_INTL}
    used: list = []
    return fh.expand(target_date_fund(), cache, used), used


def test_look_through_weight_is_fund_weight_times_underlying_weight(expanded):
    lines, _ = expanded
    by = {h["name"]: h for h in lines}
    assert by["NVIDIA Corp"]["pct"] == pytest.approx(54 / 100 * 6.0)          # 3.24% of the target-date fund
    assert by["Microsoft Corp"]["pct"] == pytest.approx(54 / 100 * 5.0)
    assert by["Broadcom Inc"]["pct"] == pytest.approx(36 / 100 * 1.0)
    assert by["NVIDIA Corp"]["value_usd"] == pytest.approx(3.24 / 100 * 1000.0)
    assert by["NVIDIA Corp"]["held_via"] == "Vanguard Total Stock Market Index Fund"


def test_look_through_conserves_total_weight(expanded):
    lines, used = expanded
    assert sum(h["pct"] for h in lines) == pytest.approx(54 + 36 + 6 + 4)       # underlying 100% x its share
    assert len(used) == 2


def test_bond_funds_stay_one_line_and_are_labelled_not_opened(expanded):
    lines, _ = expanded
    bonds = [h for h in lines if "Bond" in h["name"]]
    assert len(bonds) == 2 and {h["asset_cat"] for h in bonds} == {"BOND_FUND"}
    assert all(h["held_via"] == "" for h in bonds)


def test_fund_line_category_by_name():
    assert fh._fund_line_category("Vanguard Total Bond Market II Index Fund") == "BOND_FUND"
    assert fh._fund_line_category("Vanguard Inflation-Protected Securities Fund") == "BOND_FUND"
    assert fh._fund_line_category("Vanguard Some Equity Fund") == "OTHER_FUND"


def test_an_ordinary_fund_is_not_expanded_or_relabelled():
    plain = dict(TOTAL_STOCK, holdings=[holding("Some Fund Holdings Inc", 1.0, cusip="1")])
    lines = fh.expand(plain, {}, [])
    assert lines[0]["asset_cat"] == "EC" and lines[0]["pct"] == 1.0


def test_fund_of_funds_ai_exposure_end_to_end(expanded, match):
    lines, used = expanded
    spec = pd.Series(dict(fund_key="target_2060", display_name="Target 2060"))
    row, merged = fh.fund_row(spec, target_date_fund(), lines, used, ai_names(), match, date(2026, 8, 1))
    assert row["pct_nvidia"] == pytest.approx(3.24)
    assert row["pct_tier2"] == pytest.approx(2.70)
    assert row["pct_microsoft"] == pytest.approx(2.70) and row["pct_alphabet"] == 0.0
    assert row["pct_tier3"] == pytest.approx(0.36 + 0.72)                       # Broadcom 1% and SK hynix 2% of the 36% sleeve
    assert row["pct_ai_total"] == pytest.approx(3.24 + 2.70 + 1.08)
    assert row["pct_sum_check"] == pytest.approx(100.0)
    assert row["pct_stocks"] == pytest.approx(90.0)
    assert row["pct_bonds_and_other"] == pytest.approx(10.0)
    assert row["n_holdings"] == 4
    assert merged[0]["pct"] >= merged[-1]["pct"]
    assert "Vanguard Total Stock Market Index Fund 2026-06-30" in row["as_of_underlying"]
    assert row["source_urls"].split() == ["u0", "u1", "u2"]
    assert row["name_only_matches"] == ""


def test_ai_total_is_exactly_the_sum_of_the_three_tiers(expanded, match):
    lines, used = expanded
    row, _ = fh.fund_row(pd.Series(dict(fund_key="x", display_name="x")), target_date_fund(), lines, used, ai_names(), match, date(2026, 8, 1))
    assert row["pct_ai_total"] == pytest.approx(row["pct_nvidia"] + row["pct_tier2"] + row["pct_tier3"])


def test_effective_number_of_holdings_is_inverse_herfindahl():
    fund = dict(series_name="X", as_of="2026-06-30", net_assets=100.0, filed="f", url="u",
                holdings=[holding("A", 50.0, cusip="1"), holding("B", 30.0, cusip="2"), holding("C", 10.0, cusip="3"), holding("D", 10.0, cusip="4")])
    lines = fh.expand(fund, {}, [])
    row, _ = fh.fund_row(pd.Series(dict(fund_key="x", display_name="x")), fund, lines, [], ai_names(), fh.build_matcher(ai_names()), date(2026, 7, 1))
    assert row["effective_number_of_holdings"] == pytest.approx(1 / (0.25 + 0.09 + 0.01 + 0.01))
    assert row["pct_top10"] == 100.0


def test_top_rows_rank_and_cap():
    merged = [dict(holding(f"H{i}", 30 - i, cusip=str(i)), held_via="", ai_tier="", ai_company="", match_method="") for i in range(40)]
    rows = fh.top_rows("k", merged)
    assert len(rows) == fh.TOP_N and rows[0]["rank"] == 1 and rows[-1]["rank"] == fh.TOP_N
    assert rows[0]["pct_net_assets"] == 30


# --------------------------------------------------------------------------- flags


def flag_fund(as_of="2026-06-30"):
    return dict(as_of=as_of)


def test_flags_stale_collateral_derivatives_cash_and_shorts():
    lines = [holding("A", 90.0), holding("Coll", 0.5, cat="RA", collateral=True), holding("Fut", -0.01, cat="DE"),
             holding("MM", 1.0, cat="STIV"), holding("Short", -1.0, payoff="Short")]
    text = fh.flags_for(flag_fund("2026-01-01"), lines, date(2026, 8, 1))
    assert "older than five months (212 days)" in text
    assert "cash collateral 0.50%" in text
    assert "1 derivative lines" in text and "net -0.010%" in text
    assert "cash-like/money-market/repo 1.50%" in text      # the STIV 1.0 and the RA 0.5
    assert "has short positions" in text


def test_flags_empty_for_a_clean_fresh_fund():
    assert fh.flags_for(flag_fund("2026-06-30"), [holding("A", 100.0)], date(2026, 8, 1)) == ""


def test_age_boundary_is_150_days():
    assert fh.flags_for(flag_fund("2026-03-04"), [], date(2026, 8, 1)) == ""        # 150 days
    assert "older than" in fh.flags_for(flag_fund("2026-03-03"), [], date(2026, 8, 1))


# --------------------------------------------------------------------------- committed tables


@pytest.fixture(scope="module")
def exposure(processed):
    return pd.read_csv(processed / "fund_ai_exposure.csv")


@pytest.fixture(scope="module")
def tops(processed):
    return pd.read_csv(processed / "fund_top_holdings.csv")


def test_one_row_per_fund_and_all_funds_present(exposure, root):
    funds = pd.read_csv(root / "inputs" / "funds.csv")
    assert not exposure.fund_key.duplicated().any()
    assert set(exposure.fund_key) == set(funds.fund_key)
    assert not funds.series_id.duplicated().any()


def test_weights_sum_to_roughly_one_hundred(exposure):
    assert exposure.pct_sum_check.between(99.5, 105).all()
    # more than 100.5 only when securities-lending collateral is reinvested inside the fund, and the flags say so
    for r in exposure[exposure.pct_sum_check > 100.5].itertuples():
        assert "collateral" in r.flags, r.fund_key


def test_stocks_plus_other_equal_the_sum_check(exposure):
    assert (exposure.pct_stocks + exposure.pct_bonds_and_other).tolist() == pytest.approx(exposure.pct_sum_check.tolist())


def test_ai_total_equals_the_sum_of_tiers(exposure):
    assert (exposure.pct_nvidia + exposure.pct_tier2 + exposure.pct_tier3).tolist() == pytest.approx(exposure.pct_ai_total.tolist())


def test_tier_two_equals_the_sum_of_the_six_named_customers(exposure):
    cols = [fh._slug(c) for c in fh.TIER2]
    assert exposure[cols].sum(axis=1).tolist() == pytest.approx(exposure.pct_tier2.tolist())


def test_exposure_is_bounded_by_what_the_fund_holds(exposure):
    assert (exposure.pct_ai_total <= exposure.pct_stocks + 1e-9).all()
    assert (exposure[["pct_nvidia", "pct_tier2", "pct_tier3"]] >= 0).all().all()
    assert (exposure.pct_top10 <= exposure.pct_sum_check + 1e-9).all()
    assert (exposure.effective_number_of_holdings >= 1).all()


def test_effective_holdings_do_not_exceed_the_number_of_lines_for_ordinary_funds(exposure):
    ordinary = exposure[~exposure.fund_key.str.startswith("target_")]
    assert (ordinary.effective_number_of_holdings <= ordinary.n_holdings).all()


def test_the_two_target_date_funds_bracket_each_other_sensibly(exposure):
    e = exposure.set_index("fund_key")
    assert 0 < e.loc["target_2030", "pct_nvidia"] < e.loc["target_2060", "pct_nvidia"] < e.loc["total_us", "pct_nvidia"]
    assert e.loc["target_2030", "pct_bonds_and_other"] > e.loc["target_2060", "pct_bonds_and_other"]


def test_dates_are_recent_and_ordered(exposure):
    assert (pd.to_datetime(exposure.filed) >= pd.to_datetime(exposure.as_of)).all()
    assert exposure.source_urls.str.contains("https://www.sec.gov/").all()


def test_top_holdings_are_ranked_and_sorted(tops, exposure):
    assert set(tops.fund_key) == set(exposure.fund_key)
    for key, g in tops.groupby("fund_key"):
        assert g["rank"].tolist() == list(range(1, len(g) + 1)), key
        assert g.pct_net_assets.is_monotonic_decreasing, key
        assert len(g) <= fh.TOP_N
        assert g.pct_net_assets.sum() <= exposure.set_index("fund_key").loc[key, "pct_sum_check"] + 1e-6


def test_top_holdings_ai_tags_agree_with_the_names_file(tops, root):
    names = pd.read_csv(root / "inputs" / "ai_names.csv", dtype=str, keep_default_na=False)
    tagged = tops[tops.ai_tier.notna()]
    assert len(tagged) > 20
    cusip_to_company = dict(zip(names.cusip, names.company))
    cusip_to_tier = dict(zip(names.cusip, names.tier))
    for r in tagged[tagged.match_method == "cusip"].itertuples():
        assert cusip_to_company[r.cusip] == r.ai_company
        assert cusip_to_tier[r.cusip] == str(int(r.ai_tier))
    assert set(tagged.ai_tier.astype(int)) <= {1, 2, 3}


def test_nvidia_line_in_top_holdings_matches_the_fund_total(tops, exposure):
    e = exposure.set_index("fund_key")
    nv = tops[tops.ai_company == "NVIDIA"].groupby("fund_key").pct_net_assets.sum()
    for key, pct in nv.items():
        assert pct == pytest.approx(e.loc[key, "pct_nvidia"], abs=1e-6), key


def test_ai_names_table_is_clean(root):
    names = pd.read_csv(root / "inputs" / "ai_names.csv", dtype=str, keep_default_na=False)
    assert set(names.tier) == {"1", "2", "3"}
    assert not names.cusip[names.cusip != ""].duplicated().any()
    assert not names["isin"][names["isin"] != ""].duplicated().any()
    assert set(names[names.tier == "2"].company) == set(fh.TIER2)
    assert (names.reason.str.len() > 10).all()
