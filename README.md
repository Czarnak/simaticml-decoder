# simaticml-decoder

Translate exported **SimaticML LAD/FBD** blocks (Siemens TIA Portal **V21**) into
readability-first **SCL** plus a **JSON metadata sidecar**.

## Why

A SimaticML export stores ladder logic as a `FlgNet` — a flat netlist of parts
and wires, not line-shaped rungs. Reading that graph by hand (or by eye, from the
editor) is token-heavy and error-prone: it is easy to connect the wrong variable
in a large block, and a single contact's negation is one diagonal slash. This tool
decodes the netlist deterministically, so what you analyse is folded logic with
explicit negation and an exact write/read cross-reference — not a graph you have to
trace yourself.

## How it works

Three cleanly separated, independently testable phases:

| Phase | Module | Input → Output |
|-------|--------|----------------|
| 1. Parse | `parse.py` → `model.py` | XML → faithful syntactic mirror |
| 2. Fold  | `fold.py` → `ir.py`     | model → boolean tree + assignments |
| 3. Emit  | `emit.py`               | IR → SCL text + JSON sidecar |

Supporting modules: `instructions.py` (the part catalog — data, not logic),
`operand.py` (Access → display string), `scl_reconstruct.py` (SCL networks, which
are reconstructed from their tokenised AST rather than folded).

Two commitments run through the design: every IR node keeps the source `UId` it
came from (so any rendered claim is traceable to a net), and anything the folder
cannot interpret is surfaced **loudly** rather than dropped — a silent omission in
authoritative-looking SCL is the worst possible failure.

## Scope (v0)

Covered: FC/FB blocks; LAD/FBD folding (series→AND, `O`→OR, fan-out, `Negated`→NOT,
daisy-chained coils, structural latch detection); SCL network reconstruction;
ground-truth interface types; cross-reference table; the instruction set seen in
real V21 samples (Contact, Coil/SCoil/RCoil, `O`, Move/Add/Inc, comparisons,
Rs/Sr, P/N edges, TON family, user FC/FB calls).

Deferred (parsed losslessly, rendering flagged): GRAPH/SFC and STL networks;
absolute-addressing / array / `Operation`-template rendering. Output is
readability-first, **not** recompilable. Live TIA Openness integration is out of
scope — the tool operates on already-exported XML.

## Install

```bash
pip install -e ".[dev]"
```

Runtime dependencies: none (standard-library `xml.etree.ElementTree`). The `dev`
extra pulls `ruff` and `pytest`.

## Usage

```bash
simaticml-decode BLOCK.xml --format both
# one file at a time; --format {scl,json,both}; -o OUTDIR for output location
```

## Layout

```
src/simaticml_decoder/   parse · model · fold · ir · instructions · operand
                         scl_reconstruct · emit · cli
tests/                   authored separately; run by CI
.github/workflows/ci.yml ruff + pytest on push / PR
```

## Status

Scaffold with defined phase interfaces. Implementation proceeds phase by phase,
parse first, validated against real V21 exports.

---
*Created with Claude AI*
