"""Phase 3: ir.* -> readable SCL text + JSON metadata sidecar.

Two artifacts (readability-first, NOT recompilable):

* SCL text — per network: a ``// Network N: <title>`` header, then the folded
  statements rendered as SCL, with load-bearing constructs called out (latches,
  edges, and any ir.Unhandled rendered as a visible ``// (!) UNHANDLED ...``
  line). Edges render as ``R_TRIG(...)`` / ``F_TRIG(...)`` so the rising/falling
  intent is explicit at the point of use.
* JSON sidecar — a single dict (schema in IMPLEMENTATION_PLAN.md §7):
      { "block": {name, kind},
        "interface": [...sections/members with ground-truth types...],
        "networks": [{index, title, language, warnings}],
        "xref": { tag: [{network, role, uid}, ...] },     # write/read map
        "instruction_inventory": { "Contact": 20, ... },
        "warnings": [...],
        "trace": { uid: "claim/location", ... } }          # UId -> claim map

This module is a faithful *renderer* of the IR: fold owns the semantics and the
readability rewrites (factoring, latch detection); emit owns text formatting and
never alters logic. Operator knowledge (``+``, ``<``, ``:=`` ...) is reused from
the instruction catalog rather than duplicated here.
"""

from __future__ import annotations

from . import instructions, ir, model

_INDENT = "    "


# --------------------------------------------------------------------------- #
# SCL text artifact                                                            #
# --------------------------------------------------------------------------- #
def emit_scl(decoded: ir.DecodedBlock) -> str:
    """Render the readable SCL text artifact for a decoded block."""
    lines: list[str] = [f"// Block: {decoded.name} ({decoded.kind})"]
    if decoded.warnings:
        lines.append(f"// {len(decoded.warnings)} warning(s) — see JSON sidecar")
    lines.append("")

    for net in decoded.networks:
        lines.extend(_render_network(net))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_network(net: ir.NetworkLogic) -> list[str]:
    title = f": {net.title}" if net.title else ""
    out = [f"// Network {net.index}{title}  [{net.language}]"]
    if net.comment:
        out.append(f"// {net.comment}")
    for warning in net.warnings:
        out.append(f"// (!) {warning}")

    if net.scl_text is not None:
        # Reconstructed SCL network — already textual, emit verbatim.
        out.append(net.scl_text)
        return out

    if not net.statements:
        out.append("// (empty network)")
        return out

    for stmt in net.statements:
        out.extend(_render_statement(stmt))
    return out


# --------------------------------------------------------------------------- #
# Statements                                                                   #
# --------------------------------------------------------------------------- #
def _render_statement(stmt: ir.Statement) -> list[str]:
    if isinstance(stmt, ir.Assign):
        return _render_assign(stmt)
    if isinstance(stmt, ir.FlipFlop):
        return _render_flipflop(stmt)
    if isinstance(stmt, ir.BoxCall):
        return _render_box(stmt)
    if isinstance(stmt, ir.UserCall):
        return _render_user_call(stmt)
    if isinstance(stmt, ir.Unhandled):
        return [_unhandled_line(stmt)]
    return [f"// (!) UNRENDERED statement {type(stmt).__name__}"]


def _render_assign(stmt: ir.Assign) -> list[str]:
    target = stmt.target.name
    value = _expr(stmt.value)
    trailer = ""
    if stmt.is_latch:
        trailer = f"   // seal-in latch: {stmt.note}" if stmt.note else "   // seal-in latch"
    elif stmt.note:
        trailer = f"   // {stmt.note}"

    if stmt.kind is ir.AssignKind.NORMAL:
        return [f"{target} := {value};{trailer}"]
    if stmt.kind is ir.AssignKind.NEGATED:
        neg = _expr(ir.Not(operand=stmt.value))
        return [f"{target} := {neg};{trailer}"]
    if stmt.kind is ir.AssignKind.SET:
        return _guard_block(stmt.value, [f"{target} := TRUE;"], trailer, "set coil ( S )")
    # RESET
    return _guard_block(stmt.value, [f"{target} := FALSE;"], trailer, "reset coil ( R )")


def _render_flipflop(stmt: ir.FlipFlop) -> list[str]:
    target = stmt.target.name
    set_s = _expr(stmt.set_expr)
    reset_s = _expr(stmt.reset_expr)
    if stmt.reset_priority:
        head = f"// RS flip-flop (reset priority): {target}"
        first, first_val = reset_s, "FALSE"
        second, second_val = set_s, "TRUE"
    else:
        head = f"// SR flip-flop (set priority): {target}"
        first, first_val = set_s, "TRUE"
        second, second_val = reset_s, "FALSE"
    return [
        head,
        f"IF {first} THEN",
        f"{_INDENT}{target} := {first_val};",
        f"ELSIF {second} THEN",
        f"{_INDENT}{target} := {second_val};",
        "END_IF;",
    ]


