# Graph Report - simaticml-decoder  (2026-07-13)

## Corpus Check
- 21 files · ~15,227 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 423 nodes · 904 edges · 15 communities
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 48 edges (avg confidence: 0.79)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `54624419`
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
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]

## God Nodes (most connected - your core abstractions)
1. `_NetFolder` - 30 edges
2. `read_xml()` - 17 edges
3. `_children()` - 16 edges
4. `InputViolation` - 15 edges
5. `_ln()` - 15 edges
6. `_child()` - 15 edges
7. `_parse_block()` - 15 edges
8. `_scl_of()` - 14 edges
9. `safe_text()` - 12 edges
10. `_parse_flgnet()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `test_safe_text_is_single_line_and_bounded()` --calls--> `safe_text()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_validate_input_file_rejects_non_xml_and_sd_code()` --calls--> `validate_input_file()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_read_xml_rejects_doctype()` --calls--> `read_xml()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_read_xml_rejects_invalid_utf8()` --calls--> `read_xml()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_read_xml_rejects_a_path_changed_after_validation()` --calls--> `read_xml()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py

## Communities (15 total, 0 thin omitted)

### Community 0 - "XML Parsing Helpers"
Cohesion: 0.09
Nodes (60): _block_kind(), _child(), _child_text(), _children(), _extra_attrs(), _find_block_element(), _first_element_child(), _inline_comment() (+52 more)

### Community 1 - "Network Graph Folding"
Cohesion: 0.07
Nodes (41): _directory_lstat(), _discover(), discover_input_files(), discover_xml(), InputLimits, InputViolation, _is_regular_file(), _is_reparse_point() (+33 more)

### Community 2 - "Semantic IR Types"
Cohesion: 0.09
Nodes (25): _and(), _contains_var(), _expr_key(), _factor_or(), _fold(), fold_block(), fold_network(), _materialize() (+17 more)

### Community 3 - "XML Model Types"
Cohesion: 0.08
Nodes (41): Enum, _box(), Category, _cmp(), _coil(), lookup(), _pf(), The instruction catalog — deliberately *data, not logic*.  fold.py reasons about (+33 more)

### Community 4 - "CLI And SCL Emission"
Cohesion: 0.09
Nodes (23): fixture_file(), load_fixture(), Shared pytest setup and committed fixture-corpus helpers., Return a callable name -> Path, skipping if the fixture is absent., Return a callable name -> committed native SimaticML path., Return a callable name -> model.Document, skipping if the fixture is absent., Return a callable name -> model.Document., Unit tests for the CLI with committed native SimaticML fixtures. (+15 more)

### Community 5 - "Folding Algorithms"
Cohesion: 0.17
Nodes (29): _box_body(), _box_call_form(), _build_trace(), _claim(), emit_scl(), emit_sidecar(), _expr(), _expr_core() (+21 more)

### Community 6 - "Instruction Catalog"
Cohesion: 0.12
Nodes (26): Access, Address, Block, Call, Component, Constant, Document, FlgNet (+18 more)

### Community 7 - "Operand Rendering"
Cohesion: 0.14
Nodes (23): build_parser(), decode_file(), _dest_dir(), discover(), _error(), _exit_code(), FileOutcome, _input_error() (+15 more)

### Community 8 - "Community 8"
Cohesion: 0.19
Nodes (15): simaticml-decoder — SimaticML LAD/FBD -> readable SCL + JSON metadata sidecar., Render a model.Access into its TIA display string.  Split out because it is need, model.Access -> display string (TIA conventions; see module docstring)., render(), _render_address(), _render_component(), _render_constant(), _render_symbol() (+7 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (15): Unit tests for emit — ir.* -> SCL text + JSON sidecar.  IR objects are construct, _scl_of(), test_box_add_with_enable_guard(), test_box_inc_under_rising_edge(), test_box_move_assignment_form(), test_box_timer_instance_call_form(), test_flipflop_reset_priority(), test_latch_is_called_out() (+7 more)

### Community 10 - "Community 10"
Cohesion: 0.35
Nodes (15): Endpoint, First endpoint is the source; the rest are sinks (fan-out)., Wire, _ic(), _nc(), _net(), _pr(), Unit tests for fold — model.* -> ir.* (the wire-graph folding).  Networks are bu (+7 more)

### Community 11 - "Community 11"
Cohesion: 0.3
Nodes (11): _access(), Unit tests for operand.render — the Access -> TIA display-string conventions., test_address_bool_byte_bit(), test_address_word(), test_array_index(), test_bit_slice_renders_percent_x(), test_dotted_local_path(), test_global_variable_quotes_root_only() (+3 more)

### Community 12 - "Community 12"
Cohesion: 0.4
Nodes (10): _manifest(), _path(), Non-skipping Phase 0 regression contract for committed native exports., _semantic_summary(), test_cross_format_mapping_does_not_pair_resources_across_export_roots(), test_every_unpaired_resource_has_the_published_diagnostic(), test_expected_diagnostics_are_non_skipping_and_exact(), test_manifest_declares_local_evaluation_only_corpus() (+2 more)

### Community 13 - "Community 13"
Cohesion: 0.43
Nodes (7): check_release_version(), main(), Validate that a release tag matches the package versions., read_init_version(), read_project_version(), version_from_tag(), ValueError

### Community 14 - "Community 14"
Cohesion: 0.6
Nodes (5): test_check_release_version_accepts_matching_v_tag(), test_check_release_version_rejects_non_v_tag(), test_check_release_version_reports_init_mismatch(), test_check_release_version_reports_pyproject_mismatch(), _write_project()

## Knowledge Gaps
- **97 isolated node(s):** `Validate that a release tag matches the package versions.`, `Result of decoding one file. Carries enough to report without re-deriving.`, `Decode one block. Catches its own expected errors and reports them through the`, `Every supported input under ``root``, sorted for deterministic processing.`, `Rebuild ``source``'s parent directory, relative to ``input_root``, under     ``o` (+92 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_NetFolder` connect `Semantic IR Types` to `XML Model Types`?**
  _High betweenness centrality (0.082) - this node is a cross-community bridge._
- **Why does `read_xml()` connect `Network Graph Folding` to `XML Parsing Helpers`, `Operand Rendering`?**
  _High betweenness centrality (0.054) - this node is a cross-community bridge._
- **Why does `Wire` connect `Community 10` to `Instruction Catalog`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Are the 8 inferred relationships involving `read_xml()` (e.g. with `decode_file()` and `parse_file()`) actually correct?**
  _`read_xml()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Validate that a release tag matches the package versions.`, `Result of decoding one file. Carries enough to report without re-deriving.`, `Decode one block. Catches its own expected errors and reports them through the` to the rest of the system?**
  _97 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `XML Parsing Helpers` be split into smaller, more focused modules?**
  _Cohesion score 0.09 - nodes in this community are weakly interconnected._
- **Should `Network Graph Folding` be split into smaller, more focused modules?**
  _Cohesion score 0.07 - nodes in this community are weakly interconnected._