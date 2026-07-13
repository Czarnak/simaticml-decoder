"""Phase 2: model.* -> ir.* (the folding — the heart of the tool).

Intended algorithm per network (LAD/FBD FlgNet):

1. Build a directed pin-graph from the wires. Each Wire is one source endpoint
   followed by N sink endpoints (fan-out); add a directed edge source -> sink.
2. Resolve every operand to a display string via operand.render, keyed by UId.
3. Classify each Part via instructions.lookup -> Category. Unknown name -> the
   part folds to ir.Unhandled (loud, never dropped).
4. Walk forward from each Powerrail source. Compose power flow into expressions:
       series (A.out -> B.in)           -> And
       parallel merged at an "O" node    -> Or  (n-ary, by cardinality)
       Negated pin                       -> Not
       comparison (pre/out)              -> Compare
       edge (PContact/PBox/...)          -> Edge
   The condition feeding a coil's `in` pin is that coil's rung expression.
5. Coils -> ir.Assign (NORMAL/NEGATED/SET/RESET by part name). Daisy-chained
   coils (Coil_A.out -> Coil_B.in) share the upstream power flow — power leaving
   a coil is the coil's *operand* value, so the second coil reads that variable.
6. Flip-flops (Rs/Sr) -> ir.FlipFlop. Boxes (TON/Move/...) -> ir.BoxCall with the
   Instance rendered. Calls -> ir.UserCall (parameters from CallInfo).
7. Latch detection is *structural only*: a coil whose operand reappears inside
   its own rung expression (a seal-in contact reading the coil's variable back
   into its power path) -> mark the Assign is_latch + note. Never inferred from
   block type — a block with no such feedback (e.g. Motor.xml) gets no latch.

A readability pass factors a common AND-prefix out of OR branches, so a fan-out
through a shared chain renders as ``A AND B AND (C OR D)`` rather than the
expanded ``(A AND B AND C) OR (A AND B AND D)`` (logically identical).

SCL networks are handed to scl_reconstruct (not folded). STL/GRAPH networks are
recorded as warnings in v0 (parsed, rendering deferred).

Also builds the cross-reference table and instruction inventory for the sidecar.
"""

from __future__ import annotations

from . import instructions, ir, model, operand, scl_reconstruct
from .instructions import Category

# Sentinel for "pure power flow" (the left rail / unconditional TRUE). It is an
# identity element for AND and never appears as a rendered leaf — it is turned
# into ir.Literal("TRUE") by _materialize the moment it must become real.
_POWER = object()

_COIL_KIND = {
    "Coil": ir.AssignKind.NORMAL,
    "SCoil": ir.AssignKind.SET,
    "RCoil": ir.AssignKind.RESET,
}

# set/reset input pin names per flip-flop type (SIMATICML_READING_GUIDE.md).
_FLIPFLOP_PINS = {
    "Rs": ("s1", "r"),
    "Sr": ("s", "r1"),
}


# --------------------------------------------------------------------------- #
# Block + network entry points                                                #
# --------------------------------------------------------------------------- #


def fold_block(doc: model.Document) -> ir.DecodedBlock:
    """model.Document -> ir.DecodedBlock (folded networks + xref + inventory)."""
    block = doc.block
    decoded = ir.DecodedBlock(
        name=block.name,
        kind=block.kind.value,
        interface=block.interface,
    )

    for network in block.networks:
        logic, folder = _fold(network)
        decoded.networks.append(logic)
        decoded.warnings.extend(logic.warnings)
        if folder is not None:
            for tag, refs in folder.xref.items():
                decoded.xref.setdefault(tag, []).extend(refs)
            for name, count in folder.inventory.items():
                decoded.instruction_inventory[name] = (
                    decoded.instruction_inventory.get(name, 0) + count
                )

    return decoded


def fold_network(net: model.Network) -> ir.NetworkLogic:
    """Fold one network into statements (or reconstructed SCL text)."""
    logic, _folder = _fold(net)
    return logic


