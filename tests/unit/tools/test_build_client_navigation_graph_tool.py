"""Client navigation graph extraction tests."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support.paths import REPOSITORY_ROOT

_REGISTRY = """
WinsPreFabType.BAG_WIN = "UI/UIModules/Bag/BagWin.prefab"
WinsPreFabType.InsectFarmMainWin = 'UI/UIModules/InsectFarm/InsectFarmMainWin.prefab'
WinsPreFabType.MAIN = "UI/UIModules/Main/MainPanel.prefab"
"""

_SCENES = """
SceneName.CITY_SCENE = "CityScene/CityScene.unity";
SceneName.WORLD_MAP = 'WorldMap/WorldMapScene.unity';
"""

_HUD = """
function MainPanel:OnPackBtn()
\tWinsManager.instance:OpenWin(WinsPreFabType.BAG_WIN, LayerManager.instance.UI);
\tWinsManager.instance:OpenWin(WinsPreFabType.InsectFarmMainWin, LayerManager.instance.TOP_UI);
end

function MainPanel:OnCityBtn()
\tWinsManager.instance:CloseWin(WinsPreFabType.BAG_WIN, false);
\tWinsManager.instance:OpenWin(WinsPreFabType.GHOST_WIN, LayerManager.instance.UI);
\tWinsManager.instance:OpenWin(WinsPreFabType[dynamicName], LayerManager.instance.UI);
\tGameLevelManager:LoadLevel(SceneName.CITY_SCENE, nil, nil, false, nil, nil);
end
"""

_OVERRIDE = """
if useNewUi then
\tWinsPreFabType.MAIN = "UI/UIModules/Main/MainPanelNew.prefab"
end
"""


class BuildClientNavigationGraphToolTests(unittest.TestCase):
    """Validates static extraction against a synthetic recovered-Lua tree."""

    def setUp(self) -> None:
        self.module = _load_tool_module()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source = Path(directory.name)
        _write(self.source / "uis" / "winsprefabtype.lua", _REGISTRY)
        _write(self.source / "scenename.lua", _SCENES)
        _write(self.source / "uis" / "main" / "mainpanel.lua", _HUD)
        _write(self.source / "datas" / "override.lua", _OVERRIDE)
        self.document = self.module.build_graph_document(self.source)

    def test_registry_accepts_mixed_case_names_and_both_quote_styles(self) -> None:
        """Registers camel-case and single-quoted window entries alongside upper-case ones."""

        windows = {window["name"]: window for window in self.document["windows"]}

        self.assertIn("InsectFarmMainWin", windows)
        self.assertEqual(
            "UI/UIModules/InsectFarm/InsectFarmMainWin.prefab",
            windows["InsectFarmMainWin"]["prefab"],
        )
        self.assertEqual({"CITY_SCENE", "WORLD_MAP"}, set(self.document["scenes"]))

    def test_window_rebound_outside_the_registry_records_every_declaring_module(self) -> None:
        """Records each module that binds a window so runtime overrides stay visible."""

        windows = {window["name"]: window for window in self.document["windows"]}

        self.assertEqual(
            ["uis/winsprefabtype.lua", "datas/override.lua"],
            list(windows["MAIN"]["declared_in"]),
        )

    def test_call_sites_carry_kind_layer_and_enclosing_function(self) -> None:
        """Separates traversal from dismissal and attributes each edge to its call site."""

        edges = {(edge["target"], edge["kind"]): edge for edge in self.document["window_edges"]}

        self.assertEqual("MainPanel:OnPackBtn", edges[("BAG_WIN", "OpenWin")]["function"])
        self.assertEqual("UI", edges[("BAG_WIN", "OpenWin")]["layer"])
        self.assertEqual("TOP_UI", edges[("InsectFarmMainWin", "OpenWin")]["layer"])
        self.assertEqual("MainPanel:OnCityBtn", edges[("BAG_WIN", "CloseWin")]["function"])
        self.assertEqual("uis/main", edges[("BAG_WIN", "OpenWin")]["source_group"])

    def test_scene_loads_are_extracted_separately(self) -> None:
        """Reports LoadLevel call sites as scene edges rather than window edges."""

        self.assertEqual(
            [("uis/main/mainpanel.lua", "CITY_SCENE")],
            [(edge["source_module"], edge["target"]) for edge in self.document["scene_edges"]],
        )

    def test_coverage_counts_unregistered_and_non_constant_targets(self) -> None:
        """Distinguishes a referenced-but-unregistered window from a dynamic OpenWin argument."""

        coverage = self.document["coverage"]

        self.assertEqual(1, coverage["unregistered_targets"])
        self.assertEqual(1, coverage["untyped_open_calls"])
        self.assertEqual(3, coverage["registered_windows"])


def _write(path: Path, text: str) -> None:
    """Writes one synthetic Lua module, creating its parent directories."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_tool_module(module_name: str = "codex_test_navigation_graph_tool") -> object:
    """Loads the navigation graph tool directly from disk for isolated unit testing."""

    module_path = REPOSITORY_ROOT / "tools" / "build_client_navigation_graph.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load tool module from '{module_path}'.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
