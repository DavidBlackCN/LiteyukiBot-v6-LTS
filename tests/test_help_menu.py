import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/nonebot_plugins/liteyuki_help_menu"
spec = importlib.util.spec_from_file_location("help_catalog_tests", SOURCE / "catalog.py")
catalog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(catalog)
spec = importlib.util.spec_from_file_location("help_config_tests", SOURCE / "config.py")
config_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_module)
Config = config_module.HelpMenuConfig


def plugin(name="weather", module="src.nonebot_plugins.weather", **extra):
    return NS(name=name, module_name=module, metadata=NS(
        name="轻雪天气", description="查询当前天气", usage="/weather 深圳",
        type="application", homepage="", supported_adapters=None, extra=extra))


def test_metadata_and_source():
    items = catalog.collect_plugins([plugin(category="utility")], Config())
    assert items[0]["category_label"] == "实用工具"
    assert items[0]["source"] == "LTS 内置"
    assert catalog.source_of("other", {"liteyuki": True}) == "Liteyuki 原生"
    assert catalog.source_of("other", {}) == "第三方 NoneBot"
    item = catalog.collect_plugins([NS(name="missing", module_name="missing", metadata=None)], Config())[0]
    assert item["name"] == "missing" and item["category"] == "other"


@pytest.mark.parametrize("mode", ["hidden", "library", "config", "third_party"])
def test_filter(mode):
    p, c = plugin(), Config()
    if mode == "hidden": p.metadata.extra["hidden"] = True
    if mode == "library": p.metadata.type = "library"
    if mode == "config": c.help_menu_hidden_plugins = [p.module_name]
    if mode == "third_party":
        p.module_name = "external"
        c.help_menu_show_third_party = False
    assert not catalog.collect_plugins([p], c)


@pytest.mark.parametrize("query", ["天气", "WEATHER", "查询", "深圳", "qingxue", "qxtq"])
def test_search(query):
    items = catalog.collect_plugins([plugin()], Config())
    assert catalog.search_plugins(items, query)


def test_pagination_and_detail():
    items = catalog.collect_plugins([plugin(str(n), category="utility") for n in range(23)], Config())
    assert len(catalog.page_context(items, "工具 2")["items"]) == 10
    assert len(catalog.page_context(items, "工具 3")["items"]) == 3
    with pytest.raises(ValueError): catalog.page_context(items, "工具 4")
    p = plugin(help_commands=[{"command": "天气 深圳", "description": "查询"}])
    items = catalog.collect_plugins([p], Config())
    detail = catalog.page_context(items, "weather")["detail"]
    assert detail["commands"][0]["command"] == "天气 深圳"
    assert detail["usage"] == "/weather 深圳"
    p.metadata.usage = "长" * 4000
    items = catalog.collect_plugins([p], Config())
    assert catalog.page_context(items, "weather 3")["detail"]["usage"] == "长" * 400


@pytest.mark.parametrize("query", ["", "全部", "weather", "搜索 无匹配"])
def test_template_context(query):
    items = catalog.collect_plugins([plugin()], Config())
    items[0]["description"] = "</div><script>alert(1)</script>"
    data = catalog.page_context(items, query)
    env = Environment(loader=FileSystemLoader(ROOT / "src/resources/liteyuki_help_menu/templates"))
    html = env.get_template("help_menu.html").render(data=data)
    assert '<script>alert(1)</script>' not in html
    assert 'id="data"' in html and './css/card.css' in html
    assert data["pages"] >= 1


def test_disabled_load_and_commands(tmp_path):
    source = '''
import asyncio
import nonebot
nonebot.init(help_menu_enabled=False)
p = nonebot.load_plugin("src.nonebot_plugins.liteyuki_help_menu")
assert p is not None and not p.matcher
'''
    result = subprocess.run([sys.executable, "-c", source], cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_enabled_load_and_mock_render():
    source = '''
import asyncio
from unittest.mock import AsyncMock
import nonebot
nonebot.init()
p = nonebot.load_plugin("src.nonebot_plugins.liteyuki_help_menu")
assert p is not None and p.matcher
from src.nonebot_plugins.liteyuki_help_menu import handlers as h
assert h.menu.priority == 0 and h.menu.block
assert h.parse_request("帮助 工具 2", {"/"}) == "工具 2"
assert h.parse_request("/help weather", {"/"}) == "weather"
assert h.parse_request("菜单", {"/"}) == ""
assert h.parse_request("帮助我一下", {"/"}) is None
h.get_path = lambda _: "mock.html"
h.template2image_element = AsyncMock(return_value=b"png")
async def main():
    assert await h.render_menu({"title":"a"}) == b"png"
    assert await h.render_menu({"title":"a"}) == b"png"
    assert h.template2image_element.await_count == 1
    await h.render_menu({"title":"b"})
    assert h.template2image_element.await_count == 2
asyncio.run(main())
'''
    result = subprocess.run([sys.executable, "-c", source], cwd=ROOT,
        env=dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8"),
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
