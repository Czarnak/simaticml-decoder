"""Command-line entry point: one block or a whole directory in, SCL and/or JSON out.

Surface:

    simaticml-decode PATH [-o OUTDIR] [--format {scl,json,both}] [--no-recursive] [-q]

``PATH`` is either a single exported SimaticML ``.xml`` block (decoded as before) or
a **directory**. For a directory the tool discovers every ``.xml`` block beneath it
and decodes each through the same pipeline; the output tree **mirrors** the input's
internal folder structure (``blocks/motion/Axis.xml`` -> ``OUTDIR/motion/Axis.scl``).

The pipeline is the three phases in order:

    parse.parse_file  XML       -> model.Document
    fold.fold_block   model.*   -> ir.DecodedBlock
    emit.emit_scl / emit.emit_sidecar         -> .scl text + .json sidecar

Artifacts are written as ``<stem>.scl`` and ``<stem>.json`` either next to the input
(no ``-o``) or under ``--output`` (with the relative subtree preserved). Warnings
(deferred constructs, unknown instructions) are reported on stderr but do not fail
the run. In directory mode one bad file is reported and skipped without aborting the
batch; the process exits non-zero only when at least one file failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

from . import __version__, emit, fold, ir, parse

_EPILOG = """\
examples:
  simaticml-decode Motor.xml                 # writes Motor.scl + Motor.json beside it
  simaticml-decode Motor.xml -o out/         # writes into out/
  simaticml-decode Motor.xml --format scl    # SCL only
  simaticml-decode blocks/ -o decoded/       # bulk: mirror blocks/'s subtree into decoded/
  simaticml-decode blocks/ --no-recursive    # only the top level of blocks/
"""


@dataclass(frozen=True)
class FileOutcome:
    """Result of decoding one file. Carries enough to report without re-deriving."""

    source: Path
    status: str  # "ok" | "error"
    decoded: ir.DecodedBlock | None = None
    written: tuple[Path, ...] = ()
    error: str | None = None


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="simaticml-decode",
        description="Translate an exported SimaticML LAD/FBD block (TIA V21) into "
        "readability-first SCL plus a JSON metadata sidecar. Point at a single .xml "
        "file or at a directory to decode every block beneath it.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", metavar="PATH",
                   help="a SimaticML .xml block, or a directory to decode in bulk "
                        "(its subtree is mirrored into --output)")
    p.add_argument("-o", "--output", metavar="DIR",
                   help="output directory (default: alongside each input file). In "
                        "directory mode the input's relative subtree is preserved here.")
    p.add_argument("--format", choices=("scl", "json", "both"), default="both",
                   help="which artifact(s) to write (default: both)")
    p.add_argument("--no-recursive", dest="recursive", action="store_false",
                   help="in directory mode, decode only the top level (no subdirectories)")
    p.add_argument("-q", "--quiet", action="store_true",
                   help="suppress the per-file progress/warning summary on stderr")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    input_path = Path(args.input)
    fmt = args.format

    if input_path.is_file():
        out_dir = Path(args.output) if args.output else input_path.parent
        outcomes = [decode_file(input_path, out_dir, fmt)]
        _report(outcomes, input_root=None, quiet=args.quiet)
        return _exit_code(outcomes)

    if input_path.is_dir():
        out_root = Path(args.output) if args.output else input_path
        sources = discover(input_path, recursive=args.recursive)
        if not sources:
            print(f"no .xml blocks found under {input_path}", file=sys.stderr)
            return 0
        outcomes = [decode_file(src, _dest_dir(input_path, src, out_root), fmt)
                    for src in sources]
        _report(outcomes, input_root=input_path, quiet=args.quiet)
        return _exit_code(outcomes)

    # Neither file nor directory: nothing to decode. Soft no-op (exit 0).
    print(f"no input to decode: {input_path} not found", file=sys.stderr)
    return 0


def decode_file(source: Path, out_dir: Path, fmt: str) -> FileOutcome:
    """Decode one block. Catches its own expected errors and reports them through the
    return value rather than aborting — so a batch can continue past a bad file."""
    try:
        doc = parse.parse_file(str(source))
    except ET.ParseError as exc:
        return FileOutcome(source, "error", error=f"{source} is not well-formed XML: {exc}")
    except (OSError, ValueError) as exc:
        return FileOutcome(source, "error", error=f"failed to read {source}: {exc}")

    decoded = fold.fold_block(doc)

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return FileOutcome(source, "error",
                           error=f"cannot create output directory {out_dir}: {exc}")

    stem = source.stem
    written: list[Path] = []
    try:
        if fmt in ("scl", "both"):
            written.append(_write(out_dir / f"{stem}.scl", emit.emit_scl(decoded)))
        if fmt in ("json", "both"):
            sidecar = json.dumps(emit.emit_sidecar(decoded), indent=2, ensure_ascii=False)
            written.append(_write(out_dir / f"{stem}.json", sidecar + "\n"))
    except OSError as exc:
        return FileOutcome(source, "error",
                           error=f"failed to write artifact for {source}: {exc}")

    return FileOutcome(source, "ok", decoded=decoded, written=tuple(written))


def discover(root: Path, recursive: bool) -> list[Path]:
    """Every ``.xml`` file under ``root`` (case-insensitive), sorted for determinism."""
    walker = root.rglob("*") if recursive else root.glob("*")
    found = [p for p in walker if p.is_file() and p.suffix.lower() == ".xml"]
    return sorted(found)


def _dest_dir(input_root: Path, source: Path, out_root: Path) -> Path:
    """Rebuild ``source``'s parent directory, relative to ``input_root``, under
    ``out_root`` — this is what mirrors the input's internal structure."""
    return out_root / source.relative_to(input_root).parent


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _exit_code(outcomes: list[FileOutcome]) -> int:
    return 1 if any(o.status == "error" for o in outcomes) else 0


def _report(outcomes: list[FileOutcome], input_root: Path | None, quiet: bool) -> None:
    """Per-file lines (suppressed by ``-q``), error lines (always shown), and a batch
    summary (shown unless ``-q`` on a fully-successful batch)."""
    failures = 0
    for outcome in outcomes:
        if outcome.status == "error":
            failures += 1
            print(f"error: {outcome.error}", file=sys.stderr)
        elif not quiet:
            _report_ok(outcome, input_root)

    if input_root is not None and (not quiet or failures):
        ok = len(outcomes) - failures
        print(f"{ok} decoded, {failures} failed", file=sys.stderr)


def _report_ok(outcome: FileOutcome, input_root: Path | None) -> None:
    decoded = outcome.decoded
    prefix = ""
    if input_root is not None:
        prefix = f"{outcome.source.relative_to(input_root)}: "
    label = f"{decoded.name} ({decoded.kind})"
    files = ", ".join(p.name for p in outcome.written)
    print(f"{prefix}decoded {label}: {len(decoded.networks)} network(s) -> {files}",
          file=sys.stderr)
    if decoded.warnings:
        print(f"  {len(decoded.warnings)} warning(s):", file=sys.stderr)
        for warning in decoded.warnings:
            print(f"    - {warning}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
