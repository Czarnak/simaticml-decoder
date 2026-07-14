"""Boundary tests for untrusted decoder inputs."""

from __future__ import annotations

import contextlib
import errno
import os
import stat
from pathlib import Path, PurePath
from types import SimpleNamespace

import pytest

from simaticml_decoder import cli, parse
from simaticml_decoder import input_policy
from simaticml_decoder.input_policy import (
    InputLimits,
    InputViolation,
    direct_input_artifact,
    discover_input_files,
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
    assert [path.name for path in discover_xml(tmp_path, recursive=True)] == [
        "a.xml",
        "b.xml",
        "c.xml",
    ]
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
    assert result.error.startswith("INPUT_REJECTED: linked.xml: symbolic links are not accepted")


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
        "Inputs_FB.s7res",
        "AlarmsContainer.s7res",
        "MotorSoftstart.s7res",
        "TIME_COUNTER_FB.s7res",
        "AnalogInput.s7res",
        "deviceState.s7res",
        "AnalogInputSettings.s7res",
        "UDT_Device.s7res",
    ):
        assert f"SD_RESOURCE_WITHOUT_DCL: {name}" in stderr


def test_cli_isolates_directory_discovery_rejection(monkeypatch, tmp_path, capsys):
    def reject(*_args, **_kwargs):
        raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")

    monkeypatch.setattr(cli, "discover", reject)

    assert cli.main([str(tmp_path)]) == 1
    assert "INPUT_REJECTED" in capsys.readouterr().err


def test_cli_isolates_fold_and_output_failures(monkeypatch, tmp_path):
    source = (
        Path(__file__).parent
        / "fixtures"
        / "SimaticML"
        / "PLC_1"
        / "Program blocks"
        / "100_Inputs"
        / "Inputs_FB.xml"
    )

    monkeypatch.setattr(cli.fold, "fold_block", lambda _doc: (_ for _ in ()).throw(RuntimeError()))
    assert cli.decode_file(source, tmp_path / "fold", "scl").error == (
        "DECODE_FAILED: Inputs_FB.xml: unable to fold input"
    )

    monkeypatch.undo()
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    assert cli.decode_file(source, blocked, "scl").error is not None

    monkeypatch.setattr(cli, "_write", lambda *_args: (_ for _ in ()).throw(OSError("denied")))
    assert cli.decode_file(source, tmp_path / "write", "scl").error == (
        "OUTPUT_FAILED: Inputs_FB.xml: denied"
    )


def test_cli_sanitizes_warning_output(capsys, tmp_path):
    outcome = cli.FileOutcome(
        source=tmp_path / "source.xml",
        status="ok",
        decoded=SimpleNamespace(
            name="block\nname", kind="FC", networks=[], warnings=["bad\nwarning"]
        ),
    )

    cli._report([outcome], input_root=None, quiet=False)

    stderr = capsys.readouterr().err
    assert "block name" in stderr
    assert "bad warning" in stderr


def test_discovered_artifact_is_relative(tmp_path):
    root = tmp_path / "root"
    source = root / "nested" / "block.xml"
    source.parent.mkdir(parents=True)
    source.write_text("<Document/>", encoding="utf-8")
    artifact = discover_input_files(root, recursive=True)[0]
    assert artifact.relative_path == PurePath("nested") / "block.xml"
    assert not artifact.relative_path.is_absolute()


def test_artifact_read_is_limited(tmp_path):
    source = tmp_path / "block.xml"
    source.write_bytes(b"x" * 11)
    with pytest.raises(InputViolation, match="file_too_large"):
        direct_input_artifact(source).read_bytes(InputLimits(max_file_bytes=10))


class _StubHandle:
    """Minimal stand-in for `windows_handles.NativeHandle` /
    `_PosixFileHandle`: exposes only the `read_limited`/`close` surface
    `_make_handle_reader` actually uses, so the reader closure's
    close-after-one-read behavior (Finding 1) can be verified directly and
    platform-independently."""

    def __init__(self, raw: bytes) -> None:
        self._raw = raw
        self.closed = False

    def read_limited(self, _limit: int) -> bytes:
        return self._raw

    def close(self) -> None:
        self.closed = True


