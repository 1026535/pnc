"""Static graph proofs use synthetic source strings that must never execute."""

import unittest

from tools.test_selection.python_graph import build_graph


class PythonGraphTests(unittest.TestCase):
    def test_absolute_alias_imports_and_transitive_consumers(self) -> None:
        graph = build_graph({
            "pkg/value.py": "raise RuntimeError('analysis executed source')",
            "pkg/service.py": "import pkg.value as value",
            "tests/unit/test_service.py": "from pkg.service import Service",
            "tests/unit/test_other.py": "import json",
        })
        self.assertEqual(graph.consumers({"pkg.value"}), {
            "pkg.value", "pkg.service", "tests.unit.test_service",
        })
        self.assertFalse(graph.uncertain)

    def test_old_and_new_edges_are_unioned(self) -> None:
        old = {"pkg/old.py": "", "pkg/consumer.py": "import pkg.old",
               "tests/unit/test_api.py": "import pkg.consumer"}
        new = {"pkg/new.py": "", "pkg/consumer.py": "import pkg.new",
               "tests/unit/test_api.py": "import pkg.consumer"}
        graph = build_graph(old, new)
        for changed in ("pkg.old", "pkg.new"):
            with self.subTest(changed=changed):
                self.assertIn("tests.unit.test_api", graph.consumers({changed}))

    def test_union_order_does_not_change_graph(self) -> None:
        old = {"a.py": "import b", "b.py": ""}
        new = {"a.py": "", "b.py": "import a"}
        self.assertEqual(build_graph(old, new), build_graph(new, old))

    def test_cycle_terminates_and_unrelated_roots_stay_out(self) -> None:
        graph = build_graph({"a.py": "import b", "b.py": "import a", "c.py": ""})
        self.assertEqual(graph.consumers({"a"}), {"a", "b"})
        self.assertEqual(graph.consumers({"missing"}), {"missing"})
        self.assertEqual(graph.consumers(set()), set())

    def test_multiple_roots_union_consumers(self) -> None:
        graph = build_graph({"a.py": "", "b.py": "", "c.py": "import a, b"})
        self.assertEqual(graph.consumers({"a", "b"}), {"a", "b", "c"})

    def test_relative_from_symbol_tracks_defining_module(self) -> None:
        graph = build_graph({
            "pkg/model.py": "class Model: pass",
            "pkg/nested/service.py": "from ..model import Model as LocalModel",
            "tests/unit/test_service.py": "import pkg.nested.service",
        })
        self.assertEqual(graph.consumers({"pkg.model"}), {
            "pkg.model", "pkg.nested.service", "tests.unit.test_service",
        })

    def test_relative_from_dot_submodule(self) -> None:
        graph = build_graph({"pkg/a.py": "", "pkg/b.py": "from . import a"})
        self.assertIn("pkg.b", graph.consumers({"pkg.a"}))

    def test_relative_import_inside_package_init_uses_package_itself(self) -> None:
        graph = build_graph({"pkg/__init__.py": "from .model import Model", "pkg/model.py": ""})
        self.assertIn("pkg", graph.consumers({"pkg.model"}))

    def test_package_initialization_tracks_all_ancestor_packages(self) -> None:
        graph = build_graph({
            "pkg/__init__.py": "", "pkg/nested/__init__.py": "",
            "pkg/nested/leaf.py": "", "tests/unit/test_leaf.py": "import pkg.nested.leaf",
            "other/__init__.py": "", "other/leaf.py": "",
        })
        self.assertEqual(graph.consumers({"pkg"}), {
            "pkg", "pkg.nested", "pkg.nested.leaf", "tests.unit.test_leaf",
        })
        self.assertEqual(graph.consumers({"pkg.nested"}), {
            "pkg.nested", "pkg.nested.leaf", "tests.unit.test_leaf",
        })

    def test_star_import_retains_module_dependency(self) -> None:
        graph = build_graph({"pkg/a.py": "", "pkg/b.py": "from pkg.a import *"})
        self.assertIn("pkg.b", graph.consumers({"pkg.a"}))

    def test_imports_in_function_and_type_checking_branches_are_retained(self) -> None:
        graph = build_graph({
            "pkg/a.py": "", "pkg/b.py": "",
            "pkg/consumer.py": "if TYPE_CHECKING:\n    import pkg.a\ndef load():\n    import pkg.b\n",
        })
        for name in ("pkg.a", "pkg.b"):
            with self.subTest(name=name):
                self.assertIn("pkg.consumer", graph.consumers({name}))

    def test_lazy_exports_plain_and_annotated_tables(self) -> None:
        for assignment in ("_LAZY_EXPORTS =", "_LAZY_EXPORTS: dict[str, tuple[str, str]] ="):
            with self.subTest(assignment=assignment):
                graph = build_graph({
                    "pkg/__init__.py": assignment + " {'Thing': ('pkg.impl', 'Thing')}\n",
                    "pkg/impl.py": "class Thing: pass",
                    "tests/unit/test_facade.py": "from pkg import Thing",
                })
                self.assertIn("tests.unit.test_facade", graph.consumers({"pkg.impl"}))
                self.assertFalse(graph.uncertain)

    def test_literal_dynamic_imports_resolve(self) -> None:
        for call in ("importlib.import_module('pkg.impl')", "__import__('pkg.impl')"):
            with self.subTest(call=call):
                graph = build_graph({"pkg/impl.py": "", "pkg/client.py": call})
                self.assertIn("pkg.client", graph.consumers({"pkg.impl"}))
                self.assertFalse(graph.uncertain)

    def test_unmodeled_execution_and_imports_are_uncertain(self) -> None:
        sources = ["importlib.import_module(module_name)", "__import__(name)",
                   "importlib.import_module('.impl', 'pkg')", "exec(code)", "eval(code)",
                   "runpy.run_path(path)", "runpy.run_module(name)",
                   "importlib.util.spec_from_file_location(name, path)",
                   "from ...missing import x", "def broken(:", "_LAZY_EXPORTS = make_exports()"]
        for source in sources:
            with self.subTest(source=source):
                self.assertIn("pkg.client", build_graph({"pkg/client.py": source}).uncertain)

    def test_invalid_old_snapshot_cannot_be_erased_by_valid_new_snapshot(self) -> None:
        graph = build_graph({"pkg/a.py": "def broken(:"}, {"pkg/a.py": ""})
        self.assertIn("pkg.a", graph.uncertain)

    def test_empty_graph_is_valid_but_establishes_no_edges(self) -> None:
        graph = build_graph({}, {})
        self.assertEqual(graph.reverse, {})
        self.assertEqual(graph.uncertain, set())

    def test_lazy_export_marker_in_comment_does_not_hide_dynamic_import(self) -> None:
        source = "# _LAZY_EXPORTS is unrelated\nimportlib.import_module(target)"
        self.assertIn("pkg.client", build_graph({"pkg/client.py": source}).uncertain)

    def test_valid_lazy_table_does_not_hide_unrelated_dynamic_import(self) -> None:
        source = "_LAZY_EXPORTS = {'Thing': ('pkg.impl', 'Thing')}\nimportlib.import_module(unrelated_plugin)"
        self.assertIn("pkg.client", build_graph({"pkg/client.py": source}).uncertain)

    def test_malformed_lazy_values_are_uncertain_instead_of_crashing(self) -> None:
        for value in ("'pkg.impl'", "[]", "[[]]", "[4]", "{}", "None"):
            with self.subTest(value=value):
                graph = build_graph({"pkg/client.py": "_LAZY_EXPORTS = {'Thing': " + value + "}"})
                self.assertIn("pkg.client", graph.uncertain)

    def test_alias_of_dynamic_import_is_not_silently_treated_as_static(self) -> None:
        source = "from importlib import import_module as load\nload(plugin_name)"
        self.assertIn("pkg.client", build_graph({"pkg/client.py": source}).uncertain)
