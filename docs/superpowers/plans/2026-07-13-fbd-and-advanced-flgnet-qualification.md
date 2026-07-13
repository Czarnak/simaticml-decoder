# FBD and Advanced `FlgNet` Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Qualify native TIA Portal V21 FBD and FBD_IEC `FlgNet` exports, then extend advanced LAD/FBD `FlgNet` semantics only where committed native fixtures prove the behavior, while emitting readability-first SCL and traceable non-re-importable JSON.

**Architecture:** Do not add an FBD-specific XML parser or renderer. `parse._parse_language()` already maps `FBD` and `FBD_IEC` to `model.Language.FBD`, and `parse._parse_network_source()` already routes `FlgNet` sources into the shared folder. Retain that path through `_NetFolder`, `ir`, and `emit`; add qualification tests, evidence-gated instruction coverage, and structured diagnostics around it. A FBD diagram's geometry, visual routing, and TIA re-importability remain deliberately outside the output contract.

**Tech Stack:** Python 3.11+, existing `xml.etree.ElementTree` parser, semantic IR, standard-library JSON, pytest/golden JSON fixtures, Ruff.

## Global Constraints

- Satisfies AC-005, AC-006, AC-007, AC-012, AC-013, and AC-014 in `docs/ADVANCED_TRANSLATION_ACCEPTANCE_CRITERIA.md`.
- Input is native, sanitized V21 SimaticML export only. A fixture must record its source format, V21 provenance, redaction/license status, capability label, and golden outputs.
- A `validated` capability label means the exact fixture runs without skip in CI. Unobserved instruction names and wire shapes remain `preserved-only` or `unsupported`; they never inherit support from a neighboring LAD/FBD construct.
- Output fidelity is `readable-analysis`: readable SCL, traceable JSON, explicit limitations, and `reimportable: false`. It does not promise FBD layout preservation, exact scan-cycle equivalence beyond qualified semantics, or a TIA import artifact.
- Structured diagnostics distinguish `unknown-instruction`, `known-unsupported-form`, `malformed-input`, and `missing-reference`. Every diagnostic includes at least network index and source `UId` when one exists.
- Keep unsupported source visible. Emit `// (!) UNHANDLED ...` in SCL and a matching JSON diagnostic; never synthesize executable-looking SCL for it.
- GRAPH remains deferred. Do not use FBD work to add a GRAPH parser, a pseudo-SCL GRAPH renderer, or a re-import path.
- Shared fixture tracking and the 80% quality threshold are owned by the project-ingestion plan; this plan consumes that corpus contract rather than reintroducing fixture skips.

## Planned File Structure

| Path | Responsibility |
| --- | --- |
| `tests/fixtures/corpus/v21/simaticml/fbd/` | Native sanitized FBD/FBD_IEC exports and one intentional unsupported-shape export. |
| `tests/fixtures/corpus/v21/metadata.json` | Per-fixture provenance, expected language/source shape, instruction inventory, and capability labels. |
| `tests/golden/fbd/v21/*.ir.json` | Canonical semantic snapshots of qualified FBD networks. |
| `tests/golden/fbd/v21/*.scl` | Readability-first SCL golden outputs. |
| `tests/golden/fbd/v21/*.sidecar.json` | Trace/contract/diagnostic golden outputs. |
| `tests/test_fbd_corpus_integrity.py` | Asserts corpus completeness and no fixture-related skip path. |
| `tests/test_fbd_parse_native.py` | Verifies `FBD` and `FBD_IEC` parse to `Language.FBD` plus native `FlgNet` source. |
| `tests/test_fbd_semantics.py` | Verifies signal flow, calls, EN/ENO, fan-out, multiple outputs, and evidence-gated advanced constructs. |
| `tests/test_fbd_goldens.py` | Compares canonical semantic, SCL, and sidecar output to committed golden artifacts. |
| `tests/test_fbd_cli.py` | End-to-end CLI behavior and non-re-importability metadata. |
| `src/simaticml_decoder/semantic_snapshot.py` | Canonical, JSON-serializable immutable view of semantic IR for golden tests. |
| `src/simaticml_decoder/ir.py` | Adds a stable diagnostic code to `Unhandled` only if it cannot be derived without ambiguity. |
| `src/simaticml_decoder/fold.py` | Tags unsupported semantic paths precisely; does not branch by diagram language. |
| `src/simaticml_decoder/instructions.py` | Adds only observed instruction specifications with a native fixture and test. |
| `src/simaticml_decoder/emit.py` | Emits output contract and structured statement diagnostics in the JSON sidecar. |

