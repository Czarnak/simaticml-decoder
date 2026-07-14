"""Project-facing wrapper over `input_policy.discover_project_artifacts()`.

This module never touches the filesystem itself: it only builds an
`input_policy.InputLimits` from the relevant `ProjectLimits` fields, calls
`input_policy.discover_project_artifacts()` (the actual handle-anchored,
TOCTOU-resistant walk), and composes each returned `InputArtifact` into a
`DiscoveredFile`. `discover_project_files()` is the sole function of that
name -- callers (Task 3 onward) import it from here, never from
`input_policy`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import input_policy
from .project_model import InputFormat, ProjectDiagnostic, ProjectLimits, SourceLocation


@dataclass(frozen=True)
class DiscoveredFile:
    """One project-mode input file, ready for the next pipeline stage.

    ``artifact``'s bytes are obtained only via ``artifact.read_bytes(limits)``
    -- the reader closure captured during the same walk that discovered this
    file. ``size`` is metadata observed during that same walk (never a
    separate filesystem touch here).
    """

    artifact: input_policy.InputArtifact
    location: SourceLocation
    input_format: InputFormat
    size: int


@dataclass(frozen=True)
class DiscoveryResult:
    """The full outcome of one project-mode discovery pass."""

    files: tuple[DiscoveredFile, ...] = ()
    diagnostics: tuple[ProjectDiagnostic, ...] = ()


def discover_project_files(
    root: Path, suffixes: Mapping[str, InputFormat], limits: ProjectLimits
) -> DiscoveryResult:
    """Discover project-mode input files under ``root``, bounded by ``limits``.

    ``suffixes`` maps a lowercase file suffix (e.g. ``".xml"``) to the
    `InputFormat` it should be classified as; matching is case-insensitive
    (the underlying walk lower-cases each entry's suffix before comparing).

    All filesystem access -- enumeration, symlink/reparse-point rejection,
    and every file's handle/descriptor open -- happens inside
    `input_policy.discover_project_artifacts()`. This function only adapts
    that call's already-safe results into project-shaped types; it never
    re-derives a path or re-touches the filesystem on its own.
    """
    normalized_suffixes = {suffix.lower(): input_format for suffix, input_format in suffixes.items()}
    raw_artifacts, diagnostics = input_policy.discover_project_artifacts(
        root,
        set(normalized_suffixes),
        input_policy.InputLimits(
            max_file_bytes=limits.max_file_bytes,
            max_files=limits.max_files,
            max_depth=limits.max_relative_depth,
        ),
        limits.max_total_bytes,
    )
    files = tuple(
        DiscoveredFile(
            artifact=artifact,
            location=SourceLocation(PurePosixPath(artifact.relative_path.as_posix())),
            input_format=normalized_suffixes[artifact.suffix],
            size=artifact.size,
        )
        for artifact in raw_artifacts
    )
    return DiscoveryResult(files=files, diagnostics=diagnostics)
