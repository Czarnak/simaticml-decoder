"""Bounded, deterministic handling of untrusted decoder inputs."""

from __future__ import annotations

import errno
import os
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path, PurePath, PurePosixPath
from xml.etree import ElementTree as ET

from .project_model import DiagnosticCode, ProjectDiagnostic, SourceLocation


@dataclass(frozen=True)
class InputLimits:
    """Published limits for one XML input and one discovered input tree."""

    max_file_bytes: int = 10 * 1024 * 1024
    max_files: int = 10_000
    max_depth: int = 32
    max_xml_elements: int = 100_000
    max_xml_depth: int = 256
    max_attributes_per_element: int = 100
    max_text_chars_per_element: int = 1_048_576
    max_flgnet_networks: int = 1_000


@dataclass(frozen=True)
class InputArtifact:
    """Immutable artifact representing a discovered or direct input file.

    ``has_declaration`` is only meaningful for ``.s7res`` artifacts: it
    records whether a same-root ``.s7dcl`` sibling was observed during the
    same directory listing that discovered this file, so
    ``validate_artifact_format`` never has to re-touch the filesystem to
    answer that question.
    """

    relative_path: PurePath
    suffix: str
    _reader: Callable[[InputLimits], bytes] = field(repr=False, compare=False)
    has_declaration: bool = False
    size: int = 0
    """Byte size observed *during the same walk* that produced this artifact
    (from the native directory listing on Windows, or the classifying
    `os.stat` on POSIX) -- never a separate, later filesystem touch. Only
    populated by `discover_project_artifacts`'s soft-diagnostic walk; the
    existing hard-fail walkers and `direct_input_artifact` leave this at the
    default `0` since none of their callers need it."""

    def read_bytes(self, limits: InputLimits) -> bytes:
        """Read and validate the file content as bytes."""
        return self._reader(limits)


