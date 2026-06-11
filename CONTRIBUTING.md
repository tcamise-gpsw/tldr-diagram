# Contributing

## Prerequisites

- Python >= 3.11, [uv](https://docs.astral.sh/uv/)
- Node.js >= 20, npm

## Setup

```bash
git clone git@github.com:tcamise-gpsw/tldr-diagram.git
cd tldr-diagram
uv sync --group dev        # Python environment
cd frontend && npm install  # Frontend dependencies
```

## Running Tests

```bash
# Python (75 tests)
uv run pytest tests/ -v

# Frontend unit tests
cd frontend && npm test

# Frontend typecheck
cd frontend && npx tsc --noEmit
```

All tests must pass before opening a PR.

## Project Layout

```
src/tldr/               Python analysis pipeline
  __main__.py           CLI entry point (analyze + serve subcommands)
  pipeline.py           Orchestration — start here
  models.py             All domain dataclasses (ArchTree, Element, Connector, etc.)
  kotlin_analyzer.py    tree-sitter Kotlin parser — the only language-specific module
  classifier.py         Config-driven element routing
  splitting.py          Auto-split oversized groups
  connectors.py         Dedup and remap connectors
  aggregation.py        LCA-based connector rollup
  server.py             HTTP server for the viewer
tests/                  Python tests (pytest)
frontend/src/           React + TypeScript viewer
  data/                 YAML loading and types
  canvas/               Rendering, layout, camera, hit testing
  components/           React components
docs/                   MkDocs documentation source
```

## Adding a Language Analyzer

`kotlin_analyzer.py` is the only language-specific module. The rest of the pipeline is language-agnostic.

To add support for a new language:

1. Create `src/tldr/<language>_analyzer.py` that returns an `AnalysisResult`:

```python
@dataclass
class AnalysisResult:
    raw_elements: dict[str, dict]   # "file_path::TypeName" -> {name, kind, file_path, line, tags}
    raw_connectors: list[dict]       # [{source, target, relationship, direction, style}]
    stats: dict[str, int]
```

2. Wire it into `pipeline.py` — select by config or file extension.
3. Add tests in `tests/test_<language>_analyzer.py`.

The classifier, splitter, connectors, aggregation, and frontend require no changes.

## Frontend

The viewer is a canvas-based React SPA. All visual constants live in `src/theme.ts`. Layout is computed by dagre and cached per view ref.

```bash
cd frontend
npm run dev          # Dev server on http://localhost:5173
npm test             # Vitest unit tests
```

The `public/` directory contains sample YAML for development — replace with your own `elements.yaml` and `connectors.yaml` to test with real data.

## Pull Requests

- Keep PRs focused — one logical change per PR.
- Include tests for new behavior.
- Update `docs/` if the change affects user-facing behavior.
- The CI workflow must pass (Python tests + frontend typecheck + frontend tests).
