"""The page builders: payloads carry the keys the templates read, hold no NaN, and agree with the CSVs; the built pages embed clean JSON."""
from __future__ import annotations

import json
import math
import re

import pandas as pd
import pytest

import make_front
import make_nvidia
import make_spenders
import site_shell

DOCS_PAGES = ["index.html", "nvidia.html", "spenders.html"]
ALL_PAGES = DOCS_PAGES + ["method.html"]
TEMPLATES = {"front": "templates/index.html", "nvidia": "templates/nvidia.html"}


# --------------------------------------------------------------------------- helpers


def walk(obj, path="$"):
    """Yield (path, leaf) for every scalar in a JSON-like structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from walk(v, f"{path}[{i}]")
    else:
        yield path, obj


def assert_json_safe(obj):
    """No NaN or infinity anywhere (neither is valid JSON), and the strict encoder accepts it."""
    for path, leaf in walk(obj):
        if isinstance(leaf, float):
            assert math.isfinite(leaf), f"{path} = {leaf}"
    json.dumps(obj, allow_nan=False)


def template_text(root, name):
    """A page's own template plus the shared chart code it calls."""
    return (root / "src" / name).read_text() + (root / "docs" / "assets" / "charts.js").read_text()


def embedded_data(html: str):
    """(parsed object, the raw JSON text) assigned to `const DATA =` in a built page."""
    start = html.index("const DATA = ") + len("const DATA = ")
    obj, end = json.JSONDecoder().raw_decode(html[start:])
    return obj, html[start: start + end]


def assert_template_reads(template: str, keys):
    missing = [k for k in keys if not re.search(r"\b" + re.escape(k) + r"\b", template)]
    assert not missing, f"template never reads {missing}"


# --------------------------------------------------------------------------- front page: funds


@pytest.fixture(scope="module")
def funds():
    return make_front.funds_payload()


FUND_KEYS = {"key", "name", "tickers", "what", "as_of", "nvidia", "customers", "other_ai", "by_customer", "stocks", "n_holdings", "n_companies", "top", "fund_of_funds", "top10", "effective_n"}


def test_funds_payload_shape(funds):
    assert [f["key"] for f in funds] == make_front.ORDER
    for f in funds:
        assert set(f) == FUND_KEYS
        assert set(f["by_customer"]) == set(make_front.TIER2.values())
        assert 10 <= len(f["top"]) <= 25
        for h in f["top"]:
            assert set(h) == {"k", "name", "pct", "tier"}
            assert h["tier"] in (None, 1, 2, 3)
        assert len({h["k"] for h in f["top"]}) == len(f["top"]), "one line per company"


def test_funds_payload_has_no_nan(funds):
    assert_json_safe(funds)


def test_funds_payload_agrees_with_the_exposure_csv(funds, processed):
    e = pd.read_csv(processed / "fund_ai_exposure.csv").set_index("fund_key")
    for f in funds:
        r = e.loc[f["key"]]
        assert f["nvidia"] == pytest.approx(r.pct_nvidia)
        assert f["customers"] == pytest.approx(r.pct_tier2)
        assert f["other_ai"] == pytest.approx(r.pct_tier3)
        assert sum(f["by_customer"].values()) == pytest.approx(f["customers"])
        assert f["n_holdings"] == r.n_holdings


def test_funds_top_holdings_are_the_largest_first_and_tiers_match_the_ai_columns(funds):
    for f in funds:
        pcts = [h["pct"] for h in f["top"]]
        assert pcts == sorted(pcts, reverse=True), f["key"]
        shown_nvidia = sum(h["pct"] for h in f["top"] if h["tier"] == 1)
        assert shown_nvidia <= f["nvidia"] + 1e-9
        shown_tier2 = sum(h["pct"] for h in f["top"] if h["tier"] == 2)
        assert shown_tier2 <= f["customers"] + 1e-9


def test_front_template_reads_every_fund_key(root):
    t = template_text(root, TEMPLATES["front"])
    assert_template_reads(t, ["nvidia", "customers", "other_ai", "tickers", "what", "stocks", "n_companies", "top"])


def test_num_helper_turns_missing_into_none():
    assert make_front._num(None) is None
    assert make_front._num(float("nan")) is None
    assert make_front._num(3) == 3.0
    assert make_front._num(0) == 0.0


def test_ai_names_payload_lists_only_tier_three_distinct_companies():
    names = make_front.ai_names()
    assert names and all(set(n) == {"company", "reason"} for n in names)
    assert not any(n["reason"].startswith("Same company") for n in names)
    assert not any("(" in n["company"] for n in names)
    assert_json_safe(names)


def test_top_holdings_leave_out_cash_held_as_collateral(funds, processed):
    top = pd.read_csv(processed / "fund_top_holdings.csv")
    collateral = set(top[top.asset_category.isin(make_front.NOT_A_HOLDING)].name)
    assert collateral, "the fixture should contain at least one collateral line, or this test proves nothing"
    for f in funds:
        assert not collateral & {h["name"] for h in f["top"]}, f["key"]


def test_ticker_list_is_clean_and_points_at_funds_on_the_page(root, funds):
    t = pd.read_csv(root / "inputs" / "fund_tickers.csv", keep_default_na=False)
    assert t.ticker.is_unique and (t.ticker == t.ticker.str.upper()).all() and t.ticker.str.fullmatch(r"[A-Z]{2,6}").all()
    assert set(t.fund_key) == {f["key"] for f in funds}, "every fund type should be reachable by at least one ticker"
    assert set(t.match) <= {"same_fund", "same_index", "similar"}
    assert (t.fund_name.str.len() > 5).all()
    # a rough match must say how it differs; an exact one needs no note
    assert (t[t.match == "similar"].note.str.len() > 20).all()
    assert (t[t.match != "similar"].note == "").all()
    assert not t.note.str.contains(",").any(), "notes are written without commas so the file stays a plain CSV"


def test_each_fund_types_own_tickers_are_marked_as_the_same_fund(root):
    t = pd.read_csv(root / "inputs" / "fund_tickers.csv", keep_default_na=False).set_index("ticker")
    info = pd.read_csv(root / "inputs" / "funds.csv")
    for r in info.itertuples():
        for ticker in str(r.example_tickers).split(" / "):
            assert ticker in t.index, f"{ticker} is shown in the menu but cannot be typed"
            assert t.loc[ticker, "fund_key"] == r.fund_key and t.loc[ticker, "match"] == "same_fund", ticker


