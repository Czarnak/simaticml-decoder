"""Tests for parse.py's two entry points: parse_file() (path-based, safe
read) and parse_bytes() (pure, zero filesystem access).

These are regression tests for the Task 3 refactor: parse_file() must keep
its exact existing safety properties (it still delegates to read_xml(),
completely unchanged), and parse_bytes() must produce an equal
model.Document from the same content while never touching the filesystem.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from simaticml_decoder import parse

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _normalize(value):
    """Recursively normalize a parsed structure for equality comparison.

    ``model.py`` deliberately retains a handful of raw ``xml.etree``
    ``Element`` objects verbatim (e.g. ``RawSource.element``, and
    unrecognized children stashed under ``raw["children"]``) so nothing is
    silently dropped. ``Element`` has no ``__eq__`` (falls back to identity),
    so two independently-parsed trees holding structurally-identical but
    distinct ``Element`` instances would never compare equal via bare
    ``==``. Canonicalize any ``Element`` to its serialized XML string before
    comparing, so this test verifies *content* equality between
    ``parse_file()`` and ``parse_bytes()``, not object identity.
    """
    if isinstance(value, ET.Element):
        return ET.tostring(value, encoding="unicode")
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def test_parse_bytes_matches_parse_file_for_a_real_fixture(fixture_file):
    path = fixture_file("Inputs_FB")

    from_file = parse.parse_file(str(path))
    from_bytes = parse.parse_bytes(path.read_bytes())

    assert _normalize(dataclasses.asdict(from_file.block)) == _normalize(
        dataclasses.asdict(from_bytes.block)
    )
    assert from_file.engineering_version == from_bytes.engineering_version


def test_parse_bytes_matches_parse_file_for_a_library_block(fixture_file):
    path = fixture_file("AnalogInput")

    from_file = parse.parse_file(str(path))
    from_bytes = parse.parse_bytes(path.read_bytes())

    assert _normalize(dataclasses.asdict(from_file.block)) == _normalize(
        dataclasses.asdict(from_bytes.block)
    )


def test_parse_bytes_performs_zero_filesystem_access(monkeypatch, fixture_file):
    """parse_bytes() must be pure: no os.open/os.stat/Path access at all."""
    path = fixture_file("Inputs_FB")
    raw = path.read_bytes()

    def _fail(*_args, **_kwargs):
        raise AssertionError("parse_bytes() must not touch the filesystem")

    monkeypatch.setattr("simaticml_decoder.parse.read_xml", _fail)
    monkeypatch.setattr("simaticml_decoder.input_policy.read_xml", _fail)

    document = parse.parse_bytes(raw)

    assert document.block.name == "Inputs_FB"


def test_parse_bytes_raises_value_error_for_a_udt_export(fixture_file):
    """parse_bytes() must not be broadened into a general XML union: a
    SW.Types.PlcStruct (UDT) export still raises, exactly like
    parse_document() does today for anything without a SW.Blocks.* element.
    """
    udt_path = _FIXTURES_DIR / "SimaticML" / "PLC_1" / "PLC data types" / "UDT_Settings.xml"
    assert udt_path.is_file()

    with pytest.raises(ValueError, match="no SW.Blocks.\\* block element found"):
        parse.parse_bytes(udt_path.read_bytes())


def test_parse_bytes_rejects_malformed_xml():
    with pytest.raises(Exception):
        parse.parse_bytes(b"<Document><Unclosed>")


def test_parse_file_still_delegates_to_read_xml(monkeypatch, fixture_file):
    """Regression: parse_file()'s own path-based read must remain exactly
    read_xml() -- the O_NOFOLLOW + samestat + size-limit-before-decode path
    -- not path.read_bytes() or any other unguarded read."""
    path = fixture_file("Inputs_FB")
    calls: list[str] = []
    original = parse.read_xml

    def _spy(source, *args, **kwargs):
        calls.append(str(source))
        return original(source, *args, **kwargs)

    monkeypatch.setattr(parse, "read_xml", _spy)

    document = parse.parse_file(str(path))

    assert calls == [str(path)]
    assert document.block.name == "Inputs_FB"