def test_handle_reader_closes_the_handle_immediately_after_a_successful_read():
    handle = _StubHandle(b"<Document/>")
    reader = input_policy._make_handle_reader(handle)

    assert reader(InputLimits()) == b"<Document/>"
    assert handle.closed is True


def test_handle_reader_closes_the_handle_even_when_validation_raises():
    handle = _StubHandle(b"\xff\xfe")
    reader = input_policy._make_handle_reader(handle)

    with pytest.raises(InputViolation, match="invalid_encoding"):
        reader(InputLimits())

    assert handle.closed is True


def test_directory_discovery_fails_closed_without_dir_fd_support(monkeypatch, tmp_path):
    """Forces the POSIX branch (regardless of the host platform) and then
    forces `os.supports_dir_fd` empty, to exercise the fail-closed path that
    real dir_fd-relative traversal can't be end-to-end tested for on this
    machine."""
    (tmp_path / "block.xml").write_text("<Document/>", encoding="utf-8")
    monkeypatch.setattr(input_policy, "_use_windows_native_discovery", lambda: False)
    monkeypatch.setattr(input_policy.os, "supports_dir_fd", frozenset())

    with pytest.raises(InputViolation, match="unsupported_platform"):
        discover_input_files(tmp_path, recursive=True)


def test_cli_directory_rejects_when_dir_fd_support_is_unavailable(monkeypatch, tmp_path, capsys):
    (tmp_path / "block.xml").write_text("<Document/>", encoding="utf-8")
    monkeypatch.setattr(input_policy, "_use_windows_native_discovery", lambda: False)
    monkeypatch.setattr(input_policy.os, "supports_dir_fd", frozenset())

    assert cli.main([str(tmp_path), "-q"]) == 1
    assert "INPUT_REJECTED" in capsys.readouterr().err


# --- native-handle discovery: depth/file-count bounds (real, on-platform) --
#
# These run through whichever branch this host actually implements natively
# (Windows-native NT handles here; real dir_fd on a POSIX CI runner) -- no
# monkeypatching, so they are a genuine end-to-end exercise of the walk.


def test_discovery_enforces_traversal_depth_limit(tmp_path):
    nested = tmp_path / "root" / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "deep.xml").write_text("<Document/>", encoding="utf-8")

    with pytest.raises(InputViolation, match="traversal_too_deep"):
        discover_input_files(tmp_path / "root", recursive=True, limits=InputLimits(max_depth=1))


def test_discovery_enforces_file_count_limit(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.xml").write_text("<Document/>", encoding="utf-8")
    (root / "two.xml").write_text("<Document/>", encoding="utf-8")

    with pytest.raises(InputViolation, match="too_many_files"):
        discover_input_files(root, recursive=True, limits=InputLimits(max_files=1))


def test_discovery_skips_subdirectories_when_not_recursive(tmp_path):
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True)
    (root / "top.xml").write_text("<Document/>", encoding="utf-8")
    (root / "sub" / "nested.xml").write_text("<Document/>", encoding="utf-8")

    artifacts = discover_input_files(root, recursive=False)

    assert [str(a.relative_path) for a in artifacts] == ["top.xml"]


def test_discovery_flags_same_root_sd_declaration_without_a_second_filesystem_touch(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "paired.s7res").write_text("resource", encoding="utf-8")
    (root / "paired.s7dcl").write_text("declaration", encoding="utf-8")
    (root / "orphan.s7res").write_text("resource", encoding="utf-8")

    artifacts = {str(a.relative_path): a for a in discover_input_files(root, recursive=True)}

    assert artifacts["paired.s7res"].has_declaration is True
    assert artifacts["orphan.s7res"].has_declaration is False


# --- POSIX dir_fd walk, exercised via a fake filesystem -------------------
#
# This machine is Windows, so the real dir_fd branch (`_discover_posix` /
# `_walk_posix_directory`) can never actually run here: `discover_input_files`
# always takes the native-NT branch. The tests above cover that native branch
# for real. These tests instead fake out just the `os` primitives the POSIX
# walk calls (`os.open`, `os.stat`, `os.scandir`, `os.read`, `os.close`) with
# an in-memory tree, so the POSIX-specific logic -- dir_fd chaining, the
# lstat-before-open classification, the O_NOFOLLOW/ELOOP TOCTOU race handling,
# and the same-root .s7dcl pairing -- is exercised deterministically and
# platform-independently. It is a substitute for, not a replacement of, a real
# run on a POSIX CI runner (flagged in the task report).


