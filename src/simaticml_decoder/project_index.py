"""In-memory resolver: a collection of ``ParsedArtifact``s -> a ``ProjectIndex``.

This module is the last stage of project-scale ingestion (Tasks 1-3 built
``project_model.py``'s immutable contracts, ``project_discovery.py``'s bounded
walk, and ``project_xml.py``'s per-file V21 adapter). Given every artifact
already discovered and adapted in a project, it:

1. Collects every ``ReferenceRequest`` a parsed document emits (block calls
   via ``extract_block_references``, UDT member references via
   ``extract_udt_references``) and attaches ``source_identity`` -- left
   ``None`` by both extraction functions -- via ``dataclasses.replace``.
2. Detects artifacts that share a ``QualifiedIdentity`` (compared via
   ``.key``) and excludes every duplicate identity from the candidate pool:
   an ambiguous identity must never let a resolver silently pick one of the
   duplicates, which would be exactly the "first match" behavior this
   resolver is designed to avoid.
3. Resolves each request against the remaining candidates by exact
   (kind, name, namespace) match, plus block_kind when the request specifies
   one. Matching is deliberately origin-blind: the real corpus has genuine
   user -> project-library calls, so restricting candidates by origin would
   reject valid references. Exactly one match resolves to a ``ReferenceEdge``;
   zero matches or two-or-more matches each produce a diagnostic instead --
   never a first-match fallback and never an origin-based tie-break.
4. Stops resolving once ``limits.max_reference_edges`` would be exceeded,
   recording a ``REFERENCE_EDGE_LIMIT`` diagnostic at the cutoff.

Determinism is load-bearing: two runs over the same input must produce a
byte-identical ``ProjectIndex``, including diagnostic order. Every place this
module could depend on incidental input or dict-iteration order (requests,
matches, duplicate groups) is sorted by an explicit, stable key before it
affects output.

Cycles need no special handling here: a two-block mutual-call cycle is just
two independent requests, each resolving to its own edge. There is no
recursive graph walk in this module, only per-request matching.
"""

from __future__ import annotations

import dataclasses

from .project_model import (
    ArtifactRecord,
    DiagnosticCode,
    ProjectDiagnostic,
    ProjectIndex,
    ProjectLimits,
    QualifiedIdentity,
    ReferenceEdge,
    ReferenceRequest,
    SourceLocation,
)
from .project_xml import ParsedArtifact, extract_block_references, extract_udt_references

# --------------------------------------------------------------------------- #
# Deterministic sort keys                                                     #
# --------------------------------------------------------------------------- #


def _location_sort_key(location: SourceLocation) -> tuple[str, str]:
    return (location.relative_path.as_posix(), location.element_id or "")


def _request_sort_key(request: ReferenceRequest) -> tuple[str, str, str, str, str]:
    return (
        *_location_sort_key(request.source),
        request.kind.value,
        request.requested_name,
        request.requested_block_kind or "",
    )


def _edge_sort_key(edge: ReferenceEdge) -> tuple[str, str, str, str]:
    return (edge.source.key, edge.target.key, *_location_sort_key(edge.location))


def _diagnostic_sort_key(diagnostic: ProjectDiagnostic) -> tuple[str, str, str, str]:
    return (*_location_sort_key(diagnostic.location), diagnostic.code.value, diagnostic.message)


# --------------------------------------------------------------------------- #
# Duplicate identity detection                                                #
# --------------------------------------------------------------------------- #


def _duplicate_diagnostics(
    records: tuple[ArtifactRecord, ...],
) -> tuple[tuple[ProjectDiagnostic, ...], frozenset[str]]:
    """Group records by identity key; any key shared by 2+ records is a
    duplicate. Returns one diagnostic per duplicate group (not per record)
    and the set of duplicate keys, so callers can exclude them from the
    candidate pool used for matching.
    """
    groups: dict[str, list[ArtifactRecord]] = {}
    for record in records:
        groups.setdefault(record.identity.key, []).append(record)

    duplicate_keys = frozenset(key for key, group in groups.items() if len(group) > 1)
    diagnostics: list[ProjectDiagnostic] = []
    for key in duplicate_keys:
        group = sorted(groups[key], key=lambda record: _location_sort_key(record.location))
        paths = ", ".join(record.location.relative_path.as_posix() for record in group)
        diagnostics.append(
            ProjectDiagnostic(
                code=DiagnosticCode.DUPLICATE_IDENTITY,
                severity="error",
                message=(
                    f"identity {key!r} is declared by {len(group)} artifacts and cannot be "
                    f"resolved unambiguously: {paths}"
                ),
                location=group[0].location,
            )
        )
    return tuple(diagnostics), duplicate_keys


# --------------------------------------------------------------------------- #
# Reference request collection                                                #
# --------------------------------------------------------------------------- #


