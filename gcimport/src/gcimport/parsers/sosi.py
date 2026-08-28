"""Parse SOSI text into a lightweight tree structure."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class SosiInlineAttribute:
    """An inline attribute attached to a coordinate record."""

    name: str
    value: str | None = None


@dataclass(slots=True)
class SosiCoordinate:
    """A coordinate record that belongs to the preceding SOSI key."""

    values: tuple[int | float, ...]
    attributes: list[SosiInlineAttribute] = field(default_factory=list)
    source_line: int = 0


type SosiChild = SosiNode | SosiCoordinate


@dataclass(slots=True)
class SosiNode:
    """A hierarchical SOSI record such as ``KURVE`` or ``IDENT``."""

    name: str
    value: str | None = None
    children: list[SosiChild] = field(default_factory=list)
    source_line: int = 0


@dataclass(slots=True)
class SosiTree:
    """Parsed SOSI document root."""

    header: SosiNode | None = None
    footer: SosiNode | None = None
    children: list[SosiNode] = field(default_factory=list)


class SosiParseError(ValueError):
    """Raised when SOSI input cannot be parsed into a tree."""


@dataclass(slots=True)
class SosiStats:
    """Structural counters derived from a parsed SOSI tree."""

    has_header: bool
    has_footer: bool
    total_objects: int
    object_types: dict[str, int]
    objtypes: dict[str, int]
    coordinate_records: int
    coordinate_attribute_counts: dict[str, int]


def parse_text(text: str) -> SosiTree:
    """Parse SOSI text into a generic tree.

    The parser is intentionally structural only: it preserves directive nesting,
    repeated sections, coordinate records, and inline attributes such as
    ``...KP 1``. It does not attempt to emit or transform SOSI semantics.
    """

    text = text.removeprefix("\ufeff")
    tree = SosiTree()
    stack: list[SosiTree | SosiNode] = [tree]

    for source_line, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("."):
            depth = _directive_depth(line)
            if depth > len(stack):
                raise SosiParseError(
                    f"line {source_line}: invalid nesting depth {depth}"
                )

            while len(stack) > depth:
                stack.pop()

            node = _parse_node(line[depth:].strip(), source_line)
            _attach_node(tree, stack[-1], node, depth=depth, source_line=source_line)
            stack.append(node)
            continue

        if len(stack) == 1:
            raise SosiParseError(
                f"line {source_line}: coordinate record without a parent key"
            )

        _attach_record(stack[-1], line, source_line)

    return tree


def parse_file(path: str | Path, *, encoding: str = "utf-8") -> SosiTree:
    """Read and parse a SOSI file from disk."""

    return parse_text(Path(path).read_text(encoding=encoding))


def summarize_tree(tree: SosiTree) -> SosiStats:
    """Collect high-level structural stats from a parsed SOSI tree."""

    object_types: Counter[str] = Counter()
    objtypes: Counter[str] = Counter()
    coordinate_attribute_counts: Counter[str] = Counter()
    coordinate_records = 0

    for child in tree.children:
        object_types[child.name] += 1

        objtype = _direct_child_value(child, "OBJTYPE")
        if objtype is not None:
            objtypes[objtype] += 1

        for coordinate in _iter_coordinates(child):
            coordinate_records += 1
            for attribute in coordinate.attributes:
                coordinate_attribute_counts[attribute.name] += 1

    return SosiStats(
        has_header=tree.header is not None,
        has_footer=tree.footer is not None,
        total_objects=len(tree.children),
        object_types=dict(object_types),
        objtypes=dict(objtypes),
        coordinate_records=coordinate_records,
        coordinate_attribute_counts=dict(coordinate_attribute_counts),
    )


def _directive_depth(line: str) -> int:
    depth = 0
    for character in line:
        if character != ".":
            break
        depth += 1
    return depth


def _parse_node(payload: str, source_line: int) -> SosiNode:
    if not payload:
        raise SosiParseError(f"line {source_line}: empty SOSI directive")

    normalized_payload = payload.removesuffix(":")
    name, _, remainder = normalized_payload.partition(" ")
    value = remainder.strip() or None
    return SosiNode(name=name, value=value, source_line=source_line)


def _parse_coordinate(payload: str, source_line: int) -> SosiCoordinate:
    segments = [segment.strip() for segment in payload.split("...")]
    values_segment = segments[0]
    if not values_segment:
        raise SosiParseError(f"line {source_line}: missing coordinate values")

    values = tuple(
        _parse_number(token, source_line) for token in values_segment.split()
    )
    attributes = [
        _parse_inline_attribute(segment, source_line)
        for segment in segments[1:]
        if segment
    ]
    return SosiCoordinate(
        values=values,
        attributes=attributes,
        source_line=source_line,
    )


def _parse_inline_attribute(payload: str, source_line: int) -> SosiInlineAttribute:
    name, _, remainder = payload.partition(" ")
    if not name:
        raise SosiParseError(f"line {source_line}: empty coordinate attribute")
    value = remainder.strip() or None
    return SosiInlineAttribute(name=name, value=value)


def _attach_node(
    tree: SosiTree,
    parent: SosiTree | SosiNode,
    node: SosiNode,
    *,
    depth: int,
    source_line: int,
) -> None:
    if depth != 1 or node.name not in {"HODE", "SLUTT"}:
        parent.children.append(node)
        return

    if node.name == "HODE":
        if tree.header is not None:
            raise SosiParseError(f"line {source_line}: duplicate SOSI header")
        tree.header = node
        return

    if tree.footer is not None:
        raise SosiParseError(f"line {source_line}: duplicate SOSI footer")
    tree.footer = node


def _attach_record(node: SosiNode, payload: str, source_line: int) -> None:
    if _looks_like_coordinate_payload(payload):
        node.children.append(_parse_coordinate(payload, source_line))
        return
    _append_continuation(node, payload)


def _looks_like_coordinate_payload(payload: str) -> bool:
    values_segment = payload.split("...", maxsplit=1)[0].strip()
    if not values_segment:
        return False
    first_token, *_ = values_segment.split()
    return first_token[:1] in {"-", "+"} or first_token[:1].isdigit()


def _append_continuation(node: SosiNode, payload: str) -> None:
    node.value = payload if node.value is None else f"{node.value} {payload}"


def _parse_number(token: str, source_line: int) -> int | float:
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError as err:
            raise SosiParseError(
                f"line {source_line}: invalid coordinate value {token!r}"
            ) from err


def _direct_child_value(node: SosiNode, name: str) -> str | None:
    for child in node.children:
        if isinstance(child, SosiNode) and child.name == name:
            return child.value
    return None


def _iter_coordinates(node: SosiNode) -> list[SosiCoordinate]:
    coordinates: list[SosiCoordinate] = []
    for child in node.children:
        if isinstance(child, SosiCoordinate):
            coordinates.append(child)
            continue
        coordinates.extend(_iter_coordinates(child))
    return coordinates
