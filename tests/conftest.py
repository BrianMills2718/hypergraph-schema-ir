"""Shared test fixtures.

The package is imported as an installed package. There is no sys.path
manipulation here or anywhere else in this repository: `pyproject.toml` declares
`src/knowledgework` and the test run installs it (or runs with `PYTHONPATH=src`,
which is a runner setting rather than a code path edit).
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
EXAMPLES = Path(__file__).parent.parent / "examples"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES
