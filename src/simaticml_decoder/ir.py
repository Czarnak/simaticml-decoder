"""Phase 2 output: the folded *semantics*, with no memory of the XML.

A network becomes an ordered list of statements. Rung conditions become a boolean
expression tree. Two cross-cutting commitments live here from the start:

* Traceability — every node carries the source ``uid``(s) it came from, so emit
  can map any rendered claim back to the net it was derived from.
* Loud failure — anything the folder could not interpret becomes an ``Unhandled``
  node carrying its part name + uid, so emit can surface it visibly instead of a
  silent omission (the worst possible failure in authoritative-looking SCL).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# --------------------------------------------------------------------------- #
# Boolean / value expressions (rung conditions, comparison operands)          #
# --------------------------------------------------------------------------- #
@dataclass
class VarRef:
    """A resolved operand, already rendered to its display form by operand.py."""

    name: str  # e.g. "#FI_Forward", '"DB".field', "%MW100"
    uid: str | None = None


@dataclass
class Literal:
    value: str  # rendered constant, e.g. "0", "TRUE", "T#3s"
    uid: str | None = None


@dataclass
class Not:
    operand: Expr


@dataclass
class And:
    operands: list[Expr] = field(default_factory=list)


@dataclass
class Or:
    operands: list[Expr] = field(default_factory=list)  # n-ary, matches O cardinality


@dataclass
class Compare:
    op: str  # "<" | "<=" | "=" | ">=" | ">" | "<>"
    left: Expr
    right: Expr
    uid: str | None = None


class EdgeKind(str, Enum):
    RISING = "rising"  # P_TRIG / PContact / PBox
    FALLING = "falling"  # N_TRIG / NContact / NBox


@dataclass
class Edge:
    kind: EdgeKind
    signal: Expr  # monitored signal / incoming power flow
    mem_bit: VarRef | None = None  # edge-memory operand
    uid: str | None = None


@dataclass
class RawExpr:
    """Free-form expression text taken verbatim (e.g. a Calculate-box Equation)."""

    text: str
    uid: str | None = None


@dataclass
class Unhandled:
    """A construct parsed but not folded. Rendered loudly by emit, never dropped."""

    part_name: str
    uid: str | None = None
    note: str = ""


Expr = VarRef | Literal | Not | And | Or | Compare | Edge | RawExpr | Unhandled


# --------------------------------------------------------------------------- #
# Statements (one rung's effect)                                              #
# --------------------------------------------------------------------------- #
class AssignKind(str, Enum):
    NORMAL = "normal"  # Coil           ->  target := <cond>;
    NEGATED = "negated"  # negated Coil   ->  target := NOT <cond>;
    SET = "set"  # SCoil          ->  IF <cond> THEN target := TRUE;
    RESET = "reset"  # RCoil          ->  IF <cond> THEN target := FALSE;


@dataclass
class Assign:
    target: VarRef
    value: Expr
    kind: AssignKind = AssignKind.NORMAL
    is_latch: bool = False  # set when a structural seal-in was detected
    note: str | None = None  # surfaced by emit when load-bearing
    uid: str | None = None


@dataclass
class FlipFlop:
    """Rs / Sr — reset- or set-priority bistable on a stored operand."""

    target: VarRef
    set_expr: Expr
    reset_expr: Expr
    reset_priority: bool = True  # Rs == reset-dominant; Sr == set-dominant
    uid: str | None = None


@dataclass
class BoxCall:
    """A system FB/FC box: TON/TOF/TP, Move/Add/Inc, RD_LOC_T, ..."""

    instruction: str  # "TON", "Move", ...
    inputs: dict[str, Expr] = field(default_factory=dict)  # pin -> expression
    outputs: dict[str, VarRef] = field(default_factory=dict)  # pin -> destination
    instance: str | None = None  # rendered instance name, for system FBs
    enable: Expr | None = None  # the en / IN power-flow condition
    uid: str | None = None


@dataclass
class UserCall:
    """A Call/CallInfo to a user FC/FB — parameters self-documented in the XML."""

    name: str
    block_type: str  # FC | FB
    instance: str | None = None
    params: dict[str, Expr | VarRef] = field(default_factory=dict)
    enable: Expr | None = None
    uid: str | None = None


Statement = Assign | FlipFlop | BoxCall | UserCall | Unhandled


# --------------------------------------------------------------------------- #
# Network + block level                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class NetworkLogic:
    index: int
    language: str
    title: str | None = None
    comment: str | None = None
    statements: list[Statement] = field(default_factory=list)  # folded LAD/FBD
    scl_text: str | None = None  # set for reconstructed SCL networks
    warnings: list[str] = field(default_factory=list)


@dataclass
class TagRef:
    """One side of the cross-reference table: where a tag is written / read."""

    network_index: int
    uid: str | None = None
    role: str = ""  # "write" | "read" + context (pin/operand)


@dataclass
class DecodedBlock:
    name: str
    kind: str
    interface: object  # model.Interface, carried through for the sidecar
    networks: list[NetworkLogic] = field(default_factory=list)
    xref: dict[str, list[TagRef]] = field(default_factory=dict)  # tag -> uses
    instruction_inventory: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
