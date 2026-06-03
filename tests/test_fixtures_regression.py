"""Regression tests over the real V21 sample corpus.

These skip when tests/fixtures/ is absent (it is gitignored), so they harden the
decoder on the maintainer's machine without breaking a fixture-less CI checkout.
"""

from __future__ import annotations

import json

import pytest

from simaticml_decoder import emit, fold, ir

FIXTURE_NAMES = ["InvertBit", "SimpleDevice"]


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_decode_pipeline_runs(name, load_fixture):
    decoded = fold.fold_block(load_fixture(name))
    scl = emit.emit_scl(decoded)
    assert isinstance(scl, str) and scl.endswith("\n")
    side = emit.emit_sidecar(decoded)
    json.dumps(side)  # serialisable
    assert set(side) >= {
        "block",
        "interface",
        "networks",
        "xref",
        "instruction_inventory",
        "warnings",
        "trace",
    }


def test_motor_is_combinational_no_latch(load_fixture):
    decoded = fold.fold_block(load_fixture("Motor"))
    assert len(decoded.networks) == 5
    latched = [
        s for n in decoded.networks for s in n.statements if isinstance(s, ir.Assign) and s.is_latch
    ]
    assert latched == []  # plan §9: Motor has no seal-in latch
    scl = emit.emit_scl(decoded)
    assert "#START_MOTOR := #FQ_FWD OR #FQ_REV;" in scl
    assert "#FQ_SecondSpeed := #START_MOTOR AND #FI_SecondSpeed;" in scl  # daisy chain


def test_singlealarm_constructs(load_fixture):
    decoded = fold.fold_block(load_fixture("SingleAlarm_FB"))
    stmts = [s for n in decoded.networks for s in n.statements]
    assert any(isinstance(s, ir.FlipFlop) for s in stmts)
    assert any(isinstance(s, ir.BoxCall) and s.instruction == "TON" for s in stmts)
    scl = emit.emit_scl(decoded)
    assert "R_TRIG(" in scl  # rising edge
    assert "#Counter < #MaxCounter" in scl  # Lt comparison


def test_fbsystem_scl_network_and_slices(load_fixture):
    decoded = fold.fold_block(load_fixture("FB_SYSTEM"))
    assert any(n.scl_text for n in decoded.networks)  # reconstructed SCL network
    scl = emit.emit_scl(decoded)
    assert ".%X0" in scl  # bit slice
    resets = [
        s
        for n in decoded.networks
        for s in n.statements
        if isinstance(s, ir.Assign) and s.kind is ir.AssignKind.RESET
    ]
    assert resets  # RCoil -> reset