def test_target_date_tickers_say_which_way_the_guide_is_off(root, processed):
    t = pd.read_csv(root / "inputs" / "fund_tickers.csv", keep_default_na=False)
    stocks = pd.read_csv(processed / "fund_ai_exposure.csv").set_index("fund_key").pct_stocks
    assert stocks["target_2060"] > stocks["target_2030"]          # the notes below rely on this
    rough = t[t.fund_key.isin(["target_2030", "target_2060"]) & (t.match == "similar")]
    assert len(rough) >= 6 and rough.note.str.contains("stocks|bonds").all()
    years = rough.fund_name.str.extract(r"(20\d\d)")[0].astype(int)
    for year, note in zip(years, rough.note):
        if year < 2030:
            assert "lower" in note
        if year in (2035, 2040):
            assert "higher" in note


def test_ticker_payload_matches_the_input_file(root):
    built = make_front.fund_tickers()
    t = pd.read_csv(root / "inputs" / "fund_tickers.csv", keep_default_na=False)
    assert [b["t"] for b in built] == list(t.ticker) and all(set(b) == {"t", "key", "match", "name", "note"} for b in built)
    assert_json_safe(built)
    obj, _ = embedded_data((root / "docs" / "index.html").read_text())
    assert obj["tickers"] == built


def test_funds_of_funds_are_flagged(funds):
    flagged = {f["key"] for f in funds if f["fund_of_funds"]}
    assert {"target_2060", "target_2030"} <= flagged and "sp500" not in flagged


@pytest.fixture(scope="module")
def argument():
    return make_front.build_payload()["argument"]


def test_argument_is_json_safe_and_quotes_the_evidence_pages_unchanged(argument):
    assert_json_safe(argument)
    site, nvda = make_spenders.build_payload(), make_nvidia.build_payload()
    assert argument["leases"]["latest"] == site["leases"]["latest"]
    assert argument["pv"] == site["pv"]
    assert argument["leverage"] == site["leverage"]
    assert argument["sources_uses"] == site["sources_uses"]
    assert argument["funding"]["rows"] == site["funding"]["rows"]
    # the front page links to the companion note and quotes only its headline
    assert argument["nvidia"] == {"narrow": nvda["summary"]["narrow"], "filed": nvda["summary"]["filed"]}


def test_holding_key_treats_spellings_and_share_classes_as_one_company():
    key = make_front.holding_key
    assert key("NVIDIA Corp") == key("NVIDIA Corp.") == key("NVIDIA CORP")
    assert key("Alphabet Inc Class A") == key("Alphabet Inc. Class C") == key("Alphabet Inc")
    assert key("Amazon.com Inc") == key("Amazon.com, Inc.")
    assert key("Micron Technology, Inc.") == key("Micron Technology Inc")
    assert key("Meta Platforms Inc") != key("Microsoft Corp")
    assert key("Berkshire Hathaway Inc Class B") == "berkshire hathaway"


def test_share_classes_are_added_into_one_holding(funds, processed):
    """Alphabet's class A and class C shares are one company, in the saved table and on the page."""
    top = pd.read_csv(processed / "fund_top_holdings.csv")
    sp = top[(top.fund_key == "sp500") & top.name.str.contains("Alphabet")]
    assert len(sp) == 1, "the S&P 500 fund's two Alphabet share classes should be one line"
    exposure = pd.read_csv(processed / "fund_ai_exposure.csv").set_index("fund_key")
    assert sp.pct_net_assets.iloc[0] == pytest.approx(exposure.loc["sp500", "pct_alphabet"])
    built = [h for h in next(f for f in funds if f["key"] == "sp500")["top"] if h["k"] == "alphabet"]
    assert len(built) == 1 and built[0]["pct"] == pytest.approx(sp.pct_net_assets.sum())
    assert built[0]["tier"] == 2


def test_argument_dateline_is_the_newest_filing_any_figure_rests_on(argument, processed):
    newest_spender = make_spenders.build_payload()["latest_filing"]
    newest_nvidia = str(pd.read_csv(processed / "nvidia_supply.csv").filed.dropna().max())
    assert argument["latest_filing"] == max(newest_spender, newest_nvidia)


def test_front_template_reads_every_part_of_the_argument(root):
    t = template_text(root, TEMPLATES["front"])
    assert_template_reads(t, ["sources_uses", "leverage", "pro_forma", "backlog", "shares", "by_customer", "year_ago", "leased", "prepaid", "notes", "rate_source", "signed_at_book_rate"])


# --------------------------------------------------------------------------- NVIDIA page: supply


@pytest.fixture(scope="module")
def supply():
    return make_nvidia.supply_payload()


def test_supply_payload_shape_and_no_nan(supply):
    assert set(supply) == {"series", "table", "peers", "latest_filed"}
    assert_json_safe(supply)
    for p in supply["series"]:
        assert set(p) == {"period_end", "form", "commitments", "years", "gross_margin", "provisions_share", "growth", "source", "near_years", "years_run_rate", "near_years_run_rate"}
        assert isinstance(p["source"], str)
    assert set(supply["table"]) == {"as_of", "buckets", "rows"}
    for r in supply["table"]["rows"]:
        assert set(r) == {"row", "buckets", "url"} and r["url"].startswith("https://www.sec.gov/")


def test_supply_series_is_sorted_and_matches_the_csv(supply, processed):
    s = pd.read_csv(processed / "nvidia_supply.csv").sort_values("period_end")
    assert [p["period_end"] for p in supply["series"]] == list(s.period_end)
    for p, r in zip(supply["series"], s.itertuples()):
        if pd.isna(r.commitments_years_of_cost_of_revenue):
            assert p["years"] is None
        else:
            assert p["years"] == pytest.approx(r.commitments_years_of_cost_of_revenue)
            assert p["commitments"] / r.cost_of_revenue_ttm == pytest.approx(p["years"])