def _fold(net: model.Network) -> tuple[ir.NetworkLogic, "_NetFolder | None"]:
    """Fold a network once, returning the logic and (for FlgNet) its folder so
    fold_block can harvest xref/inventory without re-folding."""
    logic = ir.NetworkLogic(
        index=net.index,
        language=net.language.value,
        title=net.title,
        comment=net.comment,
    )

    source = net.source
    if source is None:
        return logic, None  # empty network — nothing to render

    if isinstance(source, model.StructuredText):
        logic.scl_text = scl_reconstruct.reconstruct(source)
        return logic, None

    if isinstance(source, model.FlgNet):
        folder = _NetFolder(net.index, source)
        logic.statements = folder.statements
        logic.warnings = folder.warnings
        return logic, folder

    # RawSource: STL / GRAPH / DB — parsed losslessly, rendering deferred in v0.
    lang = getattr(getattr(source, "language", None), "value", net.language.value)
    logic.warnings.append(
        f"Network {net.index}: {lang} network parsed but rendering is deferred in v0"
    )
    return logic, None


# --------------------------------------------------------------------------- #
# Per-network folder                                                          #
# --------------------------------------------------------------------------- #


class _NetFolder:
    """Folds a single FlgNet. Holds the pin-graph maps and the memoised eval."""

    def __init__(self, index: int, net: model.FlgNet) -> None:
        self.index = index
        self.net = net

        # pin-graph: who drives each sink, and what each source pin fans out to.
        self.pin_driver: dict[tuple[str, str], model.Endpoint] = {}
        self.access_driver: dict[str, model.Endpoint] = {}
        self.pin_out_sinks: dict[tuple[str, str], list[model.Endpoint]] = {}
        self._build_graph()

        self._memo: dict[tuple[str, str], object] = {}
        self._in_progress: set[tuple[str, str]] = set()

        self.statements: list[ir.Statement] = []
        self.warnings: list[str] = []
        self.xref: dict[str, list[ir.TagRef]] = {}
        self.inventory: dict[str, int] = {}

        self._build_inventory()
        self._build_xref()
        self._build_statements()

    # -- graph ------------------------------------------------------------- #
    def _build_graph(self) -> None:
        for wire in self.net.wires:
            if not wire.endpoints:
                continue
            src, *sinks = wire.endpoints
            for sink in sinks:
                if sink.kind == model.EndpointKind.NAME_CON and sink.uid is not None:
                    self.pin_driver[(sink.uid, sink.pin or "")] = src
                elif sink.kind == model.EndpointKind.IDENT_CON and sink.uid is not None:
                    self.access_driver[sink.uid] = src
            if src.kind == model.EndpointKind.NAME_CON and src.uid is not None:
                self.pin_out_sinks.setdefault((src.uid, src.pin or ""), []).extend(sinks)

    def _build_inventory(self) -> None:
        for part in self.net.parts.values():
            self.inventory[part.name] = self.inventory.get(part.name, 0) + 1

    # -- expression evaluation --------------------------------------------- #
    def _eval_source(self, endpoint: model.Endpoint | None):
        if endpoint is None:
            return _POWER
        kind = endpoint.kind
        if kind == model.EndpointKind.POWERRAIL:
            return _POWER
        if kind == model.EndpointKind.IDENT_CON:
            return self._value_of_access(endpoint.uid)
        if kind == model.EndpointKind.NAME_CON and endpoint.uid is not None:
            return self._eval_part_out(endpoint.uid, endpoint.pin or "")
        # OpenCon / Openbranch as a source: treat as pure power (unconnected).
        return _POWER

    def _value_of_access(self, uid: str | None):
        access = self.net.accesses.get(uid or "")
        if access is None:
            return ir.Unhandled("Access", uid, "unresolved access reference")
        if isinstance(access.operand, model.Constant):
            return ir.Literal(value=operand.render(access), uid=access.uid)
        return ir.VarRef(name=operand.render(access), uid=access.uid)

    def _eval_part_out(self, uid: str, pin: str):
        key = (uid, pin)
        if key in self._memo:
            return self._memo[key]
        if key in self._in_progress:
            # Defensive: a wire cycle (not expected in LAD). Break loudly.
            return ir.Unhandled(
                self.net.parts.get(uid, model.Part(uid, "?")).name,
                uid,
                "cyclic power-flow reference",
            )
        self._in_progress.add(key)
        result = self._eval_part_out_uncached(uid, pin)
        self._in_progress.discard(key)
        self._memo[key] = result
        return result

    def _eval_part_out_uncached(self, uid: str, pin: str):
        part = self.net.parts.get(uid)
        if part is None:
            return ir.Unhandled("?", uid, "unresolved part reference")
        spec = instructions.lookup(part.name)
        if spec is None:
            return ir.Unhandled(part.name, uid, "no catalog entry")

        cat = spec.category
        if cat == Category.COIL:
            # Power leaving a coil carries the coil's operand value.
            return self._operand_varref(uid) or _POWER
        if cat == Category.POWER_FLOW:
            incoming = self._driver_expr(uid, spec.power_in)
            cond = self._contact_condition(part, uid)
            return _and([incoming, cond])
        if cat == Category.COMPARISON:
            incoming = self._driver_expr(uid, spec.power_in)
            cmp = ir.Compare(
                op=spec.render or "=",
                left=_materialize(self._driver_expr(uid, "in1")),
                right=_materialize(self._driver_expr(uid, "in2")),
                uid=uid,
            )
            return _and([incoming, cmp])
        if cat == Category.EDGE:
            return self._eval_edge(part, uid, spec)
        if cat == Category.OR_JUNCTION:
            return self._eval_or(uid)
        if cat == Category.FLIPFLOP:
            return self._operand_varref(uid) or _POWER
        if cat == Category.BOX:
            # Reading a box output pin (Q/ET/OUT/RET_VAL): a member of its
            # instance, or a synthetic name when there is no instance.
            label = self._box_label(part)
            return ir.VarRef(name=f"{label}.{pin}", uid=uid)
        return ir.Unhandled(part.name, uid, "unclassified category")

    def _eval_edge(self, part: model.Part, uid: str, spec) -> ir.Expr:
        kind = ir.EdgeKind.FALLING if spec.render == "falling" else ir.EdgeKind.RISING
        mem_bit = self._pin_varref(uid, "bit")
        if spec.power_in == "in":
            # PBox/NBox: the incoming power flow *is* the monitored signal.
            signal = _materialize(self._driver_expr(uid, "in"))
            return ir.Edge(kind=kind, signal=signal, mem_bit=mem_bit, uid=uid)
        # PContact/NContact: monitored signal is `operand`, power flow is `pre`.
        incoming = self._driver_expr(uid, spec.power_in or "pre")
        signal = self._operand_varref(uid) or ir.Literal("TRUE")
        edge = ir.Edge(kind=kind, signal=signal, mem_bit=mem_bit, uid=uid)
        return _and([incoming, edge])

    def _eval_or(self, uid: str) -> ir.Expr:
        branches = []
        for pin in self._sorted_input_pins(uid):
            branches.append(_materialize(self._driver_expr(uid, pin)))
        if not branches:
            return _POWER
        return _factor_or(branches)

    # -- helpers used by eval ---------------------------------------------- #
    def _driver_expr(self, uid: str, pin: str | None):
        if pin is None:
            return _POWER
        return self._eval_source(self.pin_driver.get((uid, pin)))

    def _contact_condition(self, part: model.Part, uid: str) -> ir.Expr:
        var = self._operand_varref(uid) or ir.Literal("TRUE")
        if "operand" in part.negated_pins:
            return ir.Not(operand=var)
        return var

    def _operand_access(self, uid: str) -> model.Access | None:
        endpoint = self.pin_driver.get((uid, "operand"))
        if endpoint is not None and endpoint.kind == model.EndpointKind.IDENT_CON:
            return self.net.accesses.get(endpoint.uid or "")
        return None

    def _operand_varref(self, uid: str) -> ir.VarRef | None:
        access = self._operand_access(uid)
        if access is None:
            return None
        return ir.VarRef(name=operand.render(access), uid=access.uid)

    def _pin_varref(self, uid: str, pin: str) -> ir.VarRef | None:
        endpoint = self.pin_driver.get((uid, pin))
        if endpoint is not None and endpoint.kind == model.EndpointKind.IDENT_CON:
            access = self.net.accesses.get(endpoint.uid or "")
            if access is not None:
                return ir.VarRef(name=operand.render(access), uid=access.uid)
        return None

    def _sorted_input_pins(self, uid: str) -> list[str]:
        pins = [p for (u, p) in self.pin_driver if u == uid]
        return sorted(pins, key=_pin_sort_key)

    def _box_label(self, part: model.Part) -> str:
        if part.instance is not None:
            return _render_instance(part.instance)
        return f"#{part.name}_{part.uid}"

    # -- statement generation ---------------------------------------------- #
    def _build_statements(self) -> None:
        produced: list[tuple[int, ir.Statement]] = []

        for uid, part in self.net.parts.items():
            stmt = self._statement_for_part(uid, part)
            if stmt is not None:
                produced.append((_uid_key(uid), stmt))

        for uid, call in self.net.calls.items():
            produced.append((_uid_key(uid), self._statement_for_call(uid, call)))

        produced.sort(key=lambda pair: pair[0])
        self.statements = [stmt for _, stmt in produced]

    def _statement_for_part(self, uid: str, part: model.Part) -> ir.Statement | None:
        spec = instructions.lookup(part.name)
        if spec is None:
            note = f"unknown instruction '{part.name}'"
            self.warnings.append(f"Network {self.index}: {note} (UId {uid})")
            return ir.Unhandled(part_name=part.name, uid=uid, note=note)

        cat = spec.category
        if cat == Category.COIL:
            return self._make_assign(uid, part, spec)
        if cat == Category.FLIPFLOP:
            return self._make_flipflop(uid, part)
        if cat == Category.BOX:
            return self._make_box(uid, part, spec)
        # Contacts / comparisons / edges / OR are sub-expressions, not statements.
        return None

    def _make_assign(self, uid: str, part: model.Part, spec) -> ir.Statement:
        target = self._operand_varref(uid)
        if target is None:
            note = f"coil '{part.name}' has no operand"
            self.warnings.append(f"Network {self.index}: {note} (UId {uid})")
            return ir.Unhandled(part_name=part.name, uid=uid, note=note)

        kind = _COIL_KIND.get(part.name, ir.AssignKind.NORMAL)
        if "operand" in part.negated_pins:
            kind = ir.AssignKind.NEGATED

        value = _materialize(self._driver_expr(uid, spec.power_in or "in"))
        is_latch = _contains_var(value, target.name)
        note = None
        if is_latch:
            note = f"seal-in latch: {target.name} feeds back into its own rung"

        return ir.Assign(
            target=target, value=value, kind=kind, is_latch=is_latch, note=note, uid=uid
        )

    def _make_flipflop(self, uid: str, part: model.Part) -> ir.Statement:
        target = self._operand_varref(uid)
        if target is None:
            note = f"flip-flop '{part.name}' has no operand"
            self.warnings.append(f"Network {self.index}: {note} (UId {uid})")
            return ir.Unhandled(part_name=part.name, uid=uid, note=note)
        set_pin, reset_pin = _FLIPFLOP_PINS.get(part.name, ("s", "r"))
        return ir.FlipFlop(
            target=target,
            set_expr=_materialize(self._driver_expr(uid, set_pin)),
            reset_expr=_materialize(self._driver_expr(uid, reset_pin)),
            reset_priority=(part.name == "Rs"),
            uid=uid,
        )

    def _make_box(self, uid: str, part: model.Part, spec) -> ir.Statement:
        inputs: dict[str, ir.Expr] = {}
        outputs: dict[str, ir.VarRef] = {}
        enable: ir.Expr | None = None

        for (u, pin), endpoint in self.pin_driver.items():
            if u != uid:
                continue
            expr = self._eval_source(endpoint)
            if pin == spec.power_in:  # the en pin
                if expr is not _POWER:
                    enable = _materialize(expr)
            else:
                inputs[pin] = _materialize(expr)

        for (u, pin), sinks in self.pin_out_sinks.items():
            if u != uid or pin == spec.power_out:
                continue
            for sink in sinks:
                if sink.kind == model.EndpointKind.IDENT_CON:
                    access = self.net.accesses.get(sink.uid or "")
                    if access is not None:
                        outputs[pin] = ir.VarRef(name=operand.render(access), uid=access.uid)
                        break

        instance = _render_instance(part.instance) if part.instance else None
        if spec.render == "equation" and part.equation:
            inputs["__equation__"] = ir.RawExpr(text=part.equation, uid=uid)

        return ir.BoxCall(
            instruction=part.name,
            inputs=inputs,
            outputs=outputs,
            instance=instance,
            enable=enable,
            uid=uid,
        )

    def _statement_for_call(self, uid: str, call: model.Call) -> ir.Statement:
        params: dict[str, ir.Expr | ir.VarRef] = {}
        for param in call.parameters:
            endpoint = self.pin_driver.get((uid, param.name))
            if endpoint is not None:
                params[param.name] = _materialize(self._eval_source(endpoint))
                continue
            sinks = self.pin_out_sinks.get((uid, param.name), [])
            for sink in sinks:
                if sink.kind == model.EndpointKind.IDENT_CON:
                    access = self.net.accesses.get(sink.uid or "")
                    if access is not None:
                        params[param.name] = ir.VarRef(name=operand.render(access), uid=access.uid)
                        break

        enable_endpoint = self.pin_driver.get((uid, "en"))
        enable = None
        if enable_endpoint is not None:
            expr = self._eval_source(enable_endpoint)
            if expr is not _POWER:
                enable = _materialize(expr)

        return ir.UserCall(
            name=call.name,
            block_type=call.block_type,
            instance=_render_instance(call.instance) if call.instance else None,
            params=params,
            enable=enable,
            uid=uid,
        )

    # -- cross-reference --------------------------------------------------- #
    def _build_xref(self) -> None:
        for wire in self.net.wires:
            if not wire.endpoints:
                continue
            src, *sinks = wire.endpoints
            if src.kind == model.EndpointKind.IDENT_CON:
                for sink in sinks:
                    if sink.kind == model.EndpointKind.NAME_CON and sink.uid is not None:
                        role = self._role_for_input(sink.uid, sink.pin or "")
                        self._add_xref(src.uid, role)
            elif src.kind == model.EndpointKind.NAME_CON:
                for sink in sinks:
                    if sink.kind == model.EndpointKind.IDENT_CON:
                        self._add_xref(sink.uid, "write")

    def _role_for_input(self, target_uid: str, pin: str) -> str:
        call = self.net.calls.get(target_uid)
        if call is not None:
            section = next((p.section for p in call.parameters if p.name == pin), "")
            return {
                "Input": "read",
                "Output": "write",
                "InOut": "readwrite",
                "Return": "write",
            }.get(section, "read")

        part = self.net.parts.get(target_uid)
        if part is not None and pin == "operand":
            spec = instructions.lookup(part.name)
            if spec is not None and spec.category in (Category.COIL, Category.FLIPFLOP):
                return "write"
            if part.name in ("Inc", "Dec"):
                return "readwrite"
        return "read"

    def _add_xref(self, access_uid: str | None, role: str) -> None:
        access = self.net.accesses.get(access_uid or "")
        if access is None or isinstance(access.operand, model.Constant):
            return  # constants are not tags
        if access.operand is None:
            return
        tag = _tag_name(access)
        self.xref.setdefault(tag, []).append(
            ir.TagRef(network_index=self.index, uid=access.uid, role=role)
        )


