"""Top-level orchestrator for project-scale SimaticML ingestion.

This is the last piece that wires Tasks 1-5 together into one call:
``project_discovery.py``'s bounded walk -> ``project_xml.py``'s per-file V21
adapter -> (this module's own) ``--library-root`` origin override -> the
``project_index.py`` resolver. ``cli.py`` is the only intended caller of
``index_simaticml_project`` (see its ``--project`` mode); nothing here writes
to the filesystem or touches ``fold``/``emit`` -- this module only ever
produces an in-memory ``ProjectIndex``.

``--library-root`` override, and why it lives here rather than in
``project_xml.py``: ``project_xml._artifact_origin()`` is an already-reviewed
Task 3 convention (``Types/`` -> project-library, ``PLC_1/`` -> user, else
unknown) with no parameter for caller-supplied library roots. Rather than
threading a new parameter through that merged module, this file re-classifies
origin as an immutable post-processing step over the ``ParsedArtifact`` tuple
``parse_simaticml_artifact`` already produced: explicit CLI intent wins over
the path-convention default, expressed entirely via ``dataclasses.replace``
(never in-place mutation). When no ``--library-root`` values are given (the
common case), this step is a no-op and every artifact's origin is exactly
what Task 3's adapter produced.

Diagnostic merging: this module is the first point where diagnostics from
three independent sources -- discovery, library-root validation, and the
resolver -- must be combined into one array. All three are merged and sorted
by the same deterministic key ``project_index.py`` already uses internally
(by location, then code, then message), so the final ``ProjectIndex`` is
byte-identical across repeated runs regardless of which source raised which
diagnostic.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path, PurePosixPath

from .project_discovery import discover_project_files
from .project_index import index_project_artifacts
from .project_model import (
    ArtifactOrigin,
    DiagnosticCode,
    InputFormat,
    ProjectDiagnostic,
    ProjectIndex,
    ProjectLimits,
    SourceLocation,
)
from .project_xml import ParsedArtifact, parse_simaticml_artifact

_PROJECT_SUFFIXES = {".xml": InputFormat.SIMATICML_XML}

# --------------------------------------------------------------------------- #
# Deterministic sort key (a local copy of project_index.py's shape -- see     #
# that module's `_diagnostic_sort_key` for the canonical definition)          #
# --------------------------------------------------------------------------- #


def _location_sort_key(location: SourceLocation) -> tuple[str, str]:
    return (location.relative_path.as_posix(), location.element_id or "")


def _diagnostic_sort_key(diagnostic: ProjectDiagnostic) -> tuple[str, str, str, str]:
    return (*_location_sort_key(diagnostic.location), diagnostic.code.value, diagnostic.message)


# --------------------------------------------------------------------------- #
# --library-root validation                                                    #
# --------------------------------------------------------------------------- #

# Matches a Windows drive-letter prefix (e.g. ``C:\Lib`` or ``C:/Lib``).
# ``PurePosixPath.is_absolute()`` is False for these under POSIX semantics
# (POSIX has no drive letters), so this must be checked explicitly -- see
# ``_validate_library_roots``'s docstring.
_DRIVE_LETTER_PREFIX = re.compile(r"^[A-Za-z]:")


def _validate_library_roots(
    library_roots: tuple[str, ...],
) -> tuple[tuple[PurePosixPath, ...], tuple[ProjectDiagnostic, ...]]:
    """Normalize and validate every raw ``--library-root`` value.

    A value is rejected -- with an ``OUTSIDE_ROOT`` diagnostic, never a raised
    exception -- when it is:

    - empty (``PurePosixPath('')`` normalizes to ``'.'``, which is
      "relative to" every artifact and would silently reclassify the whole
      project as ``PROJECT_LIBRARY``);
    - a path containing a backslash (Windows-style separators are never
      reinterpreted as POSIX separators here -- doing so silently would
      turn a caller's typo into either an opaque single segment that
      matches nothing, or a different path than intended; rejecting
      outright is clearer than silently guessing);
    - a Windows drive-letter-prefixed path (e.g. ``C:\\Lib``) -- these are
      not ``PurePosixPath.is_absolute()`` under POSIX semantics, so they
      must be checked separately from the absolute-path check below;
    - absolute (POSIX-style, ``PurePosixPath.is_absolute()``); or
    - containing a ``..`` segment.

    Any of these would otherwise let a caller point the override outside
    the project root it nominally applies to, or silently no-op instead of
    matching anything. Valid values are returned as normalized
    ``PurePosixPath``s ready for the ``is_relative_to`` check below.
    """
    valid: list[PurePosixPath] = []
    diagnostics: list[ProjectDiagnostic] = []
    for raw in library_roots:
        candidate = PurePosixPath(raw)
        is_invalid = (
            not raw
            or "\\" in raw
            or _DRIVE_LETTER_PREFIX.match(raw) is not None
            or candidate.is_absolute()
            or ".." in candidate.parts
        )
        if is_invalid:
            diagnostics.append(
                ProjectDiagnostic(
                    code=DiagnosticCode.OUTSIDE_ROOT,
                    severity="error",
                    message=(
                        f"--library-root {raw!r} is not a normalized relative path "
                        "under the project root and was ignored"
                    ),
                    location=SourceLocation(candidate),
                )
            )
            continue
        valid.append(candidate)
    return tuple(valid), tuple(diagnostics)


def _apply_library_root_override(
    artifact: ParsedArtifact, library_roots: tuple[PurePosixPath, ...]
) -> ParsedArtifact:
    """Override ``artifact``'s origin to ``PROJECT_LIBRARY`` when its location
    falls under one of ``library_roots``. A no-op (returns ``artifact``
    unchanged) whenever ``library_roots`` is empty or none match -- this must
    not change behavior for the common case where no ``--library-root`` was
    given.

    Immutable by construction: ``dataclasses.replace`` the identity, then the
    record, then the artifact -- never mutates any of the three in place.
    """
    if not library_roots:
        return artifact

    relative_path = artifact.record.location.relative_path
    if not any(relative_path.is_relative_to(root) for root in library_roots):
        return artifact

    record = artifact.record
    overridden_identity = dataclasses.replace(
        record.identity, origin=ArtifactOrigin.PROJECT_LIBRARY
    )
    overridden_record = dataclasses.replace(record, identity=overridden_identity)
    return dataclasses.replace(artifact, record=overridden_record)


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def index_simaticml_project(
    root: Path, library_roots: tuple[str, ...], limits: ProjectLimits
) -> ProjectIndex:
    """Index a whole V21 SimaticML project export rooted at ``root``.

    Orchestrates, in order: bounded discovery (``.xml`` files only) ->
    per-file V21 adaptation -> the ``--library-root`` origin override ->
    reference resolution. Diagnostics from all three sources (discovery,
    library-root validation, resolution) are merged and sorted into one
    deterministic order before returning -- see module docstring.

    Serial and deterministic by construction: every step here is a plain
    generator expression or comprehension over an already-produced tuple, no
    threads or multiprocessing anywhere in this call chain.
    """
    discovery = discover_project_files(root, _PROJECT_SUFFIXES, limits)
    parsed = tuple(parse_simaticml_artifact(candidate, limits) for candidate in discovery.files)

    validated_roots, root_diagnostics = _validate_library_roots(library_roots)
    overridden = tuple(
        _apply_library_root_override(artifact, validated_roots) for artifact in parsed
    )

    index = index_project_artifacts(overridden, limits)

    merged_diagnostics = discovery.diagnostics + root_diagnostics + index.diagnostics
    sorted_diagnostics = tuple(sorted(merged_diagnostics, key=_diagnostic_sort_key))

    return dataclasses.replace(index, diagnostics=sorted_diagnostics)