class _FakePosixNode:
    """One entry in an in-memory fake filesystem tree.

    ``kind`` is one of ``"dir"``, ``"file"``, ``"symlink"``, ``"racy_file"``,
    or ``"racy_dir"``. The ``racy_*`` kinds report a safe type (regular file /
    directory) from ``stat()`` but always fail ``open()`` with ``ELOOP`` --
    simulating a rename/reparse-point swap that happens *after* the
    classifying lstat but *before* the open, which is exactly the race this
    module's O_NOFOLLOW-at-open-time design defends against.
    """

    def __init__(
        self, kind: str, children: dict[str, "_FakePosixNode"] | None = None, content: bytes = b""
    ) -> None:
        self.kind = kind
        self.children = children if children is not None else {}
        self.content = content


def _fake_dir(children: dict[str, "_FakePosixNode"]) -> _FakePosixNode:
    return _FakePosixNode("dir", children=children)


def _fake_file(content: bytes = b"<Document/>") -> _FakePosixNode:
    return _FakePosixNode("file", content=content)


def _fake_symlink() -> _FakePosixNode:
    return _FakePosixNode("symlink")


def _fake_racy_file() -> _FakePosixNode:
    return _FakePosixNode("racy_file", content=b"<Document/>")


def _fake_racy_dir() -> _FakePosixNode:
    return _FakePosixNode("racy_dir")


_FAKE_KIND_MODE = {
    "dir": stat.S_IFDIR,
    "file": stat.S_IFREG,
    "symlink": stat.S_IFLNK,
    "racy_file": stat.S_IFREG,
    "racy_dir": stat.S_IFDIR,
}


class _FakePosixFs:
    """Simulates dir_fd-relative ``os.open``/``os.stat``/``os.scandir``/
    ``os.read``/``os.close`` against an in-memory tree of ``_FakePosixNode``.
    """

    def __init__(self, root: _FakePosixNode) -> None:
        self._root = root
        self._nodes: dict[int, _FakePosixNode] = {}
        self._next_fd = 1000
        self.closed: set[int] = set()

    def _register(self, node: _FakePosixNode) -> int:
        fd = self._next_fd
        self._next_fd += 1
        self._nodes[fd] = node
        return fd

    def _child(self, dir_fd: int, name: str) -> _FakePosixNode:
        parent = self._nodes[dir_fd]
        child = parent.children.get(name)
        if child is None:
            raise FileNotFoundError(errno.ENOENT, "no such file or directory", name)
        return child

    def open(self, path: object, flags: int, dir_fd: int | None = None, **_kwargs: object) -> int:
        if dir_fd is None:
            return self._register(self._root)
        name = str(path)
        child = self._child(dir_fd, name)
        # "racy_*" always loses the TOCTOU race at open time, regardless of
        # flags. A plain "symlink" only fails when O_NOFOLLOW was requested
        # (matching real O_NOFOLLOW semantics).
        if child.kind in ("racy_file", "racy_dir") or (
            child.kind == "symlink" and flags & getattr(os, "O_NOFOLLOW", 0)
        ):
            raise OSError(errno.ELOOP, "too many levels of symbolic links", name)
        return self._register(child)

    def stat(
        self, name: str, *, dir_fd: int | None = None, follow_symlinks: bool = True
    ) -> os.stat_result:
        child = self._child(dir_fd, name)
        mode = _FAKE_KIND_MODE[child.kind] | 0o644
        return os.stat_result((mode, 0, 0, 1, 0, 0, len(child.content), 0, 0, 0))

    def scandir(self, dir_fd: int):
        parent = self._nodes[dir_fd]
        entries = [SimpleNamespace(name=name) for name in parent.children]
        return contextlib.nullcontext(entries)

    def read(self, fd: int, count: int) -> bytes:
        return self._nodes[fd].content[:count]

    def close(self, fd: int) -> None:
        self.closed.add(fd)


