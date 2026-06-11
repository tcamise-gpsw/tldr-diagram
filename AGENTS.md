# Repository Guidelines

## Project Overview

TL;DR (Tool for Linking Dependency Relationships) is an architecture diagram generator. It analyzes source code with tree-sitter, classifies elements into architectural groups via YAML config, and produces an interactive navigable diagram in the browser.

Currently supports **Kotlin** via `tree-sitter-kotlin`. The analysis pipeline is language-agnostic from the classifier onward — adding a new language means writing a new analyzer module that produces the same `AnalysisResult` shape.

## Architecture & Data Flow

Two independent components connected by YAML:

```
Python pipeline (src/tldr/)          Frontend (frontend/)
─────────────────────────            ────────────────────
.kt files → tree-sitter              elements.yaml ──→ loader.ts
         → classifier                connectors.yaml ─→ (js-yaml parse)
         → splitter                                   → dagre layout
         → connectors                                 → canvas renderer
         → aggregation                                → interactive viewer
         → elements.yaml
         → connectors.yaml
```

### Python Pipeline (`src/tldr/`)

```
CLI (__main__.py)
 → load_config(groups.yaml)        # config.py → ArchTree
 → analyze_sources(source_root)    # kotlin_analyzer.py → AnalysisResult
 → classify_raw_elements(raw, tree)# classifier.py → Element[] + unmapped
 → split_all_oversized(tree)       # splitting.py → new GroupNodes
 → process_connectors(raw, tree)   # connectors.py → Connector[] (class-level)
 → apply_connectivity_filter(tree) # pipeline.py → remove isolated
 → build_all_aggregations(conns)   # aggregation.py → dict[view → Connector[]]
 → serialize_tree + write YAML     # pipeline.py → elements.yaml, connectors.yaml
```

### Frontend (`frontend/`)

```
App.tsx (state: navigationStack, selectedNode, data)
├── Breadcrumb
├── Toolbar (fit, toggle external stubs)
├── CanvasViewport (canvas 2D, RAF loop, camera transforms)
│   ├── layout.ts (dagre positioning, cached per view)
│   ├── renderer.ts (nodes, connectors, external stubs)
│   ├── camera.ts (pan, zoom, fitToContent)
│   ├── hitTest.ts (click/hover detection)
│   ├── animation.ts (drill-in/out transitions)
│   └── stubs.ts (external connector visualization)
├── Tooltip (hover)
└── SidePanel (selected node detail, collapsible, resizable)
    └── SidePanel.logic.ts (connector resolution, sorting)
```

## Key Directories

| Path | Purpose |
|------|---------|
| `src/tldr/` | Python package — analysis pipeline, CLI, HTTP server |
| `src/tldr/models.py` | All domain dataclasses (`ArchTree`, `Module`, `GroupNode`, `Element`, `Connector`, `Rule`) |
| `src/tldr/kotlin_analyzer.py` | Tree-sitter Kotlin parser — the only language-specific module |
| `src/tldr/classifier.py` | Config-driven element routing (no hardcoded project paths) |
| `src/tldr/pipeline.py` | Orchestration — `run_pipeline()` is the main entry point |
| `src/tldr/server.py` | Python HTTP server for viewing diagrams |
| `frontend/src/` | React + TypeScript viewer |
| `frontend/src/data/` | YAML loading, types, data model |
| `frontend/src/canvas/` | Canvas rendering, layout, camera, hit testing, animations |
| `frontend/src/components/` | React components (SidePanel, Toolbar, Tooltip) |
| `tests/` | Python unit tests (pytest) |
| `frontend/tests/` | Playwright E2E tests |

## Development Commands

### Python

```bash
# Run analysis pipeline
uv run python -m tldr analyze --source-root <path> --input-dir <workspace>

# Serve the viewer
uv run python -m tldr serve --workspace <dir> --frontend-dist frontend/dist

# Run tests (75 tests)
uv run pytest tests/ -v

# Dry run (stats only, no files written)
uv run python -m tldr analyze --source-root <path> --dry-run
```

### Frontend

```bash
cd frontend
npm install
npm run build:app       # tsc && vite build → dist/
npm run dev             # vite dev server on :5173
npm test                # vitest run
npm run test:watch      # vitest watch
```

### CLI Reference

**`tldr analyze`** (default subcommand):
- `--source-root` (required) — directory containing source files
- `--input-dir` — directory with `groups.yaml` (default: cwd)
- `--output-dir` — where to write YAML (default: input-dir)
- `--repo-root` — repo root for relative paths (auto-detected via `.git`)
- `--max-group-size N` — override auto-split threshold (default: 20, 0 to disable)
- `--all-classes` — skip connectivity filter (keep isolated elements)
- `--dry-run` — print stats without writing files

**`tldr serve`**:
- `--workspace` (required) — directory with `elements.yaml` and `connectors.yaml`
- `--frontend-dist` (required) — path to built `frontend/dist/`
- `--port` — HTTP port (default: 8060)
- `--no-open` — don't open browser

