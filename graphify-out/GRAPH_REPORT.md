# Graph Report - simaticml-decoder  (2026-06-03)

## Corpus Check
- 10 files · ~10,366 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 226 nodes · 416 edges · 8 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `806b0f11`
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

## God Nodes (most connected - your core abstractions)
1. `_NetFolder` - 29 edges
2. `_children()` - 14 edges
3. `_parse_block()` - 14 edges
4. `_ln()` - 13 edges
5. `_child()` - 13 edges
6. `_parse_flgnet()` - 10 edges
7. `_materialize()` - 9 edges
8. `_parse_access()` - 9 edges
9. `_expr()` - 8 edges
10. `_parse_member()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `_NetFolder` --uses--> `Category`  [INFERRED]
  fold.py → instructions.py

## Communities (8 total, 0 thin omitted)

### Community 0 - "XML Parsing Helpers"
Cohesion: 0.08
Nodes (25): _and(), _contains_var(), _expr_key(), _factor_or(), _fold(), fold_block(), fold_network(), _materialize() (+17 more)

### Community 1 - "Network Graph Folding"
Cohesion: 0.11
Nodes (47): _block_kind(), _child(), _child_text(), _children(), _extra_attrs(), _find_block_element(), _first_element_child(), _inline_comment() (+39 more)

### Community 2 - "Semantic IR Types"
Cohesion: 0.06
Nodes (38): Enum, Category, AssignKind, EdgeKind, Access, Address, Block, BlockKind (+30 more)

### Community 3 - "XML Model Types"
Cohesion: 0.13
Nodes (28): _box_body(), _box_call_form(), _build_trace(), _claim(), emit_scl(), emit_sidecar(), _expr(), _expr_core() (+20 more)

### Community 4 - "CLI And SCL Emission"
Cohesion: 0.08
Nodes (24): And, Assign, BoxCall, Compare, DecodedBlock, Edge, FlipFlop, Literal (+16 more)

### Community 5 - "Folding Algorithms"
Cohesion: 0.19
Nodes (13): build_parser(), main(), Command-line entry point: one exported SimaticML block in, SCL and/or JSON out., _report(), _write(), simaticml-decoder — SimaticML LAD/FBD -> readable SCL + JSON metadata sidecar., Render a model.Access into its TIA display string.  Split out because it is need, model.Access -> display string (TIA conventions; see module docstring). (+5 more)

### Community 6 - "Instruction Catalog"
Cohesion: 0.33
Nodes (8): _box(), _cmp(), _coil(), lookup(), _pf(), The instruction catalog — deliberately *data, not logic*.  fold.py reasons about, Return the Spec for a Part name, or None (caller folds to ir.Unhandled)., Spec

### Community 7 - "Operand Rendering"
Cohesion: 0.36
Nodes (7): _local(), Reconstruct an SCL network from its tokenised AST.  SCL networks do not *fold* —, model.StructuredText -> SCL source text.      parse._parse_structured_text store, Render an SCL comment. Multi-line content becomes a (* ... *) block., reconstruct(), _render_comment(), _render_element()

## Knowledge Gaps
- **82 isolated node(s):** `Command-line entry point: one exported SimaticML block in, SCL and/or JSON out.`, `Phase 3: ir.* -> readable SCL text + JSON metadata sidecar.  Two artifacts (read`, `Render the readable SCL text artifact for a decoded block.`, `Build the JSON-serialisable sidecar dict (schema in plan §7).`, `UId -> short claim, so any rendered statement is traceable to its net.` (+77 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_NetFolder` connect `XML Parsing Helpers` to `Semantic IR Types`?**
  _High betweenness centrality (0.189) - this node is a cross-community bridge._
- **Why does `Category` connect `Semantic IR Types` to `XML Parsing Helpers`, `Instruction Catalog`?**
  _High betweenness centrality (0.079) - this node is a cross-community bridge._
- **What connects `Command-line entry point: one exported SimaticML block in, SCL and/or JSON out.`, `Phase 3: ir.* -> readable SCL text + JSON metadata sidecar.  Two artifacts (read`, `Render the readable SCL text artifact for a decoded block.` to the rest of the system?**
  _82 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `XML Parsing Helpers` be split into smaller, more focused modules?**
  _Cohesion score 0.08 - nodes in this community are weakly interconnected._
- **Should `Network Graph Folding` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._
- **Should `Semantic IR Types` be split into smaller, more focused modules?**
  _Cohesion score 0.06 - nodes in this community are weakly interconnected._
- **Should `XML Model Types` be split into smaller, more focused modules?**
  _Cohesion score 0.13 - nodes in this community are weakly interconnected._