def _patch_posix_dir_fd(monkeypatch, fake: _FakePosixFs) -> None:
    monkeypatch.setattr(input_policy, "_use_windows_native_discovery", lambda: False)
    monkeypatch.setattr(input_policy.os, "open", fake.open)
    monkeypatch.setattr(input_policy.os, "stat", fake.stat)
    monkeypatch.setattr(input_policy.os, "scandir", fake.scandir)
    monkeypatch.setattr(input_policy.os, "read", fake.read)
    monkeypatch.setattr(input_policy.os, "close", fake.close)
    monkeypatch.setattr(input_policy.os, "O_NOFOLLOW", 0x1000, raising=False)
    monkeypatch.setattr(
        input_policy.os, "supports_dir_fd", frozenset({fake.open, fake.stat}), raising=False
    )
    monkeypatch.setattr(
        input_policy.os, "supports_follow_symlinks", frozenset({fake.stat}), raising=False
    )


def test_posix_walk_discovers_nested_files_through_dir_fd_chaining(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir(
            {
                "a.xml": _fake_file(b"<Document/>"),
                "nested": _fake_dir({"block.xml": _fake_file(b"<Document/>")}),
            }
        )
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    artifacts = discover_input_files(Path("root"), recursive=True)

    assert sorted(str(a.relative_path) for a in artifacts) == [
        "a.xml",
        str(PurePath("nested") / "block.xml"),
    ]
    for artifact in artifacts:
        assert artifact.read_bytes(InputLimits()) == b"<Document/>"
    # Root + the "nested" subdirectory get closed once fully walked, and each
    # file descriptor is released immediately after its own single read
    # (Finding 1) rather than staying open for the rest of the batch.
    assert len(fake.closed) == 4


def test_posix_walk_rejects_symlink_entries(monkeypatch):
    fake = _FakePosixFs(_fake_dir({"linked.xml": _fake_symlink()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    with pytest.raises(InputViolation, match="symlink_not_allowed"):
        discover_input_files(Path("root"), recursive=True)


def test_posix_walk_treats_a_toctou_rename_race_on_a_file_as_symlink_rejection(monkeypatch):
    """The lstat classifies ``race.xml`` as a plain regular file, but the
    subsequent O_NOFOLLOW open fails with ELOOP anyway -- simulating a
    rename/reparse-point swap in the narrow window between the two calls.
    The walk must fail closed, not silently follow."""
    fake = _FakePosixFs(_fake_dir({"race.xml": _fake_racy_file()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    with pytest.raises(InputViolation, match="symlink_not_allowed"):
        discover_input_files(Path("root"), recursive=True)


def test_posix_walk_treats_a_toctou_rename_race_on_a_directory_as_symlink_rejection(monkeypatch):
    fake = _FakePosixFs(_fake_dir({"race": _fake_racy_dir()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    with pytest.raises(InputViolation, match="symlink_not_allowed"):
        discover_input_files(Path("root"), recursive=True)


def test_posix_walk_enforces_file_count_limit(monkeypatch):
    fake = _FakePosixFs(_fake_dir({"one.xml": _fake_file(), "two.xml": _fake_file()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    with pytest.raises(InputViolation, match="too_many_files"):
        discover_input_files(Path("root"), recursive=True, limits=InputLimits(max_files=1))


def test_posix_walk_enforces_traversal_depth_limit(monkeypatch):
    fake = _FakePosixFs(_fake_dir({"sub": _fake_dir({"deep.xml": _fake_file()})}))
    _patch_posix_dir_fd(monkeypatch, fake)

    with pytest.raises(InputViolation, match="traversal_too_deep"):
        discover_input_files(Path("root"), recursive=True, limits=InputLimits(max_depth=0))


def test_posix_walk_skips_subdirectories_when_not_recursive(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir(
            {
                "top.xml": _fake_file(),
                "sub": _fake_dir({"nested.xml": _fake_file()}),
            }
        )
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    artifacts = discover_input_files(Path("root"), recursive=False)

    assert [str(a.relative_path) for a in artifacts] == ["top.xml"]


def test_posix_walk_flags_same_root_sd_declaration_without_touching_filesystem(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir(
            {
                "paired.s7res": _fake_file(b"resource"),
                "paired.s7dcl": _fake_file(b"declaration"),
                "orphan.s7res": _fake_file(b"resource"),
            }
        )
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    artifacts = {
        str(a.relative_path): a for a in discover_input_files(Path("root"), recursive=True)
    }

    assert artifacts["paired.s7res"].has_declaration is True
    assert artifacts["orphan.s7res"].has_declaration is False


def test_posix_walk_rejects_unavailable_root_open_as_input_violation(monkeypatch):
    fake = _FakePosixFs(_fake_dir({}))

    def _raise_open(*_args: object, **_kwargs: object) -> int:
        raise OSError(errno.EACCES, "permission denied")

    _patch_posix_dir_fd(monkeypatch, fake)
    monkeypatch.setattr(input_policy.os, "open", _raise_open)
    monkeypatch.setattr(
        input_policy.os, "supports_dir_fd", frozenset({_raise_open, fake.stat}), raising=False
    )

    with pytest.raises(InputViolation, match="unreadable_input"):
        discover_input_files(Path("root"), recursive=True)


# --- Windows soft-diagnostic walk (project mode), via a duck-typed stub ---
#
# `_walk_windows_softdiag` only ever calls `directory.entries(...)` and
# `directory.open_child(...)`; nothing else about `windows_handles.
# NativeDirectory` is required, so a minimal duck-typed stand-in lets the
# TOCTOU-race downgrade branches (an `open_child` call raising
# "symlink_not_allowed" for an entry `entries()` did *not* flag as a reparse
# point -- the enumerate-then-open race window `_reject_if_reparse_point`
# exists to close) be exercised directly and deterministically, the same way
# `_FakePosixFs` exercises the POSIX walker's equivalent race without a real
# race condition.


class _FakeNativeEntry:
    def __init__(self, name, *, is_directory=False, is_reparse_point=False, size=0):
        self.name = name
        self.is_directory = is_directory
        self.is_reparse_point = is_reparse_point
        self.size = size


class _FakeNativeHandle:
    def __init__(self, content: bytes = b"") -> None:
        self._content = content
        self.closed = False

    def read_limited(self, limit: int) -> bytes:
        return self._content[: limit + 1]

    def close(self) -> None:
        self.closed = True


class _FakeNativeDirectory:
    """Duck-typed stand-in for `windows_handles.NativeDirectory`, exposing
    only the `entries()`/`open_child()` surface `_walk_windows_softdiag`
    actually uses. `racy_names` simulates `open_child` losing a TOCTOU race
    against an entry `entries()` did not flag as a reparse point."""

    def __init__(self, entries, children=None, racy_names=frozenset()):
        self._entries = tuple(entries)
        self._children = children or {}
        self._racy_names = racy_names

    def entries(self, *, reject_reparse_points: bool = True):
        return self._entries

    def open_child(self, name: str, directory: bool):
        if name in self._racy_names:
            raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")
        return self._children[name]

    def __enter__(self):
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


def test_project_windows_walk_downgrades_a_toctou_file_open_race_to_a_soft_diagnostic():
    directory = _FakeNativeDirectory(
        entries=[
            _FakeNativeEntry("kept.xml", size=11),
            _FakeNativeEntry("race.xml", size=11),
        ],
        children={"kept.xml": _FakeNativeHandle(b"<Document/>")},
        racy_names={"race.xml"},
    )
    artifacts: list = []
    diagnostics: list = []
    state = input_policy._SoftWalkState()

    from simaticml_decoder.project_model import DiagnosticCode

    input_policy._walk_windows_softdiag(
        directory, PurePath(), 0, InputLimits(), 10_000, {".xml"}, artifacts, diagnostics, state
    )

    assert [str(a.relative_path) for a in artifacts] == ["kept.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]


def test_project_windows_walk_ignores_non_matching_suffixes_without_a_diagnostic():
    directory = _FakeNativeDirectory(
        entries=[
            _FakeNativeEntry("notes.txt", size=4),
            _FakeNativeEntry("kept.xml", size=11),
        ],
        children={"kept.xml": _FakeNativeHandle(b"<Document/>")},
    )
    artifacts: list = []
    diagnostics: list = []
    state = input_policy._SoftWalkState()

    input_policy._walk_windows_softdiag(
        directory, PurePath(), 0, InputLimits(), 10_000, {".xml"}, artifacts, diagnostics, state
    )

    assert [str(a.relative_path) for a in artifacts] == ["kept.xml"]
    assert diagnostics == []


def test_project_windows_walk_propagates_a_non_symlink_dir_open_failure():
    directory = _FakeNativeDirectory(
        entries=[_FakeNativeEntry("broken", is_directory=True)],
    )

    def _broken_open_child(*_args: object, **_kwargs: object):
        raise InputViolation("unreadable_input", "boom")

    directory.open_child = _broken_open_child
    artifacts: list = []
    diagnostics: list = []
    state = input_policy._SoftWalkState()

    with pytest.raises(InputViolation, match="unreadable_input"):
        input_policy._walk_windows_softdiag(
            directory, PurePath(), 0, InputLimits(), 10_000, {".xml"}, artifacts, diagnostics, state
        )


def test_project_windows_walk_propagates_a_non_symlink_file_open_failure():
    directory = _FakeNativeDirectory(
        entries=[_FakeNativeEntry("broken.xml", size=1)],
    )

    def _broken_open_child(*_args: object, **_kwargs: object):
        raise InputViolation("unreadable_input", "boom")

    directory.open_child = _broken_open_child
    artifacts: list = []
    diagnostics: list = []
    state = input_policy._SoftWalkState()

    with pytest.raises(InputViolation, match="unreadable_input"):
        input_policy._walk_windows_softdiag(
            directory, PurePath(), 0, InputLimits(), 10_000, {".xml"}, artifacts, diagnostics, state
        )


def test_project_windows_walk_halts_a_sibling_after_a_nested_global_breach():
    inner = _FakeNativeDirectory(
        entries=[
            _FakeNativeEntry("x.xml", size=1),
            _FakeNativeEntry("y.xml", size=1),
        ],
        children={"x.xml": _FakeNativeHandle(b"x"), "y.xml": _FakeNativeHandle(b"y")},
    )
    root = _FakeNativeDirectory(
        entries=[
            _FakeNativeEntry("a", is_directory=True),
            _FakeNativeEntry("b.xml", size=1),
        ],
        children={"a": inner, "b.xml": _FakeNativeHandle(b"b")},
    )
    artifacts: list = []
    diagnostics: list = []
    state = input_policy._SoftWalkState()

    from simaticml_decoder.project_model import DiagnosticCode

    input_policy._walk_windows_softdiag(
        root, PurePath(), 0, InputLimits(max_files=1), 10_000, {".xml"}, artifacts, diagnostics, state
    )

    assert [str(a.relative_path) for a in artifacts] == [str(PurePath("a") / "x.xml")]
    assert [d.code for d in diagnostics] == [DiagnosticCode.FILE_COUNT_LIMIT]


def test_project_windows_walk_downgrades_a_toctou_dir_open_race_to_a_soft_diagnostic():
    directory = _FakeNativeDirectory(
        entries=[
            _FakeNativeEntry("race", is_directory=True),
            _FakeNativeEntry("kept.xml", size=11),
        ],
        children={"kept.xml": _FakeNativeHandle(b"<Document/>")},
        racy_names={"race"},
    )
    artifacts: list = []
    diagnostics: list = []
    state = input_policy._SoftWalkState()

    from simaticml_decoder.project_model import DiagnosticCode

    input_policy._walk_windows_softdiag(
        directory, PurePath(), 0, InputLimits(), 10_000, {".xml"}, artifacts, diagnostics, state
    )

    assert [str(a.relative_path) for a in artifacts] == ["kept.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]


# --- POSIX dir_fd soft-diagnostic walk (project mode), also via the fake fs -
#
# `discover_project_artifacts`/`_walk_posix_softdiag` reuse the exact same
# dir_fd-relative primitives exercised above for the hard-fail walker
# (`_scandir_names`, `_lstat_child`, `_open_dir_child`, `_open_file_child`);
# this is a substitute for, not a replacement of, a real run on a POSIX CI
# runner, matching the existing hard-fail-walker fake-fs tests' own caveat.


def test_project_posix_walk_discovers_nested_files_and_never_halts_without_a_breach(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir(
            {
                "a.xml": _fake_file(b"<Document/>"),
                "nested": _fake_dir({"block.xml": _fake_file(b"<Document/>")}),
            }
        )
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 10_000
    )

    assert sorted(str(a.relative_path) for a in artifacts) == [
        "a.xml",
        str(PurePath("nested") / "block.xml"),
    ]
    assert diagnostics == ()
    for artifact in artifacts:
        assert artifact.read_bytes(InputLimits()) == b"<Document/>"


def test_project_posix_walk_reports_a_symlink_as_a_soft_diagnostic_not_a_raise(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir({"linked.xml": _fake_symlink(), "kept.xml": _fake_file(b"<Document/>")})
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["kept.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]


def test_project_posix_walk_downgrades_a_toctou_open_race_to_a_soft_diagnostic(monkeypatch):
    """Mirrors test_posix_walk_treats_a_toctou_rename_race_on_a_file_as_symlink_rejection,
    but for the soft walker: the lstat says "regular file", the O_NOFOLLOW
    open then fails with ELOOP anyway (simulated rename/reparse-point swap in
    the narrow window between the two calls) -- the soft walker must record a
    diagnostic and continue, not raise."""
    fake = _FakePosixFs(_fake_dir({"race.xml": _fake_racy_file(), "kept.xml": _fake_file()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["kept.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]


def test_project_posix_walk_downgrades_a_toctou_dir_open_race_to_a_soft_diagnostic(monkeypatch):
    """Mirrors test_posix_walk_treats_a_toctou_rename_race_on_a_directory_as_symlink_rejection
    for the soft walker: the lstat says "directory", `_open_dir_child`'s
    O_NOFOLLOW open then fails with ELOOP anyway."""
    fake = _FakePosixFs(_fake_dir({"race": _fake_racy_dir(), "kept.xml": _fake_file()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["kept.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.SYMLINK_SKIPPED]


def test_project_posix_walk_enforces_file_size_limit_per_file(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir({"small.xml": _fake_file(b"ok"), "big.xml": _fake_file(b"x" * 64)})
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(max_file_bytes=16), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["small.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.FILE_SIZE_LIMIT]


def test_project_posix_walk_enforces_total_size_budget_and_halts(monkeypatch):
    fake = _FakePosixFs(_fake_dir({"a.xml": _fake_file(b"x" * 10), "b.xml": _fake_file(b"x" * 10)}))
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 15
    )

    assert [str(a.relative_path) for a in artifacts] == ["a.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.TOTAL_SIZE_LIMIT]


def test_project_posix_walk_halts_a_sibling_after_a_nested_global_breach(monkeypatch):
    """Exercises the per-iteration halted-guard itself: the breach happens
    inside subdirectory "a", and once that recursive call returns, the
    parent directory's loop must skip its next sibling ("b.xml") without
    processing it -- rather than only the mid-recursion halt taking effect."""
    fake = _FakePosixFs(
        _fake_dir(
            {
                "a": _fake_dir({"x.xml": _fake_file(), "y.xml": _fake_file()}),
                "b.xml": _fake_file(),
            }
        )
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(max_files=1), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == [str(PurePath("a") / "x.xml")]
    assert [d.code for d in diagnostics] == [DiagnosticCode.FILE_COUNT_LIMIT]


def test_project_posix_walk_ignores_non_matching_suffixes_without_a_diagnostic(monkeypatch):
    fake = _FakePosixFs(_fake_dir({"notes.txt": _fake_file(b"hi"), "kept.xml": _fake_file()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["kept.xml"]
    assert diagnostics == ()


def test_project_posix_walk_propagates_a_non_symlink_dir_open_failure(monkeypatch):
    """Unlike a symlink race (downgraded to a diagnostic), a genuinely
    unexpected `_open_dir_child` failure must still propagate out of
    `_walk_posix_softdiag` itself -- it is `discover_project_artifacts`'s
    own outer try/except (tested separately below) that turns *that* into
    a final OUTSIDE_ROOT diagnostic, not the walker swallowing it quietly."""
    fake = _FakePosixFs(_fake_dir({"broken": _fake_dir({})}))
    _patch_posix_dir_fd(monkeypatch, fake)
    root_fd = input_policy._open_posix_root(Path("root"))

    def _raise_open(*_args: object, **_kwargs: object) -> int:
        raise InputViolation("unreadable_input", "permission denied")

    monkeypatch.setattr(input_policy, "_open_dir_child", _raise_open)

    with pytest.raises(InputViolation, match="unreadable_input"):
        input_policy._walk_posix_softdiag(
            root_fd, PurePath(), 0, InputLimits(), 10_000, {".xml"}, [], [], input_policy._SoftWalkState()
        )


def test_project_posix_walk_propagates_a_non_symlink_file_open_failure(monkeypatch):
    fake = _FakePosixFs(_fake_dir({"broken.xml": _fake_file()}))
    _patch_posix_dir_fd(monkeypatch, fake)
    root_fd = input_policy._open_posix_root(Path("root"))

    def _raise_open(*_args: object, **_kwargs: object) -> int:
        raise InputViolation("unreadable_input", "permission denied")

    monkeypatch.setattr(input_policy, "_open_file_child", _raise_open)

    with pytest.raises(InputViolation, match="unreadable_input"):
        input_policy._walk_posix_softdiag(
            root_fd, PurePath(), 0, InputLimits(), 10_000, {".xml"}, [], [], input_policy._SoftWalkState()
        )


def test_project_discover_artifacts_converts_any_deep_walk_failure_to_outside_root(monkeypatch):
    """`discover_project_artifacts`'s own outer try/except is a final safety
    net: even a genuinely unexpected failure deep inside the walk (not just
    a root-open failure) must never raise out of this function -- it is
    reported as a single OUTSIDE_ROOT diagnostic instead, with whatever was
    already discovered before the failure preserved."""
    fake = _FakePosixFs(_fake_dir({"a_kept.xml": _fake_file(), "z_broken.xml": _fake_file()}))
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    real_open_file_child = input_policy._open_file_child

    def _raise_for_broken(dir_fd: int, name: str) -> int:
        if name == "z_broken.xml":
            raise InputViolation("unreadable_input", "boom")
        return real_open_file_child(dir_fd, name)

    monkeypatch.setattr(input_policy, "_open_file_child", _raise_for_broken)

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["a_kept.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.OUTSIDE_ROOT]


def test_project_posix_walk_enforces_file_count_limit_and_halts(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir({"one.xml": _fake_file(), "two.xml": _fake_file(), "three.xml": _fake_file()})
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(max_files=1), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["one.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.FILE_COUNT_LIMIT]


def test_project_posix_walk_enforces_depth_limit_per_subtree_without_halting_siblings(monkeypatch):
    fake = _FakePosixFs(
        _fake_dir(
            {
                "top.xml": _fake_file(),
                "sub": _fake_dir({"deep.xml": _fake_file()}),
            }
        )
    )
    _patch_posix_dir_fd(monkeypatch, fake)

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(max_depth=0), 10_000
    )

    assert [str(a.relative_path) for a in artifacts] == ["top.xml"]
    assert [d.code for d in diagnostics] == [DiagnosticCode.DEPTH_LIMIT]


def test_project_posix_walk_reports_missing_root_as_outside_root_diagnostic(monkeypatch):
    monkeypatch.setattr(input_policy, "_use_windows_native_discovery", lambda: False)
    monkeypatch.setattr(input_policy.os, "supports_dir_fd", frozenset())

    from simaticml_decoder.project_model import DiagnosticCode

    artifacts, diagnostics = input_policy.discover_project_artifacts(
        Path("root"), {".xml"}, InputLimits(), 10_000
    )

    assert artifacts == ()
    assert [d.code for d in diagnostics] == [DiagnosticCode.OUTSIDE_ROOT]
