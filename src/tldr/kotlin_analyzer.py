"""Tree-sitter based Kotlin source analyzer.

Replaces tld's `analyze` step with direct Python tree-sitter parsing for:
- Element discovery (classes, interfaces)
- Class-level type dependency detection (constructor params, supertypes, properties)

This gives us per-class precision for connectors, correctly handling multi-class
files without attributing all imports to all classes.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

import tree_sitter
import tree_sitter_kotlin as tskotlin

# Initialize parser once at module level
_LANGUAGE = tree_sitter.Language(tskotlin.language())
_PARSER = tree_sitter.Parser(_LANGUAGE)

# Node types that represent class/interface declarations
_CLASS_DECL_TYPES = {"class_declaration"}
# The keyword nodes that tell us what kind of declaration it is
_KIND_KEYWORDS = {"class", "interface", "object"}

# Kind marker for top-level Koin `Module` vals (DI composition manifests). Not
# classes/interfaces, but retained so their value-references become explicit edges.
_MODULE_VAL_KIND = "di_module"


@dataclass
class AnalyzedFile:
    """Result of analyzing a single Kotlin file."""

    file_path: str  # Relative path from repo root
    imports: dict[str, str] = field(default_factory=dict)  # simple_name → qualified_path
    elements: list[AnalyzedElement] = field(default_factory=list)


@dataclass
class AnalyzedElement:
    """A class or interface discovered in a Kotlin file."""

    name: str
    kind: str  # "class" or "interface"
    file_path: str
    line: int
    type_refs: set[str] = field(default_factory=set)  # Simple type names referenced in body
    supertypes: set[str] = field(default_factory=set)  # Types from delegation_specifiers (extends/implements)
    summary: str = ""  # KDoc first sentence (short, node label)
    doc: str = ""       # full KDoc prose (sidebar description)


@dataclass
class AnalysisResult:
    """Complete analysis result, compatible with pipeline input format."""

    raw_elements: dict[str, dict]  # element_key → {name, kind, file_path, ...}
    raw_connectors: list[dict]  # [{source, target, direction, style}, ...]
    stats: dict[str, int] = field(default_factory=dict)


def _extract_identifier_text(node: tree_sitter.Node) -> str | None:
    """Get the text of the first `identifier` child of a node."""
    for child in node.children:
        if child.type == "identifier":
            return child.text.decode("utf-8")
    return None


def _split_kdoc(raw: str) -> tuple[str, str]:
    """Extract (summary, description) from a `/** … */` KDoc block comment.

    Description is the leading prose with block tags (@param, @return, …) and
    everything after them removed. Summary is its first sentence. Returns
    ("", "") for a non-KDoc block comment (plain `/* … */`).
    """
    body = raw.strip()
    if not body.startswith("/**"):
        return "", ""
    body = body[3:]
    if body.endswith("*/"):
        body = body[:-2]
    lines: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        if stripped.startswith("@"):  # KDoc block tag — drop tags and everything after
            break
        lines.append(stripped)
    description = " ".join(" ".join(lines).split())
    if not description:
        return "", ""
    match = re.search(r"(?<=[.!?])\s", description)
    summary = description[: match.start()] if match else description
    return summary, description


def _extract_qualified_identifier(node: tree_sitter.Node) -> str | None:
    """Extract full dotted name from a qualified_identifier node."""
    parts = []
    for child in node.children:
        if child.type == "identifier":
            parts.append(child.text.decode("utf-8"))
    return ".".join(parts) if parts else None


def _get_declaration_kind(node: tree_sitter.Node) -> str:
    """Determine if a class_declaration is a class, interface, or object."""
    for child in node.children:
        if child.type in _KIND_KEYWORDS:
            return child.type
    return "class"


def _collect_user_types(node: tree_sitter.Node, types: set[str]) -> None:
    """Recursively collect all user_type simple names from a subtree.

    Walks the AST rooted at `node` and extracts the first identifier
    from each `user_type` node (which is the simple type name).

    Skips nested class declarations to avoid attributing their type refs
    to the parent class.
    """
    for child in node.children:
        if child.type == "class_declaration":
            # Don't descend into nested classes — they get their own analysis
            continue
        if child.type == "user_type":
            # The first identifier in user_type is the simple type name
            name = _extract_identifier_text(child)
            if name:
                types.add(name)
            # Still recurse into user_type for generic type arguments
            _collect_user_types(child, types)
        else:
            _collect_user_types(child, types)


def _find_child(node: tree_sitter.Node, type_name: str) -> tree_sitter.Node | None:
    """Return the first direct child of `node` with the given type."""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _is_koin_module_property(prop: tree_sitter.Node) -> bool:
    """True if a property_declaration binds a Koin `Module` val.

    Matches either an explicit `: Module` type annotation or a `module { }`
    initializer call, e.g. `val dataModule: Module = module { ... }`.
    """
    var_decl = _find_child(prop, "variable_declaration")
    if var_decl is not None:
        user_type = _find_child(var_decl, "user_type")
        if user_type is not None and _extract_identifier_text(user_type) == "Module":
            return True
    call = _find_child(prop, "call_expression")
    if call is not None and _extract_identifier_text(call) == "module":
        return True
    return False


def _extract_module_vals(
    node: tree_sitter.Node,
    file_path: str,
    result: AnalyzedFile,
) -> None:
    """Emit top-level Koin `Module` vals as elements.

    These are DI composition manifests (e.g. `dataModule`, `servicesModule`).
    They are referenced by value, not by type, so type-ref analysis can't see the
    dependency from a composition root that wires them via `modules(...)`. Emitting
    them as elements lets those references become explicit cross-module edges.
    """
    pending_summary = ""
    pending_desc = ""
    for child in node.children:
        if child.type == "block_comment":
            pending_summary, pending_desc = _split_kdoc(child.text.decode("utf-8"))
            continue
        if child.type == "property_declaration" and _is_koin_module_property(child):
            var_decl = _find_child(child, "variable_declaration")
            name = _extract_identifier_text(var_decl) if var_decl is not None else None
            if name:
                result.elements.append(
                    AnalyzedElement(
                        name=name,
                        kind=_MODULE_VAL_KIND,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                        summary=pending_summary,
                        doc=pending_desc,
                    )
                )
        pending_summary = ""
        pending_desc = ""


def parse_file(source: bytes, file_path: str) -> AnalyzedFile:
    """Parse a single Kotlin file and extract elements + type references.

    Args:
        source: Raw file bytes.
        file_path: Relative path from repo root.

    Returns:
        AnalyzedFile with imports, elements, and per-class type refs.
    """
    tree = _PARSER.parse(source)
    root = tree.root_node

    result = AnalyzedFile(file_path=file_path)

    # Pass 1: Extract imports
    # tree-sitter-kotlin uses "import" as the node type (not "import_header")
    # Structure: import → [import (keyword), qualified_identifier, optional "." + "*"]
    for child in root.children:
        if child.type == "import":
            qi = None
            is_wildcard = False
            for sub in child.children:
                if sub.type == "qualified_identifier":
                    qi = _extract_qualified_identifier(sub)
                elif sub.type == "identifier" and sub.text.decode("utf-8") != "import":
                    # Single-segment import (unlikely but handle it)
                    qi = sub.text.decode("utf-8")
                elif sub.type == "*":
                    is_wildcard = True
            if qi and not is_wildcard:
                simple_name = qi.rsplit(".", 1)[-1]
                result.imports[simple_name] = qi

    # Pass 2: Extract class/interface declarations (top-level and nested)
    _extract_elements(root, file_path, result)

    # Pass 3: Extract Koin Module vals (DI composition manifests)
    _extract_module_vals(root, file_path, result)

    return result


def _extract_elements(
    node: tree_sitter.Node,
    file_path: str,
    result: AnalyzedFile,
) -> None:
    """Find top-level class/interface declarations and extract their type refs.

    Only extracts declarations at the current scope level — does NOT recurse
    into nested class bodies. Nested classes are excluded from the diagram.
    """
    pending_summary = ""
    pending_desc = ""
    for child in node.children:
        if child.type == "block_comment":
            pending_summary, pending_desc = _split_kdoc(child.text.decode("utf-8"))
            continue
        if child.type == "class_declaration":
            kind = _get_declaration_kind(child)
            name = _extract_identifier_text(child)
            if kind in ("class", "interface") and name:
                # Collect type references, separating supertypes from uses.
                type_refs: set[str] = set()
                supertypes: set[str] = set()
                for sub in child.children:
                    if sub.type == "primary_constructor":
                        _collect_user_types(sub, type_refs)
                    elif sub.type == "delegation_specifiers":
                        _collect_user_types(sub, supertypes)
                    elif sub.type == "class_body":
                        _collect_user_types(sub, type_refs)
                type_refs.discard(name)
                supertypes.discard(name)
                type_refs -= supertypes

                result.elements.append(
                    AnalyzedElement(
                        name=name,
                        kind=kind,
                        file_path=file_path,
                        line=child.start_point[0] + 1,
                        type_refs=type_refs,
                        supertypes=supertypes,
                        summary=pending_summary,
                        doc=pending_desc,
                    )
                )
        pending_summary = ""
        pending_desc = ""


def _should_exclude(rel_path: str, exclude_patterns: list[str]) -> bool:
    """Check if a relative path matches any exclusion pattern."""
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # Also check against just the filename
        filename = rel_path.rsplit("/", 1)[-1]
        if fnmatch.fnmatch(filename, pattern):
            return True
        # Check path segments
        if pattern.endswith("/**") or pattern.endswith("/*"):
            prefix = pattern.rstrip("/*")
            if rel_path.startswith(prefix + "/") or rel_path == prefix:
                return True
        # fnmatch with full path
        if "**" in pattern:
            # Convert ** glob to work with fnmatch
            # fnmatch doesn't support **, so check if any segment matches
            simple_pattern = pattern.replace("**/", "")
            if fnmatch.fnmatch(rel_path, f"*/{simple_pattern}") or fnmatch.fnmatch(
                rel_path, simple_pattern
            ):
                return True
    return False


def discover_kotlin_files(
    source_root: Path,
    exclude_patterns: list[str] | None = None,
) -> list[Path]:
    """Find all .kt files under source_root, respecting exclusions.

    Args:
        source_root: Absolute path to the source directory to scan.
        exclude_patterns: Glob patterns for files/dirs to exclude.

    Returns:
        List of absolute paths to .kt files.
    """
    if exclude_patterns is None:
        exclude_patterns = []

    kt_files: list[Path] = []
    for path in sorted(source_root.rglob("*.kt")):
        rel = str(path.relative_to(source_root.parent.parent))  # relative to repo root
        if not _should_exclude(rel, exclude_patterns):
            kt_files.append(path)

    return kt_files


def analyze_sources(
    repo_root: Path,
    source_root: Path,
    exclude_patterns: list[str] | None = None,
) -> AnalysisResult:
    """Analyze all Kotlin sources and produce elements + connectors.

    This is the main entry point that replaces `tld analyze`.

    Args:
        repo_root: Absolute path to the monorepo root.
        source_root: Absolute path to the SDK source root (e.g., katalyst-connect/sdk/).
        exclude_patterns: Glob patterns for exclusions (from .tld.yaml).

    Returns:
        AnalysisResult with raw_elements and raw_connectors in pipeline-compatible format.
    """
    if exclude_patterns is None:
        exclude_patterns = []

    # Discover files
    kt_files: list[Path] = []
    for path in sorted(source_root.rglob("*.kt")):
        rel = str(path.relative_to(repo_root))
        if not _should_exclude(rel, exclude_patterns):
            kt_files.append(path)

    # Parse all files
    analyzed_files: list[AnalyzedFile] = []
    for path in kt_files:
        try:
            source = path.read_bytes()
        except OSError:
            continue
        rel_path = str(path.relative_to(repo_root))
        af = parse_file(source, rel_path)
        analyzed_files.append(af)

    # Build global element index: (file_path, name) → element_key
    # Also build simple_name → [element_keys] for cross-file resolution
    raw_elements: dict[str, dict] = {}
    name_to_keys: dict[str, list[str]] = {}
    qualified_to_key: dict[str, str] = {}  # qualified_import_path → element_key

    for af in analyzed_files:
        for elem in af.elements:
            # Element key: file_path::ClassName (unique, stable)
            key = f"{elem.file_path}::{elem.name}"
            raw_elements[key] = {
                "name": elem.name,
                "kind": elem.kind,
                "file_path": elem.file_path,
                "line": elem.line,
                "summary": elem.summary,
                "description": elem.doc,
                "tags": [],
            }

            # Index by simple name for connector resolution
            if elem.name not in name_to_keys:
                name_to_keys[elem.name] = []
            name_to_keys[elem.name].append(key)

    # Build qualified path → key index using import paths that match our elements
    # For each file's imports, if the imported name resolves to exactly one element, register it
    for af in analyzed_files:
        for simple_name, qualified in af.imports.items():
            keys = name_to_keys.get(simple_name, [])
            if len(keys) == 1:
                qualified_to_key[qualified] = keys[0]

    # Build connectors from type references
    raw_connectors: list[dict] = []
    connector_count = 0

    def _resolve_type(
        type_name: str,
        af: AnalyzedFile,
        qualified_to_key: dict[str, str],
        name_to_keys: dict[str, list[str]],
    ) -> str | None:
        """Resolve a simple type name to an element key."""
        qualified = af.imports.get(type_name)
        if qualified:
            target_key = qualified_to_key.get(qualified)
            if target_key:
                return target_key
        # Fallback: unique name match
        candidates = name_to_keys.get(type_name, [])
        if len(candidates) == 1:
            return candidates[0]
        return None

    for af in analyzed_files:
        for elem in af.elements:
            source_key = f"{elem.file_path}::{elem.name}"
            if source_key not in raw_elements:
                continue

            # Supertype connectors (extends/implements)
            for type_name in elem.supertypes:
                target_key = _resolve_type(type_name, af, qualified_to_key, name_to_keys)
                if target_key and target_key != source_key:
                    raw_connectors.append({
                        "source": source_key,
                        "target": target_key,
                        "direction": "forward",
                        "style": "smoothstep",
                        "label": "implements" if elem.kind == "class" else "extends",
                        "relationship": "inheritance",
                    })
                    connector_count += 1

            # Usage connectors (constructor params, properties, function types)
            for type_name in elem.type_refs:
                target_key = _resolve_type(type_name, af, qualified_to_key, name_to_keys)
                if target_key and target_key != source_key:
                    raw_connectors.append({
                        "source": source_key,
                        "target": target_key,
                        "direction": "forward",
                        "style": "smoothstep",
                        "relationship": "dependency",
                    })
                    connector_count += 1

    # Koin Module-val aggregation edges.
    # A class that imports a top-level `Module` val (e.g. `dataModule`) depends on
    # the module that DEFINES it. Type-ref analysis misses this because the reference
    # is a value, not a type — so composition roots that wire modules via `modules(...)`
    # would otherwise show no edge to the modules they load. Emit an explicit edge.
    module_val_keys = {
        key for key, e in raw_elements.items() if e.get("kind") == _MODULE_VAL_KIND
    }
    if module_val_keys:
        for af in analyzed_files:
            referenced = {
                qualified_to_key[q]
                for q in af.imports.values()
                if qualified_to_key.get(q) in module_val_keys
            }
            if not referenced:
                continue
            for elem in af.elements:
                if elem.kind == _MODULE_VAL_KIND:
                    continue
                source_key = f"{elem.file_path}::{elem.name}"
                for target_key in referenced:
                    if target_key == source_key:
                        continue
                    raw_connectors.append({
                        "source": source_key,
                        "target": target_key,
                        "direction": "forward",
                        "style": "smoothstep",
                        "relationship": "dependency",
                    })
                    connector_count += 1

    return AnalysisResult(
        raw_elements=raw_elements,
        raw_connectors=raw_connectors,
        stats={
            "files_scanned": len(kt_files),
            "files_with_elements": len(analyzed_files),
            "total_elements": len(raw_elements),
            "total_connectors": connector_count,
        },
    )