class InputViolation(ValueError):
    """A stable, safe-to-display input boundary rejection."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


DEFAULT_LIMITS = InputLimits()


def direct_input_artifact(path: Path) -> InputArtifact:
    """Build an InputArtifact for a direct CLI input file."""

    def reader(limits: InputLimits) -> bytes:
        """Reader closure that validates and reads the file."""
        text = read_xml(path, limits)
        return text.encode("utf-8")

    return InputArtifact(
        relative_path=PurePath(path.name),
        suffix=path.suffix.lower(),
        _reader=reader,
    )


def safe_text(value: object, *, limit: int = 160) -> str:
    """Return untrusted text as one bounded terminal line."""
    visible = "".join(char if char >= " " and char != "\x7f" else " " for char in str(value))
    flattened = " ".join(visible.split())
    if len(flattened) <= limit:
        return flattened
    return f"{flattened[: limit - 1]}…"


def validate_input_file(source: Path, limits: InputLimits = DEFAULT_LIMITS) -> None:
    """Reject unsupported, linked, or oversized direct input before parsing."""
    info = _regular_lstat(source)
    _validate_format(source)
    if info.st_size > limits.max_file_bytes:
        raise InputViolation("file_too_large", "input exceeds the configured byte limit")


def read_xml(source: Path, limits: InputLimits = DEFAULT_LIMITS) -> str:
    """Return validated XML text from a descriptor pinned to the checked file."""
    before = _regular_lstat(source)
    _validate_format(source)
    if before.st_size > limits.max_file_bytes:
        raise InputViolation("file_too_large", "input exceeds the configured byte limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError as exc:
        raise InputViolation("unreadable_input", safe_text(exc)) from exc
    try:
        opened = os.fstat(descriptor)
        if not os.path.samestat(before, opened):
            raise InputViolation("input_changed", "input changed while it was being opened")
        if opened.st_size > limits.max_file_bytes:
            raise InputViolation("file_too_large", "input exceeds the configured byte limit")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(limits.max_file_bytes + 1)
    except OSError as exc:
        raise InputViolation("unreadable_input", safe_text(exc)) from exc
    finally:
        os.close(descriptor)
    return _decode_and_validate_xml_text(raw, limits)


def _decode_and_validate_xml_text(raw: bytes, limits: InputLimits) -> str:
    """Shared tail of ``read_xml``: bytes already read from a trusted, already
    pinned/opened source -> validated XML text. No filesystem access here, so
    this is safe to reuse from handle-backed reader closures that never touch
    a path at all.
    """
    if len(raw) > limits.max_file_bytes:
        raise InputViolation("file_too_large", "input exceeds the configured byte limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputViolation("invalid_encoding", "input is not valid UTF-8") from exc
    declaration = text.casefold()
    if "<!doctype" in declaration or "<!entity" in declaration:
        raise InputViolation(
            "xml_forbidden_declaration", "DTD and entity declarations are not accepted"
        )
    _validate_xml_complexity(text, limits)
    return text


def validate_artifact_format(artifact: InputArtifact) -> None:
    """Validate an InputArtifact's format using only data captured at
    discovery time (``artifact.has_declaration``) -- never the filesystem.
    """
    suffix = artifact.suffix
    if suffix == ".s7res":
        if not artifact.has_declaration:
            raise InputViolation(
                "SD_RESOURCE_WITHOUT_DCL",
                "SIMATIC SD resource has no same-root .s7dcl declaration",
            )
        raise InputViolation("unsupported_format", "SIMATIC SD decoding is not implemented")
    if suffix == ".s7dcl":
        raise InputViolation("unsupported_format", "SIMATIC SD decoding is not implemented")
    if suffix != ".xml":
        raise InputViolation(
            "unsupported_format", "only exported SimaticML .xml files are accepted"
        )


def _validate_format(source: Path) -> None:
    suffix = source.suffix.lower()
    if suffix == ".s7res":
        declaration = source.with_suffix(".s7dcl")
        if not _is_regular_file(declaration):
            raise InputViolation(
                "SD_RESOURCE_WITHOUT_DCL",
                "SIMATIC SD resource has no same-root .s7dcl declaration",
            )
        raise InputViolation("unsupported_format", "SIMATIC SD decoding is not implemented")
    if suffix == ".s7dcl":
        raise InputViolation("unsupported_format", "SIMATIC SD decoding is not implemented")
    if suffix != ".xml":
        raise InputViolation(
            "unsupported_format", "only exported SimaticML .xml files are accepted"
        )


def discover_xml(root: Path, recursive: bool, limits: InputLimits = DEFAULT_LIMITS) -> list[Path]:
    """Discover regular XML files without following links, bounded and sorted."""
    return _discover(root, recursive, limits, {".xml"})


_ARTIFACT_SUFFIXES = {".xml", ".s7dcl", ".s7res"}


def discover_input_files(
    root: Path, recursive: bool, limits: InputLimits = DEFAULT_LIMITS
) -> tuple[InputArtifact, ...]:
    """Discover XML and SIMATIC SD inputs so unsupported files remain visible.

    Every returned artifact's reader consumes only a handle/descriptor opened
    *during this same walk* -- `windows_handles.NativeDirectory`/`NativeHandle`
    on Windows, or `dir_fd` + `O_NOFOLLOW` opens on POSIX -- never a path
    re-opened by name. A rename or reparse-point swap performed after
    discovery therefore cannot redirect a later ``artifact.read_bytes()``
    call: the handle already points at the original file-system object.

    Platforms that cannot provide descriptor-relative traversal fail closed
    with ``InputViolation("unsupported_platform", ...)`` rather than falling
    back to unsafe path-based re-resolution.
    """
    if _use_windows_native_discovery():
        return _discover_windows(root, recursive, limits, _ARTIFACT_SUFFIXES)
    return _discover_posix(root, recursive, limits, _ARTIFACT_SUFFIXES)


def _use_windows_native_discovery() -> bool:
    """Extracted so tests can force the POSIX branch via monkeypatching
    without touching the real ``sys.platform``."""
    return sys.platform == "win32"


def _make_handle_reader(handle: object) -> Callable[[InputLimits], bytes]:
    """Reader closure over an already-open handle/descriptor (never a path).

    Works for both `windows_handles.NativeHandle` and the POSIX
    `_PosixFileHandle` below -- both expose `read_limited(limit)` and
    `close()`. `read_bytes()` (and therefore this closure) is only ever
    invoked once per artifact (see `cli.decode_artifact`), so the handle is
    released immediately after that one read -- whether it succeeds or
    raises -- instead of staying open for the rest of the batch. Both handle
    types' `close()` is idempotent and safe to call again from `__del__`.
    """

    def reader(limits: InputLimits) -> bytes:
        try:
            raw = handle.read_limited(limits.max_file_bytes)
            return _decode_and_validate_xml_text(raw, limits).encode("utf-8")
        finally:
            handle.close()

    return reader


# --- Windows: native NT handle-anchored walk ---------------------------------


def _discover_windows(
    root: Path, recursive: bool, limits: InputLimits, suffixes: set[str]
) -> tuple[InputArtifact, ...]:
    from . import windows_handles  # Windows-only module; import lazily.

    artifacts: list[InputArtifact] = []
    counter = [0]
    with windows_handles.NativeDirectory.open_root(root) as root_dir:
        _walk_windows_directory(
            root_dir, PurePath(), 0, recursive, limits, suffixes, artifacts, counter
        )
    return tuple(artifacts)


def _walk_windows_directory(
    directory: object,
    relative_prefix: PurePath,
    depth: int,
    recursive: bool,
    limits: InputLimits,
    suffixes: set[str],
    artifacts: list[InputArtifact],
    counter: list[int],
) -> None:
    """Recurse one native directory handle at a time.

    `directory.entries()` is already sorted and already rejects any reparse
    point among its immediate children (Task 2's contract), so this walk only
    has to handle depth/file-count bounds and child opens.
    """
    entries = directory.entries()
    dcl_stems = {
        PurePath(entry.name).stem
        for entry in entries
        if not entry.is_directory and PurePath(entry.name).suffix.lower() == ".s7dcl"
    }
    for entry in entries:
        if entry.is_directory:
            if not recursive:
                continue
            if depth + 1 > limits.max_depth:
                raise InputViolation("traversal_too_deep", "input tree exceeds the depth limit")
            with directory.open_child(entry.name, directory=True) as child_dir:
                _walk_windows_directory(
                    child_dir,
                    relative_prefix / entry.name,
                    depth + 1,
                    recursive,
                    limits,
                    suffixes,
                    artifacts,
                    counter,
                )
            continue
        suffix = PurePath(entry.name).suffix.lower()
        if suffix not in suffixes:
            continue
        counter[0] += 1
        if counter[0] > limits.max_files:
            raise InputViolation("too_many_files", "input tree exceeds the file-count limit")
        handle = directory.open_child(entry.name, directory=False)
        has_declaration = suffix == ".s7res" and PurePath(entry.name).stem in dcl_stems
        artifacts.append(
            InputArtifact(
                relative_path=relative_prefix / entry.name,
                suffix=suffix,
                _reader=_make_handle_reader(handle),
                has_declaration=has_declaration,
            )
        )


# --- POSIX: dir_fd + O_NOFOLLOW walk ------------------------------------------


class _PosixFileHandle:
    """A POSIX file descriptor opened relative to its parent directory's own
    descriptor (``dir_fd``) with ``O_NOFOLLOW``. Read exactly once by the
    artifact's reader closure; never reopened by path. Mirrors
    `windows_handles.NativeHandle`'s close/`__del__` safety net.
    """

    __slots__ = ("_fd",)

    def __init__(self, fd: int) -> None:
        self._fd: int | None = fd

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

    def read_limited(self, limit: int) -> bytes:
        """Read at most `limit + 1` bytes so callers can detect oversized
        input without reading the full (potentially huge) file."""
        if self._fd is None:
            raise InputViolation("unreadable_input", "file descriptor is already closed")
        try:
            return os.read(self._fd, limit + 1)
        except OSError as exc:
            raise InputViolation("unreadable_input", safe_text(exc)) from exc


def _dir_fd_available() -> bool:
    """Whether this platform/Python build can do descriptor-relative,
    symlink-rejecting directory traversal at all. If not, directory discovery
    must fail closed rather than fall back to path-based re-resolution.
    """
    return (
        os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.stat in os.supports_follow_symlinks
        and hasattr(os, "O_NOFOLLOW")
    )


def _discover_posix(
    root: Path, recursive: bool, limits: InputLimits, suffixes: set[str]
) -> tuple[InputArtifact, ...]:
    if not _dir_fd_available():
        raise InputViolation(
            "unsupported_platform",
            "directory discovery requires descriptor-relative filesystem support",
        )
    artifacts: list[InputArtifact] = []
    counter = [0]
    root_fd = _open_posix_root(root)
    try:
        _walk_posix_directory(
            root_fd, PurePath(), 0, recursive, limits, suffixes, artifacts, counter
        )
    finally:
        os.close(root_fd)
    return tuple(artifacts)


def _open_posix_root(root: Path) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_DIRECTORY", 0)
    try:
        return os.open(root, flags)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise InputViolation("symlink_not_allowed", "symbolic links are not accepted") from exc
        raise InputViolation("unreadable_input", safe_text(exc)) from exc


def _scandir_names(dir_fd: int) -> list[str]:
    try:
        with os.scandir(dir_fd) as scan:
            names = [entry.name for entry in scan]
    except OSError as exc:
        raise InputViolation("unreadable_input", safe_text(exc)) from exc
    return sorted(names)


def _lstat_child(dir_fd: int, name: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError as exc:
        raise InputViolation("unreadable_input", safe_text(exc)) from exc


def _open_dir_child(dir_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_DIRECTORY", 0)
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise InputViolation("symlink_not_allowed", "symbolic links are not accepted") from exc
        raise InputViolation("unreadable_input", safe_text(exc)) from exc


def _open_file_child(dir_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise InputViolation("symlink_not_allowed", "symbolic links are not accepted") from exc
        raise InputViolation("unreadable_input", safe_text(exc)) from exc


def _walk_posix_directory(
    dir_fd: int,
    relative_prefix: PurePath,
    depth: int,
    recursive: bool,
    limits: InputLimits,
    suffixes: set[str],
    artifacts: list[InputArtifact],
    counter: list[int],
) -> None:
    """Recurse one dir_fd at a time, classifying children via an O_NOFOLLOW
    lstat-equivalent (`os.stat(..., follow_symlinks=False)`) before ever
    opening them, so entries we are going to skip are never opened at all
    (no accidental blocking open on a FIFO/special file, no unnecessary
    symlink-following opportunity). Only entries we keep -- a subdirectory to
    recurse into, or a matching file to capture a handle for -- get an actual
    `O_NOFOLLOW` open, which closes the narrow TOCTOU window between the
    lstat and the open.
    """
    names = _scandir_names(dir_fd)
    infos = {name: _lstat_child(dir_fd, name) for name in names}
    dcl_stems = {
        PurePath(name).stem
        for name, info in infos.items()
        if stat.S_ISREG(info.st_mode) and PurePath(name).suffix.lower() == ".s7dcl"
    }
    for name in names:
        info = infos[name]
        if stat.S_ISLNK(info.st_mode):
            raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")
        if stat.S_ISDIR(info.st_mode):
            if not recursive:
                continue
            if depth + 1 > limits.max_depth:
                raise InputViolation("traversal_too_deep", "input tree exceeds the depth limit")
            child_fd = _open_dir_child(dir_fd, name)
            try:
                _walk_posix_directory(
                    child_fd,
                    relative_prefix / name,
                    depth + 1,
                    recursive,
                    limits,
                    suffixes,
                    artifacts,
                    counter,
                )
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        suffix = PurePath(name).suffix.lower()
        if suffix not in suffixes:
            continue
        counter[0] += 1
        if counter[0] > limits.max_files:
            raise InputViolation("too_many_files", "input tree exceeds the file-count limit")
        has_declaration = suffix == ".s7res" and PurePath(name).stem in dcl_stems
        file_fd = _open_file_child(dir_fd, name)
        artifacts.append(
            InputArtifact(
                relative_path=relative_prefix / name,
                suffix=suffix,
                _reader=_make_handle_reader(_PosixFileHandle(file_fd)),
                has_declaration=has_declaration,
            )
        )


# --- Project-mode: soft-diagnostic siblings of the walkers above -------------
#
# Same handle-anchored, TOCTOU-resistant traversal as `_walk_windows_directory`
# / `_walk_posix_directory` / `discover_input_files` above -- native NT
# handles on Windows, `dir_fd` + `O_NOFOLLOW` on POSIX, every child opened
# relative to its parent's own already-open handle, never by re-resolving a
# composed path. The only difference is failure policy: a reparse point,
# depth breach, file-count breach, or size breach records a `ProjectDiagnostic`
# and the walk continues (skipping just the offending item/subtree), instead
# of raising and aborting the whole walk. `_walk_windows_directory`,
# `_walk_posix_directory`, and `discover_input_files` above are untouched by
# this section.


class _SoftWalkState:
    """Mutable accumulator threaded through the soft-diagnostic walk.

    Not exported -- purely internal bookkeeping for
    `discover_project_artifacts`, extending the existing hard-fail walkers'
    single-counter (`counter: list[int]`) pattern to the three values a
    *soft* walk needs to track: how many matching files have been kept, how
    many bytes they total, and whether a global (file-count/total-size)
    budget has already been exceeded -- in which case every remaining call
    frame returns immediately without recording further diagnostics.
    """

    __slots__ = ("file_count", "total_bytes", "halted")

    def __init__(self) -> None:
        self.file_count = 0
        self.total_bytes = 0
        self.halted = False


def _project_diagnostic(
    code: DiagnosticCode, relative_path: PurePath, message: str, *, severity: str = "warning"
) -> ProjectDiagnostic:
    """Build a `ProjectDiagnostic` for a location discovered during this
    walk, normalizing `relative_path` to posix separators the way
    `SourceLocation.relative_path` (a `PurePosixPath`) requires."""
    return ProjectDiagnostic(
        code=code,
        severity=severity,
        message=message,
        location=SourceLocation(PurePosixPath(relative_path.as_posix())),
    )


def _walk_windows_softdiag(
    directory: object,
    relative_prefix: PurePath,
    depth: int,
    limits: InputLimits,
    max_total_bytes: int,
    suffixes: set[str],
    artifacts: list[InputArtifact],
    diagnostics: list[ProjectDiagnostic],
    state: _SoftWalkState,
) -> None:
    """Mirrors `_walk_windows_directory`, using the same `NativeDirectory`
    handle-relative `entries()`/`open_child()` shape, but calls
    `entries(reject_reparse_points=False)` so one reparse point among this
    directory's children does not discard the rest of the listing. Every
    kept file's handle is still opened via `directory.open_child(...)` --
    relative to this directory's own already-open handle -- exactly as in
    the hard-fail walker; `open_child`'s own post-open reparse-point re-check
    (closing the enumerate-then-open race) still applies unconditionally, so
    a race that slips past the `is_reparse_point` flag is still caught and
    downgraded to a diagnostic here rather than silently followed.

    Note: this function is only ever entered (top-level or recursively) with
    `state.halted` already `False` -- the per-iteration guard below is what
    actually stops a halted walk from recursing further, so there is no
    separate top-of-function guard to duplicate that check.
    """
    entries = directory.entries(reject_reparse_points=False)
    for entry in entries:
        if state.halted:
            return
        child_relative = relative_prefix / entry.name
        if entry.is_reparse_point:
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.SYMLINK_SKIPPED,
                    child_relative,
                    "symbolic links and other reparse points are not followed",
                )
            )
            continue
        if entry.is_directory:
            if depth + 1 > limits.max_depth:
                diagnostics.append(
                    _project_diagnostic(
                        DiagnosticCode.DEPTH_LIMIT,
                        child_relative,
                        "directory exceeds the configured relative depth limit "
                        "and was not entered",
                    )
                )
                continue
            try:
                with directory.open_child(entry.name, directory=True) as child_dir:
                    _walk_windows_softdiag(
                        child_dir,
                        child_relative,
                        depth + 1,
                        limits,
                        max_total_bytes,
                        suffixes,
                        artifacts,
                        diagnostics,
                        state,
                    )
            except InputViolation as exc:
                if exc.code != "symlink_not_allowed":
                    raise
                diagnostics.append(
                    _project_diagnostic(DiagnosticCode.SYMLINK_SKIPPED, child_relative, exc.message)
                )
            continue
        suffix = PurePath(entry.name).suffix.lower()
        if suffix not in suffixes:
            continue
        if state.file_count >= limits.max_files:
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.FILE_COUNT_LIMIT,
                    child_relative,
                    "project tree exceeds the configured file-count limit; "
                    "remaining files were not discovered",
                    severity="error",
                )
            )
            state.halted = True
            return
        if entry.size > limits.max_file_bytes:
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.FILE_SIZE_LIMIT,
                    child_relative,
                    "file exceeds the configured per-file byte limit and was skipped",
                )
            )
            continue
        if state.total_bytes + entry.size > max_total_bytes:
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.TOTAL_SIZE_LIMIT,
                    child_relative,
                    "project tree exceeds the configured total-byte budget; "
                    "remaining files were not discovered",
                    severity="error",
                )
            )
            state.halted = True
            return
        try:
            handle = directory.open_child(entry.name, directory=False)
        except InputViolation as exc:
            if exc.code != "symlink_not_allowed":
                raise
            diagnostics.append(
                _project_diagnostic(DiagnosticCode.SYMLINK_SKIPPED, child_relative, exc.message)
            )
            continue
        state.file_count += 1
        state.total_bytes += entry.size
        artifacts.append(
            InputArtifact(
                relative_path=child_relative,
                suffix=suffix,
                _reader=_make_handle_reader(handle),
                size=entry.size,
            )
        )


def _walk_posix_softdiag(
    dir_fd: int,
    relative_prefix: PurePath,
    depth: int,
    limits: InputLimits,
    max_total_bytes: int,
    suffixes: set[str],
    artifacts: list[InputArtifact],
    diagnostics: list[ProjectDiagnostic],
    state: _SoftWalkState,
) -> None:
    """Mirrors `_walk_posix_directory`, reusing its exact `dir_fd`/
    `O_NOFOLLOW` primitives (`_scandir_names`, `_lstat_child`,
    `_open_dir_child`, `_open_file_child`) unchanged. The lstat-based
    classification already lets us skip a symlink without opening it at all;
    `_open_dir_child`/`_open_file_child`'s `O_NOFOLLOW` still independently
    rejects a TOCTOU-raced rename (lstat said "regular", the open's ELOOP
    says otherwise) -- that race is caught here too and downgraded to a
    diagnostic instead of raising.

    Note: as with `_walk_windows_softdiag`, this function is only ever
    entered with `state.halted` already `False`; the per-iteration guard
    below is what stops a halted walk from recursing further.
    """
    names = _scandir_names(dir_fd)
    infos = {name: _lstat_child(dir_fd, name) for name in names}
    for name in names:
        if state.halted:
            return
        info = infos[name]
        child_relative = relative_prefix / name
        if stat.S_ISLNK(info.st_mode):
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.SYMLINK_SKIPPED,
                    child_relative,
                    "symbolic links and other reparse points are not followed",
                )
            )
            continue
        if stat.S_ISDIR(info.st_mode):
            if depth + 1 > limits.max_depth:
                diagnostics.append(
                    _project_diagnostic(
                        DiagnosticCode.DEPTH_LIMIT,
                        child_relative,
                        "directory exceeds the configured relative depth limit "
                        "and was not entered",
                    )
                )
                continue
            try:
                child_fd = _open_dir_child(dir_fd, name)
            except InputViolation as exc:
                if exc.code != "symlink_not_allowed":
                    raise
                diagnostics.append(
                    _project_diagnostic(DiagnosticCode.SYMLINK_SKIPPED, child_relative, exc.message)
                )
                continue
            try:
                _walk_posix_softdiag(
                    child_fd,
                    child_relative,
                    depth + 1,
                    limits,
                    max_total_bytes,
                    suffixes,
                    artifacts,
                    diagnostics,
                    state,
                )
            finally:
                os.close(child_fd)
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        suffix = PurePath(name).suffix.lower()
        if suffix not in suffixes:
            continue
        if state.file_count >= limits.max_files:
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.FILE_COUNT_LIMIT,
                    child_relative,
                    "project tree exceeds the configured file-count limit; "
                    "remaining files were not discovered",
                    severity="error",
                )
            )
            state.halted = True
            return
        size = info.st_size
        if size > limits.max_file_bytes:
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.FILE_SIZE_LIMIT,
                    child_relative,
                    "file exceeds the configured per-file byte limit and was skipped",
                )
            )
            continue
        if state.total_bytes + size > max_total_bytes:
            diagnostics.append(
                _project_diagnostic(
                    DiagnosticCode.TOTAL_SIZE_LIMIT,
                    child_relative,
                    "project tree exceeds the configured total-byte budget; "
                    "remaining files were not discovered",
                    severity="error",
                )
            )
            state.halted = True
            return
        try:
            file_fd = _open_file_child(dir_fd, name)
        except InputViolation as exc:
            if exc.code != "symlink_not_allowed":
                raise
            diagnostics.append(
                _project_diagnostic(DiagnosticCode.SYMLINK_SKIPPED, child_relative, exc.message)
            )
            continue
        state.file_count += 1
        state.total_bytes += size
        artifacts.append(
            InputArtifact(
                relative_path=child_relative,
                suffix=suffix,
                _reader=_make_handle_reader(_PosixFileHandle(file_fd)),
                size=size,
            )
        )


def discover_project_artifacts(
    root: Path, suffixes: set[str], limits: InputLimits, max_total_bytes: int
) -> tuple[tuple[InputArtifact, ...], tuple[ProjectDiagnostic, ...]]:
    """Handle-anchored sibling of `discover_input_files()` for project mode:
    same TOCTOU-resistant traversal (native NT handles on Windows, `dir_fd` +
    `O_NOFOLLOW` on POSIX), soft per-item diagnostics instead of hard
    failure, delegating to `_walk_windows_softdiag`/`_walk_posix_softdiag`.

    Returns raw `InputArtifact`s; `project_discovery.py` wraps these into
    `DiscoveredFile` -- this function stays free of project-shaped types
    beyond the `ProjectDiagnostic` it already needs to report violations.

    `max_total_bytes` is accepted as a plain `int` (not folded into
    `InputLimits`, which has no total-budget concept and is shared with the
    directory-mode hard-fail walkers) so the running byte total can halt the
    walk itself -- bounding how much this call opens handles for -- rather
    than only being checked after the fact by the caller once the whole
    walk (and every handle it opened) already exists.

    Always recurses (there is no `recursive=False` project-mode concept);
    `limits.max_depth` bounds nesting instead.

    This function never raises. The two soft walkers already downgrade the
    breach types they know about (reparse point, depth, file-count,
    file-size, total-size) to per-item diagnostics without raising. As a
    final safety net, any *other* `InputViolation` that still escapes --
    whether the root itself could not be safely opened at all (missing
    root, root is a symlink/reparse point, unsupported platform) or an
    unexpected failure occurred deep inside the recursive walk -- is caught
    here and appended as one final `ProjectDiagnostic(code=OUTSIDE_ROOT,
    ...)` to whatever artifacts/diagnostics had already been accumulated,
    instead of propagating out of this call.
    """
    artifacts: list[InputArtifact] = []
    diagnostics: list[ProjectDiagnostic] = []
    state = _SoftWalkState()
    try:
        if _use_windows_native_discovery():
            from . import windows_handles

            with windows_handles.NativeDirectory.open_root(root) as root_dir:
                _walk_windows_softdiag(
                    root_dir,
                    PurePath(),
                    0,
                    limits,
                    max_total_bytes,
                    suffixes,
                    artifacts,
                    diagnostics,
                    state,
                )
        else:
            if not _dir_fd_available():
                raise InputViolation(
                    "unsupported_platform",
                    "directory discovery requires descriptor-relative filesystem support",
                )
            root_fd = _open_posix_root(root)
            try:
                _walk_posix_softdiag(
                    root_fd,
                    PurePath(),
                    0,
                    limits,
                    max_total_bytes,
                    suffixes,
                    artifacts,
                    diagnostics,
                    state,
                )
            finally:
                os.close(root_fd)
    except InputViolation as exc:
        diagnostics.append(
            _project_diagnostic(
                DiagnosticCode.OUTSIDE_ROOT,
                PurePath(),
                safe_text(f"{exc.code}: {exc.message}"),
                severity="error",
            )
        )
        return tuple(artifacts), tuple(diagnostics)
    return tuple(artifacts), tuple(diagnostics)


def _discover(root: Path, recursive: bool, limits: InputLimits, suffixes: set[str]) -> list[Path]:
    pending: list[tuple[Path, int]] = [(root, 0)]
    found: list[Path] = []
    while pending:
        directory, depth = pending.pop()
        before = _directory_lstat(directory)
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise InputViolation("unreadable_input", safe_text(exc)) from exc
        after = _directory_lstat(directory)
        if not os.path.samestat(before, after):
            raise InputViolation("input_changed", "directory changed while it was being scanned")
        for entry in entries:
            info = _lstat(entry)
            if _is_reparse_point(info) or stat.S_ISLNK(info.st_mode):
                raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")
            if stat.S_ISDIR(info.st_mode) and recursive:
                if depth + 1 > limits.max_depth:
                    raise InputViolation("traversal_too_deep", "input tree exceeds the depth limit")
                pending.append((entry, depth + 1))
            elif stat.S_ISREG(info.st_mode) and entry.suffix.lower() in suffixes:
                found.append(entry)
                if len(found) > limits.max_files:
                    raise InputViolation(
                        "too_many_files", "input tree exceeds the file-count limit"
                    )
    return sorted(found)


def _lstat(source: Path) -> os.stat_result:
    try:
        return os.lstat(source)
    except OSError as exc:
        raise InputViolation("unreadable_input", safe_text(exc)) from exc


def _regular_lstat(source: Path) -> os.stat_result:
    info = _lstat(source)
    if _is_reparse_point(info) or stat.S_ISLNK(info.st_mode):
        raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")
    if not stat.S_ISREG(info.st_mode):
        raise InputViolation("unreadable_input", "input is not a regular file")
    return info


def _directory_lstat(source: Path) -> os.stat_result:
    info = _lstat(source)
    if _is_reparse_point(info) or stat.S_ISLNK(info.st_mode):
        raise InputViolation("symlink_not_allowed", "symbolic links are not accepted")
    if not stat.S_ISDIR(info.st_mode):
        raise InputViolation("unreadable_input", "input is not a directory")
    return info


def _is_regular_file(source: Path) -> bool:
    try:
        info = os.lstat(source)
    except OSError:
        return False
    return stat.S_ISREG(info.st_mode) and not _is_reparse_point(info)


def _is_reparse_point(info: os.stat_result) -> bool:
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _validate_xml_complexity(text: str, limits: InputLimits) -> None:
    elements = 0
    depth = 0
    flgnets = 0
    for event, element in ET.iterparse(StringIO(text), events=("start", "end")):
        if event == "start":
            elements += 1
            depth += 1
            if elements > limits.max_xml_elements or depth > limits.max_xml_depth:
                raise InputViolation("xml_too_complex", "XML exceeds the structural limit")
            if len(element.attrib) > limits.max_attributes_per_element:
                raise InputViolation("xml_too_complex", "XML element has too many attributes")
            if _local_name(element.tag) == "FlgNet":
                flgnets += 1
                if flgnets > limits.max_flgnet_networks:
                    raise InputViolation("xml_too_complex", "XML has too many FlgNet networks")
        else:
            if len(element.text or "") > limits.max_text_chars_per_element:
                raise InputViolation("xml_too_complex", "XML element text exceeds the limit")
            depth -= 1


def _local_name(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""
