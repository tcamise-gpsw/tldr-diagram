"""Tests for the classifier module."""

import pytest

from tldr.classifier import (
    extract_package_path,
    classify_element,
    classify_raw_elements,
    RETAINED_KINDS,
)
from tldr.models import ArchTree, GroupNode, Module, Rule


# Test constants matching the katalyst-connect project layout
TEST_PREFIX = "katalyst-connect/sdk/"
TEST_MARKER = "/com/gopro/katalyst/connect/"
class TestExtractPackagePath:
    """Tests for SDK file path → (module, package_path) extraction."""

    def test_standard_api_path(self):
        path = "katalyst-connect/sdk/connect-sdk-api/src/commonMain/kotlin/com/gopro/katalyst/connect/api/domain/usecase/MyUseCase.kt"
        result = extract_package_path(path, TEST_PREFIX, TEST_MARKER)
        assert result == ("connect-sdk-api", "api/domain/usecase")

    def test_standard_domain_path(self):
        path = "katalyst-connect/sdk/connect-sdk-domain/src/commonMain/kotlin/com/gopro/katalyst/connect/domain/model/CameraState.kt"
        result = extract_package_path(path, TEST_PREFIX, TEST_MARKER)
        assert result == ("connect-sdk-domain", "domain/model")

    def test_core_deep_path(self):
        path = "katalyst-connect/sdk/connect-sdk-core/src/commonMain/kotlin/com/gopro/katalyst/connect/core/domain/camera/setting/SettingManager.kt"
        result = extract_package_path(path, TEST_PREFIX, TEST_MARKER)
        assert result == ("connect-sdk-core", "core/domain/camera/setting")

    def test_root_package_file(self):
        """A file directly under the marker package returns empty package_path."""
        path = "katalyst-connect/sdk/connect-sdk-api/src/commonMain/kotlin/com/gopro/katalyst/connect/RootFile.kt"
        result = extract_package_path(path, TEST_PREFIX, TEST_MARKER)
        assert result == ("connect-sdk-api", "")

    def test_non_sdk_path_returns_none(self):
        path = "katalyst-connect/tools/tld/main.go"
        assert extract_package_path(path, TEST_PREFIX, TEST_MARKER) is None

    def test_no_marker_returns_none(self):
        path = "katalyst-connect/sdk/connect-sdk-core/src/commonMain/kotlin/SomeFile.kt"
        assert extract_package_path(path, TEST_PREFIX, TEST_MARKER) is None

    def test_too_short_path_returns_none(self):
        path = "katalyst-connect/sdk/"
        assert extract_package_path(path, TEST_PREFIX, TEST_MARKER) is None


class TestClassifyElement:
    """Tests for module + package_path → group classification."""

    RULES = [
        Rule(module="connect-sdk-api", prefix="api/domain/usecase", group="use-cases"),
        Rule(module="connect-sdk-api", prefix="api/domain/model", group="api-models"),
        Rule(module="connect-sdk-api", prefix="api", group="api-internal"),
        Rule(module="connect-sdk-core", prefix="core/domain/camera/setting", group="core-settings"),
        Rule(module="connect-sdk-core", prefix="core", group="core-infrastructure"),
        Rule(module="connect-sdk-domain", prefix="domain/model", group="domain-models"),
        Rule(module="connect-sdk-domain", prefix="domain", group="domain-other"),
    ]

    def test_specific_prefix_wins(self):
        group, is_catch_all = classify_element("connect-sdk-api", "api/domain/usecase/commands", self.RULES)
        assert group == "use-cases"
        assert not is_catch_all

    def test_catch_all_detected(self):
        group, is_catch_all = classify_element("connect-sdk-api", "api/something/unknown", self.RULES)
        assert group == "api-internal"
        assert is_catch_all

    def test_core_specific_prefix(self):
        group, is_catch_all = classify_element("connect-sdk-core", "core/domain/camera/setting/foo", self.RULES)
        assert group == "core-settings"
        assert not is_catch_all

    def test_core_catch_all(self):
        group, is_catch_all = classify_element("connect-sdk-core", "core/util/something", self.RULES)
        assert group == "core-infrastructure"
        assert is_catch_all

    def test_no_matching_module(self):
        group, is_catch_all = classify_element("connect-sdk-di", "di/something", self.RULES)
        assert group is None
        assert not is_catch_all

    def test_no_matching_prefix(self):
        group, is_catch_all = classify_element("connect-sdk-domain", "other/path", self.RULES)
        assert group is None
        assert not is_catch_all

    def test_first_rule_wins(self):
        """When multiple rules match, the first one in order wins."""
        group, _ = classify_element("connect-sdk-api", "api/domain/model/sub", self.RULES)
        assert group == "api-models"

    def test_domain_catch_all(self):
        group, is_catch_all = classify_element("connect-sdk-domain", "domain/exception/SomeException", self.RULES)
        assert group == "domain-other"
        assert is_catch_all


