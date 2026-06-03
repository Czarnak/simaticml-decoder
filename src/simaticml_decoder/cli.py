"""Command-line entry point: one exported SimaticML block in, SCL and/or JSON out.

v0 surface (one file at a time, by decision — batch is a deliberate later add):

    simaticml-decode BLOCK.xml [-o OUTDIR] [--format {scl,json,both}] [-q]

The pipeline is the three phases in order:

    parse.parse_file  XML       -> model.Document
    fold.fold_block   model.*   -> ir.DecodedBlock
    emit.emit_scl / emit.emit_sidecar         -> .scl text + .json sidecar

Artifacts are written next to the input (or into ``--output``) as ``<stem>.scl``
and ``<stem>.json``. Warnings (deferred constructs, unknown instructions) are
reported on stderr but do not fail the run — the decoded output still surfaces
every unhandled part loudly, so a warning is informative, not fatal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from . import __version__, emit, fold, parse

_EPILOG = """\
examples:
  simaticml-decode Motor.xml                 # writes Motor.scl + Motor.json beside it
  simaticml-decode Motor.xml -o out/         # writes into out/
  simaticml-decode Motor.xml --format scl    # SCL only
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simaticml-decode",
        description="Translate an exported SimaticML LAD/FBD block (TIA V21) into "
        "readability-first SCL plus a JSON metadata sidecar.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", metavar="BLOCK.xml",
                   help="path to a single exported SimaticML .xml block")
    p.add_argument("-o", "--output", metavar="DIR",
                   help="output directory (default: alongside the input file)")
    p.add_argument("--format", choices=("scl", "json", "both"), default="both",
                   help="which artifact(s) to write (default: both)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the per-file progress/warning summary on stderr")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    input_path = Path(args.input)
    if not input_path.is_file():
        print(f"error: input file not found: {input_path}", file=sys.stderr)
        return 2

    try:
        doc = parse.parse_file(str(input_path))
    except ET.ParseError as exc:
        print(f"error: {input_path} is not well-formed XML: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: failed to read {input_path}: {exc}", file=sys.stderr)
        return 1

    decoded = fold.fold_block(doc)

    out_dir = Path(args.output) if args.output else input_path.parent
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"error: cannot create output directory {out_dir}: {exc}", file=sys.stderr)
        return 1

    stem = input_path.stem
    written: list[Path] = []
    if args.format in ("scl", "both"):
        written.append(_write(out_dir / f"{stem}.scl", emit.emit_scl(decoded)))
    if args.format in ("json", "both"):
        sidecar = json.dumps(emit.emit_sidecar(decoded), indent=2, ensure_ascii=False)
        written.append(_write(out_dir / f"{stem}.json", sidecar + "\n"))

    if not args.quiet:
        _report(decoded, written)
    return 0


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _report(decoded, written: list[Path]) -> None:
    label = f"{decoded.name} ({decoded.kind})"
    files = ", ".join(p.name for p in written)
    print(f"decoded {label}: {len(decoded.networks)} network(s) -> {files}",
          file=sys.stderr)
    if decoded.warnings:
        print(f"  {len(decoded.warnings)} warning(s):", file=sys.stderr)
        for warning in decoded.warnings:
            print(f"    - {warning}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
