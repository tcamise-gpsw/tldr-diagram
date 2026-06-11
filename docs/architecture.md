# Architecture

The TLD tool analyzes Kotlin source code and generates an interactive architecture diagram. This page describes the core pipeline, data structures, and extensibility model.

## Pipeline Overview

The analysis pipeline has six stages, orchestrated by `pipeline.py`:

### 1. Tree-sitter Analysis (`kotlin_analyzer.py`)

- Discovers all `.kt` files under `--source-root` (respects exclusion patterns)
- Parses each file with `tree-sitter-kotlin`
- Extracts: imports, top-level class/interface declarations, type references
- Two connector types:
  - **supertypes** — from `delegation_specifiers` → `implements`/`extends`
  - **usage** — constructor params, properties, function signatures → `dependency`
- Element key format: `file_path::ClassName`
- Output: `AnalysisResult` with `raw_elements` dict and `raw_connectors` list

### 2. Classification (`classifier.py`)

- For each raw element: `extract_package_path(file_path, source_prefix, package_marker)` → `(module, package_path)`
- Routes via rules: first matching `(module, prefix)` → group assignment
- Retains only `class` and `interface` kinds; skips nested classes (name contains `.`)
- Reports unmapped elements and catch-all matches

### 3. Auto-Splitting (`splitting.py`)

- Groups exceeding `max_group_size` are split by next package path segment
- Recursive: continues until all groups are within bounds
- Sub-group ref format: `parent--segment`, marked `is_auto_generated=True`
- Minimum bucket size: 2 (smaller buckets stay in parent)

### 4. Connector Processing (`connectors.py`)

- Remaps non-retained elements (functions, nested classes) to their containing class
- Deduplicates `(source, target)` pairs
- Scopes each connector's `view` to the source element's parent group

### 5. Connectivity Filter

- Removes elements with no inbound or outbound connectors
- Disabled with `--all-classes`

### 6. Aggregation (`aggregation.py`)

- For each class-level connector, finds the lowest common ancestor (LCA) of source and target
- Creates summary edges at LCA and every ancestor up to root
- Deduplicates and counts: label becomes `uses (N)`
- Output: `dict[view_ref → list[Connector]]`

## Data Model

All types are defined in `models.py`:

### ArchTree

The root container. Holds dicts of modules, groups, elements, and rules.

Tree traversal helpers:

```python
parent_of(node_ref: str) -> str | None
ancestors(node_ref: str) -> list[str]
lowest_common_ancestor(node_a: str, node_b: str) -> str
depth_of(node_ref: str) -> int
children_of(node_ref: str) -> list[str]
leaf_descendants(node_ref: str) -> list[str]
module_of(node_ref: str) -> str
```

### Module

Top-level container. Parent is always `root`.

### GroupNode

Architecture component. `parent_ref` can be a Module or another GroupNode (N-level nesting).

### Element

Leaf node (a Kotlin class/interface). Keyed by `file_path::ClassName`.

### Connector

Edge between elements. `level="class"` for leaf connectors, container ref for aggregated.

### Rule

Routing rule: `(module, prefix) → group`

## Frontend

The viewer is a React + TypeScript SPA located in `frontend/`:

- **Data loading** — fetches `elements.yaml` and `connectors.yaml` via HTTP, parses with `js-yaml`, builds a `ViewTree`
- **Layout** — `dagre` computes node positions per view, cached by view ref
- **Rendering** — Canvas 2D with RAF loop. Frustum culling for performance
- **Navigation** — stack-based drill-down into group views. Browser back button works
- **Side panel** — shows selected node details and a sortable connector table

## Language Extensibility

`kotlin_analyzer.py` is the only language-specific module. To add a new language:

### Step 1: Create a new analyzer

Create a file (e.g., `swift_analyzer.py`) that returns an `AnalysisResult`:

```python
class AnalysisResult:
    raw_elements: dict[str, dict]  # keyed by file_path::TypeName
    raw_connectors: list[dict]     # each with source, target, relationship
```

### Step 2: Update pipeline.py

Select the analyzer based on config or file extensions.

### Step 3: Configure language conventions

Set `source_prefix` and `package_marker` for the new language's path conventions.

### Note

Everything downstream (classifier, splitter, connectors, aggregation, frontend) is language-agnostic.
