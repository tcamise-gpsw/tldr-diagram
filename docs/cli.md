# CLI Reference

The `tldr` CLI has two subcommands: `analyze` and `serve`. Running `tldr` without a subcommand defaults to `analyze`.

## `tldr analyze`

Analyzes source code and generates `elements.yaml` and `connectors.yaml`.

```bash
tldr analyze --source-root <path> [options]
# or equivalently:
uv run python -m tldr analyze --source-root <path> [options]
```

### Flags

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--source-root` | Yes | — | Directory containing source files to analyze |
| `--input-dir` | No | cwd | Directory containing `groups.yaml` |
| `--output-dir` | No | input-dir | Where to write `elements.yaml` and `connectors.yaml` |
| `--repo-root` | No | auto-detect | Repository root for computing relative file paths. Auto-detected by walking up from `--source-root` to find `.git`. |
| `--max-group-size N` | No | 20 | Override the auto-split threshold. Set to 0 to disable splitting. |
| `--all-classes` | No | false | Keep all classes, even those with no connectors (skips connectivity filter). |
| `--dry-run` | No | false | Print analysis stats without writing any files. |

### Default Exclusions

The following patterns are always excluded from analysis:

```
**/*Test.kt
**/test/**
**/androidDeviceTest/**
**/androidHostTest/**
**/iosTest/**
**/commonTest/**
**/build/**
**/generated/**
**/*.kts
```

### Output

On success, writes two files to `--output-dir`:

- `elements.yaml` — all architecture elements (modules, groups, classes)
- `connectors.yaml` — all connectors (class-level + aggregated)

## `tldr serve`

Starts an HTTP server to view the diagram.

```bash
tldr serve --workspace <path> --frontend-dist <path> [options]
```

### Flags

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--workspace` | Yes | — | Directory containing `elements.yaml` and `connectors.yaml` |
| `--frontend-dist` | Yes | — | Path to the built frontend (`frontend/dist/`) |
| `--port` | No | 8060 | HTTP port |
| `--no-open` | No | false | Don't open the browser automatically |

### Server Behavior

The server serves:

- `/elements.yaml` and `/connectors.yaml` from the workspace
- All other paths from the frontend dist (SPA fallback to `index.html`)