def test_near_years_for_the_latest_quarter_is_rest_of_year_plus_prorated_next_year_over_cost(supply, processed):
    s = pd.read_csv(processed / "nvidia_supply.csv").sort_values("period_end")
    r = s.iloc[-1]
    assert pd.notna(r.due_rest_of_fiscal_year) and pd.notna(r.due_next_fiscal_year) and pd.isna(r.share_due_next_12_months)
    end = pd.Timestamp(r.period_end)
    fy_end = pd.Timestamp(year=end.year + (1 if end.month > 1 else 0), month=1, day=31)       # NVIDIA's fiscal year ends in late January
    months_left = round((fy_end - end).days / 30.44)
    assert months_left == 3                                    # the October quarter has Nov, Dec, Jan left in the year
    expected = (r.due_rest_of_fiscal_year + r.due_next_fiscal_year * (12 - months_left) / 12) / r.cost_of_revenue_ttm
    assert supply["series"][-1]["period_end"] == r.period_end
    assert supply["series"][-1]["near_years"] == pytest.approx(expected)
    assert supply["series"][-1]["near_years"] < supply["series"][-1]["years"]


def test_near_years_uses_the_disclosed_twelve_month_share_when_given(supply, processed):
    s = pd.read_csv(processed / "nvidia_supply.csv").sort_values("period_end")
    checked = 0
    for p, r in zip(supply["series"], s.itertuples()):
        if pd.notna(r.share_due_next_12_months) and pd.notna(r.commitments_years_of_cost_of_revenue):
            assert p["near_years"] == pytest.approx(r.share_due_next_12_months * r.commitments_years_of_cost_of_revenue)
            checked += 1
    assert checked > 0


def test_near_years_never_exceeds_total_years(supply):
    for p in supply["series"]:
        if p["near_years"] is not None and p["years"] is not None:
            assert 0 <= p["near_years"] <= p["years"] + 1e-9, p["period_end"]


def test_supply_table_is_the_latest_commitments_table(supply, processed):
    t = pd.read_csv(processed / "nvidia_commitments_table.csv")
    latest = t[(t.period_end == t.period_end.max()) & (t.table == "commitments")]
    assert supply["table"]["as_of"] == t.period_end.max()
    assert [r["row"] for r in supply["table"]["rows"]] == list(dict.fromkeys(latest.row))
    total = next(r for r in supply["table"]["rows"] if r["row"] == "Total")
    parts = [r for r in supply["table"]["rows"] if r["row"] != "Total"]
    for b in supply["table"]["buckets"]:
        assert sum(r["buckets"][b] for r in parts) == pytest.approx(total["buckets"][b], abs=1.5e9), b   # rounded to $ billions


def test_nvidia_template_reads_the_supply_keys(root):
    t = template_text(root, TEMPLATES["nvidia"])
    assert_template_reads(t, ["years_run_rate", "near_years_run_rate", "commitments", "gross_margin", "provisions_share", "growth", "period_end", "buckets", "rows", "peers"])


# --------------------------------------------------------------------------- NVIDIA page: financing


@pytest.fixture(scope="module")
def financing():
    return make_nvidia.financing_payload()


FIN_KEYS = {"revenue_quarter", "revenue_annualized", "capacity_carried", "period_end", "form", "revenue_ttm", "guarantees_other", "guarantee_2029", "unfunded_equity", "equity_stakes", "capacity", "narrow",
            "broad", "dso", "receivables", "top_share", "top_count", "stretch"}


def test_financing_payload_shape_and_no_nan(financing):
    assert set(financing) == {"series", "latest_items", "as_of", "payment_terms"}
    assert_json_safe(financing)
    assert all(set(p) == FIN_KEYS for p in financing["series"])
    assert all(set(i) == {"item", "amount", "evidence", "url"} and i["amount"] > 0 for i in financing["latest_items"])


def test_financing_components_add_to_narrow_and_broad(financing, processed):
    f = pd.read_csv(processed / "nvidia_financing_summary.csv").sort_values("period_end")
    for p, r in zip(financing["series"], f.itertuples()):
        z = lambda x: 0.0 if pd.isna(x) else x          # noqa: E731
        assert p["narrow"] == pytest.approx(r.narrow_support)
        assert p["broad"] == pytest.approx(r.broad_support)
        assert p["guarantees_other"] + p["guarantee_2029"] == pytest.approx(z(r.guarantees_max_exposure))
        assert p["guarantees_other"] >= -1e-6
        # the chart stacks these four layers; they must rebuild NARROW + the BROAD extras without gaps or double counting
        stack = p["guarantees_other"] + p["guarantee_2029"] + p["unfunded_equity"] + z(r.loans_to_customers)
        assert stack == pytest.approx(p["narrow"])
        assert p["narrow"] + p["equity_stakes"] + p["capacity"] == pytest.approx(p["broad"])       # capacity and broad are never altered
        assert isinstance(p["capacity_carried"], float) and p["capacity_carried"] >= 0
        assert p["revenue_quarter"] == pytest.approx(r.revenue_quarter)
        assert p["narrow"] <= p["broad"] + 1e-6


def test_financing_series_dso_and_revenue_match_the_csv(financing, processed):
    f = pd.read_csv(processed / "nvidia_financing_summary.csv").sort_values("period_end")
    assert [p["dso"] for p in financing["series"]] == pytest.approx(f.days_sales_outstanding.tolist())
    assert [p["revenue_ttm"] for p in financing["series"]] == pytest.approx(f.revenue_ttm.tolist())


def test_revenue_annualized_is_four_times_the_quarter(financing):
    for p in financing["series"]:
        assert p["revenue_annualized"] == pytest.approx(4 * p["revenue_quarter"])


def test_capacity_carried_only_fills_a_gap_and_leaves_capacity_untouched(financing, processed):
    f = pd.read_csv(processed / "nvidia_financing_summary.csv").sort_values("period_end")
    z = lambda x: 0.0 if pd.isna(x) else x          # noqa: E731
    raw = [z(r.capacity_buyback_commitments) + z(r.leases_not_commenced_for_third_parties) for r in f.itertuples()]
    s = financing["series"]
    assert [p["capacity"] for p in s] == pytest.approx(raw)
    for i, p in enumerate(s):
        if p["capacity_carried"]:
            assert p["capacity"] == 0 and p["capacity_carried"] == s[i - 1]["capacity"] > 0
        else:
            assert p["capacity_carried"] == 0.0


