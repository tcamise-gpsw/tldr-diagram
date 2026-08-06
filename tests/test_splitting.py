"""Tests for the splitting module (auto-split oversized groups)."""

import pytest

from tldr.models import ArchTree, Element, GroupNode, Module, Rule
from tldr.splitting import (
    split_oversized_group,
    split_all_oversized,
    _compute_relative_path,
    _next_segment,
    _generate_sub_group_ref,
    _generate_sub_group_name,
)


def _make_tree(max_size: int = 5) -> ArchTree:
    """Create a minimal tree for testing."""
    tree = ArchTree(max_group_size=max_size)
    tree.modules["core"] = Module(ref="core", name="Core")
    tree.groups["core-settings"] = GroupNode(
        ref="core-settings", name="Settings System", parent_ref="core"
    )
    tree.rules = [
        Rule(module="connect-sdk-core", prefix="core/domain/camera/setting", group="core-settings"),
    ]
    return tree


def _add_elements(tree: ArchTree, group_ref: str, paths: list[str]) -> None:
    """Add test elements to a tree."""
    for i, pkg_path in enumerate(paths):
        key = f"symbol-{group_ref}-{i}"
        tree.elements[key] = Element(
            key=key,
            name=f"Class{i}",
            package_path=pkg_path,
            module="connect-sdk-core",
            parent_ref=group_ref,
            file_path=f"katalyst-connect/sdk/connect-sdk-core/src/commonMain/kotlin/com/gopro/katalyst/connect/{pkg_path}/Class{i}.kt",
        )


class TestNextSegment:
    def test_single_segment(self):
        assert _next_segment("parser") == "parser"

    def test_multi_segment(self):
        assert _next_segment("parser/legacy") == "parser"

    def test_empty(self):
        assert _next_segment("") == ""


class TestGenerateSubGroupRef:
    def test_normal(self):
        assert _generate_sub_group_ref("parser", "core-settings") == "core-settings--parser"

    def test_empty_segment(self):
        assert _generate_sub_group_ref("", "core-settings") == "core-settings--root"


class TestGenerateSubGroupName:
    def test_simple(self):
        assert _generate_sub_group_name("parser", "Settings") == "Parser"

    def test_hyphenated(self):
        assert _generate_sub_group_name("data-source", "Settings") == "Data Source"

    def test_empty(self):
        assert _generate_sub_group_name("", "Settings") == "Settings (root)"


class TestComputeRelativePath:
    def test_strips_prefix(self):
        tree = _make_tree()
        elem = Element(
            key="test",
            name="Test",
            package_path="core/domain/camera/setting/parser/legacy",
            module="connect-sdk-core",
            parent_ref="core-settings",
        )
        result = _compute_relative_path(elem, tree.groups["core-settings"], tree)
        assert result == "parser/legacy"

    def test_at_prefix_root(self):
        tree = _make_tree()
        elem = Element(
            key="test",
            name="Test",
            package_path="core/domain/camera/setting",
            module="connect-sdk-core",
            parent_ref="core-settings",
        )
        result = _compute_relative_path(elem, tree.groups["core-settings"], tree)
        assert result == ""


class TestSplitOversizedGroup:
    def test_no_split_under_threshold(self):
        tree = _make_tree(max_size=10)
        _add_elements(tree, "core-settings", [
            "core/domain/camera/setting/parser/A",
            "core/domain/camera/setting/parser/B",
            "core/domain/camera/setting/model/C",
        ])
        result = split_oversized_group("core-settings", tree)
        assert result == []

    def test_splits_by_next_segment(self):
        tree = _make_tree(max_size=3)
        _add_elements(tree, "core-settings", [
            "core/domain/camera/setting/parser/A",
            "core/domain/camera/setting/parser/B",
            "core/domain/camera/setting/parser/C",
            "core/domain/camera/setting/model/D",
            "core/domain/camera/setting/model/E",
            "core/domain/camera/setting/filter/F",
            "core/domain/camera/setting/filter/G",
        ])
        result = split_oversized_group("core-settings", tree)
        # Should create sub-groups for parser, model, filter
        assert len(result) >= 2
        refs = {g.ref for g in result}
        assert "core-settings--parser" in refs
        assert "core-settings--model" in refs
        assert "core-settings--filter" in refs

    def test_small_buckets_stay_in_parent(self):
        """Buckets with < MIN_BUCKET_SIZE (2) elements stay in parent."""
        tree = _make_tree(max_size=3)
        _add_elements(tree, "core-settings", [
            "core/domain/camera/setting/parser/A",
            "core/domain/camera/setting/parser/B",
            "core/domain/camera/setting/parser/C",
            "core/domain/camera/setting/lonely/X",  # Only 1 element
        ])
        result = split_oversized_group("core-settings", tree)
        refs = {g.ref for g in result}
        assert "core-settings--parser" in refs
        assert "core-settings--lonely" not in refs
        # The lonely element should still be under core-settings
        lonely = [e for e in tree.elements.values() if "lonely" in e.package_path]
        assert lonely[0].parent_ref == "core-settings"

    def test_no_split_when_single_bucket(self):
        """If all elements share the same next segment, can't split."""
        tree = _make_tree(max_size=2)
        _add_elements(tree, "core-settings", [
            "core/domain/camera/setting/parser/A",
            "core/domain/camera/setting/parser/B",
            "core/domain/camera/setting/parser/C",
        ])
        result = split_oversized_group("core-settings", tree)
        assert result == []


