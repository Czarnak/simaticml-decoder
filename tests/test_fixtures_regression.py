"""Regression assertions for representative committed native exports."""

from __future__ import annotations

from simaticml_decoder import emit, fold, ir


def test_fc_cargador_is_three_combinational_assignments(load_fixture):
    decoded = fold.fold_block(load_fixture("FC_Cargador"))

    assert len(decoded.networks) == 4
    statements = [statement for network in decoded.networks for statement in network.statements]
    assert [statement.target.name for statement in statements] == [
        "#Load",
        "#Transfer left",
        "#Transfer right",
    ]
    assert all(isinstance(statement, ir.Assign) and not statement.is_latch for statement in statements)
    assert "#Load := NOT #Emergencia" in emit.emit_scl(decoded)


def test_mhj_function_keeps_its_scl_network(load_fixture):
    decoded = fold.fold_block(load_fixture("MHJ-PLC-Lab-Function-S71200"))

    assert len(decoded.networks) == 1
    assert decoded.networks[0].scl_text is not None
    assert "For#forVal" in emit.emit_scl(decoded)
