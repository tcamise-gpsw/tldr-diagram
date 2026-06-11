# Getting Started

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) — Python package manager
- Node.js >= 20 — for building the frontend
- A `groups.yaml` config file for your project (see [Configuration](configuration.md))

## Install

```bash
git clone git@github.com:tcamise-gpsw/tldr-diagram.git
cd tldr-diagram
```

No global install needed — `uv run` handles the Python environment automatically.

## Build the Frontend

```bash
cd frontend
npm install
npm run build:app
cd ..
```

This produces `frontend/dist/` which the serve command needs.

## First Run

Assuming you have a workspace directory with `groups.yaml` and access to the source code:

```bash
# Analyze
uv run python -m tldr analyze \
  --source-root /path/to/kotlin/sources \
  --input-dir /path/to/workspace

# View
uv run python -m tldr serve \
  --workspace /path/to/workspace \
  --frontend-dist frontend/dist
```

Opens at `http://127.0.0.1:8060/views`.

## Dry Run

To see analysis stats without writing files:

```bash
uv run python -m tldr analyze --source-root /path/to/sources --dry-run
```

!!! tip
    The `--repo-root` flag is auto-detected by walking up from `--source-root` to find `.git`. Only specify it if the source tree is outside the repo.