def _collect_requests(artifacts: tuple[ParsedArtifact, ...]) -> tuple[ReferenceRequest, ...]:
    """Extract every reference request from every artifact whose document was
    successfully parsed, attaching each request's ``source_identity``.
    Safe to call ``extract_block_references``/``extract_udt_references`` on
    any document -- a UDT's synthetic document has no networks, so block
    reference extraction against it is a no-op.
    """
    requests: list[ReferenceRequest] = []
    for artifact in artifacts:
        if artifact.document is None:
            continue
        record = artifact.record
        extracted = (
            *extract_block_references(artifact.document, record.location),
            *extract_udt_references(artifact.document, record.location),
        )
        requests.extend(
            dataclasses.replace(request, source_identity=record.identity) for request in extracted
        )
    return tuple(sorted(requests, key=_request_sort_key))


# --------------------------------------------------------------------------- #
# Matching                                                                    #
# --------------------------------------------------------------------------- #


def _matches(identity: QualifiedIdentity, request: ReferenceRequest) -> bool:
    if identity.kind != request.kind:
        return False
    if identity.name != request.requested_name:
        return False
    if identity.namespace != request.namespace:
        return False
    if request.requested_block_kind is not None and identity.block_kind != request.requested_block_kind:
        return False
    return True


def _matching_identities(
    candidates: tuple[QualifiedIdentity, ...], request: ReferenceRequest
) -> tuple[QualifiedIdentity, ...]:
    return tuple(identity for identity in candidates if _matches(identity, request))


# --------------------------------------------------------------------------- #
# Diagnostic builders                                                          #
# --------------------------------------------------------------------------- #


def _unresolved_diagnostic(request: ReferenceRequest) -> ProjectDiagnostic:
    block_kind_note = (
        f" (block_kind={request.requested_block_kind!r})" if request.requested_block_kind else ""
    )
    return ProjectDiagnostic(
        code=DiagnosticCode.UNRESOLVED_REFERENCE,
        severity="warning",
        message=(
            f"no {request.kind.value} artifact named {request.requested_name!r}"
            f"{block_kind_note} could be found"
        ),
        location=request.source,
    )


def _ambiguous_diagnostic(
    request: ReferenceRequest, matches: tuple[QualifiedIdentity, ...]
) -> ProjectDiagnostic:
    keys = ", ".join(sorted(identity.key for identity in matches))
    return ProjectDiagnostic(
        code=DiagnosticCode.AMBIGUOUS_REFERENCE,
        severity="error",
        message=(
            f"{len(matches)} {request.kind.value} artifacts named "
            f"{request.requested_name!r} match ambiguously: {keys}"
        ),
        location=request.source,
    )


def _limit_diagnostic(source: SourceLocation, limits: ProjectLimits) -> ProjectDiagnostic:
    return ProjectDiagnostic(
        code=DiagnosticCode.REFERENCE_EDGE_LIMIT,
        severity="error",
        message=(
            f"reference edge limit ({limits.max_reference_edges}) reached; "
            "remaining references were not resolved"
        ),
        location=source,
    )


# --------------------------------------------------------------------------- #
# Resolution                                                                   #
# --------------------------------------------------------------------------- #


def _resolve(
    requests: tuple[ReferenceRequest, ...],
    candidates: tuple[QualifiedIdentity, ...],
    limits: ProjectLimits,
) -> tuple[list[ReferenceEdge], list[ProjectDiagnostic]]:
    edges: list[ReferenceEdge] = []
    diagnostics: list[ProjectDiagnostic] = []
    for request in requests:
        matches = _matching_identities(candidates, request)
        if len(matches) == 1:
            edges.append(
                ReferenceEdge(request.source, request.source_identity, matches[0], request.kind)
            )
        elif not matches:
            diagnostics.append(_unresolved_diagnostic(request))
        else:
            diagnostics.append(_ambiguous_diagnostic(request, matches))

        if len(edges) > limits.max_reference_edges:
            diagnostics.append(_limit_diagnostic(request.source, limits))
            break
    return edges, diagnostics


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def index_project_artifacts(
    artifacts: tuple[ParsedArtifact, ...], limits: ProjectLimits
) -> ProjectIndex:
    """Build a ``ProjectIndex`` from every discovered/adapted artifact in a
    project.

    ``artifacts`` order is preserved as ``ProjectIndex.artifacts`` (mirroring
    discovery order); only the derived ``edges`` and ``diagnostics`` tuples
    are sorted into a stable, input-order-independent order, since those are
    built from requests gathered across multiple artifacts and must be
    byte-identical across repeated runs regardless of any incidental
    iteration order upstream.
    """
    records = tuple(artifact.record for artifact in artifacts)

    duplicate_diagnostics, duplicate_keys = _duplicate_diagnostics(records)
    candidates = tuple(
        record.identity for record in records if record.identity.key not in duplicate_keys
    )

    requests = _collect_requests(artifacts)
    edges, resolution_diagnostics = _resolve(requests, candidates, limits)

    all_diagnostics = duplicate_diagnostics + tuple(resolution_diagnostics)

    return ProjectIndex(
        artifacts=records,
        edges=tuple(sorted(edges, key=_edge_sort_key)),
        diagnostics=tuple(sorted(all_diagnostics, key=_diagnostic_sort_key)),
        limits=limits,
    )