def test_financing_latest_items_are_from_the_latest_period_and_ordered(financing):
    keep = ["guarantees_sb_energy_cap", "guarantees_power_and_systems", "guarantees_land_power_shell", "equity_investment_commitments",
            "nonmarketable_equity_securities", "public_equity_securities", "ai_cloud_agreements", "cloud_service_agreements", "accounts_receivable"]
    order = [keep.index(i["item"]) for i in financing["latest_items"]]
    assert order == sorted(order)
    assert all(len(i["evidence"]) <= 380 and i["url"].startswith("https://www.sec.gov/") for i in financing["latest_items"])
    assert financing["as_of"] == financing["series"][-1]["period_end"]


def test_nvidia_template_reads_the_financing_keys(root):
    t = template_text(root, TEMPLATES["nvidia"])
    assert_template_reads(t, ["guarantee_2029", "narrow", "dso", "revenue_annualized", "capacity_carried", "latest_items", "evidence"])


# --------------------------------------------------------------------------- NVIDIA page: history


@pytest.fixture(scope="module")
def history():
    return make_nvidia.history_payload()


HISTORY_KEYS = {"company", "peak_date", "peak_available", "peak_ratio", "peak_drawn", "peak_drawn_ratio", "commitments_complete", "charges_share", "narrow_charges_share",
                "peak_dso", "url", "annual", "peak_in_force_ratio", "peak_in_force_date", "peak_reserve_share", "path",
                "high_promised", "high_promised_date", "high_promised_complete", "peak_in_force_usd",
                "high_promised_trailing", "peak_in_force_trailing", "first_promise_date"}


def test_history_payload_shape_and_no_nan(history):
    assert set(history) == {"companies"} and history["companies"]
    assert_json_safe(history)
    for c in history["companies"]:
        assert set(c) == HISTORY_KEYS
        assert isinstance(c["commitments_complete"], bool) and isinstance(c["url"], str)
        for a in c["annual"]:
            assert set(a) == {"year", "available", "drawn", "dso"} and isinstance(a["year"], int)


def test_history_includes_exactly_the_companies_with_a_disclosed_total(history, processed):
    v = pd.read_csv(processed / "vendor_finance_history.csv")
    disclosed = set(v[v.financing_made_available.notna()].company)
    assert {c["company"] for c in history["companies"]} == disclosed
    assert all(c["peak_date"] and c["peak_available"] and c["peak_ratio"] is not None for c in history["companies"])


def test_history_is_sorted_by_peak_ratio_and_peak_is_in_dollars(history, processed):
    ratios = [c["peak_ratio"] for c in history["companies"]]
    assert ratios == sorted(ratios, reverse=True)
    v = pd.read_csv(processed / "vendor_finance_history.csv")
    for c in history["companies"]:
        g = v[v.company == c["company"]]
        peak = g.loc[g.financing_made_available.idxmax()]
        assert c["peak_date"] == peak.fiscal_period_end
        assert c["peak_available"] == pytest.approx(peak.financing_made_available * 1e6)         # the CSV is in $ millions
        assert c["peak_ratio"] == pytest.approx(peak.available_to_revenue)
        assert c["peak_ratio"] == pytest.approx(peak.financing_made_available / peak.revenue_annualized, abs=1e-4)
        assert c["peak_dso"] == pytest.approx(g.dso_days.max())
        assert c["peak_drawn"] == pytest.approx((0 if pd.isna(peak.drawn_plus_guarantees) else peak.drawn_plus_guarantees) * 1e6)
        assert c["peak_drawn_ratio"] == (None if pd.isna(peak.drawn_plus_guarantees_to_revenue) else pytest.approx(peak.drawn_plus_guarantees_to_revenue))
        assert c["commitments_complete"] == ("guarantee" in str(peak.made_available_basis))
        assert c["charges_share"] == (None if g.charges_share_of_peak.notna().sum() == 0 else pytest.approx(g.charges_share_of_peak.max()))
        assert c["narrow_charges_share"] == (None if g.narrow_charges_share_of_peak.notna().sum() == 0 else pytest.approx(g.narrow_charges_share_of_peak.max()))


def test_history_urls_come_from_the_inputs_file(history, root):
    src = pd.read_csv(root / "inputs" / "vendor_finance_2000.csv")
    for c in history["companies"]:
        if c["url"]:
            assert ((src.company == c["company"]) & (src.fiscal_period_end == c["peak_date"]) & (src.url == c["url"])).any()


def test_history_annual_rows_are_annual_and_in_year_order(history):
    for c in history["companies"]:
        years = [a["year"] for a in c["annual"]]
        assert years == sorted(years) and len(years) == len(set(years))


def test_nvidia_template_reads_the_history_keys(root):
    t = template_text(root, TEMPLATES["nvidia"])
    assert_template_reads(t, ["peak_date", "peak_drawn", "peak_drawn_ratio", "high_promised", "high_promised_date", "high_promised_complete", "peak_in_force_ratio", "peak_in_force_usd", "charges_share", "path", "url", "company"])


def test_company_with_no_financing_total_is_left_out(monkeypatch, tmp_path, processed):
    v = pd.read_csv(processed / "vendor_finance_history.csv")
    assert "Motorola" in set(v.company)
    v.loc[v.company == "Motorola", "financing_made_available"] = float("nan")
    v.to_csv(tmp_path / "vendor_finance_history.csv", index=False)
    monkeypatch.setattr(make_nvidia, "OUT", tmp_path)
    out = make_nvidia.history_payload()
    assert "Motorola" not in {c["company"] for c in out["companies"]}
    assert out["companies"]
    assert_json_safe(out)


# --------------------------------------------------------------------------- NVIDIA page: summary and the other payloads


def test_founder_exit_files_are_gone(root):
    assert not (root / "data" / "processed" / "founder_exit_returns.csv").exists()
    assert not (root / "inputs" / "founder_exits.csv").exists()


