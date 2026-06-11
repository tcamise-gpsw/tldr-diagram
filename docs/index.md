# TL;DR — Tool for Linking Dependency Relationships

TL;DR generates interactive architecture diagrams from source code. It uses tree-sitter to analyze class dependencies, classifies them into architectural groups via YAML config, and produces a navigable web-based viewer.

## What It Does

The analysis pipeline transforms raw source code into an interactive diagram:

```
Source code (.kt) → tree-sitter analysis → classifier → splitter → connectors → aggregation → YAML → viewer
```

Each stage refines and organizes the dependency information until it's ready for visualization.

## Key Features

- Tree-sitter-based static analysis (currently Kotlin, extensible to other languages)
- Config-driven classification via `groups.yaml` — no hardcoded project paths
- Auto-splitting of oversized groups by package segment
- LCA-based connector aggregation at every nesting level
- Interactive canvas-based viewer with drill-down navigation, pan/zoom, side panel
- Python HTTP server for viewing — no external dependencies beyond the stdlib

## Quick Links

| Page | Description |
|---|---|
| [Getting Started](getting-started.md) | Prerequisites, install, first run |
| [Configuration](configuration.md) | `groups.yaml` reference |
| [CLI Reference](cli.md) | `tldr analyze` and `tldr serve` commands |
| [Architecture](architecture.md) | How the pipeline works internally |
| [Viewer](viewer.md) | Frontend features and development |
| [Integration](integration.md) | Using tldr from another repository |
