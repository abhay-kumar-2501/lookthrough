"""commitments: pulling purchase commitments and backlog out of filing text, and the committed commitments tables."""
from __future__ import annotations

import re

import pandas as pd
import pytest

import commitments as cm


def spec(ticker, startswith):
    hits = [s for s in cm.SPECS[ticker] if s["item"].startswith(startswith)]
    assert len(hits) == 1, (ticker, startswith, [s["item"] for s in cm.SPECS[ticker]])
    return hits[0]


# --------------------------------------------------------------------------- small helpers


def test_usd_defaults_to_millions_when_no_unit():
    assert cm._usd("454.52", "billion") == 454_520_000_000
    assert cm._usd("1,200", None) == 1_200_000_000
    assert cm._usd("950", "million") == 950_000_000
    assert cm._usd(None, "billion") is None


def test_row_numbers_requires_parts_to_sum_to_the_total():
    assert cm._row_numbers("10,000 5,000 2,000 1,000 500 1,500 20,000") == [10000, 5000, 2000, 1000, 500, 1500, 20000]
    assert cm._row_numbers("10,000 5,000 2,000 1,000 500 1,500 21,000") is None       # footnote or wrong row
    assert cm._row_numbers("5 5") is None                                               # too short to be a schedule
    assert cm._row_numbers("Fiscal 2027 $ 10 Fiscal 2028 $ 5 Total $ 15") == [10, 5, 15]  # Oracle labels are not numbers


def test_row_numbers_tolerates_rounding_of_two():
    assert cm._row_numbers("10 5 2 18") == [10, 5, 2, 18]
    assert cm._row_numbers("10 5 2 20") is None


def test_tidy():
    assert cm._tidy("worth $ 1.2 billion , up 30 %") == "worth $1.2 billion , up 30%"


# --------------------------------------------------------------------------- Microsoft


MSFT_HEAD = ("The following table summarizes the payments due by fiscal year for our outstanding contractual obligations as of June 30, 2026: "
             "(In millions) 2027 2028 2029 2030 2031 Thereafter Total")


def test_msft_purchase_commitments_row_10k_first_column_is_twelve_months():
    text = MSFT_HEAD + " Long-term debt 1 1 1 1 1 1 6 Purchase commitments (a) 169,008 12,000 6,000 3,000 2,000 2,000 194,008 Construction commitments (b) 29,848 3,000 1,000 500 100 118 34,566"
    out = cm.extract(spec("MSFT", "Purchase commitments"), text, "10-K")
    assert out["amount"] == 194_008e6 and out["due_within_12_months"] == 169_008e6
    assert "Purchase commitments (a) 169,008" in out["evidence"] and out["evidence"].startswith("The following table")
    # the construction row is its own spec and its own numbers
    con = cm.extract(spec("MSFT", "Construction commitments"), text, "10-K")
    assert con["amount"] == 34_566e6 and con["due_within_12_months"] == 29_848e6


def test_msft_row_that_does_not_add_up_is_rejected_not_misread():
    text = MSFT_HEAD + " Purchase commitments (a) 169,008 12,000 6,000 3,000 2,000 2,000 999,999"
    assert cm.extract(spec("MSFT", "Purchase commitments"), text, "10-K") is None


def test_10q_table_splits_rest_of_year_and_next_year_instead_of_twelve_months():
    text = MSFT_HEAD + " Purchase commitments 100 50 20 10 10 10 200"
    out = cm.extract(spec("MSFT", "Purchase commitments"), text, "10-Q")
    assert out["due_within_12_months"] is None
    assert (out["due_rest_of_fiscal_year"], out["due_next_fiscal_year"]) == (100e6, 50e6)


MSFT_RPO = ("Revenue allocated to remaining performance obligations, which includes unearned revenue and amounts that will be invoiced and "
            "recognized as revenue in future periods, was $683 billion as of September 30, 2026, of which $677 billion is related to the commercial "
            "portion of revenue. We expect to recognize approximately 30% of total remaining performance obligations over the next 12 months and the rest thereafter.")


def test_msft_rpo_total_and_twelve_month_share():
    out = cm.extract(spec("MSFT", "Remaining performance obligations, total"), MSFT_RPO, "10-Q")
    assert out["amount"] == 683e9
    assert out["due_within_12_months"] == round(683e9 * 30 / 100)


