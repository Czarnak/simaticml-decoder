"""Unit tests for operand.render — the Access -> TIA display-string conventions."""

from __future__ import annotations

from simaticml_decoder import model, operand


def _access(scope, oper, uid="1"):
    return model.Access(uid=uid, scope=scope, operand=oper)


def test_local_variable_symbol():
    acc = _access("LocalVariable", model.Symbol([model.Component(name="FI_Forward")]))
    assert operand.render(acc) == "#FI_Forward"


def test_dotted_local_path():
    acc = _access(
        "LocalVariable",
        model.Symbol([model.Component(name="System"), model.Component(name="CLK100ms")]),
    )
    assert operand.render(acc) == "#System.CLK100ms"


def test_global_variable_quotes_root_only():
    acc = _access(
        "GlobalVariable",
        model.Symbol([model.Component(name="DB_Data"), model.Component(name="field")]),
    )
    assert operand.render(acc) == '"DB_Data".field'


def test_bit_slice_renders_percent_x():
    acc = _access(
        "LocalVariable", model.Symbol([model.Component(name="Clock_Byte", slice_access="x0")])
    )
    assert operand.render(acc) == "#Clock_Byte.%X0"


def test_array_index():
    idx = _access("LiteralConstant", model.Constant(value="5"), uid="2")
    acc = _access(
        "LocalVariable",
        model.Symbol([model.Component(name="buf", access_modifier="Array", indices=[idx])]),
    )
    assert operand.render(acc) == "#buf[5]"


def test_address_word():
    acc = _access("Address", model.Address(area="Memory", type="word", bit_offset=800))
    assert operand.render(acc) == "%MW100"


def test_address_bool_byte_bit():
    acc = _access("Address", model.Address(area="Output", type="bool", bit_offset=5))
    assert operand.render(acc) == "%Q0.5"


def test_literal_constant_verbatim():
    acc = _access("LiteralConstant", model.Constant(value="TRUE"))
    assert operand.render(acc) == "TRUE"


def test_unresolved_scope_is_loud_placeholder():
    acc = _access("Undef", None, uid="9")
    assert operand.render(acc) == "<Undef#9>"