# --------------------------------------------------------------------------- #
# Expression construction helpers                                              #
# --------------------------------------------------------------------------- #


def _materialize(expr):
    """Turn the _POWER sentinel into a concrete TRUE; pass anything else through."""
    if expr is _POWER:
        return ir.Literal(value="TRUE")
    return expr


def _and(parts: list) -> object:
    """AND-combine, dropping pure-power operands and flattening nested ANDs."""
    flat: list[ir.Expr] = []
    for part in parts:
        if part is _POWER:
            continue
        if isinstance(part, ir.And):
            flat.extend(part.operands)
        else:
            flat.append(part)
    if not flat:
        return _POWER
    if len(flat) == 1:
        return flat[0]
    return ir.And(operands=flat)


def _factor_or(branches: list[ir.Expr]) -> ir.Expr:
    """OR the branches, factoring a shared leading AND-prefix out front.

    ``(A AND B AND C) OR (A AND B AND D)`` -> ``A AND B AND (C OR D)``. This makes
    a fan-out through a shared contact chain read the way TIA draws it. Purely a
    readability rewrite — logically identical.
    """
    operands: list[ir.Expr] = []
    for branch in branches:
        if isinstance(branch, ir.Or):
            operands.extend(branch.operands)
        else:
            operands.append(branch)

    if len(operands) == 1:
        return operands[0]

    term_lists = [list(op.operands) if isinstance(op, ir.And) else [op] for op in operands]

    prefix: list[ir.Expr] = []
    i = 0
    while all(len(terms) > i for terms in term_lists) and all(
        _expr_key(terms[i]) == _expr_key(term_lists[0][i]) for terms in term_lists
    ):
        prefix.append(term_lists[0][i])
        i += 1

    if not prefix:
        return ir.Or(operands=operands)

    remainders: list[ir.Expr] = []
    for terms in term_lists:
        tail = terms[i:]
        if not tail:
            remainders.append(ir.Literal(value="TRUE"))
        elif len(tail) == 1:
            remainders.append(tail[0])
        else:
            remainders.append(ir.And(operands=tail))

    inner = ir.Or(operands=remainders)
    return ir.And(operands=[*prefix, inner])


