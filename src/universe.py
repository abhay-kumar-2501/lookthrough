"""The companies covered by the ledger."""

COMPANIES = [
    {"ticker": "MSFT", "name": "Microsoft", "cik": 789019},
    {"ticker": "GOOGL", "name": "Alphabet", "cik": 1652044},
    {"ticker": "AMZN", "name": "Amazon", "cik": 1018724},
    {"ticker": "META", "name": "Meta", "cik": 1326801},
    {"ticker": "ORCL", "name": "Oracle", "cik": 1341439},
    {"ticker": "CRWV", "name": "CoreWeave", "cik": 1769628},
]

BY_TICKER = {c["ticker"]: c for c in COMPANIES}