class TestRetainedKinds:
    """Tests for element kind filtering."""

    def test_class_retained(self):
        assert "class" in RETAINED_KINDS

    def test_interface_retained(self):
        assert "interface" in RETAINED_KINDS

    def test_enum_not_retained(self):
        assert "enum" not in RETAINED_KINDS

    def test_function_not_retained(self):
        assert "function" not in RETAINED_KINDS


class TestClassifyRawElements:
    """Tests for full classification pipeline including nested class filtering."""

    RULES = [
        Rule(module="connect-sdk-core", prefix="core/domain/camera/setting", group="core-settings"),
        Rule(module="connect-sdk-core", prefix="core", group="core-infra"),
    ]

    def _make_tree(self):
        return ArchTree(
            modules={"core": Module(ref="core", name="Core", description="")},
            groups={
                "core-settings": GroupNode(
                    ref="core-settings", name="Settings", description="", parent_ref="core"
                ),
                "core-infra": GroupNode(
                    ref="core-infra", name="Infra", description="", parent_ref="core"
                ),
            },
            elements={},
            rules=self.RULES,
            source_prefix=TEST_PREFIX,
            package_marker=TEST_MARKER,
        )

    def test_interface_classified(self):
        """Interfaces are retained and classified like classes."""
        raw = {
            "sym-iface": {
                "kind": "interface",
                "name": "SettingsRepository",
                "file_path": "katalyst-connect/sdk/connect-sdk-core/src/commonMain/kotlin/com/gopro/katalyst/connect/core/domain/camera/setting/repository/SettingsRepository.kt",
            }
        }
        tree = self._make_tree()
        elements, unmapped, _ = classify_raw_elements(raw, tree)
        assert len(elements) == 1
        assert elements[0].name == "SettingsRepository"
        assert elements[0].kind == "interface"

    def test_nested_class_filtered(self):
        """Nested classes (name contains '.') are excluded."""
        raw = {
            "sym-parent": {
                "kind": "class",
                "name": "FlatModeIdentifier",
                "file_path": "katalyst-connect/sdk/connect-sdk-core/src/commonMain/kotlin/com/gopro/katalyst/connect/core/domain/camera/setting/FlatModeIdentifier.kt",
            },
            "sym-nested": {
                "kind": "class",
                "name": "FlatModeIdentifier.Defined",
                "file_path": "katalyst-connect/sdk/connect-sdk-core/src/commonMain/kotlin/com/gopro/katalyst/connect/core/domain/camera/setting/FlatModeIdentifier.kt",
            },
        }
        tree = self._make_tree()
        elements, _, _ = classify_raw_elements(raw, tree)
        names = [e.name for e in elements]
        assert "FlatModeIdentifier" in names
        assert "FlatModeIdentifier.Defined" not in names

    def test_enum_not_classified(self):
        """Enums are not retained."""
        raw = {
            "sym-enum": {
                "kind": "enum",
                "name": "SettingId",
                "file_path": "katalyst-connect/sdk/connect-sdk-core/src/commonMain/kotlin/com/gopro/katalyst/connect/core/domain/camera/setting/SettingId.kt",
            }
        }
        tree = self._make_tree()
        elements, _, _ = classify_raw_elements(raw, tree)
        assert len(elements) == 0
