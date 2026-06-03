# Graph Report - simaticml-decoder  (2026-06-03)

## Corpus Check
- 18 files · ~12,578 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 315 nodes · 710 edges · 13 communities
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 16 edges (avg confidence: 0.78)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `5babe400`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_XML Parsing Helpers|XML Parsing Helpers]]
- [[_COMMUNITY_Network Graph Folding|Network Graph Folding]]
- [[_COMMUNITY_Semantic IR Types|Semantic IR Types]]
- [[_COMMUNITY_XML Model Types|XML Model Types]]
- [[_COMMUNITY_CLI And SCL Emission|CLI And SCL Emission]]
- [[_COMMUNITY_Folding Algorithms|Folding Algorithms]]
- [[_COMMUNITY_Instruction Catalog|Instruction Catalog]]
- [[_COMMUNITY_Operand Rendering|Operand Rendering]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]

## God Nodes (most connected - your core abstractions)
1. `_NetFolder` - 30 edges
2. `_children()` - 15 edges
3. `_parse_block()` - 15 edges
4. `_ln()` - 14 edges
5. `_child()` - 14 edges
6. `_scl_of()` - 14 edges
7. `_parse_flgnet()` - 11 edges
8. `_materialize()` - 10 edges
9. `_parse_access()` - 10 edges
10. `_access()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `Render the SCL text artifact. Raises until implemented (Phase 3).` --rationale_for--> `emit_scl()`  [EXTRACTED]
  emit.py → src/simaticml_decoder/emit.py
- `Build the JSON-serialisable sidecar dict. Raises until implemented.` --rationale_for--> `emit_sidecar()`  [EXTRACTED]
  emit.py → src/simaticml_decoder/emit.py
- `_pr()` --calls--> `Endpoint`  [INFERRED]
  tests/test_fold.py → src/simaticml_decoder/model.py
- `_ic()` --calls--> `Endpoint`  [INFERRED]
  tests/test_fold.py → src/simaticml_decoder/model.py
- `_nc()` --calls--> `Endpoint`  [INFERRED]
  tests/test_fold.py → src/simaticml_decoder/model.py

## Communities (13 total, 0 thin omitted)

### Community 0 - "XML Parsing Helpers"
Cohesion: 0.09
Nodes (25): _and(), _contains_var(), _expr_key(), _factor_or(), _fold(), fold_block(), fold_network(), _materialize() (+17 more)

### Community 1 - "Network Graph Folding"
Cohesion: 0.14
Nodes (47): _block_kind(), _child(), _child_text(), _children(), _extra_attrs(), _find_block_element(), _first_element_child(), _inline_comment() (+39 more)

### Community 2 - "Semantic IR Types"
Cohesion: 0.1
Nodes (35): Enum, Category, AssignKind, EdgeKind, Access, Address, Block, BlockKind (+27 more)

### Community 3 - "XML Model Types"
Cohesion: 0.17
Nodes (29): _box_body(), _box_call_form(), _build_trace(), _claim(), emit_scl(), emit_sidecar(), _expr(), _expr_core() (+21 more)

### Community 4 - "CLI And SCL Emission"
Cohesion: 0.14
Nodes (20): build_parser(), main(), Command-line entry point: one exported SimaticML block in, SCL and/or JSON out., _report(), _write(), simaticml-decoder — SimaticML LAD/FBD -> readable SCL + JSON metadata sidecar., Render a model.Access into its TIA display string.  Split out because it is need, model.Access -> display string (TIA conventions; see module docstring). (+12 more)

### Community 5 - "Folding Algorithms"
Cohesion: 0.13
Nodes (24): And, Assign, BoxCall, Compare, DecodedBlock, Edge, FlipFlop, Literal (+16 more)

### Community 6 - "Instruction Catalog"
Cohesion: 0.17
Nodes (15): Unit tests for emit — ir.* -> SCL text + JSON sidecar.  IR objects are construct, _scl_of(), test_box_add_with_enable_guard(), test_box_inc_under_rising_edge(), test_box_move_assignment_form(), test_box_timer_instance_call_form(), test_flipflop_reset_priority(), test_latch_is_called_out() (+7 more)

### Community 7 - "Operand Rendering"
Cohesion: 0.13
Nodes (14): fixture_file(), load_fixture(), Shared pytest setup and fixture-corpus helpers.  The sample XML exports live in, Return a callable name -> Path, skipping if the fixture is absent., Return a callable name -> model.Document, skipping if the fixture is absent., Unit tests for the CLI. Error paths are self-contained; happy paths use the fixt, test_format_scl_only(), test_happy_path_writes_both() (+6 more)

### Community 8 - "Community 8"
Cohesion: 0.35
Nodes (15): Endpoint, First endpoint is the source; the rest are sinks (fan-out)., Wire, _ic(), _nc(), _net(), _pr(), Unit tests for fold — model.* -> ir.* (the wire-graph folding).  Networks are bu (+7 more)

### Community 9 - "Community 9"
Cohesion: 0.3
Nodes (11): _access(), Unit tests for operand.render — the Access -> TIA display-string conventions., test_address_bool_byte_bit(), test_address_word(), test_array_index(), test_bit_slice_renders_percent_x(), test_dotted_local_path(), test_global_variable_quotes_root_only() (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.42
Nodes (8): _box(), _cmp(), _coil(), lookup(), _pf(), The instruction catalog — deliberately *data, not logic*.  fold.py reasons about, Return the Spec for a Part name, or None (caller folds to ir.Unhandled)., Spec

### Community 11 - "Community 11"
Cohesion: 0.48
Nodes (6): check_release_version(), main(), Validate that a release tag matches the package versions., read_init_version(), read_project_version(), version_from_tag()

### Community 12 - "Community 12"
Cohesion: 0.6
Nodes (5): test_check_release_version_accepts_matching_v_tag(), test_check_release_version_rejects_non_v_tag(), test_check_release_version_reports_init_mismatch(), test_check_release_version_reports_pyproject_mismatch(), _write_project()

## Knowledge Gaps
- **56 isolated node(s):** `Validate that a release tag matches the package versions.`, `Render the readable SCL text artifact for a decoded block.`, `Build the JSON-serialisable sidecar dict (schema in plan §7).`, `UId -> short claim, so any rendered statement is traceable to its net.`, `model.Document -> ir.DecodedBlock (folded networks + xref + inventory).` (+51 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_NetFolder` connect `XML Parsing Helpers` to `Semantic IR Types`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Why does `Wire` connect `Community 8` to `Semantic IR Types`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `Category` connect `Semantic IR Types` to `XML Parsing Helpers`, `Community 10`?**
  _High betweenness centrality (0.050) - this node is a cross-community bridge._
- **What connects `Validate that a release tag matches the package versions.`, `Render the readable SCL text artifact for a decoded block.`, `Build the JSON-serialisable sidecar dict (schema in plan §7).` to the rest of the system?**
  _56 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `XML Parsing Helpers` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._
- **Should `Network Graph Folding` be split into smaller, more focused modules?**
  _Cohesion score 0.14 - nodes in this community are weakly interconnected._
- **Should `Semantic IR Types` be split into smaller, more focused modules?**
  _Cohesion score 0.1 - nodes in this community are weakly interconnected._