class TestSplitAllOversized:
    def test_recursive_splitting(self):
        """Groups that are still oversized after first split get split again."""
        tree = _make_tree(max_size=2)
        _add_elements(tree, "core-settings", [
            "core/domain/camera/setting/parser/legacy/A",
            "core/domain/camera/setting/parser/legacy/B",
            "core/domain/camera/setting/parser/standard/C",
            "core/domain/camera/setting/parser/standard/D",
            "core/domain/camera/setting/model/E",
            "core/domain/camera/setting/model/F",
        ])
        result = split_all_oversized(tree)
        # First split: core-settings → parser (4), model (2)
        # Second split: parser → legacy (2), standard (2)
        assert len(result) >= 2
        # Verify parser got sub-split
        parser_children = [g for g in tree.groups.values() if g.parent_ref == "core-settings--parser"]
        assert len(parser_children) >= 2

    def test_respects_max_iterations(self):
        """Safety valve prevents infinite loops."""
        tree = _make_tree(max_size=1)
        # All elements at same leaf — can't split, but group is oversized
        _add_elements(tree, "core-settings", [
            "core/domain/camera/setting/parser/A",
            "core/domain/camera/setting/parser/B",
            "core/domain/camera/setting/parser/C",
        ])
        # Should not infinite loop — returns when no further splitting possible
        result = split_all_oversized(tree)
        # It'll create parser sub-group but then can't split further
        assert len(result) <= 5  # Bounded

    def test_no_splitting_when_disabled(self):
        """max_group_size=0 disables splitting."""
        tree = _make_tree(max_size=0)
        _add_elements(tree, "core-settings", [
            "core/domain/camera/setting/parser/A",
            "core/domain/camera/setting/parser/B",
            "core/domain/camera/setting/parser/C",
        ])
        result = split_all_oversized(tree)
        assert result == []


def _module_tree(max_size: int = 5) -> ArchTree:
    """Tree whose rule targets a MODULE directly (no structural group)."""
    tree = ArchTree(max_group_size=max_size)
    tree.modules["data"] = Module(ref="data", name="Data")
    tree.rules = [Rule(module="connect-sdk-core", prefix="core/v2", group="data")]
    return tree


class TestModuleAsSplittableContainer:
    def test_split_oversized_module(self):
        tree = _module_tree(max_size=3)
        _add_elements(tree, "data", [
            "core/v2/camera/ble/A",
            "core/v2/camera/ble/B",
            "core/v2/camera/wifi/C",
            "core/v2/camera/wifi/D",
            "core/v2/helmet/E",
            "core/v2/helmet/F",
        ])
        result = split_all_oversized(tree)
        refs = {g.ref for g in result}
        # Segments hang directly off the module — no intermediate root group.
        assert "data--camera" in refs
        assert "data--helmet" in refs
        # ...and split recursively.
        assert "data--camera--ble" in refs
        assert "data--camera--wifi" in refs
        # Elements are re-parented under the module's segment groups.
        assert tree.groups["data--helmet"].parent_ref == "data"

    def test_override_applies_name_description_docs(self):
        tree = _module_tree(max_size=1)
        tree.group_overrides["data--camera"] = {
            "name": "Camera Link",
            "description": "camera transport",
            "docs": "long form",
        }
        _add_elements(tree, "data", [
            "core/v2/camera/A",
            "core/v2/camera/B",
            "core/v2/helmet/C",
            "core/v2/helmet/D",
        ])
        split_all_oversized(tree)
        cam = tree.groups["data--camera"]
        assert cam.name == "Camera Link"
        assert cam.description == "camera transport"
        assert cam.docs == "long form"
        # A sibling with no override keeps the generated name.
        assert tree.groups["data--helmet"].name == "Helmet"