---

### Task 1: Commit a native FBD corpus contract and prohibit supported-case skips

**Files:**

- Create: `tests/test_fbd_corpus_integrity.py`
- Create: `tests/fixtures/corpus/v21/simaticml/fbd/`
- Modify: `tests/fixtures/corpus/v21/metadata.json`
- Modify: `tests/conftest.py`

**Interfaces:**

- Consumes: the user-supplied V21 SimaticML export, already sanitized for source control.
- Produces: stable fixture paths and metadata consumed by all FBD tests.

- [ ] **Step 1: Add a failing corpus-integrity test**

```python
EXPECTED_FBD_FIXTURES = {
    "fbd_signal_flow.xml",
    "fbd_iec_signal_flow.xml",
    "fbd_en_eno.xml",
    "fbd_fanout_multi_output.xml",
    "fbd_user_fc_call.xml",
    "fbd_user_fb_instance_call.xml",
    "fbd_mixed_lad_fbd.xml",
    "fbd_unsupported_part.xml",
}


def test_committed_v21_fbd_corpus_is_complete_and_non_skipping():
    actual = {path.name for path in FBD_ROOT.glob("*.xml")}
    assert EXPECTED_FBD_FIXTURES <= actual
    metadata = json.loads((CORPUS_ROOT / "metadata.json").read_text(encoding="utf-8"))
    assert all(metadata["artifacts"][name]["tia_version"] == "V21" for name in EXPECTED_FBD_FIXTURES)
    assert "pytest.skip" not in Path("tests/conftest.py").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run it and verify it fails before the corpus exists**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_corpus_integrity.py -v -p no:cacheprovider`

Expected: FAIL for missing fixture paths or missing metadata. Do not replace the failure with a skip.

- [ ] **Step 3: Add source-controlled fixture metadata**

For every file, record `tia_version: "V21"`, `format: "simaticml-xml"`, `language` (`FBD` or `FBD_IEC`), `capability` (`validated`, `preserved-only`, or `unsupported`), `expected_source: "FlgNet"`, `expected_inventory`, `redaction`, and `license`. The unsupported fixture must identify the expected diagnostic code and `UId` rather than relying on prose matching.

Change the shared fixture helper so supported V21 fixture absence raises an assertion with the expected path. If a developer needs a local-only helper, give it a distinct name and do not use it from supported-format integration tests.

- [ ] **Step 4: Run integrity validation**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_corpus_integrity.py -v -p no:cacheprovider`

Expected: PASS with every required native export present and no fixture-related skip mechanism.

- [ ] **Step 5: Commit the corpus boundary**

```bash
git add tests/fixtures/corpus/v21 tests/conftest.py tests/test_fbd_corpus_integrity.py
git commit -m "test: add native V21 FBD corpus contract"
```

### Task 2: Prove that FBD and FBD_IEC use the shared `FlgNet` front end

**Files:**

- Create: `tests/test_fbd_parse_native.py`
- Modify: `src/simaticml_decoder/parse.py` only if a native V21 fixture disproves the current source-shape handling

**Interfaces:**

- Consumes: committed FBD fixtures and `parse.parse_file(path)`.
- Produces: a qualification boundary: native FBD may proceed to folding only when it is `Language.FBD` plus `model.FlgNet`.

- [ ] **Step 1: Write failing native parsing tests**

```python
@pytest.mark.parametrize("fixture_name", ["fbd_signal_flow.xml", "fbd_iec_signal_flow.xml"])
def test_native_fbd_uses_fbd_language_and_flgnet_source(fixture_name):
    document = parse.parse_file(str(FBD_ROOT / fixture_name))
    fbd_networks = [network for network in document.block.networks if network.language is model.Language.FBD]

    assert fbd_networks
    assert all(isinstance(network.source, model.FlgNet) for network in fbd_networks)
