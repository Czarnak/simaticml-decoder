"""Shared pytest setup and committed fixture-corpus helpers."""

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

_BLOCK_FIXTURES = {
    "FC_Cargador": FIXTURES_DIR / "SimaticML" / "PLC_1" / "Program blocks" / "FC_Cargador.xml",
    "MHJ-PLC-Lab-Function-S71200": (
        FIXTURES_DIR / "SimaticML" / "PLC_1" / "Program blocks" / "MHJ-PLC-Lab-Function-S71200.xml"
    ),
}


def _require(name: str) -> Path:
    path = _BLOCK_FIXTURES[name]
    if not path.is_file():
        raise AssertionError(f"committed fixture missing: {path}")
    return path


@pytest.fixture
def fixture_file():
    """Return a callable name -> committed native SimaticML path."""
    return _require


@pytest.fixture
def load_fixture():
    """Return a callable name -> model.Document."""
    from simaticml_decoder import parse

    def _load(name: str):
        return parse.parse_file(str(_require(name)))

    return _load
