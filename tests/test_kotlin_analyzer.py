"""Tests for the kotlin_analyzer module."""

import pytest

from tldr.kotlin_analyzer import (
    parse_file,
    _should_exclude,
    _collect_user_types,
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