def test_removed_words_appear_nowhere_in_pages_sources_or_inputs(root):
    files = [*(root / "docs").glob("*.html"), *(root / "src" / "templates").glob("*.html"), *(root / "src").glob("*.py"), *(root / "inputs").glob("*.csv"), root / "README.md"]
    assert files
    for f in files:
        text = f.read_text(errors="ignore").lower()
        for word in ("misconduct", "founder"):
            assert word not in text, f"{word!r} in {f.relative_to(root)}"


def test_customers_payload_is_json_safe_and_per_company():
    c = make_nvidia.customers_payload()
    assert_json_safe(c)
    assert set(c) == {"years_low", "years_high", "capex_share_group", "over_100", "n"}
    assert 0 < c["years_low"] <= c["years_high"] and c["capex_share_group"] > 0 and c["n"] > 0
    assert all(isinstance(n, str) for n in c["over_100"]) and len(c["over_100"]) <= c["n"]
    site = make_spenders.build_payload()
    per_company = [r["years"] for r in site["funding"]["rows"] if r["years"] is not None]
    assert c["years_low"] == min(per_company) and c["years_high"] == max(per_company)    # single companies, never a sum
    assert c["n"] == len(site["funding"]["rows"])


def test_summary_headline_numbers_trace_back_to_the_csvs(supply, financing, processed):
    s = make_nvidia.summary(supply, financing)
    assert_json_safe(s)
    sup = pd.read_csv(processed / "nvidia_supply.csv").sort_values("period_end")
    last = sup[sup.commitments_years_of_cost_of_revenue.notna()].iloc[-1]
    assert s["as_of"] == last.period_end
    assert s["supply_years"] == pytest.approx(last.supply_commitments / last.cost_of_revenue_ttm)
    assert s["supply_commitments"] == last.supply_commitments
    pre = sup[sup.period_end < "2023-01-01"]
    assert s["supply_years_2022_peak"] == pytest.approx((pre.supply_commitments / pre.cost_of_revenue_ttm).max())
    fin = pd.read_csv(processed / "nvidia_financing_summary.csv").sort_values("period_end").iloc[-1]
    assert s["narrow"] == pytest.approx(fin.narrow_support)
    assert s["broad"] == pytest.approx(fin.broad_support)
    annualized = 4 * fin.revenue_quarter
    assert s["broad_share"] == pytest.approx(fin.broad_support / annualized)
    assert s["narrow_share"] == pytest.approx(fin.narrow_support / annualized)
    sb = 0 if pd.isna(fin.guarantees_sb_energy_cap) else fin.guarantees_sb_energy_cap
    assert s["guarantees_in_effect"] == pytest.approx(fin.guarantees_max_exposure - sb)
    assert s["in_effect_share"] == pytest.approx((fin.guarantees_max_exposure - sb) / annualized)
    assert s["supply_near_years"] == pytest.approx(supply["series"][-1]["near_years"])
    assert s["supply_near_years_2022_peak"] is None or s["supply_near_years_2022_peak"] <= s["supply_years_2022_peak"] + 1e-9
    assert s["narrow_ex_2029"] == pytest.approx(fin.narrow_support - (0 if pd.isna(fin.guarantees_sb_energy_cap) else fin.guarantees_sb_energy_cap))
    assert s["dso"] == pytest.approx(fin.days_sales_outstanding)


def test_summary_run_rate_figures_come_from_the_latest_quarter(supply, financing, processed):
    s = make_nvidia.summary(supply, financing)
    sup = pd.read_csv(processed / "nvidia_supply.csv").sort_values("period_end")
    last = sup[sup.commitments_years_of_cost_of_revenue.notna()].iloc[-1]
    assert s["supply_years_run_rate"] == pytest.approx(last.commitments_years_of_latest_quarter_cost)
    assert s["supply_near_years_run_rate"] <= s["supply_years_run_rate"] + 1e-9
    # the part due within a year keeps the same share of the total on either basis
    assert s["supply_near_years_run_rate"] / s["supply_years_run_rate"] == pytest.approx(s["supply_near_years"] / s["supply_years"])
    fin = pd.read_csv(processed / "nvidia_financing_summary.csv").sort_values("period_end")
    assert s["dso_two_quarters_ago"] == pytest.approx(fin.days_sales_outstanding.iloc[-3])
    assert s["receivables_stretch"] == pytest.approx(fin.receivables_stretch.iloc[-1])
    assert 0 < s["receivables_stretch"] < s["receivables"]
    year_ago = fin[fin.period_end <= str((pd.Timestamp(fin.period_end.iloc[-1]) - pd.DateOffset(months=11)).date())].iloc[-1]
    assert s["dso_year_ago"] == pytest.approx(year_ago.days_sales_outstanding)
    assert s["filed"] == str(pd.read_csv(processed / "nvidia_supply.csv").filed.dropna().max())


def test_cisco_path_uses_year_ends_only(history, processed):
    v = pd.read_csv(processed / "vendor_finance_history.csv")
    annual = set(v[(v.company == "Cisco Systems") & (v.period_type == "annual")].fiscal_period_end)
    cisco = next(c for c in history["companies"] if c["company"].startswith("Cisco"))
    assert cisco["path"] and {p["date"] for p in cisco["path"]} <= annual
    lucent = next(c for c in history["companies"] if c["company"].startswith("Lucent"))
    assert len(lucent["path"]) == int((v.company == "Lucent Technologies").sum())


def test_in_force_high_is_never_below_the_level_at_the_promise_peak(history):
    for c in history["companies"]:
        assert c["peak_in_force_ratio"] >= c["peak_drawn_ratio"] - 1e-9, c["company"]
        assert c["peak_reserve_share"] is None or 0 < c["peak_reserve_share"] <= 1


def test_highest_promised_share_is_the_series_maximum_not_the_share_at_the_dollar_peak(history, processed):
    v = pd.read_csv(processed / "vendor_finance_history.csv")
    for c in history["companies"]:
        g = v[v.company == c["company"]]
        assert c["high_promised"] == pytest.approx(g.available_to_revenue.max())
        assert c["high_promised"] >= c["peak_ratio"] - 1e-9
        assert c["high_promised_date"] in set(g.fiscal_period_end)
        assert c["peak_in_force_usd"] == pytest.approx(g.loc[g.drawn_plus_guarantees_to_revenue.idxmax()].drawn_plus_guarantees * 1e6)
    # the page says NVIDIA's promises sit inside the telecom range, not above it
    lucent = next(c for c in history["companies"] if c["company"].startswith("Lucent"))
    assert lucent["high_promised"] > 0.30


