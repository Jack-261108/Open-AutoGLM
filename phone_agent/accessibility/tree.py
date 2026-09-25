"""Parse platform accessibility dumps into a short, tappable element list."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_MAX_ELEMENTS = 80
_MAX_TEXT = 80
_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_IOS_CLICKABLE = frozenset(
    {
        "Button",
        "Cell",
        "Link",
        "Switch",
        "TextField",
        "SecureTextField",
        "SearchField",
        "Slider",
        "Tab",
        "MenuItem",
        "CheckBox",
        "RadioButton",
        "Toggle",
        "PickerWheel",
        "Key",
        "Icon",
    }
)
_IOS_SCROLLABLE = frozenset(
    {"ScrollView", "Table", "CollectionView", "WebView", "TextView"}
)


@dataclass(frozen=True)
class UIElement:
    """One control the model can aim at."""

    role: str
    text: str
    bounds: tuple[int, int, int, int]
    clickable: bool = False
    scrollable: bool = False
    enabled: bool = True


@dataclass(frozen=True)
class UITree:
    """Elements plus the screen frame used to scale centers into 0–999."""

    elements: list[UIElement]
    width: int
    height: int


def format_ui_tree(tree: UITree | None) -> str:
    """Render a tree as lines whose centers use the 0–999 tap coordinate system."""
    if tree is None or tree.width <= 0 or tree.height <= 0 or not tree.elements:
        return ""

    ranked = sorted(tree.elements, key=lambda el: (_priority(el), el.bounds[1], el.bounds[0]))
    chosen = ranked[:_MAX_ELEMENTS]
    chosen.sort(key=lambda el: (el.bounds[1], el.bounds[0]))

    lines: list[str] = []
    for index, element in enumerate(chosen, start=1):
        center_x = _scale(
            (element.bounds[0] + element.bounds[2]) / 2, tree.width
        )
        center_y = _scale(
            (element.bounds[1] + element.bounds[3]) / 2, tree.height
        )
        flags: list[str] = []
        if element.clickable:
            flags.append("clickable")
        if element.scrollable:
            flags.append("scrollable")
        if not element.enabled:
            flags.append("disabled")
        flag_text = f" {' '.join(flags)}" if flags else ""
        label = element.text.replace('"', "'")
        lines.append(
            f'[{index}] {element.role} "{label}"{flag_text} '
            f"center=[{center_x},{center_y}]"
        )
    return "\n".join(lines)


def parse_android_hierarchy(raw: str) -> UITree | None:
    """Parse a `uiautomator dump` XML document."""
    root = _xml_root(raw)
    if root is None:
        return None
    screen = _xml_screen_size(root)
    if screen is None:
        return None

    elements: list[UIElement] = []

    def walk(node: ET.Element) -> None:
        bounds = _bounds_text(node.attrib.get("bounds", ""))
        if bounds is not None and _center_inside(bounds, screen):
            password = _as_bool(node.attrib.get("password"))
            text = "" if password else (node.attrib.get("text") or "").strip()
            label = text or (node.attrib.get("content-desc") or "").strip()
            enabled = _as_bool(node.attrib.get("enabled", "true"))
            clickable = _as_bool(node.attrib.get("clickable")) and enabled
            scrollable = _as_bool(node.attrib.get("scrollable"))
            if label or clickable or scrollable:
                role = (node.attrib.get("class") or "View").rsplit(".", 1)[-1]
                elements.append(
                    UIElement(
                        role=role or "View",
                        text=_clip(label),
                        bounds=bounds,
                        clickable=clickable,
                        scrollable=scrollable,
                        enabled=enabled,
                    )
                )
        for child in list(node):
            walk(child)

    walk(root)
    return _tree(elements, screen)


def parse_harmony_hierarchy(raw: str) -> UITree | None:
    """Parse a HarmonyOS `uitest dumpLayout` JSON document."""
    payload = _json_payload(raw)
    if payload is None:
        return None
    screen = _harmony_screen_size(payload)
    if screen is None:
        return None

    elements: list[UIElement] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        if "attributes" in node or "children" in node:
            attrs = node.get("attributes") or {}
            _add_harmony(attrs if isinstance(attrs, dict) else {}, elements, screen)
            walk(node.get("children") or [])
            return
        if "windows" in node:
            walk(node.get("windows") or [])
            return
        _add_harmony(node, elements, screen)
        walk(node.get("children") or [])

    walk(payload)
    return _tree(elements, screen)


def parse_ios_source(raw: str | dict | list) -> UITree | None:
    """Parse a WebDriverAgent `/source` payload, JSON or XML."""
    if isinstance(raw, (dict, list)):
        return _parse_ios_json(raw)
    text = raw.strip()
    if not text:
        return None
    if text[0] in "{[":
        payload = _json_payload(text)
        if payload is None:
            return None
        return _parse_ios_json(payload)

    root = _xml_root(text)
    if root is None:
        return None
    screen = _xml_screen_size(root)
    if screen is None:
        return None
    elements: list[UIElement] = []

    def walk(node: ET.Element) -> None:
        if not _as_bool(node.attrib.get("visible", "true")):
            return
        bounds = _ios_xml_bounds(node.attrib)
        if bounds is not None and _center_inside(bounds, screen):
            role = _ios_role(node.tag)
            enabled = _as_bool(node.attrib.get("enabled", "true"))
            secure = role == "SecureTextField"
            label = _ios_text(
                node.attrib.get("label"),
                node.attrib.get("name"),
                None if secure else node.attrib.get("value"),
            )
            clickable = role in _IOS_CLICKABLE and enabled
            scrollable = role in _IOS_SCROLLABLE
            if label or clickable or scrollable:
                elements.append(
                    UIElement(
                        role=role,
                        text=_clip(label),
                        bounds=bounds,
                        clickable=clickable,
                        scrollable=scrollable,
                        enabled=enabled,
                    )
                )
        for child in list(node):
            walk(child)

    walk(root)
    return _tree(elements, screen)


def _parse_ios_json(payload: dict | list) -> UITree | None:
    screen = _ios_json_screen_size(payload)
    if screen is None:
        return None
    elements: list[UIElement] = []

    def walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return
        value = node.get("value")
        if "rect" not in node and "children" not in node and isinstance(value, (dict, list, str)):
            if isinstance(value, str):
                parsed = parse_ios_source(value)
                if parsed is not None:
                    elements.extend(parsed.elements)
            else:
                walk(value)
            return
        if not _as_bool(node.get("visible", True)):
            return
        bounds = _ios_json_bounds(node.get("rect"))
        if bounds is not None and _center_inside(bounds, screen):
            role = _ios_role(str(node.get("type") or "Element"))
            enabled = _as_bool(node.get("enabled", True))
            secure = role == "SecureTextField"
            label = _ios_text(
                node.get("label"),
                node.get("name"),
                None if secure or isinstance(node.get("value"), bool) else node.get("value"),
            )
            clickable = role in _IOS_CLICKABLE and enabled
            scrollable = role in _IOS_SCROLLABLE
            if label or clickable or scrollable:
                elements.append(
                    UIElement(
                        role=role,
                        text=_clip(label),
                        bounds=bounds,
                        clickable=clickable,
                        scrollable=scrollable,
                        enabled=enabled,
                    )
                )
        walk(node.get("children") or [])

    walk(payload)
    return _tree(elements, screen)


def _add_harmony(
    attrs: dict, elements: list[UIElement], screen: tuple[int, int]
) -> None:
    if not _as_bool(attrs.get("visible", True)):
        return
    bounds = _harmony_bounds(attrs.get("bounds") or attrs.get("origBounds"))
    if bounds is None or not _center_inside(bounds, screen):
        return
    role = str(attrs.get("type") or "View")
    enabled = _as_bool(attrs.get("enabled", True))
    password = _as_bool(attrs.get("password")) or "password" in role.lower()
    text = "" if password else str(attrs.get("text") or "").strip()
    label = text or str(attrs.get("description") or "").strip()
    if not label:
        label = str(attrs.get("hint") or "").strip()
    clickable = _as_bool(attrs.get("clickable")) and enabled
    scrollable = _as_bool(attrs.get("scrollable"))
    if not (label or clickable or scrollable):
        return
    elements.append(
        UIElement(
            role=role or "View",
            text=_clip(label),
            bounds=bounds,
            clickable=clickable,
            scrollable=scrollable,
            enabled=enabled,
        )
    )


def _tree(elements: list[UIElement], screen: tuple[int, int] | None) -> UITree | None:
    if screen is None or screen[0] <= 0 or screen[1] <= 0:
        return None
    return UITree(elements=elements, width=screen[0], height=screen[1])


def _center_inside(bounds: tuple[int, int, int, int], screen: tuple[int, int]) -> bool:
    center_x = (bounds[0] + bounds[2]) / 2
    center_y = (bounds[1] + bounds[3]) / 2
    return 0 <= center_x <= screen[0] and 0 <= center_y <= screen[1]


def _ios_text(label: object, name: object, value: object) -> str:
    """Prefer the visible label. WDA `name` is an identifier when one is set."""
    text = str(label or "").strip() or str(name or "").strip()
    if text or value is None:
        return text
    return str(value).strip()


def _xml_screen_size(root: ET.Element) -> tuple[int, int] | None:
    """Screen size from the root, or the union of the first level that has bounds."""
    own = _xml_node_bounds(root)
    if own is not None:
        return own[2], own[3]
    level = list(root)
    while level:
        frame = [0, 0]
        found = False
        next_level: list[ET.Element] = []
        for node in level:
            bounds = _xml_node_bounds(node)
            if bounds is None:
                next_level.extend(list(node))
                continue
            _grow(frame, bounds)
            found = True
        if found:
            if frame[0] <= 0 or frame[1] <= 0:
                return None
            return frame[0], frame[1]
        level = next_level
    return None


def _xml_node_bounds(node: ET.Element) -> tuple[int, int, int, int] | None:
    if "bounds" in node.attrib:
        return _bounds_text(node.attrib.get("bounds", ""))
    if "width" in node.attrib and "height" in node.attrib:
        return _ios_xml_bounds(node.attrib)
    return None


def _harmony_screen_size(node: object) -> tuple[int, int] | None:
    if (
        isinstance(node, dict)
        and _harmony_own_bounds(node) is None
        and isinstance(node.get("windows"), list)
    ):
        return _harmony_screen_size(node.get("windows"))
    if isinstance(node, list):
        frame = [0, 0]
        found = False
        for item in node:
            bounds = _harmony_own_bounds(item)
            if bounds is None:
                continue
            _grow(frame, bounds)
            found = True
        if found:
            if frame[0] <= 0 or frame[1] <= 0:
                return None
            return frame[0], frame[1]
        for item in node:
            size = _harmony_screen_size(item)
            if size is not None:
                return size
        return None
    bounds = _harmony_own_bounds(node)
    if bounds is not None:
        return bounds[2], bounds[3]
    if isinstance(node, dict) and isinstance(node.get("children"), list):
        return _harmony_screen_size(node.get("children"))
    return None


def _harmony_own_bounds(node: object) -> tuple[int, int, int, int] | None:
    if not isinstance(node, dict):
        return None
    attrs = node.get("attributes")
    if isinstance(attrs, dict):
        bounds = _harmony_bounds(attrs.get("bounds") or attrs.get("origBounds"))
        if bounds is not None:
            return bounds
    return _harmony_bounds(node.get("bounds") or node.get("origBounds"))


def _ios_json_screen_size(node: object) -> tuple[int, int] | None:
    if isinstance(node, str):
        parsed = parse_ios_source(node)
        if parsed is None:
            return None
        return parsed.width, parsed.height
    if isinstance(node, list):
        frame = [0, 0]
        found = False
        for item in node:
            if not isinstance(item, dict):
                continue
            bounds = _ios_json_bounds(item.get("rect"))
            if bounds is None:
                continue
            _grow(frame, bounds)
            found = True
        if not found or frame[0] <= 0 or frame[1] <= 0:
            return None
        return frame[0], frame[1]
    if not isinstance(node, dict):
        return None
    bounds = _ios_json_bounds(node.get("rect"))
    if bounds is not None:
        return bounds[2], bounds[3]
    value = node.get("value")
    if isinstance(value, (dict, list, str)):
        return _ios_json_screen_size(value)
    children = node.get("children")
    if isinstance(children, list):
        return _ios_json_screen_size(children)
    return None


def _priority(element: UIElement) -> int:
    if element.clickable and element.text:
        return 0
    if element.scrollable and element.text:
        return 1
    if element.clickable or element.scrollable:
        return 2
    return 3


def _scale(value: float, size: int) -> int:
    scaled = int(value / size * 1000)
    return min(999, max(0, scaled))


def _clip(text: str) -> str:
    compact = " ".join(text.split())
    if len(compact) <= _MAX_TEXT:
        return compact
    return compact[: _MAX_TEXT - 3] + "..."


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _grow(frame: list[int], bounds: tuple[int, int, int, int]) -> None:
    frame[0] = max(frame[0], bounds[2])
    frame[1] = max(frame[1], bounds[3])


def _bounds_text(raw: str) -> tuple[int, int, int, int] | None:
    match = _BOUNDS.search(raw)
    if match is None:
        return None
    left, top, right, bottom = (int(part) for part in match.groups())
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _harmony_bounds(raw: object) -> tuple[int, int, int, int] | None:
    if isinstance(raw, str):
        return _bounds_text(raw)
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        left, top, right, bottom = (int(part) for part in raw)
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom
    return None


def _ios_xml_bounds(attribs: dict[str, str]) -> tuple[int, int, int, int] | None:
    try:
        left = int(float(attribs["x"]))
        top = int(float(attribs["y"]))
        right = left + int(float(attribs["width"]))
        bottom = top + int(float(attribs["height"]))
    except (KeyError, TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _ios_json_bounds(raw: object) -> tuple[int, int, int, int] | None:
    if not isinstance(raw, dict):
        return None
    try:
        left = int(float(raw["x"]))
        top = int(float(raw["y"]))
        right = left + int(float(raw["width"]))
        bottom = top + int(float(raw["height"]))
    except (KeyError, TypeError, ValueError):
        return None
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _ios_role(type_name: str) -> str:
    name = type_name.rsplit(".", 1)[-1]
    prefix = "XCUIElementType"
    if name.startswith(prefix):
        return name[len(prefix) :] or "Element"
    return name or "Element"


def _xml_root(raw: str) -> ET.Element | None:
    text = raw.strip()
    start = text.find("<")
    if start < 0:
        return None
    try:
        return ET.fromstring(text[start:])
    except ET.ParseError:
        return None


def _json_payload(raw: str) -> dict | list | None:
    text = raw.strip()
    start_obj = text.find("{")
    start_list = text.find("[")
    starts = [pos for pos in (start_obj, start_list) if pos >= 0]
    if not starts:
        return None
    try:
        payload = json.loads(text[min(starts) :])
    except json.JSONDecodeError:
        return None
    if isinstance(payload, (dict, list)):
        return payload
    return None
