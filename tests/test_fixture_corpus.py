"""Non-skipping Phase 0 regression contract for committed native exports."""

from __future__ import annotations

import json
from pathlib import Path

from simaticml_decoder import cli, emit, fold, parse


CORPUS_ROOT = Path(__file__).parent / "fixtures"
MANIFEST = CORPUS_ROOT / "manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _path(relative: str) -> Path:
    candidate = CORPUS_ROOT / relative
    assert candidate.is_relative_to(CORPUS_ROOT)
    return candidate


def _semantic_summary(decoded) -> dict:
    networks = []
    for network in decoded.networks:
        statements = []
        for statement in network.statements:
            statements.append(
                {
                    "condition": emit._expr(statement.value),
                    "kind": statement.kind.value,
                    "target": statement.target.name,
                    "type": type(statement).__name__,
                }
            )
        networks.append({"index": network.index, "statements": statements})
    return {"kind": decoded.kind, "name": decoded.name, "networks": networks}


def test_manifest_declares_local_evaluation_only_corpus():
    manifest = _manifest()

    assert manifest["schema_version"] == 1
    assert manifest["provenance"]["redistributable"] is False
    assert manifest["provenance"]["redaction_reviewed"] is False
    assert manifest["provenance"]["tia_version"] == "V21"
    assert {case["capability"] for case in manifest["cases"]} <= {
        "validated",
        "preserved-only",
        "unsupported",
    }
    assert "validated" not in {case["capability"] for case in manifest["cases"]}


def test_manifest_paths_are_committed_regular_files():
    manifest = _manifest()
    referenced = []
    for mapping in manifest["cross_format_mapping"]:
        referenced.extend(mapping["paths"].values())
    for case in manifest["cases"]:
        referenced.append(case["input"])
        referenced.extend(case["goldens"].values())
    referenced.extend(manifest["unpaired_resources"])

    for relative in referenced:
        path = _path(relative)
        assert path.is_file(), relative
        assert not path.is_symlink(), relative


def test_cross_format_mapping_does_not_pair_resources_across_export_roots():
    manifest = _manifest()

    for mapping in manifest["cross_format_mapping"]:
        paths = mapping["paths"]
        if "simatic_sd_resource" in paths:
            assert paths["simatic_sd_resource"].startswith("SimaticSD/")
    for resource in manifest["unpaired_resources"]:
        assert resource.startswith("SimaticSD_s7res/")
        assert not _path(resource).with_suffix(".s7dcl").exists()


def test_preserved_simaticml_fbd_matches_ir_scl_and_json_goldens():
    case = next(case for case in _manifest()["cases"] if case["id"] == "simaticml-fbd-fc")
    source = _path(case["input"])
    decoded = fold.fold_block(parse.parse_file(str(source)))

    assert _semantic_summary(decoded) == json.loads(
        _path(case["goldens"]["semantic_ir"]).read_text(encoding="utf-8")
    )
    assert emit.emit_scl(decoded) == _path(case["goldens"]["scl"]).read_text(encoding="utf-8")
    assert emit.emit_sidecar(decoded) == json.loads(
        _path(case["goldens"]["json"]).read_text(encoding="utf-8")
    )


def test_expected_diagnostics_are_non_skipping_and_exact(tmp_path):
    manifest = _manifest()
    for case in manifest["cases"]:
        if "diagnostic" not in case["goldens"]:
            continue
        expected = json.loads(_path(case["goldens"]["diagnostic"]).read_text(encoding="utf-8"))
        source = _path(case["input"])
        outcome = cli.decode_file(source, tmp_path / case["id"], "scl")
        assert outcome.status == "error", case["id"]
        assert outcome.error == f"{expected['code']}: {source.name}: {expected['message']}"


def test_every_unpaired_resource_has_the_published_diagnostic(tmp_path):
    expected = json.loads(
        _path("golden/diagnostics/sd-unpaired-resource.json").read_text(encoding="utf-8")
    )
    for relative in _manifest()["unpaired_resources"]:
        source = _path(relative)
        outcome = cli.decode_file(source, tmp_path / source.stem, "scl")
        assert outcome.status == "error", relative
        assert outcome.error == f"{expected['code']}: {source.name}: {expected['message']}"
