import asyncio
import ast
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("card_background_test", ROOT / "src/utils/message/card_background.py")
bg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bg)


@pytest.fixture(autouse=True)
def reset():
    bg._cache_url = bg._cache_image = None
    bg._next_request = 0
    bg._lock = asyncio.Lock()


def config(**kwargs):
    return bg.CardBackgroundConfig(card_background_enabled=True, card_background_url="https://example.test/image", **kwargs)


class Response:
    url = "https://example.test/final"
    def __init__(self, body=b"png", media="image/png", error=None, length=None):
        self.body, self.error = body, error
        self.headers = {"Content-Type": media}
        self.content_length = length
        self.content = self
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def raise_for_status(self):
        if self.error: raise self.error
    async def iter_chunked(self, size):
        yield self.body


class Session:
    calls = 0
    response = Response()
    def __init__(self, **kwargs): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    def get(self, url):
        Session.calls += 1
        return Session.response


def test_config_precedence():
    result = bg.resolve_config({"status_background_enabled": True, "status_background_url": "old",
        "card_background_enabled": False, "card_background_url": ""})
    assert not result.card_background_enabled and result.card_background_url == ""
    result = bg.resolve_config({"status_background_enabled": True, "status_background_mask": 0.2})
    assert result.card_background_enabled and result.card_background_mask == 0.2
    assert bg.resolve_config({"card_background_timeout": -1}).card_background_timeout == 6


def test_disabled_and_empty():
    with patch.object(bg.aiohttp, "ClientSession", side_effect=AssertionError("must not request")):
        assert asyncio.run(bg.get_card_background(config=bg.CardBackgroundConfig()))["image"] is None
        assert asyncio.run(bg.get_card_background(config=bg.CardBackgroundConfig(card_background_enabled=True)))["image"] is None


def test_success_and_concurrent_cache():
    Session.calls, Session.response = 0, Response()
    async def run():
        results = await asyncio.gather(*(bg.get_card_background(config=config()) for _ in range(5)))
        assert all(r["image"] == "data:image/png;base64,cG5n" for r in results)
        assert Session.calls == 1
    with patch.object(bg.aiohttp, "ClientSession", Session): asyncio.run(run())


@pytest.mark.parametrize("response", [
    Response(media="text/html"), Response(error=asyncio.TimeoutError()),
    Response(error=aiohttp.ClientResponseError(None, (), status=503, message="unavailable")),
    Response(length=bg.CARD_BACKGROUND_MAX_BYTES + 1),
    Response(body=b"x" * (bg.CARD_BACKGROUND_MAX_BYTES + 1)), Response(body=b""),
])
def test_failure_with_and_without_cache(response):
    Session.calls, Session.response = 0, response
    # Avoid formatting ClientResponseError's missing mock request_info in logs.
    if isinstance(response.error, aiohttp.ClientResponseError):
        response.error.request_info = SimpleNamespace(real_url="https://example.test")
    with patch.object(bg.aiohttp, "ClientSession", Session):
        assert asyncio.run(bg.get_card_background(config=config()))["image"] is None
        bg._next_request = 0
        bg._cache_image = "data:image/png;base64,cached"
        assert asyncio.run(bg.get_card_background(config=config()))["image"].endswith("cached")
        calls = Session.calls
        asyncio.run(bg.get_card_background(config=config()))
        assert Session.calls == calls  # Failure backoff also avoids request storms.


def test_url_change_does_not_leak_cache():
    bg._cache_url, bg._cache_image = "https://old.test", "old image"
    Session.response = Response(media="text/html")
    with patch.object(bg.aiohttp, "ClientSession", Session):
        assert asyncio.run(bg.get_card_background(config=config()))["image"] is None


def test_status_context_uses_public_background():
    # Execute the real rendering function with its dependencies mocked, no plugin init.
    source = (ROOT / "src/nonebot_plugins/trimo_status/api.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_status_card")
    from unittest.mock import AsyncMock
    renderer = AsyncMock(return_value=b"png")
    background = AsyncMock(return_value={"image": "sample", "mask": 0.2})
    namespace = {"get_card_background": background, "get_local_data": AsyncMock(return_value={}),
        "template2image_element": renderer, "get_path": lambda p, **kwargs: p,
        "status_config": SimpleNamespace(status_acknowledgement="")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "status_function", "exec"), namespace)
    asyncio.run(namespace["generate_status_card"]({}, {}, {}))
    assert renderer.call_args.args[1]["data"]["background"]["image"] == "sample"


def test_only_opt_in_templates_include_background():
    root = ROOT / "src/resources/vanilla_resource/templates"
    status = (root / "status.html").read_text(encoding="utf-8")
    help_html = (ROOT / "src/resources/liteyuki_help_menu/templates/help_menu.html").read_text(encoding="utf-8")
    weather_html = (ROOT / "src/resources/liteyuki_weather/templates/weather_now.html").read_text(encoding="utf-8")
    for template in (status, help_html, weather_html):
        assert "card_background.css" in template
    assert 'id="card-background-image"' in help_html and 'id="card-background-image"' in weather_html
    for plugin in ("npm.py", "rpm.py"):
        assert "get_card_background" not in (ROOT / "src/nonebot_plugins/liteyuki_pacman" / plugin).read_text(encoding="utf-8")
