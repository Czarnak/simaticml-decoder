"""Unit tests for the CLI with committed native SimaticML fixtures."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from simaticml_decoder import cli


# --- single-file mode ------------------------------------------------------

def test_missing_path_is_soft_noop(capsys):
    code = cli.main(["definitely_not_here.xml"])
    assert code == 0
    assert "not found" in capsys.readouterr().err


def test_malformed_xml_returns_1(tmp_path, capsys):
    bad = tmp_path / "bad.xml"
    bad.write_text("<not><closed>", encoding="utf-8")
    code = cli.main([str(bad)])
    assert code == 1
    assert "MALFORMED_XML" in capsys.readouterr().err


def test_happy_path_writes_both(tmp_path, fixture_file):
    src = fixture_file("FC_Cargador")
    code = cli.main([str(src), "-o", str(tmp_path), "--format", "both", "-q"])
    assert code == 0
    assert (tmp_path / "FC_Cargador.scl").is_file()
    data = json.loads((tmp_path / "FC_Cargador.json").read_text(encoding="utf-8"))
    assert data["block"]["name"] == "FC_Cargador"


def test_format_scl_only(tmp_path, fixture_file):
    src = fixture_file("FC_Cargador")
    assert cli.main([str(src), "-o", str(tmp_path), "--format", "scl", "-q"]) == 0
    assert (tmp_path / "FC_Cargador.scl").is_file()
    assert not (tmp_path / "FC_Cargador.json").exists()


def test_quiet_suppresses_stderr(tmp_path, fixture_file, capsys):
    src = fixture_file("FC_Cargador")
    cli.main([str(src), "-o", str(tmp_path), "-q"])
    assert capsys.readouterr().err == ""


# --- directory (bulk) mode -------------------------------------------------

def test_empty_directory_is_soft_noop(tmp_path, capsys):
    code = cli.main([str(tmp_path)])
    assert code == 0
    assert "no .xml" in capsys.readouterr().err.lower()


def test_directory_with_no_xml_is_soft_noop(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "stale.scl").write_text("// leftover", encoding="utf-8")
    code = cli.main([str(tmp_path)])
    assert code == 0
    assert "no .xml" in capsys.readouterr().err.lower()


def test_directory_mirrors_subtree(tmp_path, fixture_file):
    src = fixture_file("FC_Cargador")
    nested = tmp_path / "in" / "motion" / "safety"
    nested.mkdir(parents=True)
    shutil.copy(src, nested / "Motor.xml")
    out = tmp_path / "out"
    code = cli.main([str(tmp_path / "in"), "-o", str(out), "--format", "both", "-q"])
    assert code == 0
    assert (out / "motion" / "safety" / "Motor.scl").is_file()
    data = json.loads((out / "motion" / "safety" / "Motor.json").read_text(encoding="utf-8"))
    assert data["block"]["name"] == "FC_Cargador"


def test_directory_in_place_no_output(tmp_path, fixture_file):
    src = fixture_file("FC_Cargador")
    sub = tmp_path / "in" / "a"
    sub.mkdir(parents=True)
    shutil.copy(src, sub / "Motor.xml")
    code = cli.main([str(tmp_path / "in"), "-q"])
    assert code == 0
    assert (sub / "Motor.scl").is_file()
    assert (sub / "Motor.json").is_file()


def test_one_bad_file_does_not_abort_batch(tmp_path, fixture_file, capsys):
    src = fixture_file("FC_Cargador")
    root = tmp_path / "in"
    root.mkdir()
    shutil.copy(src, root / "Motor.xml")
    (root / "bad.xml").write_text("<not><closed>", encoding="utf-8")
    out = tmp_path / "out"
    code = cli.main([str(root), "-o", str(out)])
    assert code == 1
    assert (out / "Motor.scl").is_file()      # the good file is still decoded
    err = capsys.readouterr().err
    assert "bad.xml" in err
    assert "1 failed" in err


def test_no_recursive_skips_subdirs(tmp_path, fixture_file):
    src = fixture_file("FC_Cargador")
    root = tmp_path / "in"
    (root / "sub").mkdir(parents=True)
    shutil.copy(src, root / "Top.xml")
    shutil.copy(src, root / "sub" / "Nested.xml")
    out = tmp_path / "out"
    code = cli.main([str(root), "-o", str(out), "--no-recursive", "-q"])
    assert code == 0
    assert (out / "Top.scl").is_file()
    assert not (out / "sub" / "Nested.scl").exists()


def test_format_applies_to_whole_batch(tmp_path, fixture_file):
    src = fixture_file("FC_Cargador")
    root = tmp_path / "in"
    root.mkdir()
    shutil.copy(src, root / "One.xml")
    shutil.copy(src, root / "Two.xml")
    out = tmp_path / "out"
    assert cli.main([str(root), "-o", str(out), "--format", "scl", "-q"]) == 0
    assert (out / "One.scl").is_file()
    assert (out / "Two.scl").is_file()
    assert not (out / "One.json").exists()
    assert not (out / "Two.json").exists()


# --- artifact-backed directory dispatch (native handle-anchored traversal) --


def test_directory_reports_all_unpaired_resources(capsys):
    root = Path(__file__).parent / "fixtures" / "SimaticSD_s7res"
    assert cli.main([str(root), "-q"]) == 1
    assert capsys.readouterr().err.count("SD_RESOURCE_WITHOUT_DCL") == 6


def test_directory_output_uses_artifact_relative_path(tmp_path, fixture_file):
    root = tmp_path / "in"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    shutil.copy(fixture_file("FC_Cargador"), nested / "block.xml")
    assert cli.main([str(root), "-o", str(tmp_path / "out"), "-q"]) == 0
    assert (tmp_path / "out" / "a" / "b" / "block.scl").is_file()
