"""Tests for the explicit ``--project`` CLI mode (Task 6).

Verifies mode separation (``--project`` vs. the legacy single-file/directory
``PATH`` mode), exactly-one-of enforcement, the ``--library-root`` origin
override, invalid ``--library-root`` handling, and the nonzero-exit-on-any-
``FAILED``-artifact contract -- without touching legacy CLI behavior at all.
"""

from __future__ import annotations

import json
from pathlib import Path

from simaticml_decoder import cli

PROJECT_ROOT = Path(__file__).resolve().parent / "fixtures" / "SimaticML"


def _manifest(out_dir: Path) -> dict:
    return json.loads((out_dir / "project-manifest.json").read_text(encoding="utf-8"))


# --- mode separation ---------------------------------------------------------


def test_project_mode_writes_one_manifest_and_keeps_legacy_directory_mode(tmp_path, fixture_file):
    single_block_root = fixture_file("Inputs_FB")
    project_output = tmp_path / "project-output"
    legacy_output = tmp_path / "legacy-output"

    assert cli.main(["--project", str(PROJECT_ROOT), "-o", str(project_output), "-q"]) == 0
    assert (project_output / "project-manifest.json").is_file()
    assert not list(project_output.rglob("*.scl"))

    assert (
        cli.main([str(single_block_root), "-o", str(legacy_output), "--format", "both", "-q"]) == 0
    )
    assert list(legacy_output.rglob("*.scl"))


def test_project_manifest_reports_artifacts_and_no_reimport_contract(tmp_path):
    out_dir = tmp_path / "out"
    assert cli.main(["--project", str(PROJECT_ROOT), "-o", str(out_dir), "-q"]) == 0
    manifest = _manifest(out_dir)
    assert manifest["output_contract"] == {"fidelity": "analysis-only", "reimportable": False}
    assert len(manifest["artifacts"]) > 0
    assert not list(out_dir.rglob("*.json.bak"))
    # no sidecar/scl output anywhere, only the manifest itself
    assert {p.name for p in out_dir.iterdir()} == {"project-manifest.json"}


# --- exactly-one-of PATH / --project enforcement ------------------------------


def test_both_input_and_project_given_is_an_error(tmp_path, fixture_file):
    code = cli.main(
        [str(fixture_file("Inputs_FB")), "--project", str(PROJECT_ROOT), "-o", str(tmp_path)]
    )
    assert code != 0


def test_neither_input_nor_project_given_is_an_error(capsys):
    code = cli.main([])
    assert code != 0
    assert "PATH" in capsys.readouterr().err


# --- --library-root override --------------------------------------------------


def test_library_root_override_changes_origin_in_manifest(tmp_path):
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--project",
            str(PROJECT_ROOT),
            "-o",
            str(out_dir),
            "--library-root",
            "PLC_1/Program blocks/999_MISC",
            "-q",
        ]
    )
    assert code == 0
    manifest = _manifest(out_dir)

    overridden = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["location"]["relative_path"]
        == "PLC_1/Program blocks/999_MISC/MotorSoftstart.xml"
    ]
    assert len(overridden) == 1
    assert overridden[0]["identity"]["origin"] == "project-library"

    # A sibling artifact *outside* the overridden subtree keeps the default
    # PLC_1/ -> user classification.
    unaffected = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["location"]["relative_path"] == "PLC_1/Program blocks/100_Inputs/Inputs_FB.xml"
    ]
    assert len(unaffected) == 1
    assert unaffected[0]["identity"]["origin"] == "user"


def test_no_library_root_keeps_task3_default_classification(tmp_path):
    out_dir = tmp_path / "out"
    assert cli.main(["--project", str(PROJECT_ROOT), "-o", str(out_dir), "-q"]) == 0
    manifest = _manifest(out_dir)

    by_path = {a["location"]["relative_path"]: a for a in manifest["artifacts"]}
    assert (
        by_path["PLC_1/Program blocks/999_MISC/MotorSoftstart.xml"]["identity"]["origin"] == "user"
    )
    assert by_path["Types/Blocks/AnalogInput.xml"]["identity"]["origin"] == "project-library"


def test_invalid_library_root_absolute_produces_outside_root_diagnostic(tmp_path):
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--project",
            str(PROJECT_ROOT),
            "-o",
            str(out_dir),
            "--library-root",
            "/etc/passwd",
            "-q",
        ]
    )
    assert code == 0  # invalid --library-root does not crash or fail the run
    manifest = _manifest(out_dir)
    outside_root = [d for d in manifest["diagnostics"] if d["code"] == "outside_root"]
    assert len(outside_root) == 1


def test_invalid_library_root_dotdot_produces_outside_root_diagnostic(tmp_path):
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--project",
            str(PROJECT_ROOT),
            "-o",
            str(out_dir),
            "--library-root",
            "../escape",
            "-q",
        ]
    )
    assert code == 0
    manifest = _manifest(out_dir)
    outside_root = [d for d in manifest["diagnostics"] if d["code"] == "outside_root"]
    assert len(outside_root) == 1


