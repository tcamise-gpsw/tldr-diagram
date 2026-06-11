# Integration

## Using TL;DR from Another Repository

TL;DR is designed to be consumed from a target repository via a thin shell script. Your repo provides the project-specific configuration; TL;DR provides the analysis engine and viewer.

### What Your Repo Needs

```
your-project/docs/architecture/
├── groups.yaml                    # Your routing rules
├── generate-architecture-diagram.sh  # Wrapper script
├── elements.yaml                  # Generated output (gitignored or committed)
└── connectors.yaml                # Generated output
```

### Example Wrapper Script

```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TLDR_REPO="${TLDR_REPO:-$SCRIPT_DIR/.tldr}"

# Clone or update
if [ ! -d "$TLDR_REPO/.git" ]; then
  git clone git@github.com:tcamise-gpsw/tldr-diagram.git "$TLDR_REPO"
else
  git -C "$TLDR_REPO" pull --ff-only 2>/dev/null || true
fi

# Build frontend (skip if up-to-date)
if [ ! -d "$TLDR_REPO/frontend/dist" ]; then
  (cd "$TLDR_REPO/frontend" && npm install --silent && npm run build:app)
fi

# Analyze
uv run --project "$TLDR_REPO" python -m tldr analyze \
  --input-dir "$SCRIPT_DIR" \
  --source-root "$REPO_ROOT/src" \
  --repo-root "$REPO_ROOT" \
  "$@"

# Serve
uv run --project "$TLDR_REPO" python -m tldr serve \
  --workspace "$SCRIPT_DIR" \
  --frontend-dist "$TLDR_REPO/frontend/dist"
```

!!! tip
    Set `TLDR_REPO` environment variable to point to an existing clone and avoid re-cloning.

### Example `groups.yaml`

```yaml
modules:
  api:
    name: API
    description: Public API layer.
  core:
    name: Core
    description: Business logic.

groups:
  core-network:
    name: Network
    description: HTTP and WebSocket clients.
    parent: core

rules:
  - module: my-sdk-core
    prefix: core/network
    group: core-network
  - module: my-sdk-core
    prefix: core
    group: core-infra

settings:
  source_prefix: "src/"
  package_marker: "/com/example/myapp/"
  max_group_size: 20
```

### Gitignore

Add to your `.gitignore`:

```
# TL;DR cloned tool
.tldr/
```

Decide whether to commit `elements.yaml` and `connectors.yaml` (useful for PR diffs showing architecture changes) or gitignore them (regenerated on demand).
