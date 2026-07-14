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
    "Inputs_FB": (
        FIXTURES_DIR / "SimaticML" / "PLC_1" / "Program blocks" / "100_Inputs" / "Inputs_FB.xml"
    ),
    "AnalogInput": FIXTURES_DIR / "SimaticML" / "Types" / "Blocks" / "AnalogInput.xml",
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


@pytest.fixture
def project_fixture_root() -> Path:
    """Root directory containing every native (``SimaticML/``) and
    explicitly-labeled synthetic (``SimaticML_synthetic/``) V21 project-mode
    corpus fixture. Required paths in project-mode tests are expressed
    relative to this root (e.g. ``"SimaticML/PLC_1/..."``), matching how
    ``tests/fixtures/manifest.json``'s own paths are rooted.

    Fails loudly (``AssertionError``) rather than ``pytest.skip``-ing when
    the committed corpus is absent: a missing corpus is a broken clone/CI
    checkout, not an optional capability to quietly skip past. Mirrors
    ``_require()``'s fail-loud pattern for single-block fixtures above.
    """
    manifest = FIXTURES_DIR / "manifest.json"
    if not manifest.is_file():
        raise AssertionError(f"committed fixture-corpus manifest missing: {manifest}")
    corpus = FIXTURES_DIR / "SimaticML"
    if not corpus.is_dir():
        raise AssertionError(f"committed V21 fixture corpus missing: {corpus}")
    return FIXTURES_DIR