def test_invalid_library_root_empty_string_produces_outside_root_diagnostic(tmp_path):
    """An empty ``--library-root`` normalizes to ``PurePosixPath('.')`` under
    naive handling, which is "relative to" every artifact -- this must be
    rejected, not silently treated as a match-everything root."""
    out_dir = tmp_path / "out"
    code = cli.main(
        ["--project", str(PROJECT_ROOT), "-o", str(out_dir), "--library-root", "", "-q"]
    )
    assert code == 0
    manifest = _manifest(out_dir)
    outside_root = [d for d in manifest["diagnostics"] if d["code"] == "outside_root"]
    assert len(outside_root) == 1

    # The default path-convention classification must still hold -- an empty
    # override must not silently reclassify every artifact as project-library.
    by_path = {a["location"]["relative_path"]: a for a in manifest["artifacts"]}
    assert (
        by_path["PLC_1/Program blocks/999_MISC/MotorSoftstart.xml"]["identity"]["origin"]
        == "user"
    )


def test_invalid_library_root_backslash_produces_outside_root_diagnostic(tmp_path):
    """A Windows-style backslash path must be rejected outright, not
    reinterpreted as POSIX separators -- under naive ``PurePosixPath``
    handling it becomes one opaque segment that silently matches nothing."""
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--project",
            str(PROJECT_ROOT),
            "-o",
            str(out_dir),
            "--library-root",
            "Types\\Blocks",
            "-q",
        ]
    )
    assert code == 0
    manifest = _manifest(out_dir)
    outside_root = [d for d in manifest["diagnostics"] if d["code"] == "outside_root"]
    assert len(outside_root) == 1


def test_invalid_library_root_drive_letter_produces_outside_root_diagnostic(tmp_path):
    """A Windows drive-letter path is not ``PurePosixPath.is_absolute()``
    under POSIX semantics, so it must be flagged by a dedicated check rather
    than silently accepted as a valid (but never-matching) relative path."""
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--project",
            str(PROJECT_ROOT),
            "-o",
            str(out_dir),
            "--library-root",
            "C:\\Lib",
            "-q",
        ]
    )
    assert code == 0
    manifest = _manifest(out_dir)
    outside_root = [d for d in manifest["diagnostics"] if d["code"] == "outside_root"]
    assert len(outside_root) == 1


def test_invalid_library_root_drive_letter_forward_slash_produces_outside_root_diagnostic(
    tmp_path,
):
    """Isolates the drive-letter check from the backslash check: a
    forward-slash drive-letter path has no backslash at all, so only the
    dedicated drive-letter-prefix regex can catch it."""
    out_dir = tmp_path / "out"
    code = cli.main(
        [
            "--project",
            str(PROJECT_ROOT),
            "-o",
            str(out_dir),
            "--library-root",
            "C:/Lib",
            "-q",
        ]
    )
    assert code == 0
    manifest = _manifest(out_dir)
    outside_root = [d for d in manifest["diagnostics"] if d["code"] == "outside_root"]
    assert len(outside_root) == 1


# --- manifest-write failure ---------------------------------------------------


def test_project_mode_manifest_write_failure_produces_clean_error_and_nonzero_exit(
    tmp_path, monkeypatch, capsys
):
    """``write_project_manifest`` deliberately propagates ``OSError`` (a
    read-only ``-o`` directory, permission denied, disk full, ...); ``_main_project``
    must translate that into a clean CLI error and a nonzero exit rather than
    letting the exception escape as an uncaught traceback. Uses the same
    ``Path.replace`` monkeypatch technique ``tests/test_project_emit.py``
    already uses to simulate the failure."""
    out_dir = tmp_path / "out"

    def _boom(self, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", _boom)

    code = cli.main(["--project", str(PROJECT_ROOT), "-o", str(out_dir), "-q"])

    assert code != 0
    err = capsys.readouterr().err
    assert "OUTPUT_FAILED" in err
    assert not (out_dir / "project-manifest.json").exists()


def test_project_mode_manifest_write_failure_leaves_no_orphaned_tmp_file(
    tmp_path, monkeypatch
):
    out_dir = tmp_path / "out"

    def _boom(self, target):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(Path, "replace", _boom)

    cli.main(["--project", str(PROJECT_ROOT), "-o", str(out_dir), "-q"])

    assert not (out_dir / ".project-manifest.json.tmp").exists()


# --- nonzero exit on any FAILED artifact --------------------------------------


def test_project_mode_returns_nonzero_when_an_artifact_fails(tmp_path):
    project_root = tmp_path / "broken_project"
    project_root.mkdir()
    (project_root / "bad.xml").write_text("<not><closed>", encoding="utf-8")

    out_dir = tmp_path / "out"
    code = cli.main(["--project", str(project_root), "-o", str(out_dir), "-q"])
    assert code == 1

    manifest = _manifest(out_dir)
    statuses = {a["status"] for a in manifest["artifacts"]}
    assert "failed" in statuses
