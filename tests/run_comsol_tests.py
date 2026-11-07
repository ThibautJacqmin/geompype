"""Run with python -i tests/run_comsol_tests.py to keep COMSOL connected.

Some servers exit when their last client disconnects. Keep the interactive
Python session open afterwards; this runner never stops or disconnects COMSOL.
"""

from pathlib import Path
import os
import sys
import unittest

if not sys.flags.interactive:
    raise SystemExit("Use python -i tests/run_comsol_tests.py to keep the COMSOL session open.")

project_directory = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_directory))
sys.path.insert(0, str(project_directory / "tests"))
os.environ["GEOMPYPE_TEST_COMSOL"] = "1"
from comsol_support import get_client

# Fail once, before launching the suite, if the server or its licence is absent.
# The -i interpreter remains open even if this connection raises an exception.
client = get_client()
suite = unittest.defaultTestLoader.discover(str(project_directory / "tests"))
result = unittest.TextTestRunner(verbosity=2).run(suite)
print("Tests finished. Keep this Python session open to keep COMSOL connected.")
