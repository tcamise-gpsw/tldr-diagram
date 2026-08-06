"""Pipeline orchestration: the full post-processing flow.

Each step is a pure function operating on the ArchTree. The pipeline
coordinates: analyze → classify → split → connect → aggregate → write.

Uses tree-sitter to analyze Kotlin sources directly (no tld analyze step needed).
"""

from __future__ import annotations

import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .aggregation import build_all_aggregations
from .classifier import classify_raw_elements
from .config import load_config
from .connectors import build_element_remap, process_connectors
from .kotlin_analyzer import analyze_sources
from .models import ArchTree, Connector
from .splitting import split_all_oversized


@dataclass
class PipelineResult:
    """Results from the full pipeline run."""

    tree: ArchTree
    class_connectors: list[Connector] = field(default_factory=list)
    aggregated_connectors: dict[str, list[Connector]] = field(default_factory=dict)
    unmapped: list[tuple[str, str, str]] = field(default_factory=list)
    catch_all_routed: list[tuple[str, str, str, str]] = field(default_factory=list)
    auto_split_groups: int = 0

    # Stats
    raw_element_count: int = 0
    raw_connector_count: int = 0
    kind_counts: dict[str, int] = field(default_factory=dict)
    isolated_count: int = 0



def apply_connectivity_filter(tree: ArchTree, class_connectors: list[Connector]) -> int:
    """Remove elements that don't participate in any connector.

    Returns the number of isolated elements removed.
    """
    connected_keys: set[str] = set()
    for conn in class_connectors:
        connected_keys.add(conn.source)
        connected_keys.add(conn.target)

    isolated_keys = [
        key for key, elem in tree.elements.items()
        if key not in connected_keys
    ]

    for key in isolated_keys:
        del tree.elements[key]

    return len(isolated_keys)


def update_group_descriptions(tree: ArchTree, total_before_filter: dict[str, int]) -> None:
    """Update group descriptions with class count annotations."""
    # Count shown elements per group
    shown_per_group: dict[str, int] = defaultdict(int)
    for elem in tree.elements.values():
        shown_per_group[elem.parent_ref] += 1

    for ref, group in tree.groups.items():
        total = total_before_filter.get(ref, 0)
        shown = shown_per_group.get(ref, 0)
        if total > 0 and shown < total:
            group.description = (
                f"{group.description} [{shown} of {total} classes shown"
                " — others have no cross-class connectors]"
            )
        elif total > 0:
            group.description = f"{group.description} [{total} classes]"


