"""Domain models for the tld post-processing pipeline.

The architecture tree supports arbitrary nesting depth:
    root → Module → GroupNode → GroupNode → ... → Element

GroupNodes can be children of Modules OR other GroupNodes, enabling
recursive sub-grouping without a fixed depth limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Configuration models (loaded from groups.yaml)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    """A routing rule that maps (module, package_prefix) → group_ref."""

    module: str
    prefix: str
    group: str

    @property
    def is_catch_all(self) -> bool:
        """True if this is a bare module-root rule (no '/' in prefix)."""
        return "/" not in self.prefix


# ---------------------------------------------------------------------------
# Tree node models
# ---------------------------------------------------------------------------


@dataclass
class Module:
    """Top-level container shown at root view level."""

    ref: str
    name: str
    description: str = ""

    @property
    def parent_ref(self) -> str:
        return "root"


@dataclass
class GroupNode:
    """Architecture component that can nest at any depth.

    A GroupNode's parent can be a Module ref OR another GroupNode ref,
    enabling arbitrary nesting: module → group → sub-group → sub-sub-group → ...
    """

    ref: str
    name: str
    description: str = ""
    docs: str = ""  # optional long-form documentation (override-configurable)
    parent_ref: str = ""  # ref of parent Module or GroupNode
    is_auto_generated: bool = False  # True if created by auto-split

    # Runtime: populated during tree construction
    children_refs: list[str] = field(default_factory=list)
    element_count: int = 0  # direct child elements (not recursive)


@dataclass
class Element:
    """A leaf node in the architecture tree (typically a Kotlin class).

    Always parented under a GroupNode.
    """

    key: str  # Full tld symbol key
    name: str
    kind: str = "class"
    technology: str = "kotlin"
    file_path: str = ""
    package_path: str = ""  # Extracted relative package path
    module: str = ""  # SDK module name (e.g., "connect-sdk-core")
    parent_ref: str = ""  # ref of containing GroupNode
    tags: list[str] = field(default_factory=list)


@dataclass
class Connector:
    """A relationship between two elements or nodes."""

    source: str
    target: str
    view: str = ""
    label: str = ""
    direction: str = "forward"
    style: str = "smoothstep"
    relationship: str = ""
    id: str = ""

    # Aggregation level: "class" for leaf connectors, container ref for aggregated
    level: str = "class"


# ---------------------------------------------------------------------------
# Architecture Tree
# ---------------------------------------------------------------------------


@dataclass
class ArchTree:
    """The complete architecture tree with traversal helpers.

    Supports N-level nesting. All lookups are by ref string.
    """

    modules: dict[str, Module] = field(default_factory=dict)
    groups: dict[str, GroupNode] = field(default_factory=dict)
    elements: dict[str, Element] = field(default_factory=dict)
    rules: list[Rule] = field(default_factory=list)
    # Name/description/docs overrides for auto-generated groups, keyed by their
    # generated ref (e.g. "data--camera--ble"). Applied during auto-split.
    group_overrides: dict[str, dict] = field(default_factory=dict)

    # Configuration
    max_group_size: int = 20  # Auto-split threshold
    source_prefix: str = ""  # Path prefix stripped to find module (e.g. "katalyst-connect/sdk/")
    package_marker: str = ""  # Base package path marker (e.g. "/com/gopro/katalyst/connect/")

    def all_container_refs(self) -> set[str]:
        """All refs that are containers (modules + groups), not leaf elements."""
        return set(self.modules.keys()) | set(self.groups.keys())

    def parent_of(self, ref: str) -> str:
        """Get the parent ref of any node. Returns 'root' for modules."""
        if ref in self.modules:
            return "root"
        if ref in self.groups:
            return self.groups[ref].parent_ref
        if ref in self.elements:
            return self.elements[ref].parent_ref
        return "root"

    def ancestors(self, ref: str) -> list[str]:
        """Walk up from ref to root, returning [parent, grandparent, ..., 'root'].

        Does NOT include the ref itself.
        """
        result = []
        current = self.parent_of(ref)
        seen: set[str] = set()
        while current != "root" and current not in seen:
            result.append(current)
            seen.add(current)
            current = self.parent_of(current)
        if current == "root":
            result.append("root")
        return result

    def lowest_common_ancestor(self, ref_a: str, ref_b: str) -> str:
        """Find the lowest common ancestor of two refs."""
        ancestors_a = set(self.ancestors(ref_a))
        ancestors_a.add(ref_a)

        current = ref_b
        seen: set[str] = set()
        while current not in ancestors_a and current != "root" and current not in seen:
            seen.add(current)
            current = self.parent_of(current)
        return current

    def depth_of(self, ref: str) -> int:
        """0 for root, 1 for modules, 2 for top-level groups, 3+ for sub-groups."""
        depth = 0
        current = ref
        seen: set[str] = set()
        while current != "root" and current not in seen:
            seen.add(current)
            current = self.parent_of(current)
            depth += 1
        return depth

    def children_of(self, parent_ref: str) -> list[str]:
        """Get immediate children refs of a container node."""
        children: list[str] = []
        if parent_ref == "root":
            children.extend(self.modules.keys())
        else:
            for ref, group in self.groups.items():
                if group.parent_ref == parent_ref:
                    children.append(ref)
            for key, elem in self.elements.items():
                if elem.parent_ref == parent_ref:
                    children.append(key)
        return children

    def leaf_descendants(self, container_ref: str) -> list[str]:
        """Get all leaf element keys under a container (recursive)."""
        result: list[str] = []
        stack = [container_ref]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            if current in self.elements:
                result.append(current)
            else:
                for child in self.children_of(current):
                    stack.append(child)
        return result

    def module_of(self, ref: str) -> str | None:
        """Walk up to find the module ancestor of any ref."""
        if ref in self.modules:
            return ref
        current = ref
        seen: set[str] = set()
        while current != "root" and current not in seen:
            seen.add(current)
            current = self.parent_of(current)
            if current in self.modules:
                return current
        return None
