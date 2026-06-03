"""Phase 3: ir.* -> readable SCL text + JSON metadata sidecar.

Two artifacts (readability-first, NOT recompilable):

* SCL text — per network: a `// Network N: <title>` header, then the folded
  statements rendered as SCL, with load-bearing constructs called out (latches,
  edges, and any ir.Unhandled rendered as a visible `// (!) UNHANDLED ...` line).
* JSON sidecar — a single dict:
      { "block": {name, kind},
        "interface": [...sections/members with ground-truth types...],
        "networks": [{index, title, language, warnings}],
        "xref": { tag: [{network, role, uid}, ...] },     # write/read map
        "instruction_inventory": { "Contact": 20, ... },
        "warnings": [...],
        "trace": { uid: "claim/location", ... } }          # UId -> claim map

Default CLI format is "both". JSON-from-the-start was a deliberate choice so the
plc-code-analysis skill can consume the structured map programmatically.
"""

from __future__ import annotations

from . import ir


def emit_scl(decoded: ir.DecodedBlock) -> str:
    """Render the SCL text artifact. Raises until implemented (Phase 3)."""
    raise NotImplementedError("emit_scl — Phase 3")


def emit_sidecar(decoded: ir.DecodedBlock) -> dict:
    """Build the JSON-serialisable sidecar dict. Raises until implemented."""
    raise NotImplementedError("emit_sidecar — Phase 3")
