"""N-level connector aggregation.

Creates summary connectors at each level of the architecture tree hierarchy.
For each class-level connector, determines what boundary it crosses at every
ancestor level and creates the appropriate aggregated connector.

Since groups and sub-groups are structurally identical (just tree nodes at
different depths), aggregation is uniform: find LCA, create edge between
LCA's children, propagate up to root.
"""

from __future__ import annotations

from collections import defaultdict

from .models import ArchTree, Connector


def _child_of_ancestor(ref: str, ancestor_ref: str, tree: ArchTree) -> str | None:
    """Find the direct child of ancestor_ref that is an ancestor-of (or is) ref.

    Example: ref="class-a" under "core-settings--parser" under "core-settings" under "core".
    ancestor_ref="core" → returns "core-settings".
    ancestor_ref="core-settings" → returns "core-settings--parser".
    """
    if ref == ancestor_ref:
        return None

    current = ref
    seen: set[str] = set()
    while current != "root" and current not in seen:
        parent = tree.parent_of(current)
        if parent == ancestor_ref:
            return current
        seen.add(current)
        current = parent

    return None


def build_all_aggregations(
    class_connectors: list[Connector],
    tree: ArchTree,
) -> dict[str, list[Connector]]:
    """Build connector aggregations at every level of the tree hierarchy.

    For each class-level connector:
    1. Find the lowest common ancestor (LCA) of source and target.
    2. Create an aggregated connector between the LCA's children that contain
       source and target respectively.
    3. Propagate up: at each ancestor above LCA, create an aggregated connector
       between THAT ancestor's children containing source and target.

    This handles mixed-depth trees correctly — a connector between a deeply
    nested sub-group element and a shallow group element still produces the
    right aggregation at their common ancestor.

    Returns:
        Dict mapping view_ref → list of connectors visible in that view.
        The view_ref is the container whose children are the connector endpoints.
    """
    # Accumulate edges: view_ref → {(src_child, tgt_child): count}
    edges_by_view: dict[str, dict[tuple[str, str], int]] = defaultdict(
        lambda: defaultdict(int)
    )

    for conn in class_connectors:
        src_parent = tree.parent_of(conn.source)
        tgt_parent = tree.parent_of(conn.target)

        if src_parent == tgt_parent:
            # Same immediate parent — internal to one container, no aggregation
            continue

        # Find LCA of the two elements
        lca = tree.lowest_common_ancestor(conn.source, conn.target)

        # Walk from LCA up to root, creating aggregated edges at each level
        current_view = lca
        seen: set[str] = set()
        while current_view not in seen:
            seen.add(current_view)

            src_child = _child_of_ancestor(conn.source, current_view, tree)
            tgt_child = _child_of_ancestor(conn.target, current_view, tree)

            if src_child and tgt_child and src_child != tgt_child:
                edges_by_view[current_view][(src_child, tgt_child)] += 1

            if current_view == "root":
                break
            current_view = tree.parent_of(current_view)

    # Convert to Connector objects grouped by view
    result: dict[str, list[Connector]] = {}

    for view_ref, edges in edges_by_view.items():
        connectors: list[Connector] = []
        for (src, tgt), count in sorted(edges.items(), key=lambda x: -x[1]):
            connectors.append(
                Connector(
                    source=src,
                    target=tgt,
                    view=view_ref,
                    label=f"uses ({count})",
                    direction="forward",
                    level=view_ref,
                )
            )
        if connectors:
            result[view_ref] = connectors

    return result
