"""Reconstruct an SCL network from its tokenised AST.

SCL networks do not *fold* — they are already textual, just stored as an ordered,
interleaved stream of Access / Token / comment elements (SIMATICML_READING_GUIDE.md
"SCL Is a Tokenized AST"). Reconstruction is ordered concatenation, reusing
operand.render for the Access elements. This is a distinct operation from graph
folding, hence a separate module.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from . import model, operand


def reconstruct(st: model.StructuredText) -> str:
    """model.StructuredText -> SCL source text.

    parse._parse_structured_text stores Access uses as model.Access (so operand
    rendering and the xref work) and every other token as its raw element. We
    walk that stream in order and concatenate: Tokens contribute their literal
    text, Access nodes their rendered operand, comments their (wrapped) content.
    """
    out: list[str] = []
    for item in st.items:
        if isinstance(item, model.Access):
            out.append(operand.render(item))
        elif isinstance(item, ET.Element):
            out.append(_render_element(item))
        else:  # defensive: anything else, stringify
            out.append(str(item))
    return "".join(out).strip()


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _render_element(elem: ET.Element) -> str:
    local = _local(elem.tag)

    if local == "Token":
        return elem.get("Text", "")

    if local in ("LineComment", "Comment", "Comment_G"):
        return _render_comment(elem)

    if local == "Text":
        return elem.text or ""

    if local == "Access":
        # A raw (unparsed) Access — e.g. nested inside an Expression. Recurse so
        # its inner Token/Access stream is still emitted rather than dropped.
        return "".join(_render_element(c) for c in elem)

    if local == "Parameter":
        # Named call parameter inside an SCL call: "name := <wired value>".
        name = elem.get("Name", "")
        inner = "".join(_render_element(c) for c in elem)
        return f"{name}{inner}" if inner else name

    # Unknown token type: keep whatever text it carries so nothing is lost.
    text = "".join(elem.itertext())
    return text


def _render_comment(elem: ET.Element) -> str:
    """Render an SCL comment. Multi-line content becomes a (* ... *) block."""
    text = "".join(elem.itertext())
    if not text.strip():
        return ""
    if "\n" in text.strip():
        return f"(*{text}*)" if text.startswith("\n") else f"(*\n{text}\n*)"
    return f"// {text.strip()}"
