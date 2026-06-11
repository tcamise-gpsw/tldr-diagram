"""Connector processing: remapping, deduplication, and view scoping.

Handles deduplication of tree-sitter-discovered connectors, remapping of nested
classes to their parent, and view scoping for the tld workspace.
"""

from __future__ import annotations

from collections import defaultdict

from .models import ArchTree, Connector, Element


def build_element_remap(
    raw_elements: dict, retained_keys: set[str]
) -> dict[str, str]:
    """Build a mapping from non-retained elements to their nearest retained class.

    For functions, methods, files, constructors, and nested classes: maps them to
    the primary class/interface in the same file. This allows connectors referencing
    non-retained elements to be remapped.
    """
    # Build file_path → retained element keys index
    retained_by_file: dict[str, list[str]] = defaultdict(list)
    for key, elem in raw_elements.items():
        if key in retained_keys:
            fp = elem.get("file_path", "")
            if fp:
                retained_by_file[fp].append(key)

    remap: dict[str, str] = {}

    for key, elem in raw_elements.items():
        if key in retained_keys:
            remap[key] = key  # Identity mapping for retained elements
            continue

        kind = elem.get("kind", "")
        name = elem.get("name", "")

        # Remappable: functions, methods, files, constructors, and nested classes
        is_nested_class = kind in ("class", "interface") and "." in name
        if kind not in ("function", "method", "file", "constructor") and not is_nested_class:
            continue

        file_path = elem.get("file_path", "")
        if not file_path:
            continue

        # Find retained elements in the same file
        candidates = retained_by_file.get(file_path, [])
        if len(candidates) == 1:
            remap[key] = candidates[0]
        elif len(candidates) > 1:
            # Prefer element whose name matches the filename
            filename = file_path.rsplit("/", 1)[-1].replace(".kt", "").lower()
            for c in candidates:
                if raw_elements[c]["name"].lower() == filename:
                    remap[key] = c
                    break
            else:
                remap[key] = candidates[0]  # Fall back to first
        # else: no candidates, key stays unmapped (connector will be dropped)

    return remap


def process_connectors(
    raw_connectors: list[dict],
    tree: ArchTree,
    element_remap: dict[str, str],
) -> list[Connector]:
    """Filter and re-scope connectors to class level.

    Remaps connector endpoints from functions/methods/files to their containing class.
    Keeps connectors where both remapped endpoints are retained elements.
    Scopes each connector's view to its source element's immediate parent group.
    """
    retained_keys = set(tree.elements.keys())
    output: list[Connector] = []
    seen_pairs: set[tuple[str, str]] = set()

    for conn in raw_connectors:
        source = conn.get("source", "")
        target = conn.get("target", "")

        # Remap endpoints to their class representative
        source = element_remap.get(source, source)
        target = element_remap.get(target, target)

        # Both endpoints must be retained
        if source not in retained_keys or target not in retained_keys:
            continue

        # Skip self-references
        if source == target:
            continue

        # Deduplicate (same source→target pair)
        pair = (source, target)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)

        # Determine view scope: if both in same group, use that group.
        # If different groups, use the source's parent group view.
        source_parent = tree.elements[source].parent_ref
        target_parent = tree.elements[target].parent_ref

        if source_parent == target_parent:
            view = source_parent
        else:
            # Cross-group: scope to source group's view (where the caller lives)
            view = source_parent

        output.append(Connector(
            source=source,
            target=target,
            view=view,
            label=conn.get("label", ""),
            direction=conn.get("direction", "forward"),
            style=conn.get("style", "smoothstep"),
            relationship=conn.get("relationship", ""),
            id=conn.get("id", ""),
            level="class",
        ))

    return output
