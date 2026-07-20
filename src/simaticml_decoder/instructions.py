"""The instruction catalog — deliberately *data, not logic*.

fold.py reasons about pin *categories* (power-flow in/out, comparison pre/out,
box en/eno, flip-flop, OR-junction), never about specific instruction names.
This table maps Part Name -> category + pin vocabulary + a render hint. Adding a
new instruction (TOF, CTU, NContact, ...) is a row here, not a change to the
traversal. That is what lets v0's "parse-but-flag everything else" degrade
gracefully: a name absent from this table folds to an ir.Unhandled node.

Pin names per the Part Pin Vocabulary in SIMATICML_READING_GUIDE.md. Entries are
the confirmed instructions from the six sample blocks plus their clearly-symmetric
siblings (TOF/TP, Sr, NBox/NContact, the comparison family).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Category(str, Enum):
    POWER_FLOW = "power_flow"  # in/out, contact-like: passes or blocks power
    COIL = "coil"  # in/out, writes its operand
    OR_JUNCTION = "or_junction"  # merges parallel branches (Part Name="O")
    AND_JUNCTION = "and_junction"  # merges parallel branches (Part Name="A")
    COMPARISON = "comparison"  # pre/out, contact-like compare
    EDGE = "edge"  # pre/out or in/out, rising/falling detection
    FLIPFLOP = "flipflop"  # named set/reset inputs -> q
    BOX = "box"  # en/eno operation box (Move/Add/Inc/timers/system FC)


@dataclass
class Spec:
    name: str
    category: Category
    power_in: str | None = None  # name of the power-in pin, if any
    power_out: str | None = None  # name of the power-out pin, if any
    render: str | None = None  # operator/keyword hint for emit (":=", "<", ...)
    pins: tuple[str, ...] = field(default_factory=tuple)  # informative pin list
    note: str = ""


# Helper constructors keep the table compact and readable.
def _pf(name, render=None):
    return Spec(name, Category.POWER_FLOW, "in", "out", render, ("in", "operand", "out"))


def _coil(name, render):
    return Spec(name, Category.COIL, "in", "out", render, ("in", "operand", "out"))


def _cmp(name, op):
    return Spec(name, Category.COMPARISON, "pre", "out", op, ("pre", "in1", "in2", "out"))


def _box(name, pins, render=None):
    return Spec(name, Category.BOX, "en", "eno", render, pins)


CATALOG: dict[str, Spec] = {
    # --- power flow -------------------------------------------------------- #
    "Contact": _pf("Contact"),
    "Coil": _coil("Coil", ":="),
    "SCoil": _coil("SCoil", "S"),  # set coil  ( S )
    "RCoil": _coil("RCoil", "R"),  # reset coil ( R )
    "O": Spec("O", Category.OR_JUNCTION, None, "out", "OR", ("in1", "in2", "out")),
    "A": Spec("A", Category.AND_JUNCTION, None, "out", "AND", ("in1", "in2", "out")),
    # --- comparisons (pre/out, contact-like) ------------------------------ #
    "Lt": _cmp("Lt", "<"),
    "Le": _cmp("Le", "<="),
    "Eq": _cmp("Eq", "="),
    "Ne": _cmp("Ne", "<>"),
    "Ge": _cmp("Ge", ">="),
    "Gt": _cmp("Gt", ">"),
    # --- edge detection ---------------------------------------------------- #
    "PContact": Spec(
        "PContact", Category.EDGE, "pre", "out", "rising", ("pre", "operand", "bit", "out")
    ),
    "NContact": Spec(
        "NContact", Category.EDGE, "pre", "out", "falling", ("pre", "operand", "bit", "out")
    ),
    "PBox": Spec("PBox", Category.EDGE, "in", "out", "rising", ("in", "bit", "out")),
    "NBox": Spec("NBox", Category.EDGE, "in", "out", "falling", ("in", "bit", "out")),
    # --- flip-flops -------------------------------------------------------- #
    "Rs": Spec("Rs", Category.FLIPFLOP, None, "q", "reset_priority", ("s1", "r", "operand", "q")),
    "Sr": Spec("Sr", Category.FLIPFLOP, None, "q", "set_priority", ("s", "r1", "operand", "q")),
    # --- boxes (en/eno) ---------------------------------------------------- #
    "Move": _box("Move", ("en", "in", "out1", "eno"), ":="),
    "Add": _box("Add", ("en", "in1", "in2", "out", "eno"), "+"),
    "Sub": _box("Sub", ("en", "in1", "in2", "out", "eno"), "-"),
    "Mul": _box("Mul", ("en", "in1", "in2", "out", "eno"), "*"),
    "Div": _box("Div", ("en", "in1", "in2", "out", "eno"), "/"),
    "Inc": _box("Inc", ("en", "operand", "eno"), "+1"),
    "Dec": _box("Dec", ("en", "operand", "eno"), "-1"),
    "Calculate": _box("Calculate", ("en", "eno"), "equation"),
    # --- IEC timers (system FBs; UPPERCASE pins; need Instance) ------------ #
    "TON": _box("TON", ("IN", "PT", "Q", "ET")),
    "TOF": _box("TOF", ("IN", "PT", "Q", "ET")),
    "TP": _box("TP", ("IN", "PT", "Q", "ET")),
    # --- system FC example ------------------------------------------------- #
    "RD_LOC_T": _box("RD_LOC_T", ("en", "RET_VAL", "OUT", "eno")),
    # --- F-system safety instructions (S7 F-blocks; en/eno boxes like any --- #
    # other system FB, just with F-specific pin names). Pin tuples below list
    # only the pins observed as wired in practice, not necessarily the full
    # official interface — unlisted wired pins are still discovered dynamically
    # from the network, since `pins` is informative only (see lookup()).
    "ACK_GL": _box("ACK_GL", ("en", "ACK_GLOB", "eno")),
    "ESTOP1": _box("ESTOP1", ("en", "in1", "in2", "eno")),
    "SFDOOR": _box("SFDOOR", ("en", "IN1", "eno")),
    "FDBACK": _box("FDBACK", ("en", "ON", "QBAD_FIO", "eno")),
}


def lookup(name: str) -> Spec | None:
    """Return the Spec for a Part name, or None (caller folds to ir.Unhandled)."""
    return CATALOG.get(name)
