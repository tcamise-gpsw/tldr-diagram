"""Tests for the aggregation module (N-level connector rollup)."""

import pytest

from tldr.models import ArchTree, Connector, Element, GroupNode, Module
from tldr.aggregation import build_all_aggregations


def _make_tree() -> ArchTree:
    """Create a tree with modules, groups, and sub-groups for testing."""
    tree = ArchTree()
    tree.modules["core"] = Module(ref="core", name="Core")
    tree.modules["domain"] = Module(ref="domain", name="Domain")

    tree.groups["core-settings"] = GroupNode(
        ref="core-settings", name="Settings", parent_ref="core"
    )
    tree.groups["core-network"] = GroupNode(
        ref="core-network", name="Network", parent_ref="core"
    )
    tree.groups["core-settings--parser"] = GroupNode(
        ref="core-settings--parser", name="Parser", parent_ref="core-settings"
    )
    tree.groups["core-settings--model"] = GroupNode(
        ref="core-settings--model", name="Model", parent_ref="core-settings"
    )
    tree.groups["domain-models"] = GroupNode(
        ref="domain-models", name="Domain Models", parent_ref="domain"
    )

    # Elements in sub-groups
    tree.elements["class-a"] = Element(
        key="class-a", name="A", parent_ref="core-settings--parser"
    )
    tree.elements["class-b"] = Element(
        key="class-b", name="B", parent_ref="core-settings--parser"
    )
    tree.elements["class-c"] = Element(
        key="class-c", name="C", parent_ref="core-settings--model"
    )
    tree.elements["class-d"] = Element(
        key="class-d", name="D", parent_ref="core-network"
    )
    tree.elements["class-e"] = Element(
        key="class-e", name="E", parent_ref="domain-models"
    )

    return tree


class TestBuildAllAggregations:
    def test_same_parent_not_aggregated(self):
        """Connectors between elements in the same parent produce no aggregation."""
        tree = _make_tree()
        class_conns = [
            Connector(source="class-a", target="class-b", view="core-settings--parser"),
        ]
        result = build_all_aggregations(class_conns, tree)
        # Same parent → no edges at any level
        all_conns = [c for conns in result.values() for c in conns]
        assert len(all_conns) == 0

    def test_cross_sibling_subgroups(self):
        """Connectors between sibling sub-groups aggregate at their parent."""
        tree = _make_tree()
        class_conns = [
            Connector(source="class-a", target="class-c", view="core-settings--parser"),
            Connector(source="class-b", target="class-c", view="core-settings--parser"),
        ]
        result = build_all_aggregations(class_conns, tree)

        # Should have edge at core-settings view (LCA of parser and model)
        assert "core-settings" in result
        cs_conns = result["core-settings"]
        assert len(cs_conns) == 1
        assert cs_conns[0].source == "core-settings--parser"
        assert cs_conns[0].target == "core-settings--model"
        assert cs_conns[0].view == "core-settings"
        assert "2" in cs_conns[0].label  # "uses (2)"

        # Should NOT propagate to "core" level because both elements are
        # under the same child of core (core-settings). No boundary crossed
        # at that level.
        assert "core" not in result

    def test_cross_group_within_module(self):
        """Connectors between different groups aggregate at module level."""
        tree = _make_tree()
        class_conns = [
            Connector(source="class-a", target="class-d", view="core-settings--parser"),
        ]
        result = build_all_aggregations(class_conns, tree)

        # LCA of class-a (in core-settings--parser) and class-d (in core-network) is "core"
        assert "core" in result
        core_conns = result["core"]
        assert len(core_conns) == 1
        assert core_conns[0].source == "core-settings"
        assert core_conns[0].target == "core-network"
        assert core_conns[0].view == "core"

    def test_cross_module(self):
        """Connectors between different modules aggregate at root level."""
        tree = _make_tree()
        class_conns = [
            Connector(source="class-d", target="class-e", view="core-network"),
        ]
        result = build_all_aggregations(class_conns, tree)

        # LCA of class-d (core-network) and class-e (domain-models) is "root"
        assert "root" in result
        root_conns = result["root"]
        assert len(root_conns) == 1
        assert root_conns[0].source == "core"
        assert root_conns[0].target == "domain"
        assert root_conns[0].view == "root"

    def test_multi_level_propagation(self):
        """A deep connector creates aggregated edges at every ancestor level."""
        tree = _make_tree()
        # class-a is at depth 4: root → core → core-settings → core-settings--parser → class-a
        # class-e is at depth 3: root → domain → domain-models → class-e
        class_conns = [
            Connector(source="class-a", target="class-e", view="core-settings--parser"),
        ]
        result = build_all_aggregations(class_conns, tree)

        # LCA is "root" (different modules)
        # At root: core → domain
        assert "root" in result
        root_conns = result["root"]
        assert any(
            c.source == "core" and c.target == "domain" for c in root_conns
        )

    def test_empty_connectors(self):
        """No connectors produces no aggregations."""
        tree = _make_tree()
        result = build_all_aggregations([], tree)
        assert len(result) == 0
