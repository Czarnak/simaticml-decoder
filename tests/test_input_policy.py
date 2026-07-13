"""Boundary tests for untrusted decoder inputs."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from simaticml_decoder import cli, parse
from simaticml_decoder import input_policy
from simaticml_decoder.input_policy import (
    InputLimits,
    InputViolation,
    discover_xml,
    read_xml,
    safe_text,
    validate_input_file,
)


def test_read_xml_rejects_oversized_file(tmp_path):
    source = tmp_path / "oversized.xml"
    source.write_bytes(b"<Document/>" * 4)

    with pytest.raises(InputViolation, match="file_too_large"):
        read_xml(source, InputLimits(max_file_bytes=10))


def test_read_xml_rejects_doctype(tmp_path):
    source = tmp_path / "entity.xml"
    source.write_text("<!DOCTYPE x [<!ENTITY a 'b'>]><x>&a;</x>", encoding="utf-8")

    with pytest.raises(InputViolation, match="xml_forbidden_declaration"):
        read_xml(source)


def test_validate_input_file_rejects_non_xml_and_sd_code(tmp_path):
    text = tmp_path / "notes.txt"
    text.write_text("notes", encoding="utf-8")
    code = tmp_path / "block.s7dcl"
    code.write_text("code", encoding="utf-8")

    with pytest.raises(InputViolation, match="unsupported_format"):
        validate_input_file(text)
    with pytest.raises(InputViolation, match="unsupported_format"):
        validate_input_file(code)


def test_read_xml_rejects_invalid_utf8(tmp_path):
    source = tmp_path / "invalid.xml"
    source.write_bytes(b"\xff\xfe")

    with pytest.raises(InputViolation, match="invalid_encoding"):
        read_xml(source)


def test_parse_file_cannot_bypass_the_xml_boundary(tmp_path):
    source = tmp_path / "not-an-export.txt"
    source.write_text("<Document/>", encoding="utf-8")

    with pytest.raises(InputViolation, match="unsupported_format"):
        parse.parse_file(str(source))


def test_read_xml_rejects_too_many_elements(tmp_path):
    source = tmp_path / "wide.xml"
    source.write_text("<x><a/><a/><a/></x>", encoding="utf-8")

    with pytest.raises(InputViolation, match="xml_too_complex"):
        read_xml(source, InputLimits(max_xml_elements=3))


def test_read_xml_rejects_xml_attribute_text_and_flgnet_limits(tmp_path):
    attributes = tmp_path / "attributes.xml"
    attributes.write_text("<x a='1' b='2'/>", encoding="utf-8")
    text = tmp_path / "text.xml"
    text.write_text("<x>abcd</x>", encoding="utf-8")
    flgnets = tmp_path / "flgnets.xml"
    flgnets.write_text("<x><FlgNet/><FlgNet/></x>", encoding="utf-8")

    with pytest.raises(InputViolation, match="xml_too_complex"):
        read_xml(attributes, InputLimits(max_attributes_per_element=1))
    with pytest.raises(InputViolation, match="xml_too_complex"):
        read_xml(text, InputLimits(max_text_chars_per_element=3))
    with pytest.raises(InputViolation, match="xml_too_complex"):
        read_xml(flgnets, InputLimits(max_flgnet_networks=1))


def test_discover_xml_is_deterministic_and_bounded(tmp_path):
    (tmp_path / "b.xml").write_text("<x/>", encoding="utf-8")
    (tmp_path / "a.xml").write_text("<x/>", encoding="utf-8")
    nested = tmp_path / "nested"
    nested.mkdir()
    (nested / "c.xml").write_text("<x/>", encoding="utf-8")

    assert [path.name for path in discover_xml(tmp_path, recursive=False)] == ["a.xml", "b.xml"]
    assert [path.name for path in discover_xml(tmp_path, recursive=True)] == ["a.xml", "b.xml", "c.xml"]
    with pytest.raises(InputViolation, match="too_many_files"):
        discover_xml(tmp_path, recursive=True, limits=InputLimits(max_files=2))
    with pytest.raises(InputViolation, match="traversal_too_deep"):
        discover_xml(tmp_path, recursive=True, limits=InputLimits(max_depth=0))


def test_discovery_aborts_when_a_directory_changes(monkeypatch, tmp_path):
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    states = iter((tmp_path.stat(), replacement.stat()))
    monkeypatch.setattr(input_policy, "_directory_lstat", lambda _path: next(states))

    with pytest.raises(InputViolation, match="input_changed"):
        discover_xml(tmp_path, recursive=False)


def test_discover_rejects_symlink_file(tmp_path):
    target = tmp_path / "target.xml"
    target.write_text("<Document/>", encoding="utf-8")
    link = tmp_path / "linked.xml"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(InputViolation, match="symlink_not_allowed"):
        cli.discover(tmp_path, recursive=True)


def test_decode_file_rejects_direct_symlink(tmp_path):
    target = tmp_path / "target.xml"
    target.write_text("<Document/>", encoding="utf-8")
    link = tmp_path / "linked.xml"
    try:
        os.symlink(target, link)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = cli.decode_file(link, tmp_path / "out", "scl")

    assert result.status == "error"
    assert result.error is not None
    assert result.error.startswith("INPUT_REJECTED: linked.xml: symlink_not_allowed")


def test_malformed_xml_diagnostic_redacts_path_and_controls(tmp_path, capsys):
    source = tmp_path / "bad-name.xml"
    source.write_text("<not><closed>", encoding="utf-8")

    assert cli.main([str(source)]) == 1

    stderr = capsys.readouterr().err
    assert str(tmp_path) not in stderr
    assert "MALFORMED_XML: bad-name.xml" in stderr


def test_safe_text_is_single_line_and_bounded():
    assert safe_text("bad\n\x00name", limit=12) == "bad name"
    assert safe_text("abcdefghijkl", limit=8) == "abcdefg…"


def test_sd_resource_without_same_root_declaration_is_explicit_diagnostic(tmp_path):
    resource = tmp_path / "resource.s7res"
    resource.write_text("resource", encoding="utf-8")

    result = cli.decode_file(resource, tmp_path / "out", "scl")

    assert result.status == "error"
    assert result.error == (
        "SD_RESOURCE_WITHOUT_DCL: resource.s7res: "
        "SIMATIC SD resource has no same-root .s7dcl declaration"
    )


def test_read_xml_rejects_a_path_changed_after_validation(monkeypatch, tmp_path):
    source = tmp_path / "source.xml"
    source.write_text("<Document/>", encoding="utf-8")
    replacement = tmp_path / "replacement.xml"
    replacement.write_text("<Document/>", encoding="utf-8")

    monkeypatch.setattr(input_policy.os, "fstat", lambda _fd: replacement.stat())

    with pytest.raises(InputViolation, match="input_changed"):
        read_xml(source)


def test_cli_directory_reports_each_unpaired_sd_resource(capsys):
    root = Path(__file__).parent / "fixtures" / "SimaticSD_s7res"

    assert cli.main([str(root), "-q"]) == 1

    stderr = capsys.readouterr().err
    for name in (
        "FB_Sensores.s7res",
        "FC_Cargador.s7res",
        "FC_Conveyor_entry.s7res",
        "FC_Conveyor_sides.s7res",
        "FC_Seguridad.s7res",
        "Main.s7res",
    ):
        assert f"SD_RESOURCE_WITHOUT_DCL: {name}" in stderr


def test_cli_isolates_directory_discovery_rejection(monkeypatch, tmp_path, capsys):
    def reject(*_args, **_kwargs):
        raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")

    monkeypatch.setattr(cli, "discover", reject)

    assert cli.main([str(tmp_path)]) == 1
    assert "INPUT_REJECTED" in capsys.readouterr().err


def test_cli_isolates_fold_and_output_failures(monkeypatch, tmp_path):
    source = Path(__file__).parent / "fixtures" / "SimaticML" / "PLC_1" / "Program blocks" / "FC_Cargador.xml"

    monkeypatch.setattr(cli.fold, "fold_block", lambda _doc: (_ for _ in ()).throw(RuntimeError()))
    assert cli.decode_file(source, tmp_path / "fold", "scl").error == (
        "DECODE_FAILED: FC_Cargador.xml: unable to fold input"
    )

    monkeypatch.undo()
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    assert cli.decode_file(source, blocked, "scl").error is not None

    monkeypatch.setattr(cli, "_write", lambda *_args: (_ for _ in ()).throw(OSError("denied")))
    assert cli.decode_file(source, tmp_path / "write", "scl").error == (
        "OUTPUT_FAILED: FC_Cargador.xml: denied"
    )


def test_cli_sanitizes_warning_output(capsys, tmp_path):
    outcome = cli.FileOutcome(
        source=tmp_path / "source.xml",
        status="ok",
        decoded=SimpleNamespace(name="block\nname", kind="FC", networks=[], warnings=["bad\nwarning"]),
    )

    cli._report([outcome], input_root=None, quiet=False)

    stderr = capsys.readouterr().err
    assert "block name" in stderr
    assert "bad warning" in stderr