def _render_box(stmt: ir.BoxCall) -> list[str]:
    spec = instructions.lookup(stmt.instruction)
    hint = spec.render if spec else None
    body = _box_body(stmt, hint)
    if not body:
        # Nothing recognisable to render — surface loudly rather than drop it.
        body = [f"// (!) UNHANDLED box {stmt.instruction} (UId {stmt.uid})"]
    if stmt.enable is not None:
        return _wrap_if(stmt.enable, body)
    return body


def _box_body(stmt: ir.BoxCall, hint: str | None) -> list[str]:
    if hint == ":=":  # Move: dest := in;
        src = _first(stmt.inputs, ("in", "in1"))
        if src is not None and stmt.outputs:
            return [f"{d.name} := {_expr(src)};" for d in stmt.outputs.values()]
    elif hint in ("+", "-", "*", "/"):  # Add/Sub/Mul/Div: dest := a <op> b;
        operands = [stmt.inputs[k] for k in _sorted_pins(stmt.inputs)]
        expr = f" {hint} ".join(_expr(o) for o in operands)
        return [f"{d.name} := {expr};" for d in stmt.outputs.values()]
    elif hint in ("+1", "-1"):  # Inc/Dec: operand := operand +/- 1;
        var = stmt.inputs.get("operand") or _first(stmt.inputs, ())
        if var is not None:
            name = _expr(var)
            return [f"{name} := {name} {hint[0]} 1;"]
    elif hint == "equation":  # Calculate: dest := <equation>;
        eq = stmt.inputs.get("__equation__")
        if eq is not None and stmt.outputs:
            return [f"{d.name} := {_expr(eq)};" for d in stmt.outputs.values()]

    # Fallback / call-form boxes: timers (instance), system FCs, unknown boxes.
    return _box_call_form(stmt)


def _box_call_form(stmt: ir.BoxCall) -> list[str]:
    callee = stmt.instance or stmt.instruction
    pairs = [f"{pin} := {_expr(e)}" for pin, e in stmt.inputs.items()
             if pin != "__equation__"]
    if stmt.instance is None:
        # System FC: outputs are call parameters (OUT => dest).
        pairs += [f"{pin} => {d.name}" for pin, d in stmt.outputs.items()]
    lines = _format_call(callee, pairs)
    if stmt.instance is not None:
        # Instance box (timer): outputs read back off the instance member.
        lines += [f"{d.name} := {stmt.instance}.{pin};"
                  for pin, d in stmt.outputs.items()]
    return lines


def _render_user_call(stmt: ir.UserCall) -> list[str]:
    callee = stmt.instance or stmt.name
    pairs = [f"{pin} := {_expr(val)}" for pin, val in stmt.params.items()]
    lines = _format_call(callee, pairs)
    if stmt.enable is not None:
        return _wrap_if(stmt.enable, lines)
    return lines


# --------------------------------------------------------------------------- #
# Expression rendering (SCL precedence: NOT > AND > OR; compares parenthesised  #
# inside boolean context for readability — purely cosmetic, logic unchanged)    #
# --------------------------------------------------------------------------- #
_WRAP = {
    "top": frozenset(),
    "not": frozenset({"and", "or", "cmp"}),
    "and": frozenset({"or", "cmp"}),
    "or": frozenset({"and", "cmp"}),
    "cmp": frozenset({"and", "or", "not"}),
}


def _expr(expr: ir.Expr, ctx: str = "top") -> str:
    text, kind = _expr_core(expr)
    if kind in _WRAP[ctx]:
        return f"({text})"
    return text


def _expr_core(expr: ir.Expr) -> tuple[str, str]:
    if isinstance(expr, ir.VarRef):
        return expr.name, "var"
    if isinstance(expr, ir.Literal):
        return expr.value, "lit"
    if isinstance(expr, ir.Not):
        return f"NOT {_expr(expr.operand, 'not')}", "not"
    if isinstance(expr, ir.And):
        return " AND ".join(_expr(o, "and") for o in expr.operands), "and"
    if isinstance(expr, ir.Or):
        return " OR ".join(_expr(o, "or") for o in expr.operands), "or"
    if isinstance(expr, ir.Compare):
        return f"{_expr(expr.left, 'cmp')} {expr.op} {_expr(expr.right, 'cmp')}", "cmp"
    if isinstance(expr, ir.Edge):
        fn = "R_TRIG" if expr.kind is ir.EdgeKind.RISING else "F_TRIG"
        return f"{fn}({_expr(expr.signal)})", "edge"
    if isinstance(expr, ir.RawExpr):
        return expr.text, "raw"
    if isinstance(expr, ir.Unhandled):
        return f"(* (!) UNHANDLED {expr.part_name} (UId {expr.uid}) *)", "unhandled"
    return repr(expr), "unhandled"


