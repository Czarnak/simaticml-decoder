"""V21 SimaticML project-artifact adapter.

Adapts one already-*discovered* artifact (see ``project_discovery.py``) into
a project-index record, without broadening ``model.Document`` into a general
XML union: the legacy single-block parser (``parse.py`` -> ``model.py``)
keeps recognizing only ``SW.Blocks.*`` exports. Anything else -- a
``SW.Types.PlcStruct`` (UDT) export, an unrecognized root element, a
non-V21/missing engineering version, or XML that fails to parse/decode at
all -- is *preserved* as an ``ArtifactRecord`` with an explicit
``ArtifactKind``/``ArtifactStatus``/``ProjectDiagnostic`` instead.

Security constraint (see the task brief and
``docs/superpowers/memory/native-handle-traversal-decision.md``): every
artifact's content is read **exactly once**, via
``candidate.artifact.read_bytes(limits)`` -- the reader closure captured at
discovery time. Nothing in this module re-opens a file by a stored path
(``parse.parse_file(str(candidate.path))`` or otherwise); that would
reintroduce the TOCTOU race Task 2 closed.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from . import input_policy, model, parse
from .project_discovery import DiscoveredFile
from .project_model import (
    ArtifactKind,
    ArtifactOrigin,
    ArtifactRecord,
    ArtifactStatus,
    DiagnosticCode,
    ProjectDiagnostic,
    ProjectLimits,
    QualifiedIdentity,
    ReferenceRequest,
    SourceLocation,
)

# --------------------------------------------------------------------------- #
# ParsedArtifact: the outcome of adapting one discovered artifact             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ParsedArtifact:
    """Outcome of adapting one discovered artifact through the V21 adapter.

    ``record`` is always populated: identity, status, location, and (for
    every non-``COMPLETE`` status) at least one diagnostic. ``document`` is
    the parsed ``model.Document`` only when the artifact was successfully
    read and recognized as a V21 export (a real ``SW.Blocks.*`` block, or a
    ``SW.Types.PlcStruct`` UDT adapted into a synthetic single-block
    ``model.Document`` -- see ``_udt_artifact`` below for why); it is
    ``None`` for every preserved or failed artifact. Callers that need
    outgoing references (``extract_block_references`` /
    ``extract_udt_references``) must check for ``None`` first.
    """

    record: ArtifactRecord
    document: model.Document | None = None


# --------------------------------------------------------------------------- #
# ProjectLimits -> InputLimits                                                #
# --------------------------------------------------------------------------- #


def _as_input_limits(limits: ProjectLimits) -> input_policy.InputLimits:
    """Translate project-scale ``ProjectLimits`` into the ``InputLimits``
    shape ``input_policy`` functions expect.

    ``max_attributes_per_element``, ``max_text_chars_per_element``, and
    ``max_flgnet_networks`` have no ``ProjectLimits`` equivalent -- project
    mode only publishes element-count and nesting-depth budgets at this
    layer -- so those three keep ``InputLimits``' own defaults.
    """
    return input_policy.InputLimits(
        max_file_bytes=limits.max_file_bytes,
        max_files=limits.max_files,
        max_depth=limits.max_relative_depth,
        max_xml_elements=limits.max_xml_elements,
        max_xml_depth=limits.max_xml_depth,
    )


# --------------------------------------------------------------------------- #
# Bounded XML preflight                                                       #
# --------------------------------------------------------------------------- #


def preflight_xml_bytes(raw: bytes, limits: ProjectLimits) -> DiagnosticCode | None:
    """Bounded structural preflight over bytes already obtained from
    ``read_bytes()`` -- never a reopened path.

    Reuses ``input_policy._validate_xml_complexity`` -- the exact
    element-count / nesting-depth / attribute / text-length / FlgNet-count
    gate the legacy single-file path (``read_xml``) already relies on --
    instead of re-implementing a second iterparse counter from scratch.
    Returns the diagnostic code for a violation, or ``None`` when the bytes
    preflight clean.

    Disambiguating ``XML_ELEMENT_LIMIT`` from ``XML_DEPTH_LIMIT``:
    ``_validate_xml_complexity`` raises the *identical*
    ``InputViolation("xml_too_complex", "XML exceeds the structural
    limit")`` for both an element-count breach and a depth breach (as well
    as for an attribute-count/text-length/FlgNet-count breach -- there is no
    ``DiagnosticCode`` for those, either) -- there is no way to tell them
    apart from the raised violation alone without re-deriving the counting
    loop, which would defeat the point of reusing it. This is a deliberate,
    documented choice (per the task's own guidance): any ``xml_too_complex``
    violation is reported as ``XML_ELEMENT_LIMIT``.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return DiagnosticCode.MALFORMED_XML
    try:
        input_policy._validate_xml_complexity(text, _as_input_limits(limits))
    except input_policy.InputViolation:
        return DiagnosticCode.XML_ELEMENT_LIMIT
    except ET.ParseError:
        return DiagnosticCode.MALFORMED_XML
    return None


# --------------------------------------------------------------------------- #
# Origin classification (evidence-based: the real corpus layout)              #
# --------------------------------------------------------------------------- #


def _artifact_origin(relative_path: PurePosixPath) -> ArtifactOrigin:
    """Classify origin from the project layout convention confirmed against
    the real committed corpus (2026-07-14 fixture-corpus-reuse amendment):
    ``Types/`` (Blocks and UDTs) is project-library origin; ``PLC_1/``
    (Program blocks and PLC data types) is user origin. Anything outside
    that layout (e.g. a fixture root that isn't a real project export) is
    ``UNKNOWN`` rather than guessed.
    """
    parts = relative_path.parts
    if not parts:
        return ArtifactOrigin.UNKNOWN
    if parts[0] == "Types":
        return ArtifactOrigin.PROJECT_LIBRARY
    if parts[0] == "PLC_1":
        return ArtifactOrigin.USER
    return ArtifactOrigin.UNKNOWN


def _diagnostic(
    code: DiagnosticCode, location: SourceLocation, message: str, *, severity: str
) -> ProjectDiagnostic:
    return ProjectDiagnostic(code=code, severity=severity, message=message, location=location)


# --------------------------------------------------------------------------- #
# Identity builders                                                            #
# --------------------------------------------------------------------------- #


def _identity(
    kind: ArtifactKind,
    candidate: DiscoveredFile,
    *,
    name: str | None = None,
    block_kind: str | None = None,
) -> QualifiedIdentity:
    return QualifiedIdentity(
        kind=kind,
        origin=_artifact_origin(candidate.location.relative_path),
        namespace=(),
        name=name or candidate.location.relative_path.stem,
        block_kind=block_kind,
    )


def _block_identity(document: model.Document, candidate: DiscoveredFile) -> QualifiedIdentity:
    return _identity(
        ArtifactKind.BLOCK,
        candidate,
        name=document.block.name or None,
        block_kind=document.block.kind.value,
    )


# --------------------------------------------------------------------------- #
# Outcome builders (one per terminal status)                                  #
# --------------------------------------------------------------------------- #


def _failed(candidate: DiscoveredFile, code: DiagnosticCode, message: str) -> ParsedArtifact:
    """An artifact whose bytes could not be safely read/decoded/parsed at
    all. Kind cannot be determined from unreadable content, so it defaults
    to ``ArtifactKind.BLOCK`` (the primary artifact kind this project
    handles) -- a documented, pragmatic default, not an inferred schema.
    """
    identity = _identity(ArtifactKind.BLOCK, candidate)
    diagnostic = _diagnostic(code, candidate.location, message, severity="error")
    record = ArtifactRecord(
        identity=identity,
        status=ArtifactStatus.FAILED,
        location=candidate.location,
        diagnostics=(diagnostic,),
    )
    return ParsedArtifact(record=record)


def _preserved_version(
    document: model.Document,
    candidate: DiscoveredFile,
    code: DiagnosticCode,
    version: str | None,
) -> ParsedArtifact:
    """A recognized, fully-parsed ``SW.Blocks.*`` export whose engineering
    version is not (or cannot be confirmed to be) V21."""
    identity = _block_identity(document, candidate)
    message = _version_message(code, version)
    diagnostic = _diagnostic(code, candidate.location, message, severity="warning")
    record = ArtifactRecord(
        identity=identity,
        status=ArtifactStatus.PRESERVED,
        location=candidate.location,
        diagnostics=(diagnostic,),
    )
    return ParsedArtifact(record=record)


def _preserved_udt_version(
    candidate: DiscoveredFile, name: str, code: DiagnosticCode, version: str | None
) -> ParsedArtifact:
    """A recognized ``SW.Types.PlcStruct`` (UDT) export whose engineering
    version is not (or cannot be confirmed to be) V21."""
    identity = _identity(ArtifactKind.UDT, candidate, name=name)
    message = _version_message(code, version)
    diagnostic = _diagnostic(code, candidate.location, message, severity="warning")
    record = ArtifactRecord(
        identity=identity,
        status=ArtifactStatus.PRESERVED,
        location=candidate.location,
        diagnostics=(diagnostic,),
    )
    return ParsedArtifact(record=record)


def _version_message(code: DiagnosticCode, version: str | None) -> str:
    if code is DiagnosticCode.UNSUPPORTED_TIA_VERSION:
        return f"engineering version {version!r} is not a supported V21 export"
    return "artifact has no engineering version and cannot be assumed to be V21"


def _block_artifact(document: model.Document, candidate: DiscoveredFile) -> ParsedArtifact:
    identity = _block_identity(document, candidate)
    record = ArtifactRecord(
        identity=identity, status=ArtifactStatus.COMPLETE, location=candidate.location
    )
    return ParsedArtifact(record=record, document=document)


def _unsupported_artifact(candidate: DiscoveredFile, root: ET.Element) -> ParsedArtifact:
    """Preserve unrecognized XML (neither ``SW.Blocks.*`` nor
    ``SW.Types.PlcStruct``) instead of guessing at its shape -- e.g. the
    real corpus's own ``PLC_1/PLC tags/*.xml`` (``SW.Tags.PlcTagTable``)
    naturally exercises this path.
    """
    kind = _guess_kind_from_root(root)
    identity = _identity(kind, candidate)
    root_child_names = ", ".join(sorted({parse._ln(child.tag) for child in root})) or "(none)"
    diagnostic = _diagnostic(
        DiagnosticCode.UNSUPPORTED_ARTIFACT,
        candidate.location,
        f"root element(s) [{root_child_names}] are not a recognized SimaticML "
        "block or UDT export",
        severity="warning",
    )
    record = ArtifactRecord(
        identity=identity,
        status=ArtifactStatus.PRESERVED,
        location=candidate.location,
        diagnostics=(diagnostic,),
    )
    return ParsedArtifact(record=record)


def _guess_kind_from_root(root: ET.Element) -> ArtifactKind:
    """Best-effort ``ArtifactKind`` guess for a recognized-XML-but-unsupported
    export, from the same ``SW.Blocks.*`` / ``SW.Types.*`` naming convention
    already used to recognize blocks and UDTs. Not an inferred schema --
    just picking which of the two already-known prefixes the root more
    closely resembles; defaults to ``BLOCK`` when neither matches.
    """
    for child in root:
        if parse._ln(child.tag).startswith("SW.Types."):
            return ArtifactKind.UDT
    return ArtifactKind.BLOCK


def _preserved_udt_parse_failure(candidate: DiscoveredFile, raw: bytes) -> ParsedArtifact:
    """The observed UDT shape could not be parsed safely: preserve it with
    a SHA-256 of its content (there is no dedicated hash field on
    ``ArtifactRecord`` yet, so it is carried in the diagnostic message) --
    never infer an XML schema."""
    digest = hashlib.sha256(raw).hexdigest()
    identity = _identity(ArtifactKind.UDT, candidate)
    diagnostic = _diagnostic(
        DiagnosticCode.UNSUPPORTED_ARTIFACT,
        candidate.location,
        f"UDT structure could not be safely parsed (sha256={digest})",
        severity="warning",
    )
    record = ArtifactRecord(
        identity=identity,
        status=ArtifactStatus.PRESERVED,
        location=candidate.location,
        diagnostics=(diagnostic,),
    )
    return ParsedArtifact(record=record)


def _udt_artifact(
    udt_elem: ET.Element, candidate: DiscoveredFile, version: str | None
) -> ParsedArtifact | None:
    """Adapt one recognized ``SW.Types.PlcStruct`` (UDT) export. Returns
    ``None`` (a sentinel the caller turns into
    ``_preserved_udt_parse_failure``) if the observed shape could not be
    parsed safely.

    Reuses ``parse._parse_interface`` -- the exact same
    Interface/Sections/Section/Member parsing already exercised against
    every block fixture -- since a UDT export's ``AttributeList >
    Interface`` is structurally identical to a block's (confirmed against
    all four real UDT fixtures: ``UDT_Settings.xml``,
    ``UDT_WORK_CNT.xml``, ``AnalogInputSettings.xml``, ``UDT_Device.xml``).

    The resulting ``model.Interface`` is wrapped in a synthetic
    ``model.Document``/``model.Block`` (``kind=UNKNOWN``, empty
    ``networks``) purely so ``extract_udt_references`` -- specified to
    take a ``model.Document`` -- can be reused unchanged for genuine
    UDT-to-UDT references too (e.g. ``UDT_Settings.xml``'s own
    ``Tank_1``/``Tank_2`` members reference the ``AnalogInputSettings``
    UDT). This is a reuse trick, not a claim that the export contains an
    ``SW.Blocks.*`` element: ``ArtifactRecord.identity.kind`` is always
    ``ArtifactKind.UDT`` here, never ``BLOCK``, and the empty ``networks``
    list makes ``extract_block_references`` a safe no-op if ever called on
    it by mistake.
    """
    try:
        attrs = parse._child(udt_elem, "AttributeList")
        name = parse._nz(parse._child_text(attrs, "Name")) or candidate.location.relative_path.stem
        interface = parse._parse_interface(parse._child(attrs, "Interface"))
    except Exception:  # defensive fallback; see module docstring above
        return None

    document = model.Document(
        engineering_version=version,
        block=model.Block(
            kind=model.BlockKind.UNKNOWN,
            id=udt_elem.get("ID", ""),
            name=name,
            interface=interface,
        ),
    )
    identity = _identity(ArtifactKind.UDT, candidate, name=name)
    record = ArtifactRecord(
        identity=identity, status=ArtifactStatus.COMPLETE, location=candidate.location
    )
    return ParsedArtifact(record=record, document=document)


# --------------------------------------------------------------------------- #
# Non-block XML: UDT or genuinely unsupported                                  #
# --------------------------------------------------------------------------- #


def _find_udt_element(root: ET.Element) -> ET.Element | None:
    """Mirror of ``parse._find_block_element``, but for the one observed
    UDT root shape (``SW.Types.PlcStruct``). Matched exactly, not a broader
    ``SW.Types.*`` prefix -- no other ``SW.Types.*`` shape has been
    observed in the committed corpus, and guessing at one would be
    inferring a schema.
    """
    for child in root:
        if parse._ln(child.tag) == "SW.Types.PlcStruct":
            return child
    return None


def _adapt_non_block_artifact(raw: bytes, candidate: DiscoveredFile) -> ParsedArtifact:
    """``parse.parse_bytes(raw)`` raised ``ValueError`` (no ``SW.Blocks.*``
    element) -- inspect the actual root to decide between a recognized UDT
    export and genuinely unsupported XML.
    """
    try:
        root = ET.fromstring(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ET.ParseError):
        return _failed(candidate, DiagnosticCode.MALFORMED_XML, "artifact is not well-formed XML")

    udt_elem = _find_udt_element(root)
    if udt_elem is None:
        return _unsupported_artifact(candidate, root)

    engineering = parse._child(root, "Engineering")
    version = engineering.get("version") if engineering is not None else None
    attrs = parse._child(udt_elem, "AttributeList")
    name = parse._nz(parse._child_text(attrs, "Name")) or candidate.location.relative_path.stem

    if version and "V21" not in version:
        return _preserved_udt_version(candidate, name, DiagnosticCode.UNSUPPORTED_TIA_VERSION, version)
    if not version:
        return _preserved_udt_version(candidate, name, DiagnosticCode.UNKNOWN_TIA_VERSION, None)

    outcome = _udt_artifact(udt_elem, candidate, version)
    if outcome is None:
        return _preserved_udt_parse_failure(candidate, raw)
    return outcome


# --------------------------------------------------------------------------- #
# Entry point                                                                  #
# --------------------------------------------------------------------------- #


def parse_simaticml_artifact(candidate: DiscoveredFile, limits: ProjectLimits) -> ParsedArtifact:
    """Adapt one discovered SimaticML XML artifact into a project-index
    record.

    Reads ``candidate``'s content exactly once, via
    ``candidate.artifact.read_bytes(limits)`` -- the reader closure
    captured at discovery time in Task 2. Never calls
    ``parse.parse_file(str(candidate.path))`` or otherwise reopens the file
    by a stored path.
    """
    input_limits = _as_input_limits(limits)
    try:
        raw = candidate.artifact.read_bytes(input_limits)
    except input_policy.InputViolation:
        return _failed(
            candidate, DiagnosticCode.MALFORMED_XML, "artifact could not be safely read as XML"
        )
    except ET.ParseError:
        return _failed(candidate, DiagnosticCode.MALFORMED_XML, "artifact is not well-formed XML")

    preflight_code = preflight_xml_bytes(raw, limits)
    if preflight_code is not None:
        return _failed(candidate, preflight_code, "artifact failed the bounded XML preflight")

    try:
        document = parse.parse_bytes(raw)
    except ET.ParseError:
        return _failed(candidate, DiagnosticCode.MALFORMED_XML, "artifact is not well-formed XML")
    except ValueError:
        return _adapt_non_block_artifact(raw, candidate)

    version = document.engineering_version
    if version and "V21" not in version:
        return _preserved_version(document, candidate, DiagnosticCode.UNSUPPORTED_TIA_VERSION, version)
    if not version:
        return _preserved_version(document, candidate, DiagnosticCode.UNKNOWN_TIA_VERSION, None)
    return _block_artifact(document, candidate)


# --------------------------------------------------------------------------- #
# Reference extraction                                                         #
# --------------------------------------------------------------------------- #


def extract_block_references(
    document: model.Document, source: SourceLocation
) -> tuple[ReferenceRequest, ...]:
    """Extract block-call references from a parsed V21 block's networks.

    Only ``FlgNet`` (LAD/FBD) networks carry ``Call`` elements in this
    corpus; other network sources are skipped. Uses the native field names
    already present in the parsed model (``Call.name``, ``Call.block_type``,
    ``Call.uid``) -- never an invented source-line number.
    """
    requests: list[ReferenceRequest] = []
    for network in document.block.networks:
        if not isinstance(network.source, model.FlgNet):
            continue
        for call in network.source.calls.values():
            requests.append(
                ReferenceRequest(
                    source=SourceLocation(source.relative_path, call.uid),
                    requested_name=call.name,
                    requested_block_kind=call.block_type,
                    namespace=(),
                    kind=ArtifactKind.BLOCK,
                )
            )
    return tuple(requests)


def _call_target_names(document: model.Document) -> frozenset[str]:
    """Every name called via a ``Call`` element anywhere in ``document``'s
    networks -- used to filter out a quoted-datatype member that actually
    names a block, not a UDT (see ``extract_udt_references``).
    """
    names: set[str] = set()
    for network in document.block.networks:
        if not isinstance(network.source, model.FlgNet):
            continue
        names.update(call.name for call in network.source.calls.values())
    return frozenset(names)


def _collect_udt_member_references(
    members: list[model.Member],
    source: SourceLocation,
    exclude: frozenset[str],
    requests: list[ReferenceRequest],
) -> None:
    for member in members:
        if member.is_udt:
            name = member.datatype[1:-1]
            if name not in exclude:
                requests.append(
                    ReferenceRequest(
                        source=source,
                        requested_name=name,
                        requested_block_kind=None,
                        namespace=(),
                        kind=ArtifactKind.UDT,
                    )
                )
        _collect_udt_member_references(member.children, source, exclude, requests)


def extract_udt_references(
    document: model.Document, source: SourceLocation
) -> tuple[ReferenceRequest, ...]:
    """Extract UDT (struct-type) references from quoted ``Datatype`` syntax
    observed in the real corpus -- e.g. ``UDT_Settings.xml``'s
    ``Datatype="&quot;AnalogInputSettings&quot;"``, unescaped by
    ElementTree to a literal-quoted string and already flagged by
    ``model.Member.is_udt``.

    **Known ambiguity, resolved conservatively:** the same quoted syntax is
    also used, in this same corpus, for a function-block *instance*
    declared as a Static member (e.g. ``MotorSoftstart.xml``'s
    ``C_WORK_TIME`` member, ``Datatype="&quot;TIME_COUNTER_FB&quot;"`` --
    a block, not a UDT). Neither shape carries a distinguishing attribute
    (contrast a *typed* system-FB instance like
    ``Datatype="TON_TIME" Version="1.0"``, which is never quoted at all).
    Since there is no per-member signal to tell them apart, this function
    excludes any quoted name that also appears as a ``Call``'s target name
    *within the same document* -- provably a block reference, already
    captured by ``extract_block_references`` -- rather than guessing.
    Never attaches a source-line/element id ``model.Member`` cannot prove
    (it has no ``UId``); every request reuses ``source`` unchanged.
    """
    exclude = _call_target_names(document)
    requests: list[ReferenceRequest] = []
    for section in document.block.interface.sections:
        _collect_udt_member_references(section.members, source, exclude, requests)
    return tuple(requests)
