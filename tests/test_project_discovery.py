"""Tests for bounded, deterministic project-mode file discovery.

These exercise ``project_discovery.discover_project_files`` end-to-end
against a real filesystem tree (no mocked ``os``/native-handle primitives):
real directories, real oversized files, and -- where the host permits it --
real symlinks/junctions. This matches ``tests/test_input_policy.py``'s
"native-handle discovery" section, which does the same for the existing
hard-fail walkers.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from simaticml_decoder import input_policy
from simaticml_decoder.project_discovery import discover_project_files
from simaticml_decoder.project_model import DiagnosticCode, InputFormat, ProjectLimits

_XML_SUFFIXES = {".xml": InputFormat.SIMATICML_XML}


def test_discovery_is_relative_sorted_and_never_follows_a_symlink(tmp_path):
    """Adapted from the task brief's literal test: the brief's expected
    ``result.files`` list omits ``outside.xml`` even though it is a real,
    non-symlink, root-contained file that the walk's own plan-level global
    constraint ("process only regular files physically contained by the
    resolved project root") requires it to discover. That omission looks
    like an oversight in the brief rather than intended behavior, so this
    test asserts the corrected, spec-consistent expectation (``outside.xml``
    included) instead of reproducing the omission -- see the task report for
    the full reasoning.
    """
    root = tmp_path / "project"
    (root / "z").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "z" / "Second.xml").write_text("<Document />", encoding="utf-8")
    (root / "a" / "First.xml").write_text("<Document />", encoding="utf-8")
    (root / "outside.xml").write_text("<Document />", encoding="utf-8")
    try:
        (root / "link.xml").symlink_to(root / "outside.xml")
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits())

    assert [item.location.relative_path.as_posix() for item in result.files] == [
        "a/First.xml",
        "outside.xml",
        "z/Second.xml",
    ]
    assert [item.code for item in result.diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]
    assert all(isinstance(item.artifact, input_policy.InputArtifact) for item in result.files)
    for item in result.files:
        assert item.artifact.read_bytes(input_policy.InputLimits()) == b"<Document />"


def _make_windows_junction(link, target) -> bool:
    """Create a real NTFS directory junction without requiring the
    SeCreateSymbolicLinkPrivilege that ``os.symlink`` needs on Windows, so
    the reparse-point-skip path can be exercised for real (not skipped) on
    an unprivileged Windows dev box. Returns False if junction creation is
    unavailable for any reason (non-Windows, `mklink` missing, etc.)."""
    if sys.platform != "win32":
        return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def test_discovery_skips_a_real_directory_junction_without_entering_it(tmp_path):
    """Windows-only, real-reparse-point regression test: `entries()` with
    ``reject_reparse_points=False`` must still classify a junction as a
    reparse point (not silently walk into it as a normal directory), and the
    soft walker must never call ``open_child`` on it."""
    root = tmp_path / "project"
    real = tmp_path / "outside_tree"
    real.mkdir(parents=True)
    (real / "secret.xml").write_text("<Document />", encoding="utf-8")
    root.mkdir()
    (root / "kept.xml").write_text("<Document />", encoding="utf-8")
    link = root / "junction"

    if not _make_windows_junction(link, real):
        pytest.skip("directory junction creation unavailable on this host")

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits())

    assert [item.location.relative_path.as_posix() for item in result.files] == ["kept.xml"]
    assert [d.code for d in result.diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]


def test_discovery_enforces_file_count_limit(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "one.xml").write_text("<Document/>", encoding="utf-8")
    (root / "two.xml").write_text("<Document/>", encoding="utf-8")

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits(max_files=1))

    assert [item.location.relative_path.as_posix() for item in result.files] == ["one.xml"]
    assert [d.code for d in result.diagnostics] == [DiagnosticCode.FILE_COUNT_LIMIT]


def test_discovery_enforces_file_size_limit(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "small.xml").write_bytes(b"<Document/>")
    (root / "big.xml").write_bytes(b"x" * 64)

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits(max_file_bytes=16))

    assert [item.location.relative_path.as_posix() for item in result.files] == ["small.xml"]
    assert [d.code for d in result.diagnostics] == [DiagnosticCode.FILE_SIZE_LIMIT]


def test_discovery_enforces_total_size_budget(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.xml").write_bytes(b"x" * 10)
    (root / "b.xml").write_bytes(b"x" * 10)

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits(max_total_bytes=15))

    assert [item.location.relative_path.as_posix() for item in result.files] == ["a.xml"]
    assert [d.code for d in result.diagnostics] == [DiagnosticCode.TOTAL_SIZE_LIMIT]


def test_discovery_enforces_relative_depth_limit(tmp_path):
    root = tmp_path / "project"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "deep.xml").write_text("<Document/>", encoding="utf-8")
    (root / "top.xml").write_text("<Document/>", encoding="utf-8")

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits(max_relative_depth=1))

    assert [item.location.relative_path.as_posix() for item in result.files] == ["top.xml"]
    assert [d.code for d in result.diagnostics] == [DiagnosticCode.DEPTH_LIMIT]


def test_discovery_matches_suffixes_case_insensitively(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "Block.XML").write_text("<Document/>", encoding="utf-8")

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits())

    assert [item.location.relative_path.as_posix() for item in result.files] == ["Block.XML"]
    assert result.files[0].input_format == InputFormat.SIMATICML_XML
    assert result.diagnostics == ()


def test_discovery_reports_a_missing_root_as_a_diagnostic(tmp_path):
    missing = tmp_path / "does-not-exist"

    result = discover_project_files(missing, _XML_SUFFIXES, ProjectLimits())

    assert result.files == ()
    assert [d.code for d in result.diagnostics] == [DiagnosticCode.OUTSIDE_ROOT]


def test_discovered_file_size_matches_actual_bytes(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "sized.xml").write_bytes(b"<Document/>12345")

    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits())

    assert result.files[0].size == len(b"<Document/>12345")
