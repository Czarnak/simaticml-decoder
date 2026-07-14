"""Immutable contracts for project-scale ingestion of SimaticML artifacts.

This module defines the data structures that represent a project index,
diagnostic metadata, and resolved references. All types are frozen and
immutable to support safe concurrent processing and diagnostic reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath


# --------------------------------------------------------------------------- #
# Enums: Artifact metadata                                                    #
# --------------------------------------------------------------------------- #


class ArtifactKind(str, Enum):
    """Kind of artifact in a project."""

    BLOCK = "block"
    UDT = "udt"


class ArtifactOrigin(str, Enum):
    """Origin of an artifact within the project hierarchy."""

    USER = "user"
    PROJECT_LIBRARY = "project-library"
    UNKNOWN = "unknown"


class InputFormat(str, Enum):
    """Recognized input file formats for project ingestion."""

    SIMATICML_XML = "simaticml-xml"


class ArtifactStatus(str, Enum):
    """Status of an artifact's decode/analysis."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    PRESERVED = "preserved"
    FAILED = "failed"


class DiagnosticCode(str, Enum):
    """Diagnostic codes for project discovery and analysis."""

    OUTSIDE_ROOT = "outside_root"
    SYMLINK_SKIPPED = "symlink_skipped"
    FILE_COUNT_LIMIT = "file_count_limit"
    FILE_SIZE_LIMIT = "file_size_limit"
    TOTAL_SIZE_LIMIT = "total_size_limit"
    DEPTH_LIMIT = "depth_limit"
    XML_ELEMENT_LIMIT = "xml_element_limit"
    XML_DEPTH_LIMIT = "xml_depth_limit"
    REFERENCE_EDGE_LIMIT = "reference_edge_limit"
    MALFORMED_XML = "malformed_xml"
    UNSUPPORTED_ARTIFACT = "unsupported_artifact"
    UNSUPPORTED_TIA_VERSION = "unsupported_tia_version"
    UNKNOWN_TIA_VERSION = "unknown_tia_version"
    DUPLICATE_IDENTITY = "duplicate_identity"
    UNRESOLVED_REFERENCE = "unresolved_reference"
    AMBIGUOUS_REFERENCE = "ambiguous_reference"


# --------------------------------------------------------------------------- #
# Limits: Boundary conditions for discovery                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ProjectLimits:
    """Immutable configuration for project discovery boundaries.

    Enforces hard limits on file counts, sizes, and nesting to prevent
    pathological behavior during recursive discovery.
    """

    max_files: int = 10_000
    max_file_bytes: int = 16 * 1024 * 1024
    max_total_bytes: int = 512 * 1024 * 1024
    max_relative_depth: int = 32
    max_xml_elements: int = 500_000
    max_xml_depth: int = 128
    max_reference_edges: int = 100_000
    follow_symlinks: bool = False

    def __post_init__(self) -> None:
        """Validate all positive limits."""
        limits_to_check = [
            ("max_files", self.max_files),
            ("max_file_bytes", self.max_file_bytes),
            ("max_total_bytes", self.max_total_bytes),
            ("max_relative_depth", self.max_relative_depth),
            ("max_xml_elements", self.max_xml_elements),
            ("max_xml_depth", self.max_xml_depth),
            ("max_reference_edges", self.max_reference_edges),
        ]
        for name, value in limits_to_check:
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}")


# --------------------------------------------------------------------------- #
# Identities: Stable references to artifacts                                  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class QualifiedIdentity:
    """Immutable stable identity for an artifact.

    The key combines kind, origin, namespace, name, and block_kind to create
    a stable reference that accounts for both user and library definitions.
    """

    kind: ArtifactKind
    origin: ArtifactOrigin
    namespace: tuple[str, ...]
    name: str
    block_kind: str | None = None

    @property
    def key(self) -> str:
        """Stable, origin-aware key for this identity."""
        namespace = "/".join(self.namespace) or "_"
        return ":".join(
            (
                self.kind.value,
                self.origin.value,
                namespace,
                self.name,
                self.block_kind or "_",
            )
        )


# --------------------------------------------------------------------------- #
# Diagnostics: Location and message                                           #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SourceLocation:
    """Immutable reference to a location in project source files."""

    relative_path: PurePosixPath


@dataclass(frozen=True)
class ProjectDiagnostic:
    """Immutable diagnostic message with location and severity.

    Reported during discovery, parsing, or analysis. Non-complete artifact
    status requires at least one diagnostic.
    """

    code: DiagnosticCode
    severity: str  # "error" | "warning" | "info"
    message: str
    location: SourceLocation


# --------------------------------------------------------------------------- #
# Artifacts: Records and references                                           #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ArtifactRecord:
    """Immutable record of a discovered artifact.

    Captures identity, status, location, and any diagnostics from the
    discovery or analysis phase.
    """

    identity: QualifiedIdentity
    status: ArtifactStatus
    location: SourceLocation
    diagnostics: tuple[ProjectDiagnostic, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ReferenceRequest:
    """Immutable request to resolve a reference from source to target.

    Used during reference edge construction to track explicit or inferred
    dependencies between artifacts. ``source_identity`` is left unset (``None``)
    when a request is first extracted from a block body; the code that
    assembles per-artifact requests attaches it later, before resolution,
    via ``dataclasses.replace``. All fields are keyword-only so construction
    order matches how callers (e.g. ``extract_block_references``) build these
    with keyword arguments.
    """

    source: SourceLocation
    source_identity: QualifiedIdentity | None = None
    requested_name: str
    requested_block_kind: str | None
    namespace: tuple[str, ...]
    kind: ArtifactKind


@dataclass(frozen=True)
class ReferenceEdge:
    """Immutable resolved reference edge between two artifacts.

    Represents a dependency from source to target after resolution.
    Field order matters: resolvers construct this positionally as
    ``ReferenceEdge(request.source, request.source_identity, matches[0], request.kind)``.
    """

    location: SourceLocation
    source: QualifiedIdentity
    target: QualifiedIdentity
    kind: ArtifactKind


@dataclass(frozen=True)
class ProjectIndex:
    """Immutable index of all discovered artifacts and references.

    The primary output of the discovery phase. Contains all artifacts,
    resolved references, and any diagnostics encountered.
    """

    artifacts: tuple[ArtifactRecord, ...] = ()
    edges: tuple[ReferenceEdge, ...] = ()
    diagnostics: tuple[ProjectDiagnostic, ...] = ()
    limits: ProjectLimits = ProjectLimits()
