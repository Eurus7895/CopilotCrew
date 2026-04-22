"""Test-wide fixtures. Makes ``tests/fixtures`` importable as a package path."""

import sys
from pathlib import Path

_FIXTURES = Path(__file__).parent / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))
