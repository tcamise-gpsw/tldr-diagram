"""Element classification: extract package paths and route to groups.

Handles the mapping from raw tld file paths to (module, package_path)
pairs and the rule-based routing into architecture groups.
"""

from __future__ import annotations

from .models import ArchTree, Element, Rule

# Kinds to retain as leaf elements in the output
RETAINED_KINDS = {"class", "interface"}


def extract_package_path(file_path: str, source_prefix: str, package_marker: str) -> tuple[str, str] | None:
    """Extract (module, package_path) from a file_path.

    Args:
        file_path: Raw file path from tld analyze output.
        source_prefix: Path prefix to strip to reach the module root (e.g. "katalyst-connect/sdk/").
        package_marker: Sub-path marker delimiting the architecture-relevant package (e.g. "/com/gopro/katalyst/connect/").

    Returns:
        (module, package_path) tuple, or None if the path doesn't match.
    """
    if not file_path.startswith(source_prefix):
        return None

    rest = file_path[len(source_prefix):]
    # Module is the first path segment
    parts = rest.split("/", 1)
    if len(parts) < 2:
        return None
    module = parts[0]

    # Find the package path after the marker
    idx = rest.find(package_marker)
    if idx < 0:
        return None

    # Package path is everything after the marker, minus the filename
    after_marker = rest[idx + len(package_marker):]
    pkg_parts = after_marker.rsplit("/", 1)
    package_path = pkg_parts[0] if len(pkg_parts) > 1 else ""

    return module, package_path


def classify_element(
    module: str, package_path: str, rules: list[Rule]
) -> tuple[str | None, bool]:
    """Find the group_ref for a given module + package path.

    Returns:
        (group_ref, is_catch_all) where is_catch_all is True if the matched
        rule's prefix has no '/' (bare module root like 'core', 'domain').
    """
    for rule in rules:
        if rule.module == module and package_path.startswith(rule.prefix):
            return rule.group, rule.is_catch_all
    return None, False


def classify_raw_elements(
    raw_elements: dict, tree: ArchTree
) -> tuple[list[Element], list[tuple[str, str, str]], list[tuple[str, str, str, str]]]:
    """Classify raw analyze elements into the architecture tree.

    Returns:
        (elements, unmapped, catch_all_routed) where:
        - elements: list of classified Element instances
        - unmapped: list of (class_name, module, package_path) with no matching rule
        - catch_all_routed: list of (class_name, module, package_path, group) that
          matched only a bare catch-all rule
    """
    elements: list[Element] = []
    unmapped: list[tuple[str, str, str]] = []
    catch_all_routed: list[tuple[str, str, str, str]] = []

    for key, elem in raw_elements.items():
        kind = elem.get("kind", "")
        if kind not in RETAINED_KINDS:
            continue

        # Skip nested/inner classes (e.g., "FlatModeIdentifier.Defined")
        name = elem.get("name", "")
        if "." in name:
            continue

        file_path = elem.get("file_path", "")
        extracted = extract_package_path(file_path, tree.source_prefix, tree.package_marker)
        if extracted is None:
            continue

        module, package_path = extracted
        group_ref, is_catch_all = classify_element(module, package_path, tree.rules)

        if group_ref is None:
            unmapped.append((elem.get("name", key), module, package_path))
            continue

        if is_catch_all:
            catch_all_routed.append(
                (elem.get("name", key), module, package_path, group_ref)
            )

        element = Element(
            key=key,
            name=elem["name"],
            kind=kind,
            file_path=file_path,
            package_path=package_path,
            module=module,
            parent_ref=group_ref,
            tags=elem.get("tags", []),
        )
        elements.append(element)

    return elements, unmapped, catch_all_routed
