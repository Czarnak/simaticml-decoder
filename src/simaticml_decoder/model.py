"""Phase 1 output: a faithful, behaviour-free mirror of the SimaticML XML.

This layer mirrors the *syntax* of the export (blocks, sections, parts, wires)
exactly as it appears — it does not interpret logic. Interpretation happens in
fold.py against ir.py. Keeping the two apart is the front-end/middle-end split:
adding FBD (same FlgNet) or a new output target touches one phase, not all three.

Field coverage follows the "Stable Parser Model" in SIMATICML_READING_GUIDE.md.
Large open enumerations (the 20 Access scopes, 13 address areas) are kept as
plain ``str`` plus a ``raw`` escape hatch rather than exhaustive enums, so an
unfamiliar value round-trips instead of raising.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BlockKind(str, Enum):
    FC = "FC"
    FB = "FB"
    OB = "OB"
    DB = "DB"
    UNKNOWN = "UNKNOWN"


class Language(str, Enum):
    """Per-compile-unit programming language. Subset we render in v0 + passthrough."""

    LAD = "LAD"
    FBD = "FBD"
    SCL = "SCL"
    STL = "STL"
    GRAPH = "GRAPH"
    OTHER = "OTHER"  # DB / SDB / IEC variants etc. — parsed, not rendered in v0


# ----------------------------------------------------------------------------- #
# Interface (block signature + local declarations)                              #
# ----------------------------------------------------------------------------- #
@dataclass
class Member:
    name: str
    datatype: str                       # may be a quoted UDT ref, e.g. '"PLC_System"'
    is_udt: bool = False                # True when datatype was quoted in the XML
    version: str | None = None          # system/complex types (e.g. TON_TIME "1.0")
    start_value: str | None = None      # TIA literal, e.g. "T#3s", "16#0"
    remanence: str | None = None        # e.g. "Retain"
    comment: str | None = None
    children: list[Member] = field(default_factory=list)  # nested struct members
    raw: dict = field(default_factory=dict)


@dataclass
class Section:
    name: str                           # Input | Output | InOut | Static | Temp | Constant | Return
    members: list[Member] = field(default_factory=list)


@dataclass
class Interface:
    sections: list[Section] = field(default_factory=list)


# ----------------------------------------------------------------------------- #
# Operands referenced by Access nodes                                           #
# ----------------------------------------------------------------------------- #
@dataclass
class Component:
    """One level of a (possibly dotted) symbol path, e.g. System.CLK100ms."""

    name: str
    slice_access: str | None = None     # SliceAccessModifier, e.g. "x0" / "b1"
    access_modifier: str = "None"       # None | Array | Reference | ReferenceToArray
    simple_access_modifier: str = "None"  # None | Periphery | QualityInformation | combos
    indices: list[Access] = field(default_factory=list)  # array subscripts (Access children)


@dataclass
class Symbol:
    components: list[Component] = field(default_factory=list)


@dataclass
class Constant:
    type: str | None = None             # ConstantType (may be Informative)
    value: str | None = None            # ConstantValue (may be Informative)
    name: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Address:
    area: str                           # Input | Output | Memory | DB | Timer | Counter | ...
    type: str | None = None
    bit_offset: int | None = None       # Byte*8 + Bit
    block_number: int | None = None     # DB number, for DB access


# Operand = Symbol | Constant | Address (other scope children parsed into ``raw``)
Operand = Symbol | Constant | Address | None


@dataclass
class Access:
    """A data reference. Per-use (never deduplicated): each occurrence is its own node."""

    uid: str
    scope: str                          # 20 possible values — kept as str (see guide)
    operand: Operand = None
    raw: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- #
# Instructions (Part) and user/system calls (Call)                              #
# ----------------------------------------------------------------------------- #
@dataclass
class TemplateValue:
    name: str                           # e.g. "Card", "SrcType", "time_type"
    kind: str                           # Cardinality | Type | Operation
    value: str | None = None


@dataclass
class Instance:
    """Backing static member for a system FB (TON/CTU/...) — same shape as Symbol."""

    scope: str
    components: list[Component] = field(default_factory=list)


@dataclass
class Part:
    uid: str
    name: str                           # Contact | Coil | O | Move | TON | Lt | Rs | ...
    disabled_eno: bool = False
    version: str | None = None          # system FB/FC type version
    template_values: list[TemplateValue] = field(default_factory=list)
    negated_pins: list[str] = field(default_factory=list)   # from <Negated Name="..."/>
    invisible_pins: list[str] = field(default_factory=list)
    instance: Instance | None = None    # system FB instance ref
    equation: str | None = None         # Calculate box only
    comment: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Parameter:
    name: str
    section: str                        # Input | Output | InOut | Return
    type: str | None = None
    informative: bool = False


@dataclass
class Call:
    uid: str
    name: str                           # called block name
    block_type: str                     # FC | FB | OB | DB | UDT | FBT | FCT
    instance: Instance | None = None    # for FB calls
    parameters: list[Parameter] = field(default_factory=list)
    comment: str | None = None


# ----------------------------------------------------------------------------- #
# Wires (the graph edges)                                                        #
# ----------------------------------------------------------------------------- #
class EndpointKind(str, Enum):
    POWERRAIL = "Powerrail"
    IDENT_CON = "IdentCon"              # -> Access node (data), by uid
    NAME_CON = "NameCon"               # -> Part/Call pin, by (uid, name)
    OPEN_CON = "OpenCon"               # explicitly unused output
    OPEN_BRANCH = "Openbranch"         # unterminated branch


@dataclass
class Endpoint:
    kind: EndpointKind
    uid: str | None = None              # for IdentCon / NameCon / OpenCon
    pin: str | None = None              # for NameCon


@dataclass
class Wire:
    """First endpoint is the source; the rest are sinks (fan-out)."""

    uid: str
    endpoints: list[Endpoint] = field(default_factory=list)


@dataclass
class Label:
    uid: str
    name: str
    comment: str | None = None


# ----------------------------------------------------------------------------- #
# Network sources (one per programming language)                                 #
# ----------------------------------------------------------------------------- #
@dataclass
class FlgNet:
    """LAD/FBD network: indexed parts/calls/accesses + the wire list. UIds are
    scoped to *this* compile unit only (reused across networks)."""

    accesses: dict[str, Access] = field(default_factory=dict)
    parts: dict[str, Part] = field(default_factory=dict)
    calls: dict[str, Call] = field(default_factory=dict)
    wires: list[Wire] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)


@dataclass
class StructuredText:
    """SCL network: an ordered, interleaved token/access stream (a tokenised AST).
    Reconstructed to text by scl_reconstruct.py — not folded."""

    items: list[object] = field(default_factory=list)  # Access | Token | comment nodes (raw)


# StatementList (STL) and Graph (SFC) are parsed-but-not-rendered in v0; kept as
# raw element trees so nothing is lost.
@dataclass
class RawSource:
    language: Language
    element: object = None              # retained xml.etree element for later phases


NetworkSource = FlgNet | StructuredText | RawSource | None


@dataclass
class Network:
    index: int                          # 1-based, in document order
    language: Language
    title: str | None = None
    comment: str | None = None
    source: NetworkSource = None        # None == empty network


# ----------------------------------------------------------------------------- #
# Top level                                                                      #
# ----------------------------------------------------------------------------- #
@dataclass
class Block:
    kind: BlockKind
    id: str
    name: str
    number: int | None = None
    language: Language = Language.LAD   # block-level default; networks may differ
    memory_layout: str | None = None
    memory_reserve: int | None = None   # FB only
    set_eno_automatically: bool = False
    title: str | None = None
    comment: str | None = None
    interface: Interface = field(default_factory=Interface)
    networks: list[Network] = field(default_factory=list)


@dataclass
class Document:
    engineering_version: str | None     # e.g. "V21"
    block: Block
