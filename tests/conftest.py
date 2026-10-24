"""Give each test run a fresh local temporary root on Windows.

Explicit --basetemp continues to take precedence. Existing test runs are left
untouched; a stale directory owned by another sandbox is never reused.
"""

from pathlib import Path
from tempfile import mkdtemp

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Avoid global Temp and previous-run ACLs without changing tested logic."""
    if config.option.basetemp is None:
        root = Path(__file__).resolve().parents[1] / "out" / "pytest"
        root.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = Path(mkdtemp(prefix="run_", dir=root)) / "temp"