def _expr_key(expr) -> tuple:
    """Structural signature ignoring source UIds, for prefix comparison."""
    if isinstance(expr, ir.VarRef):
        return ("var", expr.name)
    if isinstance(expr, ir.Literal):
        return ("lit", expr.value)
    if isinstance(expr, ir.Not):
        return ("not", _expr_key(expr.operand))
    if isinstance(expr, ir.And):
        return ("and", tuple(_expr_key(o) for o in expr.operands))
    if isinstance(expr, ir.Or):
        return ("or", tuple(_expr_key(o) for o in expr.operands))
    if isinstance(expr, ir.Compare):
        return ("cmp", expr.op, _expr_key(expr.left), _expr_key(expr.right))
    if isinstance(expr, ir.Edge):
        bit = expr.mem_bit.name if expr.mem_bit else None
        return ("edge", expr.kind.value, _expr_key(expr.signal), bit)
    if isinstance(expr, ir.RawExpr):
        return ("raw", expr.text)
    if isinstance(expr, ir.Unhandled):
        return ("unhandled", expr.part_name, expr.uid)
    return ("?", repr(expr))


def _contains_var(expr, name: str) -> bool:
    """True if a VarRef with this name appears anywhere in the expression tree."""
    if isinstance(expr, ir.VarRef):
        return expr.name == name
    if isinstance(expr, ir.Literal):
        return False
    if isinstance(expr, ir.Not):
        return _contains_var(expr.operand, name)
    if isinstance(expr, (ir.And, ir.Or)):
        return any(_contains_var(o, name) for o in expr.operands)
    if isinstance(expr, ir.Compare):
        return _contains_var(expr.left, name) or _contains_var(expr.right, name)
    if isinstance(expr, ir.Edge):
        return _contains_var(expr.signal, name) or (
            expr.mem_bit is not None and expr.mem_bit.name == name
        )
    return False


# --------------------------------------------------------------------------- #
# Small leaf helpers                                                           #
# --------------------------------------------------------------------------- #


def _render_instance(instance: model.Instance) -> str:
    """Render an Instance (system FB backing member) as a display name."""
    access = model.Access(
        uid="",
        scope=instance.scope or "LocalVariable",
        operand=model.Symbol(components=instance.components),
    )
    return operand.render(access)


def _tag_name(access: model.Access) -> str:
    name = operand.render(access)
    return name[1:] if name.startswith("#") else name


def _pin_sort_key(pin: str) -> tuple:
    """Order pins so in1 < in2 < ... < in10 (numeric suffix aware)."""
    digits = ""
    i = len(pin)
    while i > 0 and pin[i - 1].isdigit():
        i -= 1
    digits = pin[i:]
    base = pin[:i]
    return (base, int(digits) if digits else -1)


def _uid_key(uid: str) -> int:
    try:
        return int(uid)
    except (ValueError, TypeError):
        return 1 << 30
