"""Command-line entry point: one XML file in, SCL and/or JSON out.

v0 surface (one file at a time, by decision):
    simaticml-decode BLOCK.xml [-o OUTDIR] [--format {scl,json,both}]

The argument design / help text / error UX will be finished against the
cli-design craft skill when this is implemented — for now it wires the pipeline
so the intended flow is visible. Batch (multiple files) is a deliberate later add.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="simaticml-decode", description=__doc__)
    p.add_argument("input", help="path to a single exported SimaticML .xml block")
    p.add_argument("-o", "--output", help="output directory (default: alongside input)")
    p.add_argument("--format", choices=("scl", "json", "both"), default="both")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # Intended flow (filled as the phases land):
    #   doc      = parse.parse_file(args.input)
    #   decoded  = fold.fold_block(doc)
    #   scl/json = emit.emit_scl(decoded) / emit.emit_sidecar(decoded)
    #   write artifacts to args.output (or alongside input)
    raise NotImplementedError("pipeline wiring lands as the phases are implemented")


if __name__ == "__main__":
    sys.exit(main())