```

- [ ] **Step 2: Run the test and verify the actual source shape**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_parse_native.py -v -p no:cacheprovider`

Expected: PASS if native export uses the existing shared shape. If it fails because the source is not `FlgNet`, preserve the source and mark the fixture `preserved-only`; do not create a synthetic FBD netlist parser.

- [ ] **Step 3: Add only evidence-backed parser changes**

Keep the existing language map as the desired result:

```python
mapping = {
    "LAD": model.Language.LAD,
    "LAD_IEC": model.Language.LAD,
    "FBD": model.Language.FBD,
    "FBD_IEC": model.Language.FBD,
}
```

If the fixture exposes a namespace or local-name variation in `FlgNet`, add a regression test first, then extend the existing local-name helper. Preserve unknown XML data in `raw`; do not discard it merely to satisfy a folding test.

- [ ] **Step 4: Run parser regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_parse_native.py tests/test_parse.py -v -p no:cacheprovider`

Expected: PASS for existing LAD/SCL behavior and qualified FBD inputs.

- [ ] **Step 5: Commit the parsing qualification**

```bash
git add src/simaticml_decoder/parse.py tests/test_fbd_parse_native.py
git commit -m "test: qualify native FBD FlgNet parsing"
```

### Task 3: Lock the readable-analysis output contract and canonical semantic goldens

**Files:**

- Create: `tests/test_fbd_goldens.py`
- Create: `tests/golden/fbd/v21/`
- Create: `src/simaticml_decoder/semantic_snapshot.py`
- Modify: `src/simaticml_decoder/emit.py`

**Interfaces:**

- Consumes: `ir.DecodedBlock` from `fold.fold_block()`.
- Produces: `semantic_snapshot(decoded)`, sidecar keys `output_contract` and `diagnostics`, plus stable SCL/semantic/sidecar goldens.

- [ ] **Step 1: Write a failing sidecar contract test**

```python
def test_fbd_sidecar_declares_readable_analysis_and_no_reimportability():
    decoded = fold.fold_block(parse.parse_file(str(FBD_ROOT / "fbd_signal_flow.xml")).block)
    sidecar = emit.emit_sidecar(decoded)

    assert sidecar["output_contract"] == {
        "fidelity": "readable-analysis",
        "reimportable": False,
        "limitations": [
            "FBD diagram geometry and wire routing are not preserved",
            "Output is not a TIA import artifact",
        ],
    }
    assert sidecar["diagnostics"] == []


def test_semantic_snapshot_is_canonical_json_data():
    decoded = fold.fold_block(parse.parse_file(str(FBD_ROOT / "fbd_signal_flow.xml")).block)
    snapshot = semantic_snapshot.semantic_snapshot(decoded)

    assert snapshot["node_type"] == "DecodedBlock"
    assert json.loads(json.dumps(snapshot, sort_keys=True)) == snapshot
```

- [ ] **Step 2: Run it and verify it fails on the current sidecar schema**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_goldens.py::test_fbd_sidecar_declares_readable_analysis_and_no_reimportability -v -p no:cacheprovider`

Expected: FAIL because `output_contract` and `diagnostics` are not present.

- [ ] **Step 3: Add explicit sidecar metadata without changing SCL execution claims**

