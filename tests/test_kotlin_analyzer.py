"""Tests for the kotlin_analyzer module."""

import pytest

from tldr.kotlin_analyzer import (
    parse_file,
    analyze_sources,
    _should_exclude,
    _collect_user_types,
    _split_kdoc,
    _PARSER,
    AnalyzedFile,
)


class TestParseFileImports:
    """Tests for import extraction."""

    def test_single_import(self):
        source = b"import com.gopro.katalyst.connect.core.Foo\n\nclass Bar"
        result = parse_file(source, "test.kt")
        assert result.imports == {"Foo": "com.gopro.katalyst.connect.core.Foo"}

    def test_multiple_imports(self):
        source = b"""import com.example.Alpha
import com.example.Beta
import org.other.Gamma

class Test
"""
        result = parse_file(source, "test.kt")
        assert result.imports == {
            "Alpha": "com.example.Alpha",
            "Beta": "com.example.Beta",
            "Gamma": "org.other.Gamma",
        }

    def test_wildcard_import_skipped(self):
        source = b"""import com.example.*
import com.example.Specific

class Test
"""
        result = parse_file(source, "test.kt")
        assert ".*" not in str(result.imports)
        assert result.imports == {"Specific": "com.example.Specific"}

    def test_no_imports(self):
        source = b"class Foo"
        result = parse_file(source, "test.kt")
        assert result.imports == {}


class TestParseFileElements:
    """Tests for class/interface element extraction."""

    def test_single_class(self):
        source = b"class MyClass"
        result = parse_file(source, "src/MyClass.kt")
        assert len(result.elements) == 1
        assert result.elements[0].name == "MyClass"
        assert result.elements[0].kind == "class"
        assert result.elements[0].file_path == "src/MyClass.kt"

    def test_interface(self):
        source = b"interface MyInterface"
        result = parse_file(source, "src/MyInterface.kt")
        assert len(result.elements) == 1
        assert result.elements[0].name == "MyInterface"
        assert result.elements[0].kind == "interface"

    def test_object_skipped(self):
        source = b"object Singleton"
        result = parse_file(source, "src/Singleton.kt")
        assert len(result.elements) == 0

    def test_multi_class_file(self):
        source = b"""class First
class Second
interface Third
"""
        result = parse_file(source, "src/Multi.kt")
        assert len(result.elements) == 3
        names = [e.name for e in result.elements]
        assert names == ["First", "Second", "Third"]

    def test_nested_class_not_extracted(self):
        source = b"""class Outer {
    class Inner
}
"""
        result = parse_file(source, "src/Outer.kt")
        # Only top-level class is extracted; nested classes are hidden
        assert len(result.elements) == 1
        assert result.elements[0].name == "Outer"

    def test_line_numbers(self):
        source = b"""import com.example.Foo

class First

class Second
"""
        result = parse_file(source, "src/Test.kt")
        assert result.elements[0].line == 3
        assert result.elements[1].line == 5

    def test_private_class_excluded(self):
        source = b"private class Impl"
        result = parse_file(source, "src/Impl.kt")
        assert len(result.elements) == 0

    def test_private_interface_excluded(self):
        source = b"private interface Contract"
        result = parse_file(source, "src/Contract.kt")
        assert len(result.elements) == 0

    def test_internal_class_included(self):
        source = b"internal class Worker"
        result = parse_file(source, "src/Worker.kt")
        assert len(result.elements) == 1
        assert result.elements[0].name == "Worker"

    def test_private_sibling_excluded_public_kept(self):
        source = b"class Public\nprivate class Hidden"
        result = parse_file(source, "src/Mixed.kt")
        assert len(result.elements) == 1
        assert result.elements[0].name == "Public"


class TestParseFileTypeRefs:
    """Tests for per-class type reference collection."""

    def test_constructor_param_types(self):
        source = b"""import com.example.Dep

class MyClass(private val dep: Dep)
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "Dep" in result.elements[0].type_refs

    def test_supertype_ref(self):
        source = b"""import com.example.Base

