"""Lazy exports create caller edges without pulling in unrelated submodules."""

import unittest

from tools.test_selection.python_graph import build_graph


def export_sources(caller: str) -> dict[str, str]:
    return {
        "pkg/__init__.py": "_LAZY_EXPORTS = {'Thing': ('pkg.impl', 'Thing'), 'Other': ('pkg.other', 'Other')}\n",
        "pkg/impl.py": "class Thing: pass\n",
        "pkg/other.py": "class Other: pass\n",
        "pkg/unrelated.py": "pass\n",
        "tests/unit/test_caller.py": caller,
        "tests/unit/test_unrelated.py": "import pkg.unrelated\n",
    }


class LazyExportGraphTests(unittest.TestCase):
    def assert_requested_export(self, caller: str) -> None:
        graph = build_graph(export_sources(caller))
        consumers = graph.consumers({"pkg.impl"})
        self.assertIn("tests.unit.test_caller", consumers)
        self.assertNotIn("pkg", consumers)
        self.assertNotIn("pkg.unrelated", consumers)
        self.assertNotIn("tests.unit.test_unrelated", consumers)
        self.assertFalse(graph.uncertain)

    def test_table_alone_and_unrelated_submodule_do_not_request_export(self) -> None:
        graph = build_graph(export_sources("import pkg.unrelated\n"))
        self.assertEqual(graph.consumers({"pkg.impl"}), {"pkg.impl"})
        self.assertEqual(graph.consumers({"pkg.other"}), {"pkg.other"})

    def test_bare_package_import_does_not_request_export(self) -> None:
        graph = build_graph(export_sources("import pkg\n"))
        self.assertNotIn("tests.unit.test_caller", graph.consumers({"pkg.impl"}))

    def test_from_package_import_named_export(self) -> None:
        self.assert_requested_export("from pkg import Thing\n")

    def test_from_package_import_export_as_alias(self) -> None:
        self.assert_requested_export("from pkg import Thing as LocalThing\n")

    def test_package_attribute_requests_export(self) -> None:
        self.assert_requested_export("import pkg\nthing = pkg.Thing()\n")

    def test_package_import_alias_attribute_requests_export(self) -> None:
        self.assert_requested_export("import pkg as facade\nthing = facade.Thing()\n")

    def test_package_getattr_requests_export(self) -> None:
        self.assert_requested_export("import pkg\nthing = getattr(pkg, 'Thing')\n")

    def test_aliased_package_getattr_requests_export(self) -> None:
        self.assert_requested_export("import pkg as facade\nthing = getattr(facade, 'Thing')\n")

    def test_dynamic_getattr_conservatively_reaches_every_export(self) -> None:
        graph = build_graph(export_sources("import pkg as facade\nthing = getattr(facade, export_name)\n"))
        for module in ("pkg.impl", "pkg.other"):
            with self.subTest(module=module):
                self.assertIn("tests.unit.test_caller", graph.consumers({module}))

    def test_named_export_does_not_request_other_export(self) -> None:
        graph = build_graph(export_sources("from pkg import Thing\n"))
        self.assertNotIn("tests.unit.test_caller", graph.consumers({"pkg.other"}))

    def test_star_import_reaches_every_export(self) -> None:
        graph = build_graph(export_sources("from pkg import *\n"))
        for module in ("pkg.impl", "pkg.other"):
            with self.subTest(module=module):
                self.assertIn("tests.unit.test_caller", graph.consumers({module}))

    def test_dotted_package_alias_and_attribute_chains(self) -> None:
        callers = (
            "import root.facade\nthing = root.facade.Thing()\n",
            "import root.facade as alias\nthing = alias.Thing()\n",
            "from root import facade as alias\nthing = alias.Thing()\n",
        )
        for caller in callers:
            with self.subTest(caller=caller):
                graph = build_graph({
                    "root/__init__.py": "",
                    "root/facade/__init__.py": "_LAZY_EXPORTS = {'Thing': ('root.impl', 'Thing')}",
                    "root/impl.py": "", "tests/unit/test_caller.py": caller,
                })
                self.assertIn("tests.unit.test_caller", graph.consumers({"root.impl"}))
                self.assertNotIn("root.facade", graph.consumers({"root.impl"}))

    def test_relative_from_export_in_package_module(self) -> None:
        snapshot = export_sources("")
        snapshot["pkg/caller.py"] = "from . import Thing as LocalThing\n"
        self.assertIn("pkg.caller", build_graph(snapshot).consumers({"pkg.impl"}))

    def test_changed_export_target_retains_both_base_and_head_consumers(self) -> None:
        old = export_sources("from pkg import Thing\n")
        new = export_sources("from pkg import Thing\n")
        new["pkg/__init__.py"] = "_LAZY_EXPORTS = {'Thing': ('pkg.replacement', 'Thing')}\n"
        new["pkg/replacement.py"] = "class Thing: pass\n"
        graph = build_graph(old, new)
        for module in ("pkg.impl", "pkg.replacement"):
            with self.subTest(module=module):
                self.assertIn("tests.unit.test_caller", graph.consumers({module}))
                self.assertNotIn("tests.unit.test_unrelated", graph.consumers({module}))

    def test_removed_lazy_export_use_retains_old_consumer(self) -> None:
        graph = build_graph(export_sources("from pkg import Thing\n"), export_sources("pass\n"))
        self.assertIn("tests.unit.test_caller", graph.consumers({"pkg.impl"}))

    def test_getattr_on_dotted_package_expression_requests_export(self) -> None:
        graph = build_graph({
            "root/__init__.py": "",
            "root/facade/__init__.py": "_LAZY_EXPORTS = {'Thing': ('root.impl', 'Thing')}",
            "root/impl.py": "",
            "tests/unit/test_caller.py": "import root.facade\nthing = getattr(root.facade, 'Thing')\n",
        })
        self.assertIn("tests.unit.test_caller", graph.consumers({"root.impl"}))