## Code Conventions & Common Patterns

### Python

- **Dataclasses everywhere** — all domain objects in `models.py` are `@dataclass`. `Rule` is `frozen=True`.
- **Relative imports** — all internal imports use `from .module import ...`.
- **Type hints** — all public functions have full signatures with `from __future__ import annotations`.
- **Config-driven classification** — `source_prefix` and `package_marker` come from `groups.yaml` settings, not hardcoded. The classifier has zero project-specific knowledge.
- **Element key format** — `"file_path::ClassName"` (unique, stable across runs).
- **Group ref format** — `"module-groupname"` (config-defined), `"parent--segment"` (auto-generated by splitter).
- **N-level nesting** — `GroupNode.parent_ref` can reference a `Module` or another `GroupNode`. Tree traversal helpers on `ArchTree`: `parent_of()`, `ancestors()`, `lowest_common_ancestor()`, `depth_of()`, `children_of()`, `leaf_descendants()`.
- **Connector levels** — `level="class"` for leaf connectors, container ref for aggregated.
- **No mocks in tests** — tests build real `ArchTree` instances with helpers like `_make_tree()`, `_add_elements()`.

### Frontend (TypeScript)

- **React 18 + Vite** — functional components, hooks only.
- **Canvas 2D rendering** — no SVG or DOM-based diagrams. RAF loop in `CanvasViewport`.
- **dagre** for graph layout — `computeLayout()` cached per view via `getOrComputeLayout()`.
- **Dark theme** — constants in `theme.ts` (GitHub Dark palette). No CSS variables for canvas colors.
- **State in App.tsx** — `navigationStack`, `selectedNode`, `data`. No external state management.
- **SPA routing via state** — no router. Navigation is stack-based (`pushState`/`popstate`).
- **Vitest for unit tests**, **Playwright for E2E** (`tests/side-panel.spec.ts`).

## Important Files

| File | Role |
|------|------|
| `src/tldr/__main__.py` | CLI entry point — `analyze` and `serve` subcommands |
| `src/tldr/pipeline.py` | `run_pipeline()` — the main orchestration function |
| `src/tldr/models.py` | All dataclasses + `ArchTree` with tree traversal helpers |
| `src/tldr/kotlin_analyzer.py` | Tree-sitter parser — only language-specific code |
| `src/tldr/classifier.py` | `extract_package_path()` + rule-based routing |
| `src/tldr/server.py` | `serve()` — Python HTTP server for the viewer |
| `frontend/src/App.tsx` | Root component — state, navigation, data loading |
| `frontend/src/data/types.ts` | `DiagramData`, `Element`, `Connector`, `ViewTree` interfaces |
| `frontend/src/data/loader.ts` | YAML fetch + parse + ViewTree construction |
| `frontend/src/canvas/renderer.ts` | Canvas 2D draw functions |
| `frontend/src/canvas/layout.ts` | dagre layout with caching |
| `frontend/src/theme.ts` | All visual constants (colors, dimensions, fonts) |
| `pyproject.toml` | Package metadata, dependencies, CLI script, test config |

## Runtime/Tooling Preferences

- **Python >= 3.11** — uses `from __future__ import annotations`, `match` not used but 3.11 minimum.
- **uv** — Python package manager. `uv run` for execution, `uv sync` for install.
- **Node.js** — modern version for frontend build (Vite 6).
- **Build backend** — `hatchling` (PEP 517). Package source in `src/tldr/`.
- **No Go** — the Go binary was removed. The Python server replaces `tld serve`.
- **tree-sitter + tree-sitter-kotlin** — native C extensions via Python bindings. Requires a C compiler at install time.

## Testing & QA

### Python Tests

- **Framework**: pytest
- **Config**: `pyproject.toml` → `testpaths = ["tests"]`
- **Run**: `uv run pytest tests/ -v`
- **75 tests** across 4 files:
  - `test_classifier.py` (22) — path extraction, rule routing, kind filtering, nested class exclusion
  - `test_kotlin_analyzer.py` (31) — tree-sitter parsing, imports, type refs, exclusion patterns
  - `test_splitting.py` (17) — segment extraction, group generation, recursive splitting
  - `test_aggregation.py` (6) — LCA rollup, multi-level propagation, cross-module edges
- **No conftest.py** — each test file has its own helpers
- **Test data** — inline Kotlin source strings and hand-built `ArchTree` instances

### Frontend Tests

- **Unit**: Vitest — `cd frontend && npm test`
- **E2E**: Playwright — `frontend/tests/side-panel.spec.ts`
- **Coverage**: layout, camera, renderer, hit-test, stubs, SidePanel logic, animation

### Consumer Integration

The tool is consumed via a shell script in the target repo that:
1. Clones/updates this repo
2. Builds the frontend (`npm run build:app`)
3. Runs `tldr analyze` pointing at the target source tree
4. Runs `tldr serve` with the built frontend

The consumer repo provides only `groups.yaml` (routing config) and receives `elements.yaml`/`connectors.yaml` as output.
