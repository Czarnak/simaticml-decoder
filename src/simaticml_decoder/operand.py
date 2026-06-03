"""Render a model.Access into its TIA display string.

Split out because it is needed in two phases (fold labels its nodes; emit prints
them) and is a self-contained pile of display conventions. Conventions applied
(SIMATICML_READING_GUIDE.md "Display Conventions"):

    LocalVariable scope        -> "#name"
    GlobalVariable scope       -> '"DB".field'
    Address scope              -> "%MW100" (area letter + offset)
    SliceAccessModifier "x0"   -> ".%X0"
    multi-component symbol     -> dotted path "System.CLK100ms"
    array AccessModifier       -> "name[<index>]"
    LiteralConstant            -> the value verbatim ("0", "TRUE", "T#3s")

Phase 1 (parse) is implemented first; this is filled alongside it so folded
networks have readable names.
"""

from __future__ import annotations

from . import model

# Address Area -> TIA display prefix (SIMATICML_READING_GUIDE.md "Area values").
_AREA_PREFIX: dict[str, str] = {
    "Input": "%I",
    "Output": "%Q",
    "Memory": "%M",
    "PeripheryInput": "%PI",
    "PeripheryOutput": "%PQ",
    "Timer": "%T",
    "Counter": "%C",
    "Local": "%L",
    "DB": "%DB",
    "DI": "%DI",
}

# Address Type -> width letter used in the absolute display (%MW, %MB, ...).
# Bool is special-cased to the byte.bit form and is not in this table.
_TYPE_WIDTH: dict[str, str] = {
    "byte": "B",
    "sint": "B",
    "usint": "B",
    "char": "B",
    "word": "W",
    "int": "W",
    "uint": "W",
    "s5time": "W",
    "dword": "D",
    "dint": "D",
    "udint": "D",
    "real": "D",
    "time": "D",
    "lword": "L",
    "lint": "L",
    "ulint": "L",
    "lreal": "L",
}


def render(access: model.Access) -> str:
    """model.Access -> display string (TIA conventions; see module docstring)."""
    operand = access.operand
    if isinstance(operand, model.Symbol):
        return _render_symbol(operand, access.scope)
    if isinstance(operand, model.Constant):
        return _render_constant(operand)
    if isinstance(operand, model.Address):
        return _render_address(operand)
    # Undef / Unnamed / scopes whose child landed in raw (Expression, CallInfo,
    # ...): no readable operand. Fail visibly rather than silently — a wrong name
    # is worse than an obvious placeholder.
    return f"<{access.scope or 'Undef'}#{access.uid}>"


# --------------------------------------------------------------------------- #
# Symbols                                                                      #
# --------------------------------------------------------------------------- #
def _render_symbol(symbol: model.Symbol, scope: str | None) -> str:
    if not symbol.components:
        return f"<{scope or 'Symbol'}>"
    is_global = scope == "GlobalVariable"
    parts = [
        _render_component(comp, quote=(is_global and i == 0))
        for i, comp in enumerate(symbol.components)
    ]
    path = ".".join(parts)
    # Local/interface variables get the '#' prefix; global access is already
    # quoted at its root ('"DB".field') and takes no prefix.
    if scope == "LocalVariable":
        return "#" + path
    return path


def _render_component(comp: model.Component, quote: bool = False) -> str:
    text = f'"{comp.name}"' if quote else comp.name
    # Array subscripts: one or more Access children rendered recursively.
    if comp.access_modifier in ("Array", "ReferenceToArray") and comp.indices:
        subs = ", ".join(render(idx) for idx in comp.indices)
        text += f"[{subs}]"
    # Bit/byte/word/dword slice: "x0" -> ".%X0", "b1" -> ".%B1".
    if comp.slice_access:
        letter = comp.slice_access[0].upper()
        number = comp.slice_access[1:]
        text += f".%{letter}{number}"
    return text


# --------------------------------------------------------------------------- #
# Constants                                                                    #
# --------------------------------------------------------------------------- #
def _render_constant(const: model.Constant) -> str:
    if const.value is not None:
        return const.value
    if const.name is not None:
        return const.name
    return "<const>"


# --------------------------------------------------------------------------- #
# Absolute addresses                                                           #
# --------------------------------------------------------------------------- #
def _render_address(addr: model.Address) -> str:
    prefix = _AREA_PREFIX.get(addr.area, "%" + (addr.area or "?"))
    # DB-qualified access carries a block number: DB10.DBW0-style.
    db_qualifier = ""
    if addr.block_number is not None and addr.area in ("DB", "DI"):
        prefix = f"%DB{addr.block_number}" if addr.area == "DB" else f"%DI{addr.block_number}"
        db_qualifier = ".DB" if addr.area == "DB" else ".DI"

    if addr.bit_offset is None:
        return prefix + db_qualifier

    byte, bit = divmod(addr.bit_offset, 8)
    type_lc = (addr.type or "").lower()
    if type_lc in ("bool", "bit", ""):
        return f"{prefix}{db_qualifier}{'X' if db_qualifier else ''}{byte}.{bit}"
    width = _TYPE_WIDTH.get(type_lc)
    if width:
        return f"{prefix}{db_qualifier}{width}{byte}"
    # Unknown width: fall back to the bit-addressed form so nothing is lost.
    return f"{prefix}{db_qualifier}{byte}.{bit}"
