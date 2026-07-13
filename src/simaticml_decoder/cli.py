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
from pathlib import Path, PurePath
from xml.etree import ElementTree as ET

from . import __version__, emit, fold, ir, model, parse
from .input_policy import (
    DEFAULT_LIMITS,
    InputArtifact,
    InputViolation,
    discover_input_files,
    read_xml,
    safe_text,
    validate_artifact_format,
)

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

    source: PurePath
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
        try:
            artifacts = discover(input_path, recursive=args.recursive)
        except InputViolation as exc:
            print(f"error: {_input_error(input_path, exc)}", file=sys.stderr)
            return 1
        if not artifacts:
            print(f"no .xml blocks found under {input_path}", file=sys.stderr)
            return 0
        outcomes = [decode_artifact(artifact, _dest_dir(artifact.relative_path, out_root), fmt)
                    for artifact in artifacts]
        _report(outcomes, input_root=input_path, quiet=args.quiet)
        return _exit_code(outcomes)

    # Neither file nor directory: nothing to decode. Soft no-op (exit 0).
    print(f"no input to decode: {input_path} not found", file=sys.stderr)
    return 0


def decode_file(source: Path, out_dir: Path, fmt: str) -> FileOutcome:
    """Decode one direct-path block (single-file CLI mode). Kept path-based
    and unchanged in behavior: format validation and reading go through
    ``read_xml``'s live-filesystem checks, exactly as before. Catches its own
    expected errors and reports them through the return value rather than
    aborting — so a batch can continue past a bad file."""
    try:
        doc = parse.parse_document(read_xml(source))
    except InputViolation as exc:
        return FileOutcome(source, "error", error=_input_error(source, exc))
    except ET.ParseError as exc:
        return FileOutcome(source, "error", error=_error(source, "MALFORMED_XML", safe_text(exc)))
    except (OSError, ValueError) as exc:
        return FileOutcome(source, "error", error=_error(source, "INPUT_REJECTED", safe_text(exc)))

    return _finish_decode(source, doc, out_dir, fmt)


def decode_artifact(source: InputArtifact, out_dir: Path, fmt: str) -> FileOutcome:
    """Decode one discovered artifact (directory-mode CLI). Reads bytes only
    through the artifact's own reader closure, which is bound to an
    already-open native handle/descriptor opened during discovery — this
    never re-opens a path by name, so a rename or reparse-point swap that
    happens after discovery cannot redirect the read."""
    try:
        validate_artifact_format(source)
        text = source.read_bytes(DEFAULT_LIMITS).decode("utf-8")
        doc = parse.parse_document(text)
    except InputViolation as exc:
        return FileOutcome(source.relative_path, "error", error=_input_error(source.relative_path, exc))
    except ET.ParseError as exc:
        return FileOutcome(
            source.relative_path, "error", error=_error(source.relative_path, "MALFORMED_XML", safe_text(exc))
        )
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return FileOutcome(
            source.relative_path, "error", error=_error(source.relative_path, "INPUT_REJECTED", safe_text(exc))
        )

    return _finish_decode(source.relative_path, doc, out_dir, fmt)


def _finish_decode(source: PurePath, doc: model.Document, out_dir: Path, fmt: str) -> FileOutcome:
    """Shared fold/emit tail for both ``decode_file`` and ``decode_artifact``."""
    try:
        decoded = fold.fold_block(doc)
    except Exception:
        return FileOutcome(source, "error", error=_error(source, "DECODE_FAILED", "unable to fold input"))

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return FileOutcome(source, "error", error=_error(source, "OUTPUT_FAILED", safe_text(exc)))

    stem = source.stem
    written: list[Path] = []
    try:
        if fmt in ("scl", "both"):
            written.append(_write(out_dir / f"{stem}.scl", emit.emit_scl(decoded)))
        if fmt in ("json", "both"):
            sidecar = json.dumps(emit.emit_sidecar(decoded), indent=2, ensure_ascii=False)
            written.append(_write(out_dir / f"{stem}.json", sidecar + "\n"))
    except (OSError, ValueError) as exc:
        return FileOutcome(source, "error", error=_error(source, "OUTPUT_FAILED", safe_text(exc)))

    return FileOutcome(source, "ok", decoded=decoded, written=tuple(written))


def discover(root: Path, recursive: bool) -> tuple[InputArtifact, ...]:
    """Every supported input under ``root``, sorted for deterministic processing."""
    return discover_input_files(root, recursive)


def _dest_dir(relative_path: PurePath, out_root: Path) -> Path:
    """Rebuild the artifact's parent directory under ``out_root`` — this is
    what mirrors the input's internal structure. ``relative_path`` (an
    ``InputArtifact.relative_path``) is already root-relative, so no further
    resolution against the input root is needed."""
    return out_root / relative_path.parent


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
    """``outcome.source`` is already root-relative in directory mode (it's an
    ``InputArtifact.relative_path``), so the prefix needs no further
    ``.relative_to()`` resolution against ``input_root`` — that parameter is
    only used here as the "are we in directory mode" flag."""
    decoded = outcome.decoded
    prefix = f"{safe_text(outcome.source)}: " if input_root is not None else ""
    label = f"{safe_text(decoded.name)} ({decoded.kind})"
    files = ", ".join(safe_text(p.name) for p in outcome.written)
    print(f"{prefix}decoded {label}: {len(decoded.networks)} network(s) -> {files}",
          file=sys.stderr)
    if decoded.warnings:
        print(f"  {len(decoded.warnings)} warning(s):", file=sys.stderr)
        for warning in decoded.warnings:
            print(f"    - {safe_text(warning)}", file=sys.stderr)


def _input_error(source: PurePath, exc: InputViolation) -> str:
    code = exc.code if exc.code == "SD_RESOURCE_WITHOUT_DCL" else "INPUT_REJECTED"
    return _error(source, code, exc.message)


def _error(source: PurePath, code: str, detail: str) -> str:
    return f"{code}: {safe_text(source.name)}: {safe_text(detail)}"


if __name__ == "__main__":
    sys.exit(main())