def test_msft_rpo_commercial_portion_is_the_part_not_the_total():
    out = cm.extract(spec("MSFT", "Remaining performance obligations, commercial"), MSFT_RPO, "10-Q")
    assert out["amount"] == 677e9


def test_msft_openai_funding_takes_the_total_not_the_funded_part():
    text = "We have made total funding commitments of $13.0 billion related to our investment, of which $11.6 billion has been funded as of September 30, 2026."
    assert cm.extract(spec("MSFT", "Funding commitments to OpenAI"), text, "10-Q")["amount"] == 13e9


# --------------------------------------------------------------------------- Alphabet


def test_googl_material_purchase_commitments_both_wordings():
    a = "Of the total material purchase commitments of $924.4 billion, $213.4 billion is due within 12 months."
    out = cm.extract(spec("GOOGL", "Material purchase commitments"), a, "10-Q")
    assert (out["amount"], out["due_within_12_months"]) == (924.4e9, 213.4e9)
    b = "As of December 31, 2025, we had material purchase commitments and other contractual obligations of $12.0 billion, of which $5.0 billion was short-term."
    out = cm.extract(spec("GOOGL", "Material purchase commitments"), b, "10-K")
    assert (out["amount"], out["due_within_12_months"]) == (12.0e9, 5.0e9)


def test_googl_million_is_not_read_as_billion():
    text = "Of the total material purchase commitments of $950 million, $400 million is due within 12 months."
    out = cm.extract(spec("GOOGL", "Material purchase commitments"), text, "10-Q")
    assert (out["amount"], out["due_within_12_months"]) == (950e6, 400e6)


GOOGL_BACKLOG = ("As of September 30, 2026, we had $567.7 billion of remaining performance obligations (“revenue backlog”), of which $560.8 billion "
                 "related to Google Cloud. We expect to recognize about half over the next 24 months.")


def test_googl_backlog_total_is_not_the_google_cloud_part():
    assert cm.extract(spec("GOOGL", "Revenue backlog, total"), GOOGL_BACKLOG, "10-Q")["amount"] == 567.7e9
    assert cm.extract(spec("GOOGL", "Revenue backlog, Google Cloud"), GOOGL_BACKLOG, "10-Q")["amount"] == 560.8e9


def test_googl_contingent_items_are_kept_out_of_the_totals():
    for s in cm.SPECS["GOOGL"]:
        if s["item"].startswith("Contingent"):
            assert s["in_total"] is False


# --------------------------------------------------------------------------- Meta, Oracle, CoreWeave, Amazon


META = ("As of December 31, 2025, we had $30.0 billion of non-cancelable contractual commitments, primarily related to cloud capacity and servers. "
        "These commitments are expected to be paid, with approximately $12.0 billion and $9.0 billion due in 2026 and 2027, respectively.")


def test_meta_non_cancelable_commitments_and_first_two_years():
    s = spec("META", "Non-cancelable")
    k = cm.extract(s, META, "10-K")
    assert k["amount"] == 30e9 and k["due_within_12_months"] == 12e9
    q = cm.extract(s, META, "10-Q")
    assert (q["due_rest_of_fiscal_year"], q["due_next_fiscal_year"]) == (12e9, 9e9) and q["due_within_12_months"] is None


def test_meta_contingent_cloud_purchase_amount():
    text = "Under an agreement, as of September 30, 2026, we have contingent obligations to purchase up to $14.7 billion of cloud capacity from a provider if it cannot resell it."
    assert cm.extract(spec("META", "Contingent: obligation to purchase"), text, "10-Q")["amount"] == 14.7e9


ORCL_RPO = "Remaining performance obligations were $664 billion as of August 31, 2026, of which we expect to recognize approximately 13% as revenues over the next twelve months and the remainder thereafter."


def test_orcl_rpo_with_twelve_month_percentage():
    out = cm.extract(spec("ORCL", "Remaining performance obligations"), ORCL_RPO, "10-Q")
    assert out["amount"] == 664e9 and out["due_within_12_months"] == round(664e9 * 0.13)