# --------------------------------------------------------------------------- #
# Small rendering helpers                                                      #
# --------------------------------------------------------------------------- #
def _wrap_if(cond: ir.Expr, body: list[str]) -> list[str]:
    out = [f"IF {_expr(cond)} THEN"]
    out += [f"{_INDENT}{line}" for line in body]
    out.append("END_IF;")
    return out


def _guard_block(cond: ir.Expr, body: list[str], trailer: str, label: str) -> list[str]:
    lines = _wrap_if(cond, body)
    lines[0] = f"{lines[0]}{trailer}" if trailer else f"{lines[0]}   // {label}"
    return lines


def _format_call(callee: str, pairs: list[str]) -> list[str]:
    if not pairs:
        return [f"{callee}();"]
    if len(pairs) == 1:
        return [f"{callee}({pairs[0]});"]
    prefix = f"{callee}("
    pad = " " * len(prefix)
    lines = [f"{prefix}{pairs[0]},"]
    lines += [f"{pad}{p}," for p in pairs[1:-1]]
    lines.append(f"{pad}{pairs[-1]});")
    return lines


def _first(inputs: dict[str, ir.Expr], preferred: tuple[str, ...]) -> ir.Expr | None:
    for pin in preferred:
        if pin in inputs:
            return inputs[pin]
    for pin, expr in inputs.items():
        if pin != "__equation__":
            return expr
    return None


def _sorted_pins(inputs: dict[str, ir.Expr]) -> list[str]:
    pins = [p for p in inputs if p != "__equation__"]
    return sorted(pins, key=_pin_sort_key)


def _pin_sort_key(pin: str) -> tuple[str, int]:
    i = len(pin)
    while i > 0 and pin[i - 1].isdigit():
        i -= 1
    return (pin[:i], int(pin[i:]) if pin[i:] else -1)


def _unhandled_line(stmt: ir.Unhandled) -> str:
    note = f" - {stmt.note}" if stmt.note else ""
    return f"// (!) UNHANDLED {stmt.part_name} (UId {stmt.uid}){note}"


# --------------------------------------------------------------------------- #
# JSON sidecar artifact                                                        #
# --------------------------------------------------------------------------- #
def emit_sidecar(decoded: ir.DecodedBlock) -> dict:
    """Build the JSON-serialisable sidecar dict (schema in plan §7)."""
    return {
        "block": {"name": decoded.name, "kind": decoded.kind},
        "interface": _interface_json(decoded.interface),
        "networks": [
            {
                "index": net.index,
                "title": net.title,
                "language": net.language,
                "warnings": list(net.warnings),
            }
            for net in decoded.networks
        ],
        "xref": {
            tag: [
                {"network": ref.network_index, "role": ref.role, "uid": ref.uid}
                for ref in refs
            ]
            for tag, refs in decoded.xref.items()
        },
        "instruction_inventory": dict(decoded.instruction_inventory),
        "warnings": list(decoded.warnings),
        "trace": _build_trace(decoded),
    }


def _interface_json(interface: object) -> list[dict]:
    if not isinstance(interface, model.Interface):
        return []
    return [
        {"name": section.name, "members": [_member_json(m) for m in section.members]}
        for section in interface.sections
    ]


def _member_json(member: model.Member) -> dict:
    out: dict = {"name": member.name, "datatype": member.datatype}
    if member.is_udt:
        out["is_udt"] = True
    for attr in ("version", "start_value", "remanence", "comment"):
        value = getattr(member, attr)
        if value is not None:
            out[attr] = value
    if member.children:
        out["children"] = [_member_json(c) for c in member.children]
    return out


def _build_trace(decoded: ir.DecodedBlock) -> dict[str, str]:
    """UId -> short claim, so any rendered statement is traceable to its net."""
    trace: dict[str, str] = {}
    for net in decoded.networks:
        for stmt in net.statements:
            uid = getattr(stmt, "uid", None)
            if uid is None:
                continue
            trace[uid] = f"Network {net.index}: {_claim(stmt)}"
    return trace


def _claim(stmt: ir.Statement) -> str:
    if isinstance(stmt, ir.Assign):
        return f"{stmt.kind.value} assign {stmt.target.name}"
    if isinstance(stmt, ir.FlipFlop):
        kind = "Rs" if stmt.reset_priority else "Sr"
        return f"{kind} flip-flop {stmt.target.name}"
    if isinstance(stmt, ir.BoxCall):
        inst = f" {stmt.instance}" if stmt.instance else ""
        return f"box {stmt.instruction}{inst}"
    if isinstance(stmt, ir.UserCall):
        return f"call {stmt.block_type} {stmt.name}"
    if isinstance(stmt, ir.Unhandled):
        return f"UNHANDLED {stmt.part_name}"
    return type(stmt).__name__
