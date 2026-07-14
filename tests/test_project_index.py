"""Tests for the in-memory project reference resolver (project_index.py).

Builds ``ParsedArtifact`` fixtures directly out of ``model.Document`` /
``model.Block`` / ``model.FlgNet`` / ``model.Call`` pieces (never through real
XML or ``project_xml.parse_simaticml_artifact``) so each scenario -- unique
match, ambiguous match, unresolved reference, duplicate identity, and a
two-block call cycle -- is isolated to the resolver's own matching and
diagnostic logic.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from simaticml_decoder import model
from simaticml_decoder.project_index import index_project_artifacts
from simaticml_decoder.project_model import (
    ArtifactKind,
    ArtifactOrigin,
    ArtifactRecord,
    ArtifactStatus,
    DiagnosticCode,
    ProjectLimits,
    QualifiedIdentity,
    SourceLocation,
)
from simaticml_decoder.project_xml import ParsedArtifact

# --------------------------------------------------------------------------- #
# Fixture builders                                                             #
# --------------------------------------------------------------------------- #


def _identity(
    kind: ArtifactKind,
    origin: ArtifactOrigin,
    name: str,
    block_kind: str | None = None,
    namespace: tuple[str, ...] = (),
) -> QualifiedIdentity:
    return QualifiedIdentity(
        kind=kind, origin=origin, namespace=namespace, name=name, block_kind=block_kind
    )


def _call_network(call_uid: str, name: str, block_type: str) -> model.Network:
    call = model.Call(uid=call_uid, name=name, block_type=block_type)
    return model.Network(
        index=1,
        language=model.Language.FBD,
        source=model.FlgNet(calls={call_uid: call}),
    )


def _block_document(networks: list[model.Network]) -> model.Document:
    return model.Document(
        engineering_version="V21",
        block=model.Block(kind=model.BlockKind.FC, id="1", name="Body", networks=networks),
    )


def _record(
    identity: QualifiedIdentity, path: str, status: ArtifactStatus = ArtifactStatus.COMPLETE
) -> ArtifactRecord:
    return ArtifactRecord(
        identity=identity, status=status, location=SourceLocation(PurePosixPath(path))
    )


def _caller_artifact(
    identity: QualifiedIdentity, path: str, calls: list[tuple[str, str, str]]
) -> ParsedArtifact:
    """``calls`` is a list of (uid, requested_name, block_type)."""
    networks = [_call_network(uid, name, block_type) for uid, name, block_type in calls]
    return ParsedArtifact(record=_record(identity, path), document=_block_document(networks))


def _leaf_artifact(identity: QualifiedIdentity, path: str) -> ParsedArtifact:
    """A target-only artifact: present in the record pool, no outgoing calls."""
    return ParsedArtifact(record=_record(identity, path))


# --------------------------------------------------------------------------- #
# Given by the brief: ambiguous reference                                     #
# --------------------------------------------------------------------------- #


def _ambiguous_project_artifacts() -> tuple[ParsedArtifact, ...]:
    caller_identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller", "FC")
    target_user = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "AmbiguousTarget", "FC")
    target_library = _identity(
        ArtifactKind.BLOCK, ArtifactOrigin.PROJECT_LIBRARY, "AmbiguousTarget", "FC"
    )
    return (
        _caller_artifact(
            caller_identity, "PLC_1/Caller.xml", [("10", "AmbiguousTarget", "FC")]
        ),
        _leaf_artifact(target_user, "PLC_1/AmbiguousTarget.xml"),
        _leaf_artifact(target_library, "Types/Blocks/AmbiguousTarget.xml"),
    )


def test_resolver_never_selects_the_first_of_two_matching_candidates():
    index = index_project_artifacts(_ambiguous_project_artifacts(), ProjectLimits())

    assert index.edges == ()
    assert [diagnostic.code for diagnostic in index.diagnostics] == [
        DiagnosticCode.AMBIGUOUS_REFERENCE
    ]


# --------------------------------------------------------------------------- #
# Given by the brief: two-block call cycle                                    #
# --------------------------------------------------------------------------- #


def _two_block_cycle() -> tuple[ParsedArtifact, ...]:
    identity_a = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "A", "FC")
    identity_b = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "B", "FC")
    return (
        _caller_artifact(identity_a, "PLC_1/A.xml", [("10", "B", "FC")]),
        _caller_artifact(identity_b, "PLC_1/B.xml", [("20", "A", "FC")]),
    )


def test_cycle_records_edges_without_recursive_traversal():
    index = index_project_artifacts(_two_block_cycle(), ProjectLimits())

    assert [(edge.source.key, edge.target.key) for edge in index.edges] == [
        ("block:user:_:A:FC", "block:user:_:B:FC"),
        ("block:user:_:B:FC", "block:user:_:A:FC"),
    ]
    assert index.diagnostics == ()


# --------------------------------------------------------------------------- #
# Unique match (happy path)                                                    #
# --------------------------------------------------------------------------- #


def test_resolves_a_request_with_exactly_one_matching_candidate():
    caller_identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller", "FC")
    target_identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.PROJECT_LIBRARY, "Target", "FC")
    artifacts = (
        _caller_artifact(caller_identity, "PLC_1/Caller.xml", [("10", "Target", "FC")]),
        _leaf_artifact(target_identity, "Types/Blocks/Target.xml"),
    )

    index = index_project_artifacts(artifacts, ProjectLimits())

    assert index.diagnostics == ()
    assert len(index.edges) == 1
    edge = index.edges[0]
    assert edge.source == caller_identity
    assert edge.target == target_identity
    assert edge.kind == ArtifactKind.BLOCK
    assert edge.location == SourceLocation(PurePosixPath("PLC_1/Caller.xml"), "10")


# --------------------------------------------------------------------------- #
# Unresolved reference (zero matches)                                         #
# --------------------------------------------------------------------------- #


def test_reports_unresolved_reference_when_no_candidate_matches():
    caller_identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller", "FC")
    artifacts = (
        _caller_artifact(caller_identity, "PLC_1/Caller.xml", [("10", "Missing", "FC")]),
    )

    index = index_project_artifacts(artifacts, ProjectLimits())

    assert index.edges == ()
    assert [d.code for d in index.diagnostics] == [DiagnosticCode.UNRESOLVED_REFERENCE]
    assert index.diagnostics[0].location == SourceLocation(PurePosixPath("PLC_1/Caller.xml"), "10")


# --------------------------------------------------------------------------- #
# Duplicate identity                                                          #
# --------------------------------------------------------------------------- #


def test_duplicate_identity_is_excluded_from_the_candidate_pool():
    dup_identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.PROJECT_LIBRARY, "Shared", "FC")
    caller_identity = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller", "FC")
    artifacts = (
        _caller_artifact(caller_identity, "PLC_1/Caller.xml", [("10", "Shared", "FC")]),
        _leaf_artifact(dup_identity, "Types/Blocks/Shared.xml"),
        _leaf_artifact(dup_identity, "Types/Blocks/Shared_copy.xml"),
    )

    index = index_project_artifacts(artifacts, ProjectLimits())

    assert index.edges == ()
    codes = [d.code for d in index.diagnostics]
    assert sorted(codes, key=lambda c: c.value) == sorted(
        [DiagnosticCode.DUPLICATE_IDENTITY, DiagnosticCode.UNRESOLVED_REFERENCE],
        key=lambda c: c.value,
    )
    assert len(index.diagnostics) == 2


# --------------------------------------------------------------------------- #
# Determinism                                                                  #
# --------------------------------------------------------------------------- #


def test_running_the_resolver_twice_on_the_same_input_is_byte_identical():
    artifacts = _two_block_cycle()

    first = index_project_artifacts(artifacts, ProjectLimits())
    second = index_project_artifacts(artifacts, ProjectLimits())

    assert first == second


# --------------------------------------------------------------------------- #
# Reference edge limit                                                        #
# --------------------------------------------------------------------------- #


def test_reference_edge_limit_stops_resolution_and_emits_a_diagnostic():
    target_a = _identity(ArtifactKind.BLOCK, ArtifactOrigin.PROJECT_LIBRARY, "TargetA", "FC")
    target_b = _identity(ArtifactKind.BLOCK, ArtifactOrigin.PROJECT_LIBRARY, "TargetB", "FC")
    caller_1 = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller1", "FC")
    caller_2 = _identity(ArtifactKind.BLOCK, ArtifactOrigin.USER, "Caller2", "FC")
    artifacts = (
        _caller_artifact(caller_1, "PLC_1/Caller1.xml", [("10", "TargetA", "FC")]),
        _caller_artifact(caller_2, "PLC_1/Caller2.xml", [("10", "TargetB", "FC")]),
        _leaf_artifact(target_a, "Types/Blocks/TargetA.xml"),
        _leaf_artifact(target_b, "Types/Blocks/TargetB.xml"),
    )

    index = index_project_artifacts(artifacts, ProjectLimits(max_reference_edges=1))

    assert len(index.edges) == 2
    assert [d.code for d in index.diagnostics] == [DiagnosticCode.REFERENCE_EDGE_LIMIT]
