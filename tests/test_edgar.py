"""edgar.py: the on-disk cache and the filing index, with the cache pointed at a temp folder.

Nothing here reaches the network (conftest blocks it) or reads the real .env.
"""
from __future__ import annotations

import json

import pytest

import edgar
from conftest import NetworkBlocked


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar, "RAW", tmp_path)
    monkeypatch.setattr(edgar, "_MIN_INTERVAL", 0.0)

    def put(url: str, body) -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        edgar._cache_path(url).write_bytes(data)

    return put


def test_cached_response_is_served_without_the_network(cache):
    url = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/doc.htm"
    cache(url, b"<html>cached</html>")
    assert edgar.get(url) == b"<html>cached</html>"


def test_cache_miss_goes_to_the_network(cache):
    with pytest.raises(NetworkBlocked):
        edgar.get("https://www.sec.gov/Archives/edgar/data/1/000000000126000001/not-cached.htm")


def test_refresh_bypasses_the_cache(cache):
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    cache(url, {"stale": True})
    with pytest.raises(NetworkBlocked):
        edgar.get(url, refresh=True)


def test_cache_paths_are_stable_and_distinct(cache):
    a = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/index.json"
    b = "https://www.sec.gov/Archives/edgar/data/1/000000000126000002/index.json"
    assert edgar._cache_path(a) == edgar._cache_path(a)
    assert edgar._cache_path(a) != edgar._cache_path(b)
    assert edgar._cache_path(a).parent == edgar.RAW
    long_a, long_b = "https://x.test/" + "a" * 300 + "/same-tail.xml", "https://x.test/" + "b" * 300 + "/same-tail.xml"
    assert edgar._cache_path(long_a) != edgar._cache_path(long_b)
    assert len(edgar._cache_path(long_a).name) < 140


SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "10-K", "10-K/A", "10-Q"],
            "accessionNumber": ["0000000001-26-000009", "0000000001-26-000008", "0000000001-26-000005", "0000000001-26-000006", "0000000001-25-000030"],
            "filingDate": ["2026-11-01", "2026-10-28", "2026-07-29", "2026-08-15", "2025-10-29"],
            "reportDate": ["2026-10-30", "2026-09-30", "2026-06-30", "2026-06-30", "2025-09-30"],
            "primaryDocument": ["ex99.htm", "tst-20260930.htm", "tst-20260630.htm", "tst-20260630a.htm", "tst-20250930.htm"],
        },
        "files": [{"name": "CIK0000000001-submissions-001.json"}],
    }
}
OLDER = {
    "form": ["10-K", "4"],
    "accessionNumber": ["0000000001-14-000002", "0000000001-14-000001"],
    "filingDate": ["2014-07-31", "2014-07-01"],
    "reportDate": ["2014-06-30", "2014-06-30"],
    "primaryDocument": ["tst-10k_20140630.htm", "form4.xml"],
}


@pytest.fixture
def filings(cache):
    cache("https://data.sec.gov/submissions/CIK0000000001.json", SUBMISSIONS)
    cache("https://data.sec.gov/submissions/CIK0000000001-submissions-001.json", OLDER)
    return edgar.filings(1)


def test_filings_newest_first_and_only_the_requested_forms(filings):
    assert [(f["form"], f["period"]) for f in filings] == [
        ("10-Q", "2026-09-30"),
        ("10-K", "2026-06-30"),
        ("10-Q", "2025-09-30"),
        ("10-K", "2014-06-30"),
    ]
    assert filings[0] == {
        "form": "10-Q",
        "accession": "0000000001-26-000008",
        "filed": "2026-10-28",
        "period": "2026-09-30",
        "primary_doc": "tst-20260930.htm",
    }


def test_filings_form_filter_is_exact(cache, filings):
    assert [f["period"] for f in edgar.filings(1, forms=("10-K",))] == ["2026-06-30", "2014-06-30"]  # no 10-K/A


def test_filing_urls(filings):
    f = filings[1]
    assert edgar.cik10(789019) == "0000789019"
    assert edgar.filing_base(1, f["accession"]) == "https://www.sec.gov/Archives/edgar/data/1/000000000126000005"
    assert edgar.primary_doc_url(1, f) == "https://www.sec.gov/Archives/edgar/data/1/000000000126000005/tst-20260630.htm"


def index(names):
    return {"directory": {"item": [{"name": n} for n in names]}}


def test_instance_url_prefers_the_inline_xbrl_extract(cache, filings):
    f = filings[1]
    base = edgar.filing_base(1, f["accession"])
    cache(f"{base}/index.json", index(["tst-20260630.htm", "tst-20260630_htm.xml", "tst-20260630_cal.xml", "FilingSummary.xml", "R1.htm"]))
    assert edgar.xbrl_instance_url(1, f) == f"{base}/tst-20260630_htm.xml"


def test_instance_url_for_older_filings_skips_linkbases(cache, filings):
    f = filings[3]
    base = edgar.filing_base(1, f["accession"])
    names = ["tst-10k_20140630.htm", "tst-20140630.xml", "tst-20140630_cal.xml", "tst-20140630_def.xml", "tst-20140630_lab.xml",
             "tst-20140630_pre.xml", "FilingSummary.xml", "R2.xml"]
    cache(f"{base}/index.json", index(names))
    assert edgar.xbrl_instance_url(1, f) == f"{base}/tst-20140630.xml"


def test_instance_url_is_none_when_the_filing_has_no_xbrl(cache, filings):
    f = filings[3]
    cache(f"{edgar.filing_base(1, f['accession'])}/index.json", index(["tst-10k_20140630.htm", "FilingSummary.xml"]))
    assert edgar.xbrl_instance_url(1, f) is None


def test_client_id_comes_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar, "ROOT", tmp_path)  # never look at the real .env
    monkeypatch.setenv("SEC_CLIENT_ID", "Jane Doe jane@example.com")
    assert edgar._client_id() == "Jane Doe jane@example.com"


def test_client_id_from_a_dotenv_file(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar, "ROOT", tmp_path)
    for key in edgar._ID_KEYS:
        monkeypatch.delenv(key, raising=False)
    (tmp_path / ".env").write_text('# comment\nOTHER=1\nSEC_CLIENT_ID="Jane Doe jane@example.com"\n')
    assert edgar._client_id() == "Jane Doe jane@example.com"


def test_fresh_clone_without_an_id_stops_with_a_clear_message(monkeypatch, tmp_path):
    monkeypatch.setattr(edgar, "ROOT", tmp_path)
    for key in edgar._ID_KEYS:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(SystemExit, match="SEC_CLIENT_ID"):
        edgar._client_id()
