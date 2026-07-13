"""Bounded, deterministic handling of untrusted decoder inputs."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path, PurePath
from xml.etree import ElementTree as ET


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
    """Immutable artifact representing a discovered or direct input file."""

    relative_path: PurePath
    suffix: str
    _reader: Callable[[InputLimits], bytes] = field(repr=False, compare=False)

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


def _make_artifact_reader(path: Path) -> Callable[[InputLimits], bytes]:
    """Create a reader closure for a discovered file."""
    def reader(limits: InputLimits) -> bytes:
        """Reader closure that validates and reads the file."""
        text = read_xml(path, limits)
        return text.encode("utf-8")

    return reader


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
    if len(raw) > limits.max_file_bytes:
        raise InputViolation("file_too_large", "input exceeds the configured byte limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputViolation("invalid_encoding", "input is not valid UTF-8") from exc
    declaration = text.casefold()
    if "<!doctype" in declaration or "<!entity" in declaration:
        raise InputViolation("xml_forbidden_declaration", "DTD and entity declarations are not accepted")
    _validate_xml_complexity(text, limits)
    return text


def validate_artifact_format(artifact: InputArtifact) -> None:
    """Validate file format from an InputArtifact (for discovered or direct files)."""
    suffix = artifact.suffix
    if suffix == ".s7res":
        # For discovered artifacts with only relative path, can't check for sibling .s7dcl
        # The .s7res check for sibling .s7dcl happens at decode time in cli.decode_file
        raise InputViolation("unsupported_format", "SIMATIC SD decoding is not implemented")
    if suffix == ".s7dcl":
        raise InputViolation("unsupported_format", "SIMATIC SD decoding is not implemented")
    if suffix != ".xml":
        raise InputViolation("unsupported_format", "only exported SimaticML .xml files are accepted")


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
        raise InputViolation("unsupported_format", "only exported SimaticML .xml files are accepted")


def discover_xml(root: Path, recursive: bool, limits: InputLimits = DEFAULT_LIMITS) -> list[Path]:
    """Discover regular XML files without following links, bounded and sorted."""
    return _discover(root, recursive, limits, {".xml"})


def discover_input_files(root: Path, recursive: bool, limits: InputLimits = DEFAULT_LIMITS) -> tuple[InputArtifact, ...]:
    """Discover XML and SIMATIC SD inputs so unsupported files remain visible."""
    paths = _discover(root, recursive, limits, {".xml", ".s7dcl", ".s7res"})
    artifacts = tuple(
        InputArtifact(
            relative_path=path.relative_to(root),
            suffix=path.suffix.lower(),
            _reader=_make_artifact_reader(path),
        )
        for path in paths
    )
    return artifacts


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
                    raise InputViolation("too_many_files", "input tree exceeds the file-count limit")
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
