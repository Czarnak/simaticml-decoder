"""Unit tests for the CLI. Error paths are self-contained; happy paths use the
fixture corpus (skipped when absent)."""

from __future__ import annotations

import json

from simaticml_decoder import cli


def test_missing_file_returns_2(capsys):
    code = cli.main(["definitely_not_here.xml"])
    assert code == 2
    assert "not found" in capsys.readouterr().err


def test_malformed_xml_returns_1(tmp_path, capsys):
    bad = tmp_path / "bad.xml"
    bad.write_text("<not><closed>", encoding="utf-8")
    code = cli.main([str(bad)])
    assert code == 1
    assert "well-formed" in capsys.readouterr().err


def test_happy_path_writes_both(tmp_path, fixture_file):
    src = fixture_file("Motor")
    code = cli.main([str(src), "-o", str(tmp_path), "--format", "both", "-q"])
    assert code == 0
    assert (tmp_path / "Motor.scl").is_file()
    data = json.loads((tmp_path / "Motor.json").read_text(encoding="utf-8"))
    assert data["block"]["name"] == "Motor"


def test_format_scl_only(tmp_path, fixture_file):
    src = fixture_file("Motor")
    assert cli.main([str(src), "-o", str(tmp_path), "--format", "scl", "-q"]) == 0
    assert (tmp_path / "Motor.scl").is_file()
    assert not (tmp_path / "Motor.json").exists()


def test_quiet_suppresses_stderr(tmp_path, fixture_file, capsys):
    src = fixture_file("Motor")
    cli.main([str(src), "-o", str(tmp_path), "-q"])
    assert capsys.readouterr().err == ""