```python
def _output_contract() -> dict[str, object]:
    return {
        "fidelity": "readable-analysis",
        "reimportable": False,
        "limitations": [
            "FBD diagram geometry and wire routing are not preserved",
            "Output is not a TIA import artifact",
        ],
    }


# src/simaticml_decoder/semantic_snapshot.py
def _snapshot(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            "node_type": type(value).__name__,
            **{field.name: _snapshot(getattr(value, field.name)) for field in fields(value)},
        }
    if isinstance(value, dict):
        return {str(key): _snapshot(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_snapshot(item) for item in value]
    return value


def semantic_snapshot(decoded: ir.DecodedBlock) -> dict[str, object]:
    snapshot = _snapshot(decoded)
    assert isinstance(snapshot, dict)
    return snapshot


def emit_sidecar(decoded: ir.DecodedBlock) -> dict:
    return {
        "output_contract": _output_contract(),
        "diagnostics": _statement_diagnostics(decoded),
        # retain all existing sidecar fields below this point
    }
```

Build `*.ir.json` with `semantic_snapshot(decoded)`, and build `*.sidecar.json` with `emit_sidecar(decoded)`; neither uses Python `repr()` output. Use `json.dumps(..., sort_keys=True, indent=2)` for both goldens and normalize a terminal newline.

- [ ] **Step 4: Run contract and golden tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_goldens.py -v -p no:cacheprovider`

Expected: PASS; qualified fixtures match semantic, SCL, and JSON goldens byte-for-byte.

- [ ] **Step 5: Commit the fidelity contract**

```bash
git add src/simaticml_decoder/emit.py tests/test_fbd_goldens.py tests/golden/fbd/v21
git commit -m "feat: declare FBD analysis output contract"
```

### Task 4: Fold qualified FBD signal-flow semantics through the existing graph folder

**Files:**

- Create: `tests/test_fbd_semantics.py`
- Modify: `src/simaticml_decoder/fold.py`
- Modify: `src/simaticml_decoder/instructions.py` only for fixture-proven part names and forms
- Modify: `src/simaticml_decoder/ir.py` only if `Unhandled` needs a non-derivable diagnostic code

**Interfaces:**

- Consumes: `model.FlgNet`, the fixture metadata's expected inventory, and instruction specifications.
- Produces: correct `ir.NetworkLogic` statements, source trace, and precise unsupported diagnostics.

- [ ] **Step 1: Write failing behavior tests for every qualified semantic family**

```python
@pytest.mark.parametrize(
    "fixture_name",
    [
        "fbd_signal_flow.xml",
        "fbd_en_eno.xml",
        "fbd_fanout_multi_output.xml",
        "fbd_user_fc_call.xml",
        "fbd_user_fb_instance_call.xml",
    ],
)
def test_qualified_fbd_fixture_has_expected_semantic_inventory(fixture_name):
    decoded = _decode_fixture(fixture_name)
    expected_inventory = _fixture_metadata(fixture_name)["expected_inventory"]
    assert {key: decoded.instruction_inventory[key] for key in expected_inventory} == expected_inventory
    assert not _unhandled_statements(decoded)
```

For advanced `FlgNet` support, add one fixture-and-test pair for each observed family: advanced access path, array/bit slice, UDT or DB addressing, multi-instance user call, and any instruction whose metadata says `validated`. No catalog entry is added without its pair.

- [ ] **Step 2: Run the behavior tests and verify each missing semantic is visible**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_semantics.py -v -p no:cacheprovider`

Expected: FAIL only for the specific fixture-proven instruction/form that lacks folding behavior; unrelated fixtures remain stable.

- [ ] **Step 3: Add minimal instruction and folding behavior per observed form**

Use the existing `instructions.lookup()` and `_NetFolder` path. For a fixture-proven instruction, add a specification that names its category, required inputs, outputs, and rendering behavior; then verify it against the native UIds/pins. The implementation shape remains shared:

