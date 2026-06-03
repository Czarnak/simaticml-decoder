"""Shared pytest setup and fixture-corpus helpers.

The sample XML exports live in ``tests/fixtures/`` which is gitignored, so a
fresh checkout (e.g. CI) has no corpus. The fixture-backed tests therefore
``pytest.skip`` cleanly when a file is absent; the self-contained unit tests
build ``model``/``ir`` objects directly and never touch the corpus.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# src-layout: make the package importable without an editable install (CI does
# install it, but this keeps a bare ``pytest`` working from a clean clone too).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _require(name: str) -> Path:
    path = FIXTURES_DIR / f"{name}.xml"
    if not path.is_file():
        pytest.skip(f"fixture {name}.xml not present (tests/fixtures/ is gitignored)")
    return path


@pytest.fixture
def fixture_file():
    """Return a callable name -> Path, skipping if the fixture is absent."""
    return _require


@pytest.fixture
def load_fixture():
    """Return a callable name -> model.Document, skipping if the fixture is absent."""
    from simaticml_decoder import parse

    def _load(name: str):
        return parse.parse_file(str(_require(name)))

    return _load
