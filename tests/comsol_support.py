"""One lazily connected MPh client for the opt-in integration test process."""

import sys

from geompype._comsol import get_client as project_client

_client = None


def get_client():
    global _client
    if not sys.flags.interactive:
        raise RuntimeError(
            "Run python -i tests/run_comsol_tests.py to keep COMSOL connected after testing.")
    if _client is None:
        _client = project_client()
    return _client
