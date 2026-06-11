"""Auto-split oversized groups by package path segment.

When a group exceeds the configured max_group_size, this module splits it
into sub-groups based on the next differentiating package path segment.
The splitting is recursive — sub-groups that still exceed the limit get
split further until all leaf groups are within bounds.

This produces the N-level nesting that makes large codebases navigable.
"""

from __future__ import annotations

from collections import defaultdict

from .models import ArchTree, Element, GroupNode


def _compute_relative_path(element: Element, group: GroupNode, tree: ArchTree) -> str:
    """Compute the package path segment relative to the group's routing rule.

    For a group matched by prefix "core/domain/camera/setting" and an element
    with package_path "core/domain/camera/setting/parser/legacy", returns
    "parser/legacy".

    For auto-generated sub-groups, walks up to the original rule-defined
    ancestor, computes the full relative path, then strips segments that
    correspond to intermediate auto-generated parents.
    """
    # Walk up to find the original rule-defined group
    ancestor_ref = group.ref
    segments_to_strip: list[str] = []
    while ancestor_ref in tree.groups and tree.groups[ancestor_ref].is_auto_generated:
        # Extract the segment from the ref (parent--segment convention)
        parts = ancestor_ref.rsplit("--", 1)
        if len(parts) == 2 and parts[1] != "root":
            segments_to_strip.insert(0, parts[1])
        ancestor_ref = tree.groups[ancestor_ref].parent_ref

    # Find the rule that routed to the ancestor group
    for rule in tree.rules:
        if rule.group == ancestor_ref and rule.module == element.module:
            if element.package_path.startswith(rule.prefix):
                relative = element.package_path[len(rule.prefix):].lstrip("/")
                # Strip intermediate segments from auto-generated parents
                strip_prefix = "/".join(segments_to_strip)
                if strip_prefix and relative.startswith(strip_prefix):
                    relative = relative[len(strip_prefix):].lstrip("/")
                return relative

    # Fallback: use the full package path (shouldn't happen with valid config)
    return element.package_path


def _next_segment(relative_path: str) -> str:
    """Extract the first path segment from a relative path.

    "parser/legacy" → "parser"
    "parser" → "parser"
    "" → ""
    """
    if not relative_path:
        return ""
    return relative_path.split("/", 1)[0]


def _generate_sub_group_name(segment: str, parent_name: str) -> str:
    """Generate a human-readable name for an auto-generated sub-group.

    Capitalizes the segment and uses it as the sub-group name.
    "parser" → "Parser"
    "cache" → "Cache"
    """
    if not segment:
        return f"{parent_name} (root)"
    # Title-case each word, replace hyphens/underscores with spaces
    words = segment.replace("-", " ").replace("_", " ").split()
    return " ".join(w.capitalize() for w in words)


def _generate_sub_group_ref(segment: str, parent_ref: str) -> str:
    """Generate a unique ref for an auto-generated sub-group.

    "parser" under "core-settings" → "core-settings--parser"
    """
    if not segment:
        return f"{parent_ref}--root"
    return f"{parent_ref}--{segment}"


def split_oversized_group(
    group_ref: str,
    tree: ArchTree,
) -> list[GroupNode]:
    """Split a single oversized group into sub-groups by next package segment.

    Elements with no further path segments (at the group's root package)
    remain directly under the original group. Elements with a common next
    segment are grouped together under a new sub-group.

    Returns:
        List of newly created GroupNode instances (empty if no split needed).
    """
    group = tree.groups[group_ref]

    # Gather elements directly under this group
    child_elements = [
        elem for elem in tree.elements.values()
        if elem.parent_ref == group_ref
    ]

    if len(child_elements) <= tree.max_group_size:
        return []  # No split needed

    # Bucket elements by their next path segment
    buckets: dict[str, list[Element]] = defaultdict(list)
    for elem in child_elements:
        relative = _compute_relative_path(elem, group, tree)
        segment = _next_segment(relative)
        buckets[segment].append(elem)

    # Only split if we actually get multiple buckets
    # (if everything is in one bucket, splitting won't help)
    non_empty_buckets = {k: v for k, v in buckets.items() if k}
    if len(non_empty_buckets) <= 1:
        return []  # Can't meaningfully split

    # Create sub-groups for buckets that have enough elements to justify isolation
    # Small buckets (1-2 elements) stay in the parent group to avoid noise
    MIN_BUCKET_SIZE = 2
    new_groups: list[GroupNode] = []

    for segment, elements in sorted(non_empty_buckets.items()):
        if len(elements) < MIN_BUCKET_SIZE:
            continue  # Too small to justify its own sub-group

        sub_ref = _generate_sub_group_ref(segment, group_ref)
        sub_name = _generate_sub_group_name(segment, group.name)

        sub_group = GroupNode(
            ref=sub_ref,
            name=sub_name,
            description=f"Auto-grouped from {group.name} by package segment '{segment}'.",
            parent_ref=group_ref,
            is_auto_generated=True,
        )
        new_groups.append(sub_group)

        # Re-parent elements to the new sub-group
        for elem in elements:
            elem.parent_ref = sub_ref

        # Register in tree
        tree.groups[sub_ref] = sub_group

    return new_groups


def split_all_oversized(tree: ArchTree) -> list[GroupNode]:
    """Recursively split all oversized groups in the tree.

    Processes groups from deepest to shallowest, then recurses on
    newly created sub-groups until all leaf groups are within bounds.

    Returns:
        All newly created GroupNode instances across all splits.
    """
    all_new: list[GroupNode] = []
    max_iterations = 20  # Safety valve against infinite recursion

    for _ in range(max_iterations):
        # Find groups that exceed the limit (process deepest first)
        oversized = []
        for ref, group in list(tree.groups.items()):
            child_count = sum(
                1 for e in tree.elements.values() if e.parent_ref == ref
            )
            group.element_count = child_count
            if child_count > tree.max_group_size:
                oversized.append((tree.depth_of(ref), ref))

        if not oversized:
            break  # All groups within bounds

        # Process deepest first (so parent splits use already-split children)
        oversized.sort(key=lambda x: -x[0])

        round_new: list[GroupNode] = []
        for _depth, ref in oversized:
            created = split_oversized_group(ref, tree)
            round_new.extend(created)

        if not round_new:
            break  # No further splitting possible (all at leaf segments)

        all_new.extend(round_new)

    return all_new