def test_path_carries_dollars_so_a_falling_denominator_can_be_told_from_rising_lending(history):
    for c in history["companies"]:
        assert all("in_force_usd" in p for p in c["path"])
    nortel = next(c for c in history["companies"] if c["company"].startswith("Nortel"))
    assert nortel["peak_in_force_usd"] < nortel["peak_drawn"] and nortel["peak_in_force_ratio"] > nortel["peak_drawn_ratio"]


def fake_fin(periods, narrow):
    return {"series": [{"period_end": p, "narrow": n, "guarantee_2029": 0.0, "guarantees_other": n, "broad": 2 * n, "revenue_ttm": 1e11, "unfunded_equity": 0.0,
                        "revenue_quarter": 3e10, "revenue_annualized": 1.2e11, "dso": 50.0, "receivables": 2e10, "stretch": 1e9, "equity_stakes": 5e9, "top_share": 30.0, "top_count": 2.0}
                       for p, n in zip(periods, narrow)]}


def fake_supply():
    return {"series": [{"period_end": "2022-07-31", "years": 1.5, "near_years": 1.0, "commitments": 9e9, "years_run_rate": 1.2, "near_years_run_rate": 0.8},
                       {"period_end": "2026-01-25", "years": 3.0, "near_years": 1.2, "commitments": 95e9, "years_run_rate": 2.5, "near_years_run_rate": 1.0}],
            "latest_filed": "2026-02-20"}


def test_year_ago_is_twelve_months_before_not_the_previous_calendar_year():
    fin = fake_fin(["2025-01-26", "2025-04-27", "2025-07-27", "2025-10-26", "2026-01-25"], [10e9, 11e9, 12e9, 13e9, 14e9])
    s = make_nvidia.summary(fake_supply(), fin)
    assert s["narrow_year_ago"] == 10e9


def test_year_ago_when_the_latest_quarter_is_an_october_quarter():
    fin = fake_fin(["2025-07-27", "2025-10-26", "2026-01-25", "2026-04-26", "2026-07-26", "2026-10-25"], [12e9, 13e9, 14e9, 15e9, 16e9, 17e9])
    assert make_nvidia.summary(fake_supply(), fin)["narrow_year_ago"] == 13e9


# --------------------------------------------------------------------------- built pages


@pytest.fixture(scope="module", params=DOCS_PAGES)
def page(request, root):
    html = (root / "docs" / request.param).read_text()
    return request.param, html


def test_page_embeds_parseable_json_without_nan_or_undefined(page):
    name, html = page
    obj, raw = embedded_data(html)
    assert not re.search(r"\bNaN\b", raw), name
    assert not re.search(r"\bundefined\b", raw), name
    assert not re.search(r"\bInfinity\b", raw), name
    assert_json_safe(obj)


def test_page_data_is_strict_json(page):
    name, html = page

    def refuse(constant):
        raise ValueError(f"{name}: {constant} is not valid JSON")

    start = html.index("const DATA = ") + len("const DATA = ")
    obj, _ = json.JSONDecoder(parse_constant=refuse).raw_decode(html[start:])
    assert isinstance(obj, dict) and obj


def test_page_has_no_unfilled_placeholder_and_no_raw_script_close_in_data(page):
    name, html = page
    assert "/*__DATA__*/" not in html
    _, raw = embedded_data(html)
    assert "</" not in raw      # escaped as <\/ so a string such as "</script>" cannot end the script early


def test_front_page_embeds_the_same_funds_as_the_payload(root, funds):
    obj, _ = embedded_data((root / "docs" / "index.html").read_text())
    assert [f["key"] for f in obj["funds"]] == [f["key"] for f in funds]
    for built, now in zip(obj["funds"], funds):
        assert built["nvidia"] == pytest.approx(now["nvidia"]) and built["customers"] == pytest.approx(now["customers"])
        assert built["other_ai"] == pytest.approx(now["other_ai"])


def test_nvidia_page_embeds_the_current_summary(root, supply, financing):
    obj, _ = embedded_data((root / "docs" / "nvidia.html").read_text())
    assert set(obj) >= {"supply", "financing", "history", "customers", "summary"}
    now = make_nvidia.summary(supply, financing)
    for k in ("as_of", "supply_commitments", "narrow", "broad", "dso"):
        assert obj["summary"][k] == pytest.approx(now[k]) if not isinstance(now[k], str) else obj["summary"][k] == now[k]
    assert [p["period_end"] for p in obj["supply"]["series"]] == [p["period_end"] for p in supply["series"]]


def test_spenders_page_has_the_blocks_its_template_needs(root):
    obj, _ = embedded_data((root / "docs" / "spenders.html").read_text())
    for key in ["companies", "funding", "leases", "pv", "names", "latest_filing", "validation", "leverage", "sources_uses", "counterparties", "required"]:
        assert key in obj, key
    assert {r["ticker"] for r in obj["funding"]["rows"]} == set(obj["names"])
    assert {r["ticker"] for r in obj["leverage"]} == set(obj["names"])


def test_required_revenue_is_one_middle_case_per_company_and_life(processed):
    q = make_spenders.required_revenue_payload()
    assert_json_safe(q)
    assert q["lives"] == sorted(q["lives"]) and len(q["rows"]) == 6 * len(q["lives"])
    grid = pd.read_csv(processed / "required_revenue.csv")
    for r in q["rows"]:
        g = grid[(grid.ticker == r["ticker"]) & (grid.equipment_life_years == r["life"]) & (grid.equipment_share == 0.6) & (grid.required_return == 0.10) & (grid.margin_before_depreciation == 0.4)]
        assert len(g) == 1 and r["needed"] == pytest.approx(g.required_revenue.iloc[0])
        assert r["share_of_revenue"] == pytest.approx(r["needed"] / r["revenue"])
    by = {(r["ticker"], r["life"]): r["needed"] for r in q["rows"]}
    for t in {r["ticker"] for r in q["rows"]}:      # equipment that wears out faster needs more revenue
        assert by[(t, q["lives"][0])] > by[(t, q["lives"][-1])]


