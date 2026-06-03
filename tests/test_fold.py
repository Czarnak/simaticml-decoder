"""Unit tests for fold — model.* -> ir.* (the wire-graph folding).

Networks are built by hand from model objects so the folding is exercised
without any XML or fixture dependency.
"""

from __future__ import annotations

from simaticml_decoder import fold, ir, model
from simaticml_decoder.model import Endpoint
from simaticml_decoder.model import EndpointKind as EK
from simaticml_decoder.model import Wire


def _net(parts, accesses, wires, index=1):
    flg = model.FlgNet(accesses=accesses, parts=parts, calls={}, wires=wires)
    return model.Network(index=index, language=model.Language.LAD, source=flg)


def _sym(uid, name):
    return model.Access(uid=uid, scope="LocalVariable",
                        operand=model.Symbol([model.Component(name=name)]))


def _pr():
    return Endpoint(kind=EK.POWERRAIL)


def _ic(uid):
    return Endpoint(kind=EK.IDENT_CON, uid=uid)


def _nc(uid, pin):
    return Endpoint(kind=EK.NAME_CON, uid=uid, pin=pin)


def test_contact_drives_coil():
    parts = {"1": model.Part(uid="1", name="Contact"),
             "2": model.Part(uid="2", name="Coil")}
    accesses = {"10": _sym("10", "a"), "11": _sym("11", "y")}
    wires = [
        Wire(uid="w1", endpoints=[_pr(), _nc("1", "in")]),
        Wire(uid="w2", endpoints=[_ic("10"), _nc("1", "operand")]),
        Wire(uid="w3", endpoints=[_nc("1", "out"), _nc("2", "in")]),
        Wire(uid="w4", endpoints=[_ic("11"), _nc("2", "operand")]),
    ]
    logic = fold.fold_network(_net(parts, accesses, wires))
    assert len(logic.statements) == 1
    stmt = logic.statements[0]
    assert isinstance(stmt, ir.Assign)
    assert stmt.target.name == "#y"
    assert isinstance(stmt.value, ir.VarRef) and stmt.value.name == "#a"
    assert stmt.is_latch is False


def test_negated_contact_is_not():
    parts = {"1": model.Part(uid="1", name="Contact", negated_pins=["operand"]),
             "2": model.Part(uid="2", name="Coil")}
    accesses = {"10": _sym("10", "a"), "11": _sym("11", "y")}
    wires = [
        Wire(uid="w1", endpoints=[_pr(), _nc("1", "in")]),
        Wire(uid="w2", endpoints=[_ic("10"), _nc("1", "operand")]),
        Wire(uid="w3", endpoints=[_nc("1", "out"), _nc("2", "in")]),
        Wire(uid="w4", endpoints=[_ic("11"), _nc("2", "operand")]),
    ]
    stmt = fold.fold_network(_net(parts, accesses, wires)).statements[0]
    assert isinstance(stmt.value, ir.Not)
    assert stmt.value.operand.name == "#a"


def test_or_junction_is_nary_or():
    parts = {"1": model.Part(uid="1", name="Contact"),
             "2": model.Part(uid="2", name="Contact"),
             "3": model.Part(uid="3", name="O"),
             "4": model.Part(uid="4", name="Coil")}
    accesses = {"10": _sym("10", "a"), "11": _sym("11", "b"), "12": _sym("12", "y")}
    wires = [
        Wire(uid="w1", endpoints=[_pr(), _nc("1", "in")]),
        Wire(uid="w2", endpoints=[_ic("10"), _nc("1", "operand")]),
        Wire(uid="w3", endpoints=[_pr(), _nc("2", "in")]),
        Wire(uid="w4", endpoints=[_ic("11"), _nc("2", "operand")]),
        Wire(uid="w5", endpoints=[_nc("1", "out"), _nc("3", "in1")]),
        Wire(uid="w6", endpoints=[_nc("2", "out"), _nc("3", "in2")]),
        Wire(uid="w7", endpoints=[_nc("3", "out"), _nc("4", "in")]),
        Wire(uid="w8", endpoints=[_ic("12"), _nc("4", "operand")]),
    ]
    stmt = fold.fold_network(_net(parts, accesses, wires)).statements[0]
    assert isinstance(stmt.value, ir.Or)
    assert sorted(o.name for o in stmt.value.operands) == ["#a", "#b"]


def test_latch_detected_when_coil_feeds_back():
    # Seal-in: (#start OR #y) -> coil #y. The coil's own operand reappears in its
    # rung, which is the *only* thing that should mark a latch (never block type).
    parts = {"1": model.Part(uid="1", name="Contact"),
             "2": model.Part(uid="2", name="Contact"),
             "3": model.Part(uid="3", name="O"),
             "4": model.Part(uid="4", name="Coil")}
    accesses = {"10": _sym("10", "start"), "11": _sym("11", "y"), "12": _sym("12", "y")}
    wires = [
        Wire(uid="w1", endpoints=[_pr(), _nc("1", "in")]),
        Wire(uid="w2", endpoints=[_ic("10"), _nc("1", "operand")]),
        Wire(uid="w3", endpoints=[_pr(), _nc("2", "in")]),
        Wire(uid="w4", endpoints=[_ic("11"), _nc("2", "operand")]),
        Wire(uid="w5", endpoints=[_nc("1", "out"), _nc("3", "in1")]),
        Wire(uid="w6", endpoints=[_nc("2", "out"), _nc("3", "in2")]),
        Wire(uid="w7", endpoints=[_nc("3", "out"), _nc("4", "in")]),
        Wire(uid="w8", endpoints=[_ic("12"), _nc("4", "operand")]),
    ]
    stmt = fold.fold_network(_net(parts, accesses, wires)).statements[0]
    assert stmt.target.name == "#y"
    assert stmt.is_latch is True


def test_daisy_chained_coils_share_upstream_flow():
    # Coil_A.out -> Coil_B.in: power leaving Coil_A carries A's operand value.
    parts = {"1": model.Part(uid="1", name="Contact"),
             "2": model.Part(uid="2", name="Coil"),
             "3": model.Part(uid="3", name="Coil")}
    accesses = {"10": _sym("10", "cond"), "11": _sym("11", "a"), "12": _sym("12", "b")}
    wires = [
        Wire(uid="w1", endpoints=[_pr(), _nc("1", "in")]),
        Wire(uid="w2", endpoints=[_ic("10"), _nc("1", "operand")]),
        Wire(uid="w3", endpoints=[_nc("1", "out"), _nc("2", "in")]),
        Wire(uid="w4", endpoints=[_ic("11"), _nc("2", "operand")]),
        Wire(uid="w5", endpoints=[_nc("2", "out"), _nc("3", "in")]),
        Wire(uid="w6", endpoints=[_ic("12"), _nc("3", "operand")]),
    ]
    by_target = {s.target.name: s for s in fold.fold_network(_net(parts, accesses, wires)).statements}
    assert by_target["#a"].value.name == "#cond"
    assert by_target["#b"].value.name == "#a"


def test_unknown_instruction_folds_to_unhandled_and_warns():
    parts = {"1": model.Part(uid="1", name="Frobnicate")}
    logic = fold.fold_network(_net(parts, {}, []))
    assert len(logic.statements) == 1
    assert isinstance(logic.statements[0], ir.Unhandled)
    assert logic.statements[0].part_name == "Frobnicate"
    assert any("Frobnicate" in w for w in logic.warnings)


def test_empty_network_has_no_statements():
    net = model.Network(index=1, language=model.Language.LAD, source=None)
    logic = fold.fold_network(net)
    assert logic.statements == []
    assert logic.scl_text is None
