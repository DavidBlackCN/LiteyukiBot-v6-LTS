import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("help_category_test", Path("src/nonebot_plugins/liteyuki_help_menu/catalog.py"))
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)


@pytest.mark.parametrize("module,extra,kind,expected", [
    ("nonebot_plugin_htmlrender", {}, "", "system"),
    ("nonebot_plugin_alconna.uniseg", {}, "", "system"),
    ("dependency", {"liteyuki": True}, "library", "system"),
    ("src.nonebot_plugins.trimo_status", {}, "", "basic"),
    ("native", {"liteyuki": True}, "", "basic"),
    ("src.nonebot_plugins.liteyuki_group_manager", {"lts_builtin": True}, "", "builtin"),
    ("src.nonebot_plugins.liteyuki_help_menu", {"lts_builtin": True, "category": "system"}, "", "builtin"),
    ("nonebot_plugin_remind", {}, "", "third_party"),
    ("unknown", {}, "", "third_party"),
    ("unknown", {"help_category": "system", "lts_builtin": True}, "", "system"),
])
def test_category(module, extra, kind, expected):
    assert catalog.category_of(module, extra, kind) == expected


def test_home_four_categories():
    home = catalog.page_context([], "")
    assert [c["name"] for c in home["categories"]] == ["系统插件", "基础插件", "内置插件", "第三方插件"]
