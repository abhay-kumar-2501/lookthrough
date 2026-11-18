"""Shared test setup.

* puts src/ on the import path (also done by pytest.ini, repeated here so a
  single test file can be run from anywhere);
* gives `edgar` a client id from the environment, so importing it never reads
  the user's .env and never exits on a fresh clone;
* blocks all network access: every test must run from hand-written fixtures or
  the CSVs committed under data/processed and inputs/.
"""
from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

# Must be set before `import edgar` (it resolves the id at import time).
os.environ["SEC_CLIENT_ID"] = "lookthrough test suite (offline)"


class NetworkBlocked(RuntimeError):
    pass


def _blocked(*args, **kwargs):
    raise NetworkBlocked("tests must not touch the network")


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", _blocked)
    monkeypatch.setattr(requests.sessions.Session, "request", _blocked)
    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def processed() -> Path:
    return ROOT / "data" / "processed"
