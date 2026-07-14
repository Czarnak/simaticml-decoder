"""Tests for the V21 SimaticML project-artifact adapter (project_xml.py).

Exercises the real committed corpus end-to-end through
``project_discovery.discover_project_files`` -> ``project_xml.parse_simaticml_artifact``
(no mocked filesystem access), plus a handful of inline byte-string cases for
XML-robustness paths (malformed XML, structural limits) that are not
"corpus content" concerns.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

import pytest

from simaticml_decoder import model, project_xml
from simaticml_decoder.project_discovery import DiscoveryResult, discover_project_files
from simaticml_decoder.project_model import (
    ArtifactKind,
    ArtifactOrigin,
    ArtifactStatus,
    DiagnosticCode,
    InputFormat,
    ProjectLimits,
    SourceLocation,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
_XML_SUFFIXES = {".xml": InputFormat.SIMATICML_XML}


# --------------------------------------------------------------------------- #
# Step 1: corpus-contract test                                                #
# --------------------------------------------------------------------------- #


def test_native_v21_project_corpus_is_complete(project_fixture_root):
    required = {
        "SimaticML/PLC_1/Program blocks/100_Inputs/Inputs_FB.xml",
        "SimaticML/PLC_1/PLC data types/UDT_Settings.xml",
        "SimaticML/Types/Blocks/AnalogInput.xml",
        "SimaticML/Types/UDTs/AnalogInputSettings.xml",
        # Corpus inventory (Task 3) found real Call sites across
        # SimaticML/PLC_1/Program blocks/** resolve uniquely to a real
        # exported block in every case -- no naturally-occurring
        # missing-reference or ambiguous-reference call, and every real
        # export declares Engineering version="V21" -- so these three cases
        # are minimal, explicitly-labeled synthetic additions instead
        # (see tests/fixtures/manifest.json's project_mode.artifacts for the
        # full "why", including each fixture's test_purpose).
        "SimaticML_synthetic/PLC_1/Program blocks/SyntheticCases_FB.xml",
        "SimaticML_synthetic/PLC_1/Program blocks/AmbiguousTarget.xml",
        "SimaticML_synthetic/Types/Blocks/AmbiguousTarget.xml",
        "SimaticML_synthetic/NonV21/UnsupportedVersion_FB.xml",
        "SimaticML_synthetic/NonV21/MissingVersion_FB.xml",
    }
    actual = {
        path.relative_to(project_fixture_root).as_posix()
        for path in project_fixture_root.rglob("*.xml")
    }
    assert required <= actual


def test_project_mode_manifest_paths_exist_and_synthetic_ones_are_labeled(project_fixture_root):
    manifest = json.loads((project_fixture_root / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["project_mode"]["artifacts"]:
        path = project_fixture_root / entry["path"]
        assert path.is_file(), entry["path"]
        if entry["path"].startswith("SimaticML_synthetic/"):
            assert entry["origin_tag"] == "synthetic", entry["path"]
            assert "test_purpose" in entry, entry["path"]
        else:
            assert entry["origin_tag"] == "native", entry["path"]


# --------------------------------------------------------------------------- #
# Shared discovery fixture: real end-to-end discovery, no mocking            #
# --------------------------------------------------------------------------- #


@pytest.fixture
def simaticml_discovery() -> DiscoveryResult:
    """Function-scoped (not module-scoped): each discovered artifact's
    reader closure is single-consumption by design (Task 2's security
    model -- the handle is closed after its one read), so every test that
    calls ``parse_simaticml_artifact`` needs its own fresh discovery pass
    rather than sharing already-read handles with other tests."""
    root = FIXTURES_DIR / "SimaticML"
    return discover_project_files(root, _XML_SUFFIXES, ProjectLimits())


@pytest.fixture
def synthetic_discovery() -> DiscoveryResult:
    """Function-scoped for the same single-consumption-handle reason as
    ``simaticml_discovery`` above."""
    root = FIXTURES_DIR / "SimaticML_synthetic"
    return discover_project_files(root, _XML_SUFFIXES, ProjectLimits())


def _by_relative_path(result: DiscoveryResult):
    return {item.location.relative_path.as_posix(): item for item in result.files}


# --------------------------------------------------------------------------- #
# parse_simaticml_artifact: real V21 blocks                                   #
# --------------------------------------------------------------------------- #


def test_parses_a_real_user_block_with_a_library_call(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/Program blocks/100_Inputs/Inputs_FB.xml"]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.COMPLETE
    assert outcome.record.diagnostics == ()
    assert outcome.record.identity.kind == ArtifactKind.BLOCK
    assert outcome.record.identity.origin == ArtifactOrigin.USER
    assert outcome.record.identity.name == "Inputs_FB"
    assert outcome.record.identity.block_kind == "FB"
    assert outcome.document is not None
    assert outcome.document.engineering_version == "V21"


def test_parses_a_real_project_library_block(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["Types/Blocks/AnalogInput.xml"]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.COMPLETE
    assert outcome.record.identity.kind == ArtifactKind.BLOCK
    assert outcome.record.identity.origin == ArtifactOrigin.PROJECT_LIBRARY
    assert outcome.record.identity.name == "AnalogInput"
    assert outcome.record.identity.block_kind == "FB"


def test_parses_a_real_user_udt_and_wraps_its_interface_in_a_document(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/PLC data types/UDT_Settings.xml"]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.COMPLETE
    assert outcome.record.diagnostics == ()
    assert outcome.record.identity.kind == ArtifactKind.UDT
    assert outcome.record.identity.origin == ArtifactOrigin.USER
    assert outcome.record.identity.name == "UDT_Settings"
    assert outcome.record.identity.block_kind is None
    assert outcome.document is not None
    assert outcome.document.engineering_version == "V21"
    assert outcome.document.block.kind == model.BlockKind.UNKNOWN


def test_parses_a_real_project_library_udt(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["Types/UDTs/AnalogInputSettings.xml"]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.COMPLETE
    assert outcome.record.identity.kind == ArtifactKind.UDT
    assert outcome.record.identity.origin == ArtifactOrigin.PROJECT_LIBRARY
    assert outcome.record.identity.name == "AnalogInputSettings"


def test_real_plc_tag_table_is_preserved_as_unsupported_artifact(simaticml_discovery):
    """PLC_1/PLC tags/*.xml (SW.Tags.PlcTagTable) is neither a SW.Blocks.*
    block nor a SW.Types.PlcStruct UDT -- this is a naturally-occurring
    UNSUPPORTED_ARTIFACT case in the real corpus (no synthetic fixture
    needed for this diagnostic code)."""
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/PLC tags/Inputs.xml"]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.UNSUPPORTED_ARTIFACT]
    assert outcome.document is None


# --------------------------------------------------------------------------- #
# parse_simaticml_artifact: synthetic version cases                           #
# --------------------------------------------------------------------------- #


def test_synthetic_non_v21_version_is_preserved(synthetic_discovery):
    files = _by_relative_path(synthetic_discovery)
    candidate = files["NonV21/UnsupportedVersion_FB.xml"]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert [d.code for d in outcome.record.diagnostics] == [
        DiagnosticCode.UNSUPPORTED_TIA_VERSION
    ]
    assert outcome.record.identity.name == "UnsupportedVersion_FB"
    assert outcome.document is None


def test_synthetic_missing_version_is_preserved(synthetic_discovery):
    files = _by_relative_path(synthetic_discovery)
    candidate = files["NonV21/MissingVersion_FB.xml"]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.UNKNOWN_TIA_VERSION]
    assert outcome.record.identity.name == "MissingVersion_FB"


# --------------------------------------------------------------------------- #
# parse_simaticml_artifact: malformed / oversized XML (inline, not corpus)    #
# --------------------------------------------------------------------------- #


class _FakeArtifact:
    """Minimal duck-typed stand-in for input_policy.InputArtifact, proving
    parse_simaticml_artifact reads content via exactly one
    ``read_bytes(limits)`` call and nothing else."""

    def __init__(self, raw: bytes):
        self._raw = raw
        self.read_calls = 0

    def read_bytes(self, limits) -> bytes:
        self.read_calls += 1
        return self._raw


class _FakeDiscoveredFile:
    def __init__(self, raw: bytes, relative_path: str):
        self.artifact = _FakeArtifact(raw)
        self.location = SourceLocation(PurePosixPath(relative_path))


def test_malformed_xml_is_failed_with_a_single_read():
    candidate = _FakeDiscoveredFile(b"<Document><Unclosed>", "broken.xml")

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.FAILED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.MALFORMED_XML]
    assert candidate.artifact.read_calls == 1


def test_element_count_limit_is_reported_as_xml_element_limit():
    raw = ("<Document>" + "<X/>" * 50 + "</Document>").encode("utf-8")
    candidate = _FakeDiscoveredFile(raw, "huge.xml")
    limits = ProjectLimits(max_xml_elements=10)

    outcome = project_xml.parse_simaticml_artifact(candidate, limits)

    assert outcome.record.status == ArtifactStatus.FAILED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.XML_ELEMENT_LIMIT]
    assert candidate.artifact.read_calls == 1


def test_unrecognized_but_well_formed_xml_is_preserved_as_unsupported():
    raw = b'<Document><Engineering version="V21" /><SomethingElse ID="0" /></Document>'
    candidate = _FakeDiscoveredFile(raw, "other.xml")

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.UNSUPPORTED_ARTIFACT]
    assert outcome.record.identity.kind == ArtifactKind.BLOCK  # default guess


def test_unrecognized_xml_with_sw_types_prefix_guesses_udt_kind():
    raw = b'<Document><Engineering version="V21" /><SW.Types.PlcArray ID="0" /></Document>'
    candidate = _FakeDiscoveredFile(raw, "array.xml")

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.UNSUPPORTED_ARTIFACT]
    assert outcome.record.identity.kind == ArtifactKind.UDT


def test_a_real_discovered_malformed_file_fails_via_read_bytes_parse_error(tmp_path):
    """Real end-to-end regression (no fake artifact): a genuinely discovered
    artifact's ``read_bytes()`` call itself raises an *uncaught*
    ``xml.etree.ElementTree.ParseError`` for malformed XML content --
    ``input_policy._validate_xml_complexity``'s ``iterparse`` fails during
    the read itself, before ``preflight_xml_bytes`` ever runs. Verified
    directly against ``discover_project_files`` -> real handle-backed
    ``read_bytes()``, not a mock.
    """
    root = tmp_path / "project"
    root.mkdir()
    (root / "broken.xml").write_bytes(b"<Document><Unclosed>")
    result = discover_project_files(root, _XML_SUFFIXES, ProjectLimits())
    candidate = result.files[0]

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.FAILED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.MALFORMED_XML]


def test_read_bytes_input_violation_is_failed_with_malformed_xml():
    """A ``read_bytes()`` call that itself raises ``InputViolation`` (e.g. a
    handle-level failure) must be converted into a FAILED ParsedArtifact,
    not propagate out of parse_simaticml_artifact."""
    from simaticml_decoder import input_policy

    class _RaisingArtifact:
        def read_bytes(self, limits):
            raise input_policy.InputViolation("unreadable_input", "simulated handle failure")

    candidate = _FakeDiscoveredFile(b"", "unreadable.xml")
    candidate.artifact = _RaisingArtifact()

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.FAILED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.MALFORMED_XML]


def test_synthetic_udt_with_unsupported_version_is_preserved():
    raw = (
        b'<Document><Engineering version="V19" /><SW.Types.PlcStruct ID="0">'
        b"<AttributeList><Name>SomeUdt</Name></AttributeList></SW.Types.PlcStruct></Document>"
    )
    candidate = _FakeDiscoveredFile(raw, "old_udt.xml")

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert [d.code for d in outcome.record.diagnostics] == [
        DiagnosticCode.UNSUPPORTED_TIA_VERSION
    ]
    assert outcome.record.identity.kind == ArtifactKind.UDT
    assert outcome.record.identity.name == "SomeUdt"


def test_synthetic_udt_with_missing_version_is_preserved():
    raw = (
        b"<Document><SW.Types.PlcStruct ID=\"0\">"
        b"<AttributeList><Name>SomeUdt</Name></AttributeList></SW.Types.PlcStruct></Document>"
    )
    candidate = _FakeDiscoveredFile(raw, "no_version_udt.xml")

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.UNKNOWN_TIA_VERSION]
    assert outcome.record.identity.kind == ArtifactKind.UDT


def test_preflight_rejects_bytes_that_do_not_decode_as_utf8():
    raw = b"\xff\xfe\x00not valid utf-8 \xff"
    assert project_xml.preflight_xml_bytes(raw, ProjectLimits()) is DiagnosticCode.MALFORMED_XML


def test_parse_bytes_parse_error_is_failed_with_malformed_xml(monkeypatch, simaticml_discovery):
    """Defensive-only branch: by the time preflight_xml_bytes has succeeded,
    parse.parse_bytes(raw) parsing the identical text should never raise
    ET.ParseError differently. Exercise the fallback directly via
    monkeypatch to prove it still degrades safely if it ever did."""
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/Program blocks/100_Inputs/Inputs_FB.xml"]

    def _boom(_raw):
        import xml.etree.ElementTree as ET

        raise ET.ParseError("simulated parse failure after preflight passed")

    monkeypatch.setattr(project_xml.parse, "parse_bytes", _boom)

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.FAILED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.MALFORMED_XML]


def test_adapt_non_block_artifact_falls_back_when_root_re_parse_fails(monkeypatch):
    """Defensive-only branch: by the time parse.parse_bytes(raw) has raised
    ValueError, raw already decoded successfully at least once (during
    preflight), so re-decoding it again here should never actually fail in
    practice. Exercise the fallback directly via monkeypatch to prove it
    still degrades safely if it ever did."""
    import xml.etree.ElementTree as ET

    def _boom(*_args, **_kwargs):
        raise ET.ParseError("simulated re-parse failure")

    monkeypatch.setattr(project_xml.ET, "fromstring", _boom)

    candidate = _FakeDiscoveredFile(b"", "whatever.xml")
    outcome = project_xml._adapt_non_block_artifact(b"<Document />", candidate)

    assert outcome.record.status == ArtifactStatus.FAILED
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.MALFORMED_XML]


def test_artifact_origin_defaults_to_unknown_for_an_empty_relative_path():
    """Defensive edge case: a relative_path with no parts at all (never
    produced by real discovery, which always includes at least a filename)
    still resolves to UNKNOWN rather than raising."""
    assert project_xml._artifact_origin(PurePosixPath()) == ArtifactOrigin.UNKNOWN


def test_reads_artifact_bytes_exactly_once_for_a_real_fixture(simaticml_discovery):
    """Security-constraint regression: parse_simaticml_artifact must read a
    discovered artifact's content exactly once via
    ``candidate.artifact.read_bytes(limits)``, never re-opening by path."""
    files = _by_relative_path(simaticml_discovery)
    real_candidate = files["PLC_1/Program blocks/100_Inputs/Inputs_FB.xml"]
    raw = real_candidate.artifact.read_bytes(project_xml._as_input_limits(ProjectLimits()))
    wrapped = _FakeDiscoveredFile(raw, "PLC_1/Program blocks/100_Inputs/Inputs_FB.xml")

    outcome = project_xml.parse_simaticml_artifact(wrapped, ProjectLimits())

    assert wrapped.artifact.read_calls == 1
    assert outcome.record.status == ArtifactStatus.COMPLETE


# --------------------------------------------------------------------------- #
# preflight_xml_bytes: direct unit tests                                      #
# --------------------------------------------------------------------------- #


def test_preflight_accepts_clean_bytes():
    raw = b'<Document><Engineering version="V21" /></Document>'
    assert project_xml.preflight_xml_bytes(raw, ProjectLimits()) is None


def test_preflight_rejects_malformed_xml():
    raw = b"<Document><Unclosed>"
    assert project_xml.preflight_xml_bytes(raw, ProjectLimits()) is DiagnosticCode.MALFORMED_XML


def test_preflight_rejects_excess_depth():
    nested = "<A>" * 50 + "</A>" * 50
    raw = f"<Document>{nested}</Document>".encode()
    limits = ProjectLimits(max_xml_depth=5)
    assert project_xml.preflight_xml_bytes(raw, limits) is DiagnosticCode.XML_ELEMENT_LIMIT


# --------------------------------------------------------------------------- #
# extract_block_references                                                    #
# --------------------------------------------------------------------------- #


def test_extract_block_references_from_real_user_to_library_call(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/Program blocks/100_Inputs/Inputs_FB.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_block_references(outcome.document, candidate.location)

    assert len(requests) == 2
    for request in requests:
        assert request.requested_name == "AnalogInput"
        assert request.requested_block_kind == "FB"
        assert request.kind == ArtifactKind.BLOCK
        assert request.namespace == ()
        assert request.source.relative_path == candidate.location.relative_path
        assert request.source.element_id == "28"


def test_extract_block_references_from_real_multi_target_caller(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/Program blocks/999_MISC/MotorSoftstart.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_block_references(outcome.document, candidate.location)

    called = {(r.requested_name, r.requested_block_kind) for r in requests}
    assert called == {("TIME_COUNTER_FB", "FB"), ("deviceState", "FC")}


def test_extract_block_references_from_synthetic_missing_and_ambiguous_caller(
    synthetic_discovery,
):
    files = _by_relative_path(synthetic_discovery)
    candidate = files["PLC_1/Program blocks/SyntheticCases_FB.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_block_references(outcome.document, candidate.location)

    called = {(r.requested_name, r.requested_block_kind) for r in requests}
    assert called == {("Unexported_Helper", "FC"), ("AmbiguousTarget", "FC")}


def test_extract_block_references_skips_non_flgnet_and_empty_networks(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    # InputValues_DB.xml is a GlobalDB with no LAD/FBD networks at all.
    candidate = files["PLC_1/Program blocks/100_Inputs/InputValues_DB.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_block_references(outcome.document, candidate.location)

    assert requests == ()


# --------------------------------------------------------------------------- #
# extract_udt_references                                                       #
# --------------------------------------------------------------------------- #


def test_extract_udt_references_from_real_udt_to_udt_nested_members(simaticml_discovery):
    """UDT_Settings.xml's own nested Tank_1/Tank_2 members (two levels deep,
    under Sensors -> LiquidLevel) reference the AnalogInputSettings UDT --
    real observed UDT-to-UDT syntax, reached via the synthetic
    document/block wrapper `_udt_artifact` builds."""
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/PLC data types/UDT_Settings.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_udt_references(outcome.document, candidate.location)

    assert len(requests) == 2
    for request in requests:
        assert request.requested_name == "AnalogInputSettings"
        assert request.requested_block_kind is None
        assert request.kind == ArtifactKind.UDT


def test_extract_udt_references_excludes_a_quoted_datatype_that_is_actually_a_block_call(
    simaticml_discovery,
):
    """Regression for the real ambiguity found during Task 3's corpus
    inventory: MotorSoftstart.xml's "C_WORK_TIME" static member has
    Datatype='"TIME_COUNTER_FB"' (quoted, matching model.Member.is_udt),
    but TIME_COUNTER_FB is a block (called via a real <Call> in this same
    document), not a UDT. extract_udt_references must not report it."""
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/Program blocks/999_MISC/MotorSoftstart.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_udt_references(outcome.document, candidate.location)

    names = {r.requested_name for r in requests}
    assert names == {"UDT_WORK_CNT", "UDT_Device"}
    assert "TIME_COUNTER_FB" not in names


def test_extract_udt_references_from_real_block_interface_member(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/Program blocks/999_MISC/TIME_COUNTER_FB.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_udt_references(outcome.document, candidate.location)

    assert {r.requested_name for r in requests} == {"UDT_WORK_CNT"}


def test_extract_udt_references_from_real_library_block_settings_member(simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["Types/Blocks/AnalogInput.xml"]
    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    requests = project_xml.extract_udt_references(outcome.document, candidate.location)

    assert {r.requested_name for r in requests} == {"AnalogInputSettings"}


# --------------------------------------------------------------------------- #
# UDT parse-failure fallback (defensive, currently unreachable via any        #
# observed real or synthetic input -- exercised directly via monkeypatch)     #
# --------------------------------------------------------------------------- #


def test_udt_parse_failure_falls_back_to_preserved_with_sha256(monkeypatch, simaticml_discovery):
    files = _by_relative_path(simaticml_discovery)
    candidate = files["PLC_1/PLC data types/UDT_Settings.xml"]

    def _boom(*_args, **_kwargs):
        raise RuntimeError("simulated unsafe UDT shape")

    monkeypatch.setattr(project_xml.parse, "_parse_interface", _boom)

    outcome = project_xml.parse_simaticml_artifact(candidate, ProjectLimits())

    assert outcome.record.status == ArtifactStatus.PRESERVED
    assert outcome.record.identity.kind == ArtifactKind.UDT
    assert [d.code for d in outcome.record.diagnostics] == [DiagnosticCode.UNSUPPORTED_ARTIFACT]
    assert "sha256=" in outcome.record.diagnostics[0].message
    assert outcome.document is None
