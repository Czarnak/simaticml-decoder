"""Regression assertions for representative committed native exports."""

from __future__ import annotations

from simaticml_decoder import emit, fold, ir


def test_inputs_fb_preserves_digital_input_assignments(load_fixture):
    decoded = fold.fold_block(load_fixture("Inputs_FB"))

    assert len(decoded.networks) == 21
    statements = [statement for network in decoded.networks for statement in network.statements]
    assignments = [statement for statement in statements if isinstance(statement, ir.Assign)]
    assert len(assignments) == 14
    assert assignments[0].target.name == '"InputValues_DB".InputsDigital.EmergencyStop'
    assert all(not statement.is_latch for statement in assignments)
    assert '"InputValues_DB".InputsDigital.EmergencyStop :=' in emit.emit_scl(decoded)


def test_analog_input_keeps_its_scl_network(load_fixture):
    decoded = fold.fold_block(load_fixture("AnalogInput"))

    assert len(decoded.networks) == 1
    assert decoded.networks[0].scl_text is not None
    assert "REGIONChoose input" in emit.emit_scl(decoded)