def run_pipeline(
    input_dir: Path,
    source_root: Path,
    repo_root: Path,
    max_group_size: int | None = None,
    all_classes: bool = False,
    exclude_patterns: list[str] | None = None,
) -> PipelineResult:
    """Execute the full post-processing pipeline.

    Args:
        input_dir: Directory containing groups.yaml.
        source_root: Kotlin source directory to analyze with tree-sitter.
        repo_root: Repository root for relative path computation.
        max_group_size: Override for auto-split threshold (None = use config default).
        all_classes: If True, skip connectivity filter.
        exclude_patterns: Glob patterns for source exclusion.

    Returns:
        PipelineResult with the processed tree and all connectors.
    """
    result = PipelineResult(tree=ArchTree())

    # --- Load config ---
    tree = load_config(input_dir / "groups.yaml")
    if max_group_size is not None:
        tree.max_group_size = max_group_size
    result.tree = tree

    # --- Analyze Kotlin sources with tree-sitter ---
    print(f"Analyzing Kotlin sources in {source_root}...")
    analysis = analyze_sources(repo_root, source_root, exclude_patterns)
    raw_elements = analysis.raw_elements
    raw_connectors = analysis.raw_connectors
    print(f"  Tree-sitter: {analysis.stats['files_scanned']} files → "
          f"{analysis.stats['total_elements']} elements, "
          f"{analysis.stats['total_connectors']} connectors")

    result.raw_element_count = len(raw_elements)
    result.raw_connector_count = len(raw_connectors)

    # Count by kind
    for elem in raw_elements.values():
        kind = elem.get("kind", "unknown")
        result.kind_counts[kind] = result.kind_counts.get(kind, 0) + 1

    print(f"\nRaw input: {len(raw_elements)} elements, {len(raw_connectors)} connectors")
    print(f"  Element kinds: {result.kind_counts}")

    # --- Classify elements ---
    elements, unmapped, catch_all_routed = classify_raw_elements(raw_elements, tree)
    result.unmapped = unmapped
    result.catch_all_routed = catch_all_routed

    # Register elements in tree
    for elem in elements:
        tree.elements[elem.key] = elem

    # --- Auto-split oversized groups ---
    if tree.max_group_size > 0:
        new_groups = split_all_oversized(tree)
        result.auto_split_groups = len(new_groups)
        if new_groups:
            print(f"\n  Auto-split: created {len(new_groups)} sub-groups (max_size={tree.max_group_size})")
            for g in new_groups:
                child_count = sum(1 for e in tree.elements.values() if e.parent_ref == g.ref)
                print(f"    {g.ref}: {g.name} ({child_count} classes)")

    # Warn about group overrides that matched no generated group.
    unused_overrides = [ref for ref in tree.group_overrides if ref not in tree.groups]
    if unused_overrides:
        print(f"\n  ⚠ {len(unused_overrides)} group override(s) matched no generated group:")
        for ref in sorted(unused_overrides):
            print(f"      {ref}")

    # --- Process connectors ---
    retained_keys = set(tree.elements.keys())
    element_remap = build_element_remap(raw_elements, retained_keys)
    class_connectors = process_connectors(raw_connectors, tree, element_remap)
    result.class_connectors = class_connectors

    # --- Connectivity filter ---
    if not all_classes:
        # Count totals per group BEFORE filtering
        total_per_group: dict[str, int] = defaultdict(int)
        for elem in tree.elements.values():
            total_per_group[elem.parent_ref] += 1

        isolated = apply_connectivity_filter(tree, class_connectors)
        result.isolated_count = isolated

        update_group_descriptions(tree, total_per_group)
        print(f"\n  Connectivity filter: removed {isolated} isolated classes")

    # --- Aggregate connectors at all levels ---
    result.aggregated_connectors = build_all_aggregations(class_connectors, tree)

    # --- Stats ---
    container_count = len(tree.modules) + len(tree.groups)
    class_count = len(tree.elements)
    print(f"\nOutput: {container_count + class_count} elements "
          f"({container_count} containers + {class_count} classes)")
    print(f"  Class-level connectors: {len(class_connectors)}")
    agg_total = sum(len(conns) for conns in result.aggregated_connectors.values())
    print(f"  Aggregated connectors: {agg_total} across {len(result.aggregated_connectors)} views")

    # Group distribution
    group_sizes: dict[str, int] = defaultdict(int)
    for elem in tree.elements.values():
        group_sizes[elem.parent_ref] += 1
    print("\n  Group sizes:")
    for ref, size in sorted(group_sizes.items(), key=lambda x: -x[1]):
        print(f"    {ref}: {size} classes")

    # Top aggregated connectors at root view
    if "root" in result.aggregated_connectors:
        print(f"\n  Root-level (module) connectors:")
        for conn in result.aggregated_connectors["root"][:15]:
            print(f"    {conn.source} → {conn.target} ({conn.label})")

    # Top aggregated connectors at module views
    for mod_ref in sorted(tree.modules.keys()):
        if mod_ref in result.aggregated_connectors:
            print(f"\n  {mod_ref} view connectors:")
            for conn in result.aggregated_connectors[mod_ref][:10]:
                print(f"    {conn.source} → {conn.target} ({conn.label})")

    # Unmapped / catch-all reports
    if unmapped:
        print(f"\n  ⚠ Unmapped classes ({len(unmapped)} — no matching rule):")
        by_module: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for name, mod, pkg in unmapped:
            by_module[mod].append((name, pkg))
        for mod in sorted(by_module):
            print(f"    [{mod}] ({len(by_module[mod])})")
            for name, pkg in sorted(by_module[mod], key=lambda x: x[1])[:10]:
                print(f"      {pkg}  ({name})")
            remaining = len(by_module[mod]) - 10
            if remaining > 0:
                print(f"      ... and {remaining} more")

    if catch_all_routed:
        print(f"\n  ℹ Catch-all routed classes ({len(catch_all_routed)} — matched bare module prefix):")
        by_group: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for name, _mod, pkg, grp in catch_all_routed:
            by_group[grp].append((name, pkg))
        for grp in sorted(by_group):
            print(f"    [{grp}] ({len(by_group[grp])})")
            for name, pkg in sorted(by_group[grp], key=lambda x: x[1])[:10]:
                print(f"      {pkg}  ({name})")
            remaining = len(by_group[grp]) - 10
            if remaining > 0:
                print(f"      ... and {remaining} more")

    return result


