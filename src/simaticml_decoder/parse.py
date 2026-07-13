"""Phase 1: SimaticML XML -> model.* (a faithful, behaviour-free mirror).

All XML-quirk handling is isolated here so the later phases never touch a raw
element. Decoder rules from SIMATICML_READING_GUIDE.md that this phase owns:

* Parse namespace-aware but match by *local name* (FlgNet is /v5, StructuredText
  is /v4, Interface is /v5 — versions drift; local-name matching is robust).
* Scope every UId lookup table *per compile unit* — UIds repeat across networks.
  (Each FlgNet owns its own accesses/parts/calls dicts, so this is structural.)
* Never deduplicate Access nodes — one node per use (each use has a unique UId).
* Unescape ``&quot;...&quot;`` datatypes and mark them as UDT references.
  (ElementTree unescapes entities; a datatype left wrapped in quotes is a UDT.)
* Read ``Informative`` values but do not depend on them.
* Preserve unknown attributes/elements in ``raw`` for forward compatibility.
* Empty ``<NetworkSource />`` -> Network.source = None.

This is the first module implemented, validated against the six V21 samples.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from . import model
from .input_policy import read_xml

# --------------------------------------------------------------------------- #
# Namespace-agnostic element helpers (match by local name only)               #
# --------------------------------------------------------------------------- #


def _ln(tag: object) -> str:
    """Local name of an element tag, dropping any ``{namespace}`` prefix."""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _children(elem: ET.Element, name: str | None = None) -> list[ET.Element]:
    """Direct child elements, optionally filtered by local name."""
    return [c for c in elem if name is None or _ln(c.tag) == name]


def _child(elem: ET.Element | None, name: str) -> ET.Element | None:
    """First direct child with the given local name, or None."""
    if elem is None:
        return None
    for c in elem:
        if _ln(c.tag) == name:
            return c
    return None


def _child_text(elem: ET.Element | None, name: str) -> str | None:
    c = _child(elem, name)
    return c.text if c is not None else None


def _first_element_child(elem: ET.Element | None) -> ET.Element | None:
    """First child element (ignoring text/whitespace); None if there are none."""
    if elem is None:
        return None
    for c in elem:
        return c
    return None


def _nz(text: str | None) -> str | None:
    """Normalise a metadata string: strip, and collapse empty/blank to None."""
    if text is None:
        return None
    stripped = text.strip()
    return stripped or None


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (ValueError, AttributeError):
        return None


def _extra_attrs(elem: ET.Element, known: set[str]) -> dict:
    """Unknown attributes preserved for forward compatibility (the raw hatch)."""
    return {k: v for k, v in elem.attrib.items() if k not in known}


# --------------------------------------------------------------------------- #
# Entry points                                                                 #
# --------------------------------------------------------------------------- #


def parse_document(xml_text: str) -> model.Document:
    """Raw XML string -> model.Document (a faithful syntactic mirror)."""
    root = ET.fromstring(xml_text)

    engineering = _child(root, "Engineering")
    version = engineering.get("version") if engineering is not None else None

    block_elem = _find_block_element(root)
    if block_elem is None:
        raise ValueError("no SW.Blocks.* block element found in document")

    return model.Document(engineering_version=version, block=_parse_block(block_elem))


def parse_file(path: str) -> model.Document:
    """Read a boundary-validated SimaticML file and parse it."""
    return parse_document(read_xml(Path(path)))


# --------------------------------------------------------------------------- #
# Block                                                                        #
# --------------------------------------------------------------------------- #


def _find_block_element(root: ET.Element) -> ET.Element | None:
    for child in root:
        if _ln(child.tag).startswith("SW.Blocks."):
            return child
    return None


def _block_kind(tag_local: str) -> model.BlockKind:
    suffix = tag_local.split(".")[-1]
    try:
        return model.BlockKind(suffix)
    except ValueError:
        return model.BlockKind.UNKNOWN


def _parse_block(elem: ET.Element) -> model.Block:
    attrs = _child(elem, "AttributeList")
    objlist = _child(elem, "ObjectList")

    block = model.Block(
        kind=_block_kind(_ln(elem.tag)),
        id=elem.get("ID", ""),
        name=_nz(_child_text(attrs, "Name")) or "",
        number=_int_or_none(_child_text(attrs, "Number")),
        language=_parse_language(_child_text(attrs, "ProgrammingLanguage")),
        memory_layout=_nz(_child_text(attrs, "MemoryLayout")),
        memory_reserve=_int_or_none(_child_text(attrs, "MemoryReserve")),
        set_eno_automatically=_is_true(_child_text(attrs, "SetENOAutomatically")),
        interface=_parse_interface(_child(attrs, "Interface")),
    )

    if objlist is not None:
        block.title, block.comment = _titles_and_comments(objlist)
        index = 0
        for cu in _children(objlist, "SW.Blocks.CompileUnit"):
            index += 1
            block.networks.append(_parse_compile_unit(cu, index))

    return block


def _parse_language(value: str | None) -> model.Language:
    """Per-compile-unit / block language -> model.Language (unknown -> OTHER)."""
    raw = (value or "").strip()
    mapping = {
        "LAD": model.Language.LAD,
        "LAD_IEC": model.Language.LAD,
        "FBD": model.Language.FBD,
        "FBD_IEC": model.Language.FBD,
        "SCL": model.Language.SCL,
        "STL": model.Language.STL,
        "GRAPH": model.Language.GRAPH,
    }
    return mapping.get(raw, model.Language.OTHER)


# --------------------------------------------------------------------------- #
# Interface (sections + members)                                              #
# --------------------------------------------------------------------------- #


def _parse_interface(elem: ET.Element | None) -> model.Interface:
    interface = model.Interface()
    if elem is None:
        return interface
    sections = _child(elem, "Sections")
    if sections is None:
        return interface
    for sec in _children(sections, "Section"):
        section = model.Section(name=sec.get("Name", ""))
        for member in _children(sec, "Member"):
            section.members.append(_parse_member(member))
        interface.sections.append(section)
    return interface


_MEMBER_KNOWN_ATTRS = {"Name", "Datatype", "Version", "Remanence", "Accessibility"}


def _parse_member(elem: ET.Element) -> model.Member:
    # ElementTree already unescaped &quot; -> a datatype still wrapped in double
    # quotes is a UDT reference (e.g. '"PLC_System"'). Keep the quotes; flag it.
    datatype = elem.get("Datatype", "")
    is_udt = len(datatype) >= 2 and datatype.startswith('"') and datatype.endswith('"')

    raw: dict = {}
    accessibility = elem.get("Accessibility")
    if accessibility is not None:
        raw["accessibility"] = accessibility
    extra = _extra_attrs(elem, _MEMBER_KNOWN_ATTRS)
    if extra:
        raw["attrs"] = extra
    attr_list = _child(elem, "AttributeList")
    if attr_list is not None:
        bool_attrs = {
            ba.get("Name"): (ba.text or "").strip()
            for ba in _children(attr_list, "BooleanAttribute")
        }
        if bool_attrs:
            raw["boolean_attributes"] = bool_attrs

    return model.Member(
        name=elem.get("Name", ""),
        datatype=datatype,
        is_udt=is_udt,
        version=elem.get("Version"),
        start_value=_nz(_child_text(elem, "StartValue")),
        remanence=elem.get("Remanence"),
        comment=_inline_comment(_child(elem, "Comment")),
        children=[_parse_member(c) for c in _children(elem, "Member")],
        raw=raw,
    )


# --------------------------------------------------------------------------- #
# Compile units / networks                                                     #
# --------------------------------------------------------------------------- #


def _parse_compile_unit(elem: ET.Element, index: int) -> model.Network:
    attrs = _child(elem, "AttributeList")
    objlist = _child(elem, "ObjectList")

    language = _parse_language(_child_text(attrs, "ProgrammingLanguage"))
    title, comment = (_titles_and_comments(objlist) if objlist is not None else (None, None))
    source = _parse_network_source(_child(attrs, "NetworkSource"), language)

    return model.Network(
        index=index,
        language=language,
        title=title,
        comment=comment,
        source=source,
    )


def _parse_network_source(elem: ET.Element | None, language: model.Language):
    """NetworkSource -> FlgNet | StructuredText | RawSource | None.

    An empty ``<NetworkSource />`` (no element children) is a blank network and
    resolves to None.
    """
    if elem is None:
        return None
    container = _first_element_child(elem)
    if container is None:
        return None  # empty network

    local = _ln(container.tag)
    if local == "FlgNet":
        return _parse_flgnet(container)
    if local == "StructuredText":
        return _parse_structured_text(container)
    # STL (StatementList) and GRAPH (Graph) are parsed losslessly but not
    # rendered in v0 — retain the element tree so nothing is dropped.
    return model.RawSource(language=language, element=container)


# --------------------------------------------------------------------------- #
# FlgNet (LAD/FBD graph)                                                        #
# --------------------------------------------------------------------------- #


def _parse_flgnet(elem: ET.Element) -> model.FlgNet:
    net = model.FlgNet()

    parts = _child(elem, "Parts")
    if parts is not None:
        for child in parts:
            local = _ln(child.tag)
            if local == "Access":
                access = _parse_access(child)
                net.accesses[access.uid] = access
            elif local == "Part":
                part = _parse_part(child)
                net.parts[part.uid] = part
            elif local == "Call":
                call = _parse_call(child)
                net.calls[call.uid] = call

    labels = _child(elem, "Labels")
    if labels is not None:
        for decl in _children(labels, "LabelDeclaration"):
            label_el = _child(decl, "Label")
            net.labels.append(
                model.Label(
                    uid=decl.get("UId", ""),
                    name=(label_el.get("Name", "") if label_el is not None else ""),
                    comment=_inline_comment(_child(decl, "Comment")),
                )
            )

    wires = _child(elem, "Wires")
    if wires is not None:
        for wire in _children(wires, "Wire"):
            net.wires.append(_parse_wire(wire))

    return net


_ACCESS_KNOWN_ATTRS = {"Scope", "UId"}


def _parse_access(elem: ET.Element) -> model.Access:
    operand: model.Operand = None
    raw: dict = {}

    for child in elem:
        local = _ln(child.tag)
        if local == "Symbol":
            operand = _parse_symbol(child)
        elif local == "Constant":
            operand = _parse_constant(child)
        elif local == "Address":
            operand = _parse_address(child)
        elif local == "Comment":
            continue
        else:
            # Expression / CallInfo / Instruction / DataType / Reference / ...
            # are not LAD/FBD operands; round-trip them via raw rather than raise.
            raw.setdefault("children", {})[local] = child

    extra = _extra_attrs(elem, _ACCESS_KNOWN_ATTRS)
    if extra:
        raw["attrs"] = extra

    return model.Access(
        uid=elem.get("UId", ""),
        scope=elem.get("Scope", ""),
        operand=operand,
        raw=raw,
    )


def _parse_symbol(elem: ET.Element) -> model.Symbol:
    return model.Symbol(components=[_parse_component(c) for c in _children(elem, "Component")])


def _parse_component(elem: ET.Element) -> model.Component:
    slice_access = elem.get("SliceAccessModifier")
    if slice_access in (None, "undef"):
        slice_access = None
    return model.Component(
        name=elem.get("Name", ""),
        slice_access=slice_access,
        access_modifier=elem.get("AccessModifier", "None"),
        simple_access_modifier=elem.get("SimpleAccessModifier", "None"),
        indices=[_parse_access(a) for a in _children(elem, "Access")],
    )


def _parse_constant(elem: ET.Element) -> model.Constant:
    type_el = _child(elem, "ConstantType")
    value_el = _child(elem, "ConstantValue")
    raw: dict = {}
    if type_el is not None and _is_true(type_el.get("Informative")):
        raw["type_informative"] = True
    if value_el is not None and _is_true(value_el.get("Informative")):
        raw["value_informative"] = True
    fmt = {
        sa.get("Name"): sa.text
        for sa in _children(elem, "StringAttribute")
    }
    if fmt:
        raw["format"] = fmt
    return model.Constant(
        type=type_el.text if type_el is not None else None,
        value=value_el.text if value_el is not None else None,
        name=elem.get("Name"),
        raw=raw,
    )


def _parse_address(elem: ET.Element) -> model.Address:
    return model.Address(
        area=elem.get("Area", ""),
        type=elem.get("Type"),
        bit_offset=_int_or_none(elem.get("BitOffset")),
        block_number=_int_or_none(elem.get("BlockNumber")),
    )


_PART_KNOWN_ATTRS = {"Name", "UId", "DisabledENO", "Version"}


def _parse_part(elem: ET.Element) -> model.Part:
    template_values: list[model.TemplateValue] = []
    negated_pins: list[str] = []
    invisible_pins: list[str] = []
    instance: model.Instance | None = None
    equation: str | None = None
    comment: str | None = None
    raw: dict = {}

    for child in elem:
        local = _ln(child.tag)
        if local == "TemplateValue":
            template_values.append(
                model.TemplateValue(
                    name=child.get("Name", ""),
                    kind=child.get("Type", ""),
                    value=child.text,
                )
            )
        elif local == "Negated":
            negated_pins.append(child.get("Name", ""))
        elif local == "Invisible":
            invisible_pins.append(child.get("Name", ""))
        elif local == "Instance":
            instance = _parse_instance(child)
        elif local == "Equation":
            equation = child.text
        elif local == "Comment":
            comment = _inline_comment(child)
        elif local == "AutomaticTyped":
            raw.setdefault("automatic_typed", []).append(child.get("Name"))
        else:
            raw.setdefault("children", {})[local] = child

    extra = _extra_attrs(elem, _PART_KNOWN_ATTRS)
    if extra:
        raw["attrs"] = extra

    return model.Part(
        uid=elem.get("UId", ""),
        name=elem.get("Name", ""),
        disabled_eno=_is_true(elem.get("DisabledENO")),
        version=elem.get("Version"),
        template_values=template_values,
        negated_pins=negated_pins,
        invisible_pins=invisible_pins,
        instance=instance,
        equation=equation,
        comment=comment,
        raw=raw,
    )


def _parse_instance(elem: ET.Element) -> model.Instance:
    return model.Instance(
        scope=elem.get("Scope", ""),
        components=[_parse_component(c) for c in _children(elem, "Component")],
    )


def _parse_call(elem: ET.Element) -> model.Call:
    info = _child(elem, "CallInfo")
    name = ""
    block_type = ""
    instance: model.Instance | None = None
    parameters: list[model.Parameter] = []

    if info is not None:
        name = info.get("Name", "")
        block_type = info.get("BlockType", "")
        for child in info:
            local = _ln(child.tag)
            if local == "Parameter":
                parameters.append(
                    model.Parameter(
                        name=child.get("Name", ""),
                        section=child.get("Section", ""),
                        type=child.get("Type"),
                        informative=_is_true(child.get("Informative")),
                    )
                )
            elif local == "Instance":
                instance = _parse_instance(child)

    return model.Call(
        uid=elem.get("UId", ""),
        name=name,
        block_type=block_type,
        instance=instance,
        parameters=parameters,
        comment=_inline_comment(_child(elem, "Comment")),
    )


_ENDPOINT_KINDS = {
    "Powerrail": model.EndpointKind.POWERRAIL,
    "IdentCon": model.EndpointKind.IDENT_CON,
    "NameCon": model.EndpointKind.NAME_CON,
    "OpenCon": model.EndpointKind.OPEN_CON,
    "Openbranch": model.EndpointKind.OPEN_BRANCH,
}


def _parse_wire(elem: ET.Element) -> model.Wire:
    endpoints: list[model.Endpoint] = []
    for child in elem:
        kind = _ENDPOINT_KINDS.get(_ln(child.tag))
        if kind is None:
            continue
        endpoints.append(
            model.Endpoint(kind=kind, uid=child.get("UId"), pin=child.get("Name"))
        )
    return model.Wire(uid=elem.get("UId", ""), endpoints=endpoints)


# --------------------------------------------------------------------------- #
# StructuredText (SCL tokenised AST) — parsed losslessly, reconstructed later   #
# --------------------------------------------------------------------------- #


def _parse_structured_text(elem: ET.Element) -> model.StructuredText:
    """Interleaved Access/Token/Text/comment stream.

    Access nodes are parsed into model.Access (so operand.render and the xref
    work); every other token is retained as its raw element so scl_reconstruct
    (Phase 2) can rebuild the source verbatim. Nothing is dropped.
    """
    items: list[object] = []
    for child in elem:
        if _ln(child.tag) == "Access":
            items.append(_parse_access(child))
        else:
            items.append(child)
    return model.StructuredText(items=items)


# --------------------------------------------------------------------------- #
# Multilingual text (block / network titles and comments)                      #
# --------------------------------------------------------------------------- #


def _titles_and_comments(objlist: ET.Element) -> tuple[str | None, str | None]:
    title: str | None = None
    comment: str | None = None
    for mlt in _children(objlist, "MultilingualText"):
        composition = mlt.get("CompositionName")
        text = _multilingual_text(mlt)
        if composition == "Title":
            title = text
        elif composition == "Comment":
            comment = text
    return title, comment


def _multilingual_text(mlt: ET.Element) -> str | None:
    """Extract the en-US text from a MultilingualText, falling back to the first.

    MultilingualText > ObjectList > MultilingualTextItem > AttributeList >
    {Culture, Text}. Empty/whitespace text resolves to None.
    """
    objlist = _child(mlt, "ObjectList")
    if objlist is None:
        return None
    fallback: str | None = None
    for item in _children(objlist, "MultilingualTextItem"):
        attrs = _child(item, "AttributeList")
        if attrs is None:
            continue
        culture = (_child_text(attrs, "Culture") or "").strip()
        text = _nz(_child_text(attrs, "Text"))
        if culture == "en-US":
            return text
        if fallback is None:
            fallback = text
    return fallback


def _inline_comment(elem: ET.Element | None) -> str | None:
    """Inline Part/Call/Member Comment: <Comment><MultiLanguageText .../></Comment>."""
    if elem is None:
        return None
    fallback: str | None = None
    for mlt in _children(elem, "MultiLanguageText"):
        text = _nz(mlt.text)
        if mlt.get("Lang") == "en-US":
            return text
        if fallback is None:
            fallback = text
    return fallback
