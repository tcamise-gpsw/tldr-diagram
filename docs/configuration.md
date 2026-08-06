# Configuration

The tool is driven by a single `groups.yaml` file in the workspace directory.

## File Structure

The file has four top-level keys:

```yaml
modules:    # Top-level containers
groups:     # Architecture components (children of modules or other groups)
rules:      # Package prefix routing
settings:   # Tool behavior
```

## Modules

Modules are the highest-level containers, shown at the root view.

```yaml
modules:
  api:
    name: API
    description: Use case layer.
  core:
    name: Core
    description: SDK implementation.
  domain:
    name: Domain
    description: Domain models and contracts.
```

The key (e.g. `api`) becomes the module's `ref` used in rules and group parents.

## Groups

Groups are architecture components nested under modules or other groups. N-level nesting is supported.

```yaml
groups:
  core-network:
    name: Network
    description: Transport layer.
    parent: core

  core-network-ble:
    name: BLE
    description: Bluetooth Low Energy transport.
    parent: core-network    # nested under another group
```

The `parent` field references a module key or another group key.

### Auto-Group Overrides

An entry without `parent` customizes the group that auto-splitting creates for
the same generated ref:

```yaml
groups:
  core--network--ble:
    name: BLE
    summary: Bluetooth transport.
```

Set `inline: true` when a package bucket should remain visible as individual
elements in its generated parent instead of becoming another group:

```yaml
groups:
  core--network--connection:
    inline: true
    summary: Connection orchestration.
```

The override is considered matched when auto-splitting encounters that package
bucket, even though no group node is created.

### Explicit Groups Under Generated Hierarchies

A rule may target a configured parentless group directly. The generated ref
encodes its parent using `parent--segment`; configured ancestors are materialized
as needed. This supports curated grouping without replacing the surrounding
auto-generated hierarchy:

```yaml
groups:
  core--network:
    name: Network
    summary: Network implementation.
  core--network--protocol:
    name: Protocol
    summary: Wire protocol implementation.

rules:
  - module: my-core
    prefix: core/network/protocol
    group: core--network--protocol
  - module: my-core
    prefix: core/network
    group: core--network
```

More-specific rules must appear before less-specific rules.

## Rules

Rules route elements to groups based on `(module, package_prefix)`. They are evaluated in order — first match wins.

```yaml
rules:
  - module: my-sdk-core
    prefix: core/network/ble
    group: core-network-ble

  - module: my-sdk-core
    prefix: core/network
    group: core-network

  - module: my-sdk-core
    prefix: core
    group: core-infra          # catch-all
```

!!! warning
    Put more-specific prefixes before less-specific ones. A bare module prefix (no `/`) is a catch-all and is flagged in the output.

## Settings

```yaml
settings:
  max_group_size: 20
  source_prefix: "sdk/"
  package_marker: "/com/example/myproject/"
```

| Key | Default | Description |
|-----|---------|-------------|
| `source_prefix` | `""` | Stripped from file paths to find the module directory. Example: if files are at `sdk/my-module/src/.../Foo.kt`, use `"sdk/"`. |
| `package_marker` | `""` | Sub-path that marks where architecture-relevant packages start. Example: `"/com/example/myproject/"` — everything after this becomes the package path used for rule matching. |
| `max_group_size` | `20` | Groups with more elements are auto-split by next package segment. Set to `0` to disable. |

## How Classification Works

For each source file:

1. Strip `source_prefix` from the file path → first segment is the module name
2. Find `package_marker` in the remaining path → everything after it (minus filename) is the package path
3. Match `(module, package_path)` against rules in order → first matching prefix wins → element is placed in that group

### Example

```
File: sdk/my-core/src/main/kotlin/com/example/myproject/core/network/ble/Scanner.kt
source_prefix: "sdk/"
→ module: "my-core"
package_marker: "/com/example/myproject/"
→ package_path: "core/network/ble"
Rule match: (my-core, core/network/ble) → core-network-ble
```