# ---------------------------------------------------------------------------
# YAML Output
# ---------------------------------------------------------------------------


def _write_yaml(data, path: Path) -> None:
    """Write YAML with clean formatting."""
    class CleanDumper(yaml.SafeDumper):
        pass

    CleanDumper.ignore_aliases = lambda self, data: True

    with open(path, "w") as f:
        yaml.dump(
            data,
            f,
            Dumper=CleanDumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )


def serialize_tree(result: PipelineResult) -> tuple[dict, list[dict]]:
    """Serialize the ArchTree into tld-compatible YAML structures.

    Returns:
        (elements_dict, connectors_list) ready for YAML output.
    """
    tree = result.tree
    elements: dict[str, dict] = {}

    # Modules
    for ref, mod in tree.modules.items():
        elements[ref] = {
            "name": mod.name,
            "kind": "component",
            "summary": mod.summary,
            "description": mod.description,
            "technology": "kotlin",
            "has_view": True,
            "placements": [{"parent": "root"}],
        }

    # Groups (including auto-generated sub-groups)
    for ref, group in tree.groups.items():
        # Determine if this group has any visible content
        has_children = any(
            e.parent_ref == ref for e in tree.elements.values()
        ) or any(
            g.parent_ref == ref for g in tree.groups.values()
        )

        entry = {
            "name": group.name,
            "kind": "component",
            "summary": group.summary,
            "description": group.description,
            "technology": "kotlin",
            "has_view": has_children,
            "placements": [{"parent": group.parent_ref}],
        }
        if group.docs:
            entry["docs"] = group.docs
        elements[ref] = entry

    # Elements (classes) — summary/description come from KDoc; fall back to package path.
    for key, elem in tree.elements.items():
        package_desc = elem.package_path.replace("/", ".") if elem.package_path else ""
        description = elem.description or package_desc

        entry: dict = {
            "name": elem.name,
            "kind": elem.kind,
            "summary": elem.summary,
            "description": description,
            "technology": elem.technology,
            "language": "kotlin",
            "has_view": False,
            "placements": [{"parent": elem.parent_ref}],
        }
        if elem.file_path:
            entry["file_path"] = elem.file_path
        if elem.tags:
            entry["tags"] = elem.tags
        elements[key] = entry

    # Connectors: combine all levels (module → group → sub-group → class)
    connectors: list[dict] = []

    # Add aggregated connectors (highest level first)
    for _level_name, level_conns in sorted(
        result.aggregated_connectors.items(),
        key=lambda x: x[0],  # alphabetical: "group", "module", "sub-group-N"
        reverse=True,
    ):
        for conn in level_conns:
            entry: dict = {
                "view": conn.view,
                "source": conn.source,
                "target": conn.target,
                "label": conn.label,
                "direction": conn.direction,
                "style": conn.style,
            }
            if conn.relationship:
                entry["relationship"] = conn.relationship
            connectors.append(entry)

    # Add class-level connectors
    for conn in result.class_connectors:
        entry: dict = {
            "view": conn.view,
            "source": conn.source,
            "target": conn.target,
            "direction": conn.direction,
            "style": conn.style,
        }
        if conn.label:
            entry["label"] = conn.label
        if conn.relationship:
            entry["relationship"] = conn.relationship
        if conn.id:
            entry["id"] = conn.id
        connectors.append(entry)

    return elements, connectors


def write_output(result: PipelineResult, output_dir: Path) -> None:
    """Write the pipeline results to YAML files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    elements, connectors = serialize_tree(result)

    out_elements = output_dir / "elements.yaml"
    out_connectors = output_dir / "connectors.yaml"

    print(f"\nWriting {out_elements}...")
    _write_yaml(elements, out_elements)

    print(f"Writing {out_connectors}...")
    _write_yaml(connectors, out_connectors)

    print("\nDone! Run `tld validate -w .` and `echo yes | tld apply -w .` to apply.")
