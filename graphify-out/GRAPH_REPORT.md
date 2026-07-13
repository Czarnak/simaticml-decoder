# Graph Report - simaticml-decoder  (2026-07-13)

## Corpus Check
- 23 files · ~19,551 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 563 nodes · 1207 edges · 18 communities (16 shown, 2 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 94 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `a74792b9`
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
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]

## God Nodes (most connected - your core abstractions)
1. `InputViolation` - 42 edges
2. `_NetFolder` - 30 edges
3. `safe_text()` - 23 edges
4. `discover_input_files()` - 23 edges
5. `_FakePosixFs` - 21 edges
6. `read_xml()` - 20 edges
7. `InputLimits` - 16 edges
8. `_children()` - 16 edges
9. `_ln()` - 15 edges
10. `_child()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `test_safe_text_is_single_line_and_bounded()` --calls--> `safe_text()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_validate_input_file_rejects_non_xml_and_sd_code()` --calls--> `validate_input_file()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_read_xml_rejects_doctype()` --calls--> `read_xml()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_read_xml_rejects_invalid_utf8()` --calls--> `read_xml()`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py
- `test_discover_xml_is_deterministic_and_bounded()` --calls--> `InputLimits`  [INFERRED]
  tests/test_input_policy.py → src/simaticml_decoder/input_policy.py

## Communities (18 total, 2 thin omitted)

### Community 0 - "XML Parsing Helpers"
Cohesion: 0.06
Nodes (49): direct_input_artifact(), discover_input_files(), InputLimits, Discover XML and SIMATIC SD inputs so unsupported files remain visible., Published limits for one XML input and one discovered input tree., Published limits for one XML input and one discovered input tree., Published limits for one XML input and one discovered input tree., Discover XML and SIMATIC SD inputs so unsupported files remain visible.      Eve (+41 more)

### Community 1 - "Network Graph Folding"
Cohesion: 0.07
Nodes (56): _decode_and_validate_xml_text(), _dir_fd_available(), _directory_lstat(), _discover(), _discover_posix(), _discover_windows(), discover_xml(), InputArtifact (+48 more)

### Community 2 - "Semantic IR Types"
Cohesion: 0.09
Nodes (60): _block_kind(), _child(), _child_text(), _children(), _extra_attrs(), _find_block_element(), _first_element_child(), _inline_comment() (+52 more)

### Community 3 - "XML Model Types"
Cohesion: 0.09
Nodes (25): _and(), _contains_var(), _expr_key(), _factor_or(), _fold(), fold_block(), fold_network(), _materialize() (+17 more)

### Community 4 - "CLI And SCL Emission"
Cohesion: 0.08
Nodes (41): Enum, _box(), Category, _cmp(), _coil(), lookup(), _pf(), The instruction catalog — deliberately *data, not logic*.  fold.py reasons about (+33 more)

### Community 5 - "Folding Algorithms"
Cohesion: 0.1
Nodes (41): Access, Address, Block, Call, Component, Constant, Document, Endpoint (+33 more)

### Community 6 - "Instruction Catalog"
Cohesion: 0.08
Nodes (25): _close_handle(), FILE_ID_BOTH_DIR_INFORMATION, IO_STATUS_BLOCK, _IoStatusUnion, _make_unicode_string(), NativeDirectory, NativeEntry, NativeHandle (+17 more)

### Community 7 - "Operand Rendering"
Cohesion: 0.11
Nodes (32): build_parser(), decode_artifact(), decode_file(), _dest_dir(), discover(), _error(), _exit_code(), FileOutcome (+24 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (24): fixture_file(), load_fixture(), Shared pytest setup and committed fixture-corpus helpers., Return a callable name -> Path, skipping if the fixture is absent., Return a callable name -> committed native SimaticML path., Return a callable name -> model.Document, skipping if the fixture is absent., Return a callable name -> model.Document., Unit tests for the CLI with committed native SimaticML fixtures. (+16 more)

### Community 9 - "Community 9"
Cohesion: 0.17
Nodes (29): _box_body(), _box_call_form(), _build_trace(), _claim(), emit_scl(), emit_sidecar(), _expr(), _expr_core() (+21 more)

### Community 10 - "Community 10"
Cohesion: 0.19
Nodes (15): simaticml-decoder — SimaticML LAD/FBD -> readable SCL + JSON metadata sidecar., Render a model.Access into its TIA display string.  Split out because it is need, model.Access -> display string (TIA conventions; see module docstring)., render(), _render_address(), _render_component(), _render_constant(), _render_symbol() (+7 more)

### Community 11 - "Community 11"
Cohesion: 0.17
Nodes (15): Unit tests for emit — ir.* -> SCL text + JSON sidecar.  IR objects are construct, _scl_of(), test_box_add_with_enable_guard(), test_box_inc_under_rising_edge(), test_box_move_assignment_form(), test_box_timer_instance_call_form(), test_flipflop_reset_priority(), test_latch_is_called_out() (+7 more)

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (12): _manifest(), _path(), Non-skipping Phase 0 regression contract for committed native exports., Regression: verify fixture corpus itself is set up correctly.      If unpaired r, _semantic_summary(), test_cross_format_mapping_does_not_pair_resources_across_export_roots(), test_every_unpaired_resource_has_the_published_diagnostic(), test_expected_diagnostics_are_non_skipping_and_exact() (+4 more)

### Community 13 - "Community 13"
Cohesion: 0.3
Nodes (11): _access(), Unit tests for operand.render — the Access -> TIA display-string conventions., test_address_bool_byte_bit(), test_address_word(), test_array_index(), test_bit_slice_renders_percent_x(), test_dotted_local_path(), test_global_variable_quotes_root_only() (+3 more)

### Community 14 - "Community 14"
Cohesion: 0.43
Nodes (7): check_release_version(), main(), Validate that a release tag matches the package versions., read_init_version(), read_project_version(), version_from_tag(), ValueError

### Community 16 - "Community 16"
Cohesion: 0.6
Nodes (5): test_check_release_version_accepts_matching_v_tag(), test_check_release_version_rejects_non_v_tag(), test_check_release_version_reports_init_mismatch(), test_check_release_version_reports_pyproject_mismatch(), _write_project()

## Knowledge Gaps
- **137 isolated node(s):** `Validate that a release tag matches the package versions.`, `Result of decoding one file. Carries enough to report without re-deriving.`, `Decode one direct-path block (single-file CLI mode). Kept path-based     and unc`, `Decode one discovered artifact (directory-mode CLI). Reads bytes only     throug`, `Every supported input under ``root``, sorted for deterministic processing.` (+132 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **2 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `InputViolation` connect `Network Graph Folding` to `XML Parsing Helpers`, `Instruction Catalog`, `Community 14`, `Operand Rendering`?**
  _High betweenness centrality (0.113) - this node is a cross-community bridge._
- **Why does `_NetFolder` connect `XML Model Types` to `CLI And SCL Emission`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `discover_input_files()` connect `XML Parsing Helpers` to `Network Graph Folding`, `Operand Rendering`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Are the 16 inferred relationships involving `InputViolation` (e.g. with `FileOutcome` and `UNICODE_STRING`) actually correct?**
  _`InputViolation` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `safe_text()` (e.g. with `decode_file()` and `decode_artifact()`) actually correct?**
  _`safe_text()` has 8 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `discover_input_files()` (e.g. with `discover()` and `test_discovered_artifact_is_relative()`) actually correct?**
  _`discover_input_files()` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `_FakePosixFs` (e.g. with `InputLimits` and `InputViolation`) actually correct?**
  _`_FakePosixFs` has 2 INFERRED edges - model-reasoned connections that need verification._