class MyClass : Base()
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "Base" in result.elements[0].supertypes
        assert "Base" not in result.elements[0].type_refs

    def test_interface_implementation(self):
        source = b"""import com.example.MyInterface

class MyClass : MyInterface
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "MyInterface" in result.elements[0].supertypes
        assert "MyInterface" not in result.elements[0].type_refs

    def test_property_type(self):
        source = b"""import com.example.Logger

class MyClass {
    private val logger: Logger = Logger()
}
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "Logger" in result.elements[0].type_refs

    def test_function_return_type(self):
        source = b"""import com.example.Result

class MyClass {
    fun doWork(): Result = TODO()
}
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "Result" in result.elements[0].type_refs

    def test_function_param_type(self):
        source = b"""import com.example.Request

class MyClass {
    fun handle(request: Request) {}
}
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "Request" in result.elements[0].type_refs

    def test_self_reference_excluded(self):
        source = b"""class MyClass {
    companion object {
        fun create(): MyClass = MyClass()
    }
}
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "MyClass" not in result.elements[0].type_refs

    def test_multi_class_scoped_refs(self):
        """Each class gets only its own type refs, not the other class's."""
        source = b"""import com.example.DepA
import com.example.DepB

class ClassA(val dep: DepA)

class ClassB(val dep: DepB)
"""
        result = parse_file(source, "src/Multi.kt")
        class_a = next(e for e in result.elements if e.name == "ClassA")
        class_b = next(e for e in result.elements if e.name == "ClassB")
        assert "DepA" in class_a.type_refs
        assert "DepB" not in class_a.type_refs
        assert "DepB" in class_b.type_refs
        assert "DepA" not in class_b.type_refs

    def test_nested_class_types_not_attributed_to_parent(self):
        """Type refs in nested class body don't bleed into parent."""
        source = b"""import com.example.ParentDep
import com.example.NestedDep

class Parent(val dep: ParentDep) {
    class Nested(val dep: NestedDep)
}
"""
        result = parse_file(source, "src/Parent.kt")
        parent = next(e for e in result.elements if e.name == "Parent")
        assert "ParentDep" in parent.type_refs
        assert "NestedDep" not in parent.type_refs

    def test_generic_type_params(self):
        source = b"""import com.example.Wrapper

class MyClass {
    val items: List<Wrapper> = emptyList()
}
"""
        result = parse_file(source, "src/MyClass.kt")
        assert "Wrapper" in result.elements[0].type_refs


class TestShouldExclude:
    """Tests for file exclusion pattern matching."""

    def test_test_file_pattern(self):
        assert _should_exclude("module/src/FooTest.kt", ["**/*Test.kt"])

    def test_test_dir_pattern(self):
        assert _should_exclude("module/src/test/Foo.kt", ["**/test/**"])

    def test_build_dir_pattern(self):
        assert _should_exclude("module/build/gen/Foo.kt", ["**/build/**"])

    def test_no_match(self):
        assert not _should_exclude("module/src/main/Foo.kt", ["**/test/**", "**/*Test.kt"])

    def test_kts_pattern(self):
        assert _should_exclude("module/build.gradle.kts", ["**/*.kts"])

    def test_module_exclude(self):
        assert _should_exclude(
            "katalyst-connect/sdk/connect-sdk-api-external/src/Foo.kt",
            ["katalyst-connect/sdk/connect-sdk-api-external/**"],
        )

    def test_non_excluded_module(self):
        assert not _should_exclude(
            "katalyst-connect/sdk/connect-sdk-core/src/Foo.kt",
            ["katalyst-connect/sdk/connect-sdk-api-external/**"],
        )


class TestCollectUserTypes:
    """Tests for _collect_user_types AST traversal."""

    def _parse_class_body(self, body_source: str) -> set[str]:
        """Helper: parse a class with body and return collected types."""
        full_source = f"class Test {{\n{body_source}\n}}".encode()
        tree = _PARSER.parse(full_source)
        root = tree.root_node
        # Find the class_body node
        class_decl = root.children[0]
        for child in class_decl.children:
            if child.type == "class_body":
                types: set[str] = set()
                _collect_user_types(child, types)
                return types
        return set()

    def test_simple_property(self):
        types = self._parse_class_body("val x: String = \"\"")
        assert "String" in types

    def test_multiple_types(self):
        types = self._parse_class_body("""
    val a: Alpha = Alpha()
    val b: Beta = Beta()
""")
        assert "Alpha" in types
        assert "Beta" in types

    def test_skips_nested_class(self):
        types = self._parse_class_body("""
    val outer: OuterDep = OuterDep()
    class Nested(val dep: NestedDep)
""")
        assert "OuterDep" in types
        assert "NestedDep" not in types


class TestImportedBodyRefs:
    """Identifiers used in function bodies, object access, etc. that match imports."""

    def test_constructor_call_in_function_body(self):
        source = b"""import com.example.SetShutterCommand

class DefaultGateway {
    fun execute(on: Boolean) {
        sender.send(SetShutterCommand(on))
    }
}
"""
        result = parse_file(source, "test.kt")
        assert "SetShutterCommand" in result.elements[0].type_refs

    def test_companion_object_access(self):
        source = b"""import com.example.DeviceResponse

class DefaultGateway {
    fun check(r: Any) {
        if (r == DeviceResponse.NotSupported) return
    }
}
"""
        result = parse_file(source, "test.kt")
        assert "DeviceResponse" in result.elements[0].type_refs

    def test_sealed_class_branch(self):
        source = b"""import com.example.ConnectionState

class Manager {
    fun handle(s: Any) {
        if (s is ConnectionState.Connected) doWork()
    }
}
"""
        result = parse_file(source, "test.kt")
        assert "ConnectionState" in result.elements[0].type_refs

    def test_non_imported_identifier_excluded(self):
        """Identifiers without a matching import are not added."""
        source = b"""class Foo {
    fun run() { localHelper() }
}
"""
        result = parse_file(source, "test.kt")
        assert "localHelper" not in result.elements[0].type_refs

    def test_import_ref_scoped_to_class_not_sibling(self):
        """Import used only in ClassA's body must not appear in ClassB's refs."""
        source = b"""import com.example.Alpha
import com.example.Beta

class ClassA {
    fun run() { Alpha.create() }
}

class ClassB {
    fun run() { Beta.process() }
}
"""
        result = parse_file(source, "test.kt")
        a = next(e for e in result.elements if e.name == "ClassA")
        b = next(e for e in result.elements if e.name == "ClassB")
        assert "Alpha" in a.type_refs
        assert "Beta" not in a.type_refs
        assert "Beta" in b.type_refs
        assert "Alpha" not in b.type_refs

    def test_nested_class_body_not_attributed_to_outer(self):
        """Import used only in nested class must not appear in outer class refs."""
        source = b"""import com.example.OuterDep
import com.example.InnerDep

class Outer {
    fun run() { OuterDep.call() }
    class Inner {
        fun run() { InnerDep.call() }
    }
}
"""
        result = parse_file(source, "test.kt")
        outer = next(e for e in result.elements if e.name == "Outer")
        assert "OuterDep" in outer.type_refs
        assert "InnerDep" not in outer.type_refs


class TestParseFileModuleVals:
    """Tests for Koin `Module` val detection (DI composition manifests)."""

    def test_detects_module_val_by_type_annotation(self):
        source = b"val dataModule: Module = module { single { Foo() } }\n"
        result = parse_file(source, "DataModule.kt")
        mods = [e for e in result.elements if e.kind == "di_module"]
        assert [e.name for e in mods] == ["dataModule"]

    def test_detects_module_val_by_initializer(self):
        # No explicit `: Module` type; detected via the `module { }` initializer.
        source = b"val servicesModule = module { single { Bar() } }\n"
        result = parse_file(source, "ServicesModule.kt")
        assert any(
            e.kind == "di_module" and e.name == "servicesModule"
            for e in result.elements
        )

    def test_plain_val_and_object_are_not_module_vals(self):
        source = b"val count = 5\nobject Thing\nclass Real"
        result = parse_file(source, "Misc.kt")
        assert all(e.kind != "di_module" for e in result.elements)
        # A real class in the same file is still detected normally.
        assert any(e.name == "Real" and e.kind == "class" for e in result.elements)


class TestModuleValConnectors:
    """A class importing a Koin `Module` val gets an edge to that val's module."""

    def test_module_val_import_creates_edge(self, tmp_path):
        repo = tmp_path
        src = repo / "src"
        (src / "data").mkdir(parents=True)
        (src / "api").mkdir(parents=True)
        (src / "data" / "DataModule.kt").write_bytes(
            b"package com.example.data\n"
            b"import org.koin.core.module.Module\n"
            b"import org.koin.dsl.module\n"
            b"val dataModule: Module = module { }\n"
        )
        (src / "api" / "Sdk.kt").write_bytes(
            b"package com.example.api\n"
            b"import com.example.data.dataModule\n"
            b"class Sdk { fun wire() { modules(dataModule) } }\n"
        )

        result = analyze_sources(repo_root=repo, source_root=src)

        # The Module val is retained as a di_module element.
        assert any(e["kind"] == "di_module" for e in result.raw_elements.values())
        # Sdk -> dataModule edge exists despite the reference being a value, not a type.
        sdk_key = "src/api/Sdk.kt::Sdk"
        dm_key = "src/data/DataModule.kt::dataModule"
        assert any(
            c["source"] == sdk_key and c["target"] == dm_key
            for c in result.raw_connectors
        )


class TestSplitKdoc:
    """Tests for KDoc summary/description extraction."""

    def test_summary_is_first_sentence_description_is_full_prose(self):
        raw = "/**\n * First sentence. Second sentence.\n */"
        summary, desc = _split_kdoc(raw)
        assert summary == "First sentence."
        assert desc == "First sentence. Second sentence."

    def test_block_tags_are_dropped(self):
        raw = "/**\n * Connects to a camera.\n *\n * @param device the camera\n * @return a handle\n */"
        summary, desc = _split_kdoc(raw)
        assert summary == "Connects to a camera."
        assert desc == "Connects to a camera."

    def test_oneliner(self):
        assert _split_kdoc("/** Owns the Koin application. */") == (
            "Owns the Koin application.",
            "Owns the Koin application.",
        )

    def test_non_kdoc_block_comment_ignored(self):
        assert _split_kdoc("/* plain comment */") == ("", "")


class TestParseFileKdoc:
    """KDoc attaches to the immediately following declaration only."""

    def test_kdoc_attached_to_class(self):
        result = parse_file(b"/**\n * A widget repository.\n */\nclass WidgetRepo", "W.kt")
        e = next(e for e in result.elements if e.name == "WidgetRepo")
        assert e.summary == "A widget repository."
        assert e.doc == "A widget repository."

    def test_kdoc_attached_to_module_val(self):
        result = parse_file(b"/** The data DI module. */\nval dataModule: Module = module { }", "D.kt")
        e = next(e for e in result.elements if e.name == "dataModule")
        assert e.kind == "di_module"
        assert e.summary == "The data DI module."

    def test_line_comment_is_not_kdoc(self):
        result = parse_file(b"// not a doc\nclass Foo", "F.kt")
        e = next(e for e in result.elements if e.name == "Foo")
        assert e.summary == ""
        assert e.doc == ""

    def test_kdoc_not_leaked_to_next_declaration(self):
        result = parse_file(b"/** Doc for A. */\nclass A\nclass B", "AB.kt")
        a = next(e for e in result.elements if e.name == "A")
        b = next(e for e in result.elements if e.name == "B")
        assert a.summary == "Doc for A."
        assert b.summary == ""
