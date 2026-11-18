"""Rebuild everything from EDGAR:  python run.py

Filings are cached under data/raw/ after the first run. Delete that folder to
pull fresh filings (for example after a new 10-Q is filed).
"""
import subprocess
import sys

STEPS = [
    "build_dataset",  # annual financials and gross server assets
    "model",  # depreciation model and validation
    "calibrate",  # prints the blended lives backed out from disclosures
    "leases",  # leases not yet commenced, every quarter
    "fundamentals",  # latest-quarter balance sheet and trailing-twelve-month flows
    "lease_pv",  # present value of the uncommenced leases
    "commitments",  # purchase commitments and contracted backlog
    "funding_gap",  # commitments against operating cash flow
    "leverage",  # debt against cash earnings, before and after the signed leases; where the cash went
    "fund_holdings",  # what common funds hold, from N-PORT filings
    "nvidia_supply",  # NVIDIA's supply commitments since 2019
    "nvidia_financing",  # NVIDIA's support for its customers
    "vendor_finance_history",  # Lucent, Nortel, Cisco, Motorola 1997-2003
    "make_spenders",  # docs/spenders.html: evidence behind the ledger
    "make_nvidia",  # docs/nvidia.html: evidence for the chip seller's promise
    "make_front",  # docs/index.html: the argument, with the fund tool
    "make_checklist",  # checks/author_checks.csv: headline figures to check by hand
    "recheck",  # second pass over those figures, on freshly downloaded filings
    "make_method",  # docs/method.html
    "make_charts",  # four still images in charts/
]
# src/market_scan.py (every SEC registrant) is slow and is run separately.

for step in STEPS:
    print(f"\n=== {step} ===", flush=True)
    subprocess.run([sys.executable, "-W", "ignore", f"src/{step}.py"], check=True)
