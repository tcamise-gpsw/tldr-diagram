"""Tests for config loading — module rule targets and auto-group overrides."""

import textwrap

from tldr.config import load_config


def _write(tmp_path, text: str):
    p = tmp_path / "groups.yaml"
    p.write_text(textwrap.dedent(text))
    return p


def test_rule_can_target_module(tmp_path):
    cfg = _write(tmp_path, """
        modules:
          data:
            name: Data
        rules:
          - module: connect-sdk-core
            prefix: core/v2
            group: data
    """)
    tree = load_config(cfg)
    assert "data" in tree.modules
    assert tree.rules[0].group == "data"


def test_group_without_parent_becomes_override(tmp_path):
    cfg = _write(tmp_path, """
        modules:
          data:
            name: Data
        groups:
          data--camera--ble:
            name: BLE
            docs: Bluetooth stack.
        rules:
          - module: connect-sdk-core
            prefix: core/v2
            group: data
    """)
    tree = load_config(cfg)
    # Stored as an override, NOT a structural group node.
    assert "data--camera--ble" not in tree.groups
    assert tree.group_overrides["data--camera--ble"] == {
        "name": "BLE",
        "docs": "Bluetooth stack.",
    }


def test_structural_group_with_parent_still_works(tmp_path):
    cfg = _write(tmp_path, """
        modules:
          data:
            name: Data
        groups:
          data-core:
            name: Core
            parent: data
        rules:
          - module: connect-sdk-core
            prefix: core/v2
            group: data-core
    """)
    tree = load_config(cfg)
    assert "data-core" in tree.groups
    assert tree.groups["data-core"].parent_ref == "data"
    assert "data-core" not in tree.group_overrides