# --------------------------------------------------------------------------- the shared frame


@pytest.mark.parametrize("name", ALL_PAGES)
def test_every_page_shares_the_frame(root, name):
    html = (root / "docs" / name).read_text()
    assert 'href="assets/site.css"' in html and 'src="assets/charts.js"' in html
    assert "<style" not in html, "page-specific styles belong in docs/assets/site.css"
    for href, _ in site_shell.PAGES:
        assert html.count(f'href="{href}"') >= 2, f"{name} is missing a link to {href}"      # masthead and footer
    assert html.count('aria-current="page"') == 2 and f'href="{name}" aria-current="page"' in html
    assert site_shell.AUTHOR in html and "Built with Claude Code" in html and "not investment advice" in html


@pytest.mark.parametrize("name", ALL_PAGES)
def test_every_page_carries_a_link_preview(root, name):
    """Pasting the address into LinkedIn should draw a card: a title, a description and a picture at a full address."""
    html = (root / "docs" / name).read_text()
    tags = dict(re.findall(r'<meta property="(og:[a-z_:]+)" content="([^"]*)">', html))
    assert {"og:title", "og:description", "og:url", "og:image", "og:image:width", "og:image:height", "og:type", "og:site_name"} <= set(tags)
    assert tags["og:image"] == site_shell.SITE_URL + site_shell.CARD and tags["og:image"].startswith("https://")
    assert tags["og:url"] == site_shell.SITE_URL + ("" if name == "index.html" else name)
    assert 25 <= len(tags["og:title"]) <= 90 and tags["og:title"] != site_shell.SITE_NAME, "the card headline should say something"
    assert 60 <= len(tags["og:description"]) <= 220, "long enough to say something, short enough not to be cut off"
    assert f'<link rel="canonical" href="{tags["og:url"]}">' in html and '<link rel="icon"' in html
    assert '"' not in tags["og:description"]


def test_the_preview_picture_exists_at_the_size_the_page_declares(root):
    import struct

    data = (root / "docs" / site_shell.CARD).read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height = struct.unpack(">II", data[16:24])
    assert (width, height) == site_shell.CARD_SIZE == (1200, 627)
    assert len(data) < 1_000_000


def test_site_address_is_consistent(root):
    assert site_shell.SITE_URL.startswith("https://") and site_shell.SITE_URL.endswith("/")
    assert site_shell.SITE_URL in (root / "README.md").read_text()
    assert (root / "docs" / ".nojekyll").exists(), "tells GitHub Pages to serve the files exactly as they are"


def test_every_page_in_the_navigation_exists(root):
    assert [p for p, _ in site_shell.PAGES] == ["index.html", "spenders.html", "nvidia.html", "method.html"]
    for page, _ in site_shell.PAGES:
        assert (root / "docs" / page).exists(), page
    assert (root / "docs" / "assets" / "site.css").exists() and (root / "docs" / "assets" / "charts.js").exists()


def test_front_page_keeps_every_chart_behind_a_click(root):
    """The front page shows the ledger and its results; charts appear only when a reader opens an evidence panel."""
    html = (root / "docs" / "index.html").read_text()
    body = html[: html.index("<script>\nconst DATA")]
    depth, charts = 0, 0
    for m in re.finditer(r'<details\b|</details>|class="chart"', body):
        token = m.group(0)
        if token.startswith("<details"):
            depth += 1
        elif token == "</details>":
            depth -= 1
        else:
            charts += 1
            assert depth > 0, "a chart on the front page is not inside an evidence panel"
    assert charts >= 4 and depth == 0
    assert "<details class=\"ev\" open" not in body and "<details open" not in body


def test_front_page_is_one_topic_fund_first_then_the_bills(root):
    html = (root / "docs" / "index.html").read_text()
    order = [html.index(f'id="{i}"') for i in ("tool", "research", "ledger", "h-total", "bills", "why", "verdict", "check")]
    assert order == sorted(order), "the fund tool opens the page; the ledger of bills comes straight after"
    # a tool and a research note are different things, and the page says which part is which
    tool = html[html.index('id="tool"'): html.index('id="research"')]
    assert "Part 1 · The tool" in tool and "Part 2 · The research" in html[html.index('id="research"'): html.index('id="ledger"')]
    assert 'href="#tool"' in html[: html.index('id="tool"')] and 'href="#research"' in html[: html.index('id="tool"')]
    assert "this part is opinion" in html[html.index('id="verdict"'): html.index('id="check"')]
    assert html.count("<h1>") == 1 and "retirement fund" in html[html.index("<h1>"): html.index("</h1>")]
    # the chip seller's guarantees are a separate question: linked as a companion note, not told on this page
    body = html[: html.index("<script>\nconst DATA")]
    assert 'id="seller"' not in html and 'href="nvidia.html"' in body
    assert "telecom" not in body and "guarantee" not in body, "that story belongs to the companion note"
    # "AI builders" reads as the companies that make the models, so the page says what the six are and who is left out
    assert "AI builders" not in html and "Microsoft, Alphabet (Google), Amazon, Meta, Oracle and CoreWeave" in body
    assert "OpenAI and Anthropic are not on this list" in body
    assert '<li class="step"' not in html and "four findings" not in html


def test_every_bill_adds_up(argument):
    """A bill shows three kinds of promise, their total, and the total over cash profit. The lines must agree."""
    assert len(argument["leverage"]) == 6
    for r in argument["leverage"]:
        assert all(r[k] is not None and r[k] >= 0 for k in ("debt", "leases", "signed")) and r["ebitda"] > 0
        assert (r["debt"] + r["leases"] + r["signed"]) / r["ebitda"] == pytest.approx(r["pro_forma"], rel=1e-6), r["ticker"]
        assert (r["debt"] + r["leases"]) / r["ebitda"] == pytest.approx(r["today"], rel=1e-6), r["ticker"]
        assert r["pro_forma_low"] <= r["pro_forma"] <= r["pro_forma_high"]
        pv = next(p for p in argument["pv"]["rows"] if p["ticker"] == r["ticker"])
        assert pv["base"] == pytest.approx(r["signed"]) and pv["undiscounted"] > r["signed"], "the ledger counts leases at today's value, below the payments total"


