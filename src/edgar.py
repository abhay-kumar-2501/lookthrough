"""Thin, cached client for SEC EDGAR.

Everything in this project comes from three public EDGAR endpoints:
  * submissions  - the list of filings for a company
  * companyfacts - every XBRL-tagged number a company has reported
  * Archives     - the filings themselves (HTML + XBRL instance documents)

Responses are cached on disk under data/raw/ so the pipeline is reproducible
and stays well inside the SEC's 10-requests-per-second fair-access limit.

The SEC asks automated clients to identify themselves. Copy .env.example to
.env and fill in your own name and email before running.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
_ID_KEYS = ("SEC_CLIENT_ID", "SEC_USER_AGENT")


def _client_id() -> str:
    """Who we tell the SEC we are: from the environment, else the git-ignored .env file."""
    for key in _ID_KEYS:
        if os.environ.get(key):
            return os.environ[key]
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            key, _, value = line.partition("=")
            if key.strip() in _ID_KEYS and value.strip():
                return value.strip().strip('"')
    raise SystemExit("Set SEC_CLIENT_ID (see .env.example) - the SEC requires it.")


_MIN_INTERVAL = 0.15  # seconds between live requests (~6/sec)
_last_request = 0.0
# Filing lists and companyfacts change when a company files; filings themselves never change.
LISTING_MAX_AGE_HOURS = 24


def _cache_path(url: str) -> Path:
    tail = re.sub(r"[^A-Za-z0-9._-]+", "_", url.split("://", 1)[1])[-120:]
    digest = hashlib.sha1(url.encode()).hexdigest()[:10]
    return RAW / f"{digest}_{tail}"


def _is_stale(url: str, path: Path) -> bool:
    """Listings (data.sec.gov JSON) expire; documents under /Archives/ are immutable."""
    if "data.sec.gov" not in url:
        return False
    return (time.time() - path.stat().st_mtime) > LISTING_MAX_AGE_HOURS * 3600


def get(url: str, refresh: bool = False) -> bytes:
    """GET a URL, using the on-disk cache unless refresh=True or a listing has expired."""
    global _last_request
    path = _cache_path(url)
    if path.exists() and not refresh and not _is_stale(url, path):
        return path.read_bytes()
    wait = _MIN_INTERVAL - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    headers = {"User-Agent": _client_id()}  # looked up only when a download is actually needed
    for attempt in range(4):
        try:
            resp = requests.get(url, headers=headers, timeout=60)
        except OSError:
            if path.exists():  # offline: an expired listing is better than none
                return path.read_bytes()
            raise
        _last_request = time.time()
        if resp.status_code == 200:
            RAW.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(path.suffix + ".part")
            tmp.write_bytes(resp.content)  # write then rename, so a crash never leaves half a file
            tmp.replace(path)
            return resp.content
        if resp.status_code in (429, 503):
            time.sleep(2 * (attempt + 1))
            continue
        resp.raise_for_status()
    raise RuntimeError(f"EDGAR kept refusing {url}")


def get_json(url: str, refresh: bool = False) -> dict:
    return json.loads(get(url, refresh))


def cik10(cik: int) -> str:
    return f"{int(cik):010d}"


def companyfacts(cik: int, refresh: bool = False) -> dict:
    return get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10(cik)}.json", refresh)


def filings(cik: int, forms=("10-K", "10-Q"), refresh: bool = False) -> list[dict]:
    """All filings of the given form types, newest first."""
    sub = get_json(f"https://data.sec.gov/submissions/CIK{cik10(cik)}.json", refresh)
    blocks = [sub["filings"]["recent"]]
    for extra in sub["filings"].get("files", []):
        blocks.append(get_json(f"https://data.sec.gov/submissions/{extra['name']}", refresh))
    out = []
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form in forms:
                out.append(
                    {
                        "form": form,
                        "accession": b["accessionNumber"][i],
                        "filed": b["filingDate"][i],
                        "period": b["reportDate"][i],
                        "primary_doc": b["primaryDocument"][i],
                    }
                )
    out.sort(key=lambda f: f["filed"], reverse=True)
    return out


def filing_base(cik: int, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"


def filing_files(cik: int, accession: str) -> list[str]:
    idx = get_json(f"{filing_base(cik, accession)}/index.json")
    return [item["name"] for item in idx["directory"]["item"]]


def primary_doc_url(cik: int, filing: dict) -> str:
    return f"{filing_base(cik, filing['accession'])}/{filing['primary_doc']}"


def xbrl_instance_url(cik: int, filing: dict) -> str | None:
    """Locate the XBRL instance document (the machine-readable facts) for a filing."""
    names = filing_files(cik, filing["accession"])
    stem = filing["primary_doc"].rsplit(".", 1)[0]
    for candidate in (f"{stem}_htm.xml",):
        if candidate in names:
            return f"{filing_base(cik, filing['accession'])}/{candidate}"
    # Pre-2019 filings ship a standalone instance: the .xml that is not a linkbase.
    plain = [
        n
        for n in names
        if n.endswith(".xml")
        and not re.search(r"_(cal|def|lab|pre)\.xml$", n)
        and n not in ("FilingSummary.xml",)
        and not n.startswith("R")
    ]
    if plain:
        plain.sort(key=len)
        return f"{filing_base(cik, filing['accession'])}/{plain[0]}"
    return None
