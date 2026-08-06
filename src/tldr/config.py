"""Configuration loading and validation for groups.yaml.

Supports N-level nesting: a group's parent can be a module OR another group.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from .models import ArchTree, GroupNode, Module, Rule


def load_config(config_path: Path) -> ArchTree:
    """Load modules, groups, and routing rules from groups.yaml into an ArchTree.

    Validates:
    - Every rule references a known group
    - Every group's parent is a known module OR known group (N-level nesting)
    - No circular parent references
    - No duplicate (module, prefix) pairs in rules
    """
    if not config_path.exists():
        print(f"ERROR: {config_path} not found.", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    raw_modules = config.get("modules", {})
    raw_groups = config.get("groups", {})
    raw_rules = config.get("rules", [])

    # Build tree
    tree = ArchTree()

    # Modules
    for ref, mod in raw_modules.items():
        tree.modules[ref] = Module(
            ref=ref,
            name=mod["name"],
            description=mod.get("description", ""),
        )

    # Groups. An entry WITH a `parent` is a structural group (rules may target it).
    # An entry WITHOUT a `parent` is an override for an auto-generated group of the
    # same ref: it supplies name/description/docs when auto-split creates that group.
    structural_group_refs = {
        r for r, g in raw_groups.items() if g.get("parent") is not None
    }
    valid_parents = set(tree.modules.keys()) | structural_group_refs
    for ref, group in raw_groups.items():
        parent = group.get("parent")
        if parent is None:
            tree.group_overrides[ref] = {
                k: group[k] for k in ("name", "description", "docs") if k in group
            }
            continue

        if parent not in valid_parents:
            print(
                f"ERROR: group '{ref}' references unknown parent '{parent}'. "
                f"Known parents: {sorted(valid_parents)}",
                file=sys.stderr,
            )
            sys.exit(1)

        tree.groups[ref] = GroupNode(
            ref=ref,
            name=group["name"],
            description=group.get("description", ""),
            docs=group.get("docs", ""),
            parent_ref=parent,
        )

    # Validate no circular parent references
    for ref in tree.groups:
        visited: set[str] = set()
        current = ref
        while current in tree.groups:
            if current in visited:
                print(
                    f"ERROR: circular parent reference detected: {ref} → ... → {current}",
                    file=sys.stderr,
                )
                sys.exit(1)
            visited.add(current)
            current = tree.groups[current].parent_ref

    # Rules — a rule may target a module OR a structural group.
    valid_targets = set(tree.groups.keys()) | set(tree.modules.keys())
    seen_rule_keys: dict[tuple[str, str], int] = {}

    for i, rule in enumerate(raw_rules):
        if rule["group"] not in valid_targets:
            print(
                f"ERROR: rules[{i}] references unknown target '{rule['group']}'. "
                f"Known modules/groups: {sorted(valid_targets)}",
                file=sys.stderr,
            )
            sys.exit(1)

        key = (rule["module"], rule["prefix"])
        if key in seen_rule_keys:
            print(
                f"ERROR: Duplicate rule at index {i}: "
                f"module='{key[0]}', prefix='{key[1]}' "
                f"(first seen at index {seen_rule_keys[key]})",
                file=sys.stderr,
            )
            sys.exit(1)
        seen_rule_keys[key] = i

        tree.rules.append(Rule(
            module=rule["module"],
            prefix=rule["prefix"],
            group=rule["group"],
        ))

    # Load settings from config if present
    settings = config.get("settings", {})
    if "max_group_size" in settings:
        tree.max_group_size = settings["max_group_size"]
    if "source_prefix" in settings:
        tree.source_prefix = settings["source_prefix"]
    if "package_marker" in settings:
        tree.package_marker = settings["package_marker"]

    return tree