def test_ledger_totals_and_the_card_sentence(argument):
    t = make_front.ledger_totals(argument)
    assert t["total"] == pytest.approx(t["debt"] + t["leases"] + t["signed"])
    assert t["signed"] == pytest.approx(sum(p["base"] for p in argument["pv"]["rows"]))
    text = make_front.description(argument)
    assert f"${t['total'] / 1e12:.1f} trillion" in text and "401(k)" in text and 60 <= len(text) <= 220
    assert make_front.rent_share_in_words({"leases": 30, "signed": 34, "total": 100}) == "nearly two thirds"
    assert make_front.rent_share_in_words({"leases": 30, "signed": 37, "total": 100}) == "two thirds"
    assert make_front.rent_share_in_words({"leases": 20, "signed": 30, "total": 100}) == "50%"


def test_front_template_builds_each_bill_from_the_ledger_lines(root):
    t = (root / "src" / "templates" / "index.html").read_text()
    for line in ("Borrowed", "Leases running", "Leases signed, not started", "Total promised", "Cash profit, last twelve months", "Total ÷ cash profit", "Cash and investments it holds", "Cash from operations", "New shares sold", "In your fund"):
        assert f'ln("{line}"' in t, line
    assert_template_reads(t, ["signed", "undiscounted", "pro_forma_low", "net_pro_forma", "n_figures"])
    # limits a finance reader looks for: the profit measure is named, and what the ratio leaves out is said
    for phrase in ("(EBITDA)", "EBITDAR", "not subtracted", "purchase orders"):
        assert phrase in t, phrase


def test_links_between_pages_point_at_sections_that_exist(root):
    ids = {p: set(re.findall(r'id="([^"]+)"', (root / "docs" / p).read_text())) for p in ALL_PAGES}
    for p in ALL_PAGES:
        for target, anchor in re.findall(r'href="([a-z]+\.html)#([a-z-]+)"', (root / "docs" / p).read_text()):
            assert target in ids and anchor in ids[target], f"{p} links to {target}#{anchor}, which does not exist"


def test_method_page_reports_the_recorded_checks(root):
    html = (root / "docs" / "method.html").read_text()
    checks = pd.read_csv(root / "checks" / "author_checks.csv", dtype=str).fillna("")
    recheck = pd.read_csv(root / "checks" / "machine_recheck.csv")
    assert f"{int((recheck.machine_result == 'pass').sum())} of {len(recheck)} source figures confirmed" in html
    done = checks[(checks.checked_by != "") & (checks.matches.str.lower() == "yes")]
    if len(done) == len(checks):
        assert f"each of the {len(checks)} source figures" in html
    assert "automated tests" not in html and "independent review" not in html      # no counts offered as proof
    assert "share-price" not in html and "share price" not in html


def test_no_page_claims_reading_or_collecting_done_by_hand(root):
    """First person is for the author's views and choices, not for work a program did."""
    for name in ALL_PAGES:
        text = (root / "docs" / name).read_text()
        for phrase in ("I collected", "I scanned", "I read every", "I followed", "I measured", "I ran it", "I first ran"):
            assert phrase not in text, f"{phrase!r} in {name}"


def test_front_page_does_not_overstate(root):
    html = (root / "docs" / "index.html").read_text()
    for phrase in ("past every telecom maker", "no longer pays for itself", "The difference is being borrowed", "weak points", "short of cash", "Falls only if"):
        assert phrase not in html, phrase


def test_the_required_revenue_table_uses_the_grids_own_middle():
    import funding_gap

    a = make_spenders.required_revenue_payload()["assumptions"]
    m = funding_gap.MIDDLE
    assert (a["equipment_share"], a["required_return"], a["margin"], a["middle_life"]) == (m["equipment_share"], m["required_return"], m["margin_before_depreciation"], m["equipment_life_years"])
    for name, values in (("required_return", funding_gap.REQUIRED_RETURNS), ("margin_before_depreciation", funding_gap.MARGINS), ("equipment_life_years", funding_gap.EQUIPMENT_LIVES)):
        assert m[name] == sorted(values)[len(values) // 2], f"{name} is not the middle of the values tested"


def test_fund_concentration_looks_at_stocks_by_company(processed):
    e = pd.read_csv(processed / "fund_ai_exposure.csv").set_index("fund_key")
    # an equal-weight fund of about 500 companies cannot have 6% in its ten largest; that figure was two collateral lines
    assert e.loc["equal_weight_500", "pct_top10"] < 3 and e.loc["equal_weight_500", "effective_number_of_holdings"] > 450
    # a retirement fund's stocks are as spread out as the stock funds inside it, whatever its bond share
    assert e.loc["target_2030", "effective_number_of_holdings"] == pytest.approx(e.loc["target_2060", "effective_number_of_holdings"], rel=0.02)
    assert (e.n_companies <= e.n_holdings).all() or (e.n_companies > 1000).any()


def test_each_bill_note_names_its_filing(root):
    notes = make_spenders.ledger_notes_payload()
    assert {"MSFT", "GOOGL", "AMZN", "META", "ORCL", "CRWV"} >= set(notes) and notes
    for ticker, items in notes.items():
        for n in items:
            assert n["url"].startswith("https://www.sec.gov/Archives/edgar/data/") and len(n["text"]) > 30
    assert any(n["kind"] == "locked" for n in notes["GOOGL"]) and any(n["kind"] == "left_out" for n in notes["CRWV"])


def test_no_page_claims_every_figure_links_to_a_sentence(root):
    for name in ALL_PAGES:
        text = (root / "docs" / name).read_text()
        assert "Every figure links" not in text and "and links to the sentence it came from" not in text


def test_method_page_lists_the_assumptions_behind_each_headline(root):
    html = (root / "docs" / "method.html").read_text()
    assert "Assumptions and judgment calls" in html
    for phrase in ("interest rate for signed leases", "What counts as borrowed", "Cash profit", "Profit is held still", "upper limit",
                   "highest disclosed reading", "counted whole", "long-term lines", "claims no ranking"):
        assert phrase in html, phrase
