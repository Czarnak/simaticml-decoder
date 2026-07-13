# SimaticML Decoder

![PyPI - Downloads](https://img.shields.io/pypi/dm/simaticml-decoder)

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

## Scope

Covered: FC/FB blocks; LAD/FBD folding (series→AND, `O`→OR, fan-out, `Negated`→NOT,
daisy-chained coils, structural latch detection); SCL network reconstruction;
ground-truth interface types; cross-reference table; the instruction set seen in
real V21 samples (Contact, Coil/SCoil/RCoil, `O`, Move/Add/Inc, comparisons,
Rs/Sr, P/N edges, TON family, user FC/FB calls).

Deferred (parsed losslessly, rendering flagged): GRAPH/SFC and STL networks;
absolute-addressing / array / `Operation`-template rendering. Output is
readability-first, **not** recompilable. Live TIA Openness integration is out of
scope — the tool operates on already-exported XML.

## Fixture provenance and compatibility

Support claims require a sanitized, redistributable fixture, golden output or
diagnostic, and a non-skipping CI regression. Until those conditions are met, a
format is not `validated`.

Current temporary compatibility probes were exported from
[felipebojorquem/sorting-cell-s7-1200](https://github.com/felipebojorquem/sorting-cell-s7-1200).
That upstream repository has no declared licence, so these probes are used only
for local decoder evaluation; they are not a distributable fixture corpus and do
not validate feature support. A replacement corpus from a suitably licensed,
redaction-reviewed project is pending.

Current input boundary: exported SimaticML FC/FB block XML is the decoder's
working input. SIMATIC SD `.s7dcl`/`.s7res`, UDT/type XML, and PLC tag-table XML
are unsupported; GRAPH/SFC/STL remain deferred as described above. Output is
diagnostic/readability-first, not recompilable.

## Install

```bash
pip install simaticml-decoder
```

For local development:

```bash
pip install -e ".[dev]"
```

Runtime dependencies: none (standard-library `xml.etree.ElementTree`). The `dev`
extra pulls lint, test, coverage, build, and package-validation tools.

## Usage

```bash
# Single block -> SCL + JSON, written beside the input (or into -o OUTDIR):
simaticml-decode BLOCK.xml --format both     # --format {scl,json,both}

# Bulk: point at a directory to decode every .xml beneath it. The output tree
# mirrors the input's folder structure (blocks/motion/Axis.xml -> OUTDIR/motion/Axis.scl).
simaticml-decode blocks/ -o decoded/
simaticml-decode blocks/ --no-recursive      # top level only, skip subdirectories
```

In bulk mode each file is independent: a malformed block is reported on stderr and
skipped rather than aborting the run, and the process exits non-zero only when at
least one file failed. Pointing at a missing path or an empty directory is a quiet
no-op (exit 0). `-q` silences the per-file progress summary.

## Layout

```
src/simaticml_decoder/   parse · model · fold · ir · instructions · operand
                         scl_reconstruct · emit · cli
tests/                   authored separately; run by CI
.github/workflows/ci.yml ruff + pytest on push / PR
```

## Future

Support for new YAML-like S7 PLCs export formats.

---
*Created with Claude AI*