def test_orcl_purchase_obligations_table_with_inline_fiscal_labels():
    text = ("As of May 31, 2026 , our unconditional purchase and certain other obligations were as follows (in millions): Fiscal 2027 $ 10,000 "
            "Fiscal 2028 $ 5,000 Fiscal 2029 $ 3,000 Thereafter $ 2,000 Total $ 20,000 Other text")
    out = cm.extract(spec("ORCL", "Unconditional purchase"), text, "10-K")
    assert out["amount"] == 20_000e6 and out["due_within_12_months"] == 10_000e6


def test_crwv_construction_commitments_million_vs_billion():
    s = spec("CRWV", "Contractual commitments for future construction")
    assert cm.extract(s, "As of September 30, 2026, the Company has contractual commitments of approximately $2.1 billion for future construction costs.", "10-Q")["amount"] == 2.1e9
    assert cm.extract(s, "As of December 31, 2025, the Company had contractual commitments of approximately $650 million for future construction costs.", "10-K")["amount"] == 650e6


def test_crwv_equipment_range_takes_the_high_end():
    text = ("the Company has contractual obligations to procure and install equipment at the leased premises. Depending on timing and scope. "
            "As of September 30, 2026, the Company estimated that it would incur between $500 million and $817 million to fulfill these commitments.")
    assert cm.extract(spec("CRWV", "Equipment to procure"), text, "10-Q")["amount"] == 817e6


AMZN_HEAD = ("The following summarizes our principal contractual commitments, excluding open orders for inventory purchases, as of December 31, 2025 "
             "(in millions): 2026 2027 2028 2029 2030 Thereafter Total")


def test_amzn_two_rows_do_not_bleed_into_each_other():
    text = AMZN_HEAD + (" Property and equipment (3) 40,000 30,000 20,000 10,000 5,000 5,000 110,000 "
                        "Unconditional purchase obligations (4) 6,000 5,000 4,000 3,000 2,000 1,000 21,000 "
                        "Other commitments (5) 1,000 1,000 1,000 1,000 1,000 1,000 6,000")
    pe = cm.extract(spec("AMZN", "Property and equipment"), text, "10-K")
    upo = cm.extract(spec("AMZN", "Unconditional purchase"), text, "10-K")
    assert pe["amount"] == 110_000e6 and pe["due_within_12_months"] == 40_000e6
    assert upo["amount"] == 21_000e6 and upo["due_within_12_months"] == 6_000e6


def test_amzn_aws_backlog_wording():
    text = ("Additionally, we have performance obligations, primarily related to AWS, that are not yet recognized in revenue. "
            "Total customer commitments not yet recognized were estimated to be approximately $578.0 billion as of September 30, 2026.")
    assert cm.extract(spec("AMZN", "Customer commitments"), text, "10-Q")["amount"] == 578e9


def test_text_without_the_wording_returns_none():
    assert cm.extract(spec("META", "Non-cancelable"), "We repurchased $5.0 billion of shares.", "10-K") is None


# --------------------------------------------------------------------------- specs themselves


def test_every_spec_has_a_valid_kind_and_compiles():
    kinds = {"purchase_commitments", "construction", "backlog_rpo", "other"}
    for ticker, specs in cm.SPECS.items():
        items = [s["item"] for s in specs]
        assert len(items) == len(set(items)), ticker
        for s in specs:
            assert s["kind"] in kinds
            for p in s["patterns"]:
                re.compile(p)
            if not s["in_total"]:
                assert s["note"], (ticker, s["item"])        # a row left out of the totals must say why


# --------------------------------------------------------------------------- xbrl cross-check


def test_xbrl_tag_only_matches_relevant_concepts_with_the_exact_value(monkeypatch):
    df = pd.DataFrame([
        dict(concept="UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount", end="2026-06-30", value=194_008e6),
        dict(concept="StockRepurchasedAndRetiredDuringPeriodValue", end="2026-06-30", value=194_008e6),     # coincidence
        dict(concept="PurchaseObligation", end="2025-06-30", value=194_008e6),                              # other date
        dict(concept="PurchaseObligation", end="2026-06-30", value=100e6),                                  # other value
    ])
    monkeypatch.setattr(cm.xbrl, "filing_facts", lambda cik, f: df)
    monkeypatch.setattr(cm.xbrl, "numeric", lambda d: d)
    cm._facts.clear()
    tag = cm.xbrl_tag(789019, {"accession": "test-1", "period": "2026-06-30"}, 194_008e6)
    assert tag == "UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount"
    cm._facts.clear()


def test_filing_rows_builds_rows_with_evidence_and_url(monkeypatch):
    text = MSFT_HEAD + " Purchase commitments (a) 169,008 12,000 6,000 3,000 2,000 2,000 194,008"
    monkeypatch.setattr(cm.text, "filing_sentences", lambda cik, f: [text[:60], text[60:]])
    monkeypatch.setattr(cm.edgar, "primary_doc_url", lambda cik, f: "https://www.sec.gov/Archives/edgar/data/789019/x/msft.htm")
    company = {"ticker": "MSFT", "cik": 789019}
    filing = {"form": "10-K", "period": "2026-06-30", "filed": "2026-07-30", "accession": "a"}
    rows = cm.filing_rows(company, filing, cm.SPECS["MSFT"], check_xbrl=False)
    assert [r["kind"] for r in rows] == ["purchase_commitments"]
    r = rows[0]
    assert r["amount"] == 194_008e6 and r["due_within_12_months"] == 169_008e6 and r["in_total"] is True
    assert r["as_of"] == "2026-06-30" and r["url"].startswith("https://www.sec.gov/") and r["evidence"]


# --------------------------------------------------------------------------- committed tables


@pytest.fixture(scope="module")
def table(processed):
    return pd.read_csv(processed / "commitments.csv")


@pytest.fixture(scope="module")
def history(processed):
    return pd.read_csv(processed / "commitments_history.csv")


def test_no_company_item_is_listed_twice(table):
    assert not table.duplicated(["ticker", "item"]).any()


def test_items_in_the_table_exist_in_the_specs(table):
    for r in table.itertuples():
        assert any(s["item"] == r.item and s["kind"] == r.kind and s["in_total"] == bool(r.in_total) for s in cm.SPECS[r.ticker]), (r.ticker, r.item)


def test_amounts_are_positive_and_twelve_month_parts_do_not_exceed_the_total(table):
    assert (table.amount > 0).all()
    d = table.dropna(subset=["due_within_12_months"])
    assert (d.due_within_12_months <= d.amount).all()
    both = table.dropna(subset=["due_rest_of_fiscal_year", "due_next_fiscal_year"])
    assert ((both.due_rest_of_fiscal_year + both.due_next_fiscal_year) <= both.amount).all()


def test_every_row_has_evidence_containing_its_amount_and_an_sec_url(table):
    assert table.url.str.startswith("https://www.sec.gov/").all()
    for r in table.itertuples():
        assert len(r.evidence) > 30
        tokens = {float(t.replace(",", "")) for t in re.findall(r"\d[\d,]*(?:\.\d+)?", r.evidence)}
        assert any(abs(t - r.amount / s) < 1e-6 for t in tokens for s in (1e6, 1e9)), (r.ticker, r.item, r.amount)


def test_rows_outside_the_totals_explain_themselves(table):
    out = table[~table.in_total.astype(bool)]
    assert len(out) >= 8
    assert out.note.fillna("").str.len().gt(10).all()


def test_part_rows_are_smaller_than_their_parent_rows(table):
    t = table.set_index(["ticker", "item"]).amount
    assert t[("MSFT", "Remaining performance obligations, commercial portion")] <= t[("MSFT", "Remaining performance obligations, total company")]
    assert t[("GOOGL", "Revenue backlog, Google Cloud")] <= t[("GOOGL", "Revenue backlog, total")]
    assert t[("GOOGL", "Contracts with remaining terms over one year (long-term supply, energy, content)")] <= \
        t[("GOOGL", "Material purchase commitments (technical infrastructure and inventory, energy take-or-pay, content, open purchase orders)")]


def test_history_has_no_duplicates_and_only_the_wanted_kinds(history):
    assert not history.duplicated(["ticker", "item", "as_of"]).any()
    assert "other" not in set(history.kind)
    assert (history.amount > 0).all()
    assert history.as_of.min() >= cm.SINCE


def test_latest_rows_agree_with_the_same_date_in_history(table, history):
    h = history.set_index(["ticker", "item", "as_of"]).amount
    for r in table[table.kind != "other"].itertuples():
        key = (r.ticker, r.item, r.as_of)
        if key in h.index:
            assert h[key] == r.amount, key
