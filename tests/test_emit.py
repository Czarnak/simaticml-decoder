"""Unit tests for emit — ir.* -> SCL text + JSON sidecar.

IR objects are constructed directly, so these run without any XML/fixtures.
"""

from __future__ import annotations

import json

from simaticml_decoder import emit, ir, model


def _scl_of(stmt):
    block = ir.DecodedBlock(name="B", kind="FB", interface=model.Interface())
    block.networks.append(ir.NetworkLogic(index=1, language="LAD", statements=[stmt]))
    return emit.emit_scl(block)


def test_normal_assign():
    assert "#x := #y;" in _scl_of(ir.Assign(target=ir.VarRef("#x"), value=ir.VarRef("#y")))


def test_precedence_not_binds_tightest_or_parenthesised():
    val = ir.And(
        [ir.VarRef("#a"), ir.Not(ir.VarRef("#b")), ir.Or([ir.VarRef("#c"), ir.VarRef("#d")])]
    )
    s = _scl_of(ir.Assign(target=ir.VarRef("#x"), value=val))
    assert "#x := #a AND NOT #b AND (#c OR #d);" in s


def test_or_wraps_and_groups_for_readability():
    val = ir.Or(
        [ir.And([ir.VarRef("#a"), ir.VarRef("#b")]), ir.And([ir.VarRef("#c"), ir.VarRef("#d")])]
    )
    assert "(#a AND #b) OR (#c AND #d)" in _scl_of(ir.Assign(target=ir.VarRef("#x"), value=val))


def test_negated_assign():
    s = _scl_of(
        ir.Assign(target=ir.VarRef("#x"), value=ir.VarRef("#y"), kind=ir.AssignKind.NEGATED)
    )
    assert "#x := NOT #y;" in s


def test_reset_coil_emits_if_guard():
    s = _scl_of(ir.Assign(target=ir.VarRef("#x"), value=ir.VarRef("#c"), kind=ir.AssignKind.RESET))
    assert "IF #c THEN" in s and "#x := FALSE;" in s and "END_IF;" in s


def test_latch_is_called_out():
    s = _scl_of(
        ir.Assign(
            target=ir.VarRef("#x"),
            value=ir.Or([ir.VarRef("#start"), ir.VarRef("#x")]),
            is_latch=True,
            note="seal-in latch: #x feeds back",
        )
    )
    assert "seal-in latch" in s


def test_flipflop_reset_priority():
    s = _scl_of(
        ir.FlipFlop(
            target=ir.VarRef("#q"),
            set_expr=ir.VarRef("#s"),
            reset_expr=ir.VarRef("#r"),
            reset_priority=True,
        )
    )
    assert "RS flip-flop (reset priority)" in s
    assert "IF #r THEN" in s and "ELSIF #s THEN" in s


def test_box_move_assignment_form():
    s = _scl_of(
        ir.BoxCall(
            instruction="Move", inputs={"in": ir.Literal("0")}, outputs={"out1": ir.VarRef("#c")}
        )
    )
    assert "#c := 0;" in s


def test_box_add_with_enable_guard():
    s = _scl_of(
        ir.BoxCall(
            instruction="Add",
            inputs={"in1": ir.VarRef("#x"), "in2": ir.Literal("10")},
            outputs={"out": ir.VarRef("#x")},
            enable=ir.VarRef("#e"),
        )
    )
    assert "IF #e THEN" in s and "#x := #x + 10;" in s


def test_box_inc_under_rising_edge():
    edge = ir.Edge(kind=ir.EdgeKind.RISING, signal=ir.VarRef("#alarm"))
    s = _scl_of(ir.BoxCall(instruction="Inc", inputs={"operand": ir.VarRef("#c")}, enable=edge))
    assert "IF R_TRIG(#alarm) THEN" in s and "#c := #c + 1;" in s


def test_box_timer_instance_call_form():
    s = _scl_of(
        ir.BoxCall(
            instruction="TON",
            inputs={"IN": ir.VarRef("#s"), "PT": ir.VarRef("#t")},
            instance="#Timer",
        )
    )
    assert "#Timer(IN := #s," in s and "PT := #t);" in s


def test_user_call_fc():
    s = _scl_of(ir.UserCall(name="deviceState", block_type="FC", params={"Alarm": ir.VarRef("#a")}))
    assert "deviceState(Alarm := #a);" in s


def test_unhandled_statement_is_loud():
    s = _scl_of(ir.Unhandled(part_name="Frobnicate", uid="99", note="no catalog entry"))
    assert "// (!) UNHANDLED Frobnicate (UId 99) - no catalog entry" in s


def test_scl_has_block_and_network_headers_and_trailing_newline():
    block = ir.DecodedBlock(name="MyBlock", kind="FC", interface=model.Interface())
    block.networks.append(
        ir.NetworkLogic(
            index=1,
            language="LAD",
            title="Net One",
            statements=[ir.Assign(target=ir.VarRef("#x"), value=ir.VarRef("#y"))],
        )
    )
    s = emit.emit_scl(block)
    assert s.startswith("// Block: MyBlock (FC)")
    assert "// Network 1: Net One  [LAD]" in s
    assert s.endswith("\n")


def test_empty_network_marker():
    block = ir.DecodedBlock(name="B", kind="FC", interface=model.Interface())
    block.networks.append(ir.NetworkLogic(index=2, language="LAD"))
    assert "// (empty network)" in emit.emit_scl(block)


def test_sidecar_schema_interface_and_xref():
    interface = model.Interface(
        sections=[
            model.Section(
                name="Input",
                members=[
                    model.Member(name="FI_Start", datatype="Bool"),
                    model.Member(name="Cfg", datatype='"PLC_System"', is_udt=True),
                ],
            ),
        ]
    )
    block = ir.DecodedBlock(name="B", kind="FB", interface=interface)
    block.networks.append(ir.NetworkLogic(index=1, language="LAD", title="N1"))
    block.xref = {"FI_Start": [ir.TagRef(network_index=1, uid="21", role="read")]}
    block.instruction_inventory = {"Contact": 2}
    block.warnings = ["something deferred"]

    side = emit.emit_sidecar(block)
    assert set(side) >= {
        "block",
        "interface",
        "networks",
        "xref",
        "instruction_inventory",
        "warnings",
        "trace",
    }
    assert side["block"] == {"name": "B", "kind": "FB"}
    assert side["interface"][0]["name"] == "Input"
    members = side["interface"][0]["members"]
    assert members[0] == {"name": "FI_Start", "datatype": "Bool"}
    assert members[1]["is_udt"] is True
    assert side["xref"]["FI_Start"][0] == {"network": 1, "role": "read", "uid": "21"}
    assert side["instruction_inventory"] == {"Contact": 2}
    json.dumps(side)  # must be JSON-serialisable


def test_sidecar_trace_maps_statement_uid():
    block = ir.DecodedBlock(name="B", kind="FB", interface=model.Interface())
    block.networks.append(
        ir.NetworkLogic(
            index=3,
            language="LAD",
            statements=[ir.Assign(target=ir.VarRef("#x"), value=ir.VarRef("#y"), uid="40")],
        )
    )
    side = emit.emit_sidecar(block)
    assert side["trace"]["40"].startswith("Network 3:")
