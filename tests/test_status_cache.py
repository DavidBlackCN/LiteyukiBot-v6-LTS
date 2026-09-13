import ast
import asyncio
import time
from collections import defaultdict
from pathlib import Path


def test_status_cache_separates_markdown_mode() -> None:
    source = Path("src/nonebot_plugins/liteyuki_status/status.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {"STATUS_CACHE_TTL", "status_card_cache", "_status_render_locks", "_cache_is_fresh", "_get_status_card"}
    nodes = [
        node for node in tree.body
        if getattr(node, "name", None) in names
        or any(getattr(target, "id", None) in names for target in getattr(node, "targets", []))
        or getattr(getattr(node, "target", None), "id", None) in names
    ]
    calls = {"html": 0, "markdown": 0}

    async def data(*_args, **_kwargs):
        return {}

    async def motto():
        return ("text", "source")

    async def html(**_kwargs):
        calls["html"] += 1
        return b"html"

    async def markdown(**_kwargs):
        calls["markdown"] += 1
        return b"markdown"

    namespace = {
        "asyncio": asyncio, "time": time, "defaultdict": defaultdict,
        "get_hitokoto": motto, "get_bots_data": data, "get_hardware_data": data,
        "get_liteyuki_data": data, "generate_status_card": html,
        "generate_status_card_markdown": markdown,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "status_cache", "exec"), namespace)

    async def run():
        assert await namespace["_get_status_card"]("zh-CN", refresh=False, markdown=False, bot_id="1") == b"html"
        assert await namespace["_get_status_card"]("zh-CN", refresh=False, markdown=True, bot_id="1") == b"markdown"
        assert await namespace["_get_status_card"]("zh-CN", refresh=False, markdown=False, bot_id="1") == b"html"

    asyncio.run(run())
    assert calls == {"html": 1, "markdown": 1}
    assert set(namespace["status_card_cache"]) == {("zh-CN", False), ("zh-CN", True)}