```python
if isinstance(source, model.FlgNet):
    folder = _NetFolder(net.index, source)
    logic.statements = folder.statements
    logic.warnings = folder.warnings
    return logic, folder
```

Do not add `if net.language is FBD` branches. The semantics are driven by the graph, pins, and instruction specification, not the editor used to draw the network.

- [ ] **Step 4: Run focused semantics and existing folding tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_semantics.py tests/test_fold.py tests/test_instructions.py -v -p no:cacheprovider`

Expected: PASS; each claimed advanced form is represented by a committed native fixture and its golden output.

- [ ] **Step 5: Commit each independently qualified semantic family**

```bash
git add src/simaticml_decoder/fold.py src/simaticml_decoder/instructions.py src/simaticml_decoder/ir.py tests/test_fbd_semantics.py tests/fixtures/corpus/v21 tests/golden/fbd/v21
git commit -m "feat: qualify advanced FBD FlgNet semantics"
```

### Task 5: Make unknown and known-unsupported FBD constructs diagnosable end to end

**Files:**

- Create: `tests/test_fbd_diagnostics.py`
- Modify: `src/simaticml_decoder/ir.py`
- Modify: `src/simaticml_decoder/fold.py`
- Modify: `src/simaticml_decoder/emit.py`

**Interfaces:**

- Consumes: unsupported native `FlgNet` fixture and `ir.Unhandled` statements.
- Produces: SCL comment and JSON diagnostic with a canonical diagnostic code, network index, `UId`, and part name.

- [ ] **Step 1: Write a failing unsupported-form test**

```python
def test_unsupported_fbd_part_is_visible_but_not_rendered_as_executable_scl():
    decoded = _decode_fixture("fbd_unsupported_part.xml")
    scl = emit.emit_scl(decoded)
    sidecar = emit.emit_sidecar(decoded)
    expected = _fixture_metadata("fbd_unsupported_part.xml")["expected_diagnostic"]

    assert "// (!) UNHANDLED" in scl
    assert sidecar["diagnostics"] == [expected]
    assert f"{expected['part_name']}(" not in scl
```

The committed fixture metadata contains the literal diagnostic dictionary, including its network index, `UId`, code, and part name. The test loads that tracked oracle and therefore remains deterministic without matching a broad warning substring.

- [ ] **Step 2: Run it and verify the current generic warning is insufficient**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_diagnostics.py -v -p no:cacheprovider`

Expected: FAIL because the sidecar lacks a structured statement-level diagnostic.

- [ ] **Step 3: Add a canonical diagnostic code to `Unhandled` when needed**

```python
@dataclass(frozen=True)
class Unhandled:
    part_name: str
    uid: str | None = None
    note: str | None = None
    diagnostic_code: str = "unknown-instruction"
```

Use `known-unsupported-form` when the part name is known but its pin shape/semantic form is not qualified, `malformed-input` for structurally invalid source, and `missing-reference` for a declared source reference not found in the block/project context. `_statement_diagnostics()` must sort by `(network_index, uid or "", code, part_name)` and emit new dictionaries; it must not mutate statements.

- [ ] **Step 4: Run diagnostics plus golden regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_diagnostics.py tests/test_fbd_goldens.py -v -p no:cacheprovider`

Expected: PASS; SCL and JSON identify the same unsupported source construct.

- [ ] **Step 5: Commit the diagnostic contract**

```bash
git add src/simaticml_decoder/ir.py src/simaticml_decoder/fold.py src/simaticml_decoder/emit.py tests/test_fbd_diagnostics.py
git commit -m "feat: add structured FBD unsupported diagnostics"
```

### Task 6: Test the CLI and enforce the qualified support boundary

**Files:**

- Create: `tests/test_fbd_cli.py`
- Modify: `README.md`
- Modify: `docs/PROJECT_CAPABILITY_ASSESSMENT.md`
- Modify: `docs/ADVANCED_TRANSLATION_ROADMAP.md`

**Interfaces:**

- Consumes: qualified fixtures and golden artifacts.
- Produces: end-to-end proof that CLI output carries the same fidelity contract, and a support matrix limited to native verified forms.

- [ ] **Step 1: Write the failing CLI output test**

```python
def test_cli_writes_fbd_scl_and_sidecar_with_non_reimportability(tmp_path):
    source = FBD_ROOT / "fbd_signal_flow.xml"
    assert cli.main([str(source), "-o", str(tmp_path), "--format", "both", "-q"]) == 0

    sidecar = json.loads((tmp_path / "fbd_signal_flow.json").read_text(encoding="utf-8"))
    assert (tmp_path / "fbd_signal_flow.scl").is_file()
    assert sidecar["output_contract"]["reimportable"] is False
```

- [ ] **Step 2: Run the CLI test and verify the missing contract fails it**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_cli.py -v -p no:cacheprovider`

Expected: FAIL until Task 3's sidecar contract is available, then PASS.

- [ ] **Step 3: Update only evidence-backed support documentation**

In `README.md`, enumerate FBD capabilities by fixture family and label advanced forms individually. State that all qualified FBD output is readable analysis, not re-importable TIA source. Keep GRAPH marked deferred with the future JSON state-machine direction; do not call it supported because FBD tests pass.

- [ ] **Step 4: Run full FBD and existing CLI regression tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_*.py tests/test_cli.py -v -p no:cacheprovider`

Expected: PASS with zero skipped FBD fixture tests.

- [ ] **Step 5: Commit FBD support claims**

```bash
git add tests/test_fbd_cli.py README.md docs/PROJECT_CAPABILITY_ASSESSMENT.md docs/ADVANCED_TRANSLATION_ROADMAP.md
git commit -m "docs: define qualified FBD support boundary"
```

### Task 7: Run the immediate-scope quality gate

**Files:**

- Modify: `pyproject.toml` only if the shared project plan has not already raised coverage to 80%.
- Modify: `.github/workflows/ci.yml` only if it does not run the committed FBD tests.

**Interfaces:**

- Consumes: all FBD tests, shared corpus integrity test, and project-wide coverage setup.
- Produces: AC-013 proof for the FBD portion of the immediate scope.

- [ ] **Step 1: Run the FBD test set with coverage**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_fbd_*.py -v -p no:cacheprovider --cov=src/simaticml_decoder --cov-fail-under=80`

Expected: PASS with no FBD fixture skips.

- [ ] **Step 2: Run the repository quality commands**

Run: `./.venv/Scripts/python.exe -m pytest -v -p no:cacheprovider --cov=src/simaticml_decoder --cov-fail-under=80`

Expected: PASS.

Run: `./.venv/Scripts/python.exe -m ruff check src tests`

Expected: PASS.

- [ ] **Step 3: Commit verification-only configuration changes when present**

```bash
git add pyproject.toml .github/workflows/ci.yml
git commit -m "ci: run qualified FBD coverage checks"
```

## Self-Review

- AC coverage: Task 1 makes the fixture corpus runnable from a fresh clone; Task 2 proves native FBD/FBD_IEC routing; Tasks 3–5 establish readable analysis, golden semantics, and safe diagnostics; Task 6 verifies CLI and deferral claims; Task 7 provides the quality gate.
- Advanced-block coverage: observed advanced `FlgNet` forms have an explicit fixture-first workflow and do not require a separate FBD language branch.
- Fidelity: no step claims diagram geometry, TIA importability, or GRAPH execution semantics.
- Completeness scan: the tracked fixture metadata supplies deterministic UIds and part names; the implementation never guesses an unobserved instruction contract.
- Type consistency: the current parser/model/folder pipeline stays intact, while output diagnostics are immutable newly created dictionaries.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-13-fbd-and-advanced-flgnet-qualification.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task and review each qualified semantic family.
2. **Inline Execution** — execute the tasks in this session in small TDD batches with review checkpoints.
