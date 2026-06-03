# Graph Report - C:\Users\LCZ\Desktop\RnD\TIA-Portal\simaticml-decoder  (2026-06-03)

## Corpus Check
- Corpus is ~8,821 words - fits in a single context window. You may not need a graph.

## Summary
- 200 nodes · 360 edges · 8 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

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
9. `_parse_member()` - 8 edges
10. `_inline_comment()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `_NetFolder` --uses--> `Category`  [INFERRED]
  fold.py → instructions.py

## Communities (8 total, 0 thin omitted)

### Community 0 - "XML Parsing Helpers"
Cohesion: 0.11
Nodes (47): _block_kind(), _child(), _child_text(), _children(), _extra_attrs(), _find_block_element(), _first_element_child(), _inline_comment() (+39 more)

### Community 1 - "Network Graph Folding"
Cohesion: 0.14
Nodes (9): _and(), _materialize(), _NetFolder, Folds a single FlgNet. Holds the pin-graph maps and the memoised eval., Turn the _POWER sentinel into a concrete TRUE; pass anything else through., AND-combine, dropping pure-power operands and flattening nested ANDs., Render an Instance (system FB backing member) as a display name., _render_instance() (+1 more)

### Community 2 - "Semantic IR Types"
Cohesion: 0.07
Nodes (33): Enum, Category, And, Assign, AssignKind, BoxCall, Compare, DecodedBlock (+25 more)

### Community 3 - "XML Model Types"
Cohesion: 0.07
Nodes (29): Access, Address, Block, Call, Component, Constant, Document, Endpoint (+21 more)

### Community 4 - "CLI And SCL Emission"
Cohesion: 0.12
Nodes (16): build_parser(), main(), Command-line entry point: one XML file in, SCL and/or JSON out.  v0 surface (one, emit_scl(), emit_sidecar(), Phase 3: ir.* -> readable SCL text + JSON metadata sidecar.  Two artifacts (read, Render the SCL text artifact. Raises until implemented (Phase 3)., Build the JSON-serialisable sidecar dict. Raises until implemented. (+8 more)

### Community 5 - "Folding Algorithms"
Cohesion: 0.14
Nodes (16): _contains_var(), _expr_key(), _factor_or(), _fold(), fold_block(), fold_network(), _pin_sort_key(), Phase 2: model.* -> ir.* (the folding — the heart of the tool).  Intended algori (+8 more)

### Community 6 - "Instruction Catalog"
Cohesion: 0.33
Nodes (8): _box(), _cmp(), _coil(), lookup(), _pf(), The instruction catalog — deliberately *data, not logic*.  fold.py reasons about, Return the Spec for a Part name, or None (caller folds to ir.Unhandled)., Spec

### Community 7 - "Operand Rendering"
Cohesion: 0.43
Nodes (7): Render a model.Access into its TIA display string.  Split out because it is need, model.Access -> display string (TIA conventions; see module docstring)., render(), _render_address(), _render_component(), _render_constant(), _render_symbol()

## Knowledge Gaps
- **79 isolated node(s):** `Command-line entry point: one XML file in, SCL and/or JSON out.  v0 surface (one`, `Phase 3: ir.* -> readable SCL text + JSON metadata sidecar.  Two artifacts (read`, `Render the SCL text artifact. Raises until implemented (Phase 3).`, `Build the JSON-serialisable sidecar dict. Raises until implemented.`, `Phase 2: model.* -> ir.* (the folding — the heart of the tool).  Intended algori` (+74 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_NetFolder` connect `Network Graph Folding` to `Semantic IR Types`, `Folding Algorithms`?**
  _High betweenness centrality (0.215) - this node is a cross-community bridge._
- **Why does `Category` connect `Semantic IR Types` to `Network Graph Folding`, `Instruction Catalog`?**
  _High betweenness centrality (0.100) - this node is a cross-community bridge._
- **Why does `_materialize()` connect `Network Graph Folding` to `Folding Algorithms`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **What connects `Command-line entry point: one XML file in, SCL and/or JSON out.  v0 surface (one`, `Phase 3: ir.* -> readable SCL text + JSON metadata sidecar.  Two artifacts (read`, `Render the SCL text artifact. Raises until implemented (Phase 3).` to the rest of the system?**
  _79 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `XML Parsing Helpers` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._
- **Should `Network Graph Folding` be split into smaller, more focused modules?**
  _Cohesion score 0.14 - nodes in this community are weakly interconnected._
- **Should `Semantic IR Types` be split into smaller, more focused modules?**
  _Cohesion score 0.07 - nodes in this community are weakly interconnected._