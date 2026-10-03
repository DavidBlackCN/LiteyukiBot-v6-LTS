from __future__ import annotations

import asyncio
import json

import pytest

from test_liteyuki_twitter_parser import html_post, modules, rss, rss_item
from test_liteyuki_twitter_state import state


class Content:
    def __init__(self, raw): self.raw = raw
    async def iter_chunked(self, _):
        split = max(1, len(self.raw) // 2)
        for start in range(0, len(self.raw), split):
            yield self.raw[start:start + split]


class Response:
    def __init__(self, raw=b"", *, status=200, content_type="application/rss+xml", headers=None):
        self.status = status
        self.headers = {"Content-Type": content_type, **(headers or {})}
        self.content_length = None
        self.content = Content(raw)
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


class Session:
    closed = False
    def __init__(self, replies): self.replies = iter(replies); self.calls = []
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = next(self.replies)
        if isinstance(response, Exception): raise response
        return response
    def post(self, url, **kwargs): return self.get(url, **kwargs)
    async def close(self): self.closed = True


def client():
    _, Config, _, _ = modules()
    from src.nonebot_plugins.liteyuki_twitter.client import NitterClient
    return NitterClient(Config(twitter_nitter_instances=["https://one.example", "https://two.example"]))


def test_rss_unsupported_fallback_and_primary_failure_switch():
    c = client()
    c.session = Session([Response(status=404), Response(('<div class="timeline">' + html_post() + '</div>').encode())])
    assert asyncio.run(c.get_timeline("example"))[0].post_id == "100"
    assert [url for url, _ in c.session.calls] == ["https://one.example/example/rss", "https://one.example/example"]
    c = client()
    c.session = Session([Response(status=503), Response(rss(rss_item()))])
    assert asyncio.run(c.get_timeline("example"))[0].post_id == "100"
    assert c.health["https://one.example"]["failures"] == 1
    assert c.session.calls[1][0].startswith("https://two.example")


@pytest.mark.parametrize("response", [Response(status=429), Response(status=403), Response(b"<html>captcha</html>")])
def test_blocked_source_does_not_cycle_mirrors(response):
    _, _, _, Error = modules()
    c = client()
    c.session = Session([response])
    with pytest.raises(Error): asyncio.run(c.get_timeline("example"))
    assert len(c.session.calls) == 1
    assert c.health["https://one.example"]["until"] > 0
    with pytest.raises(Error, match="退避"): asyncio.run(c.get_timeline("example"))
    assert len(c.session.calls) == 1


def test_post_text_mentioning_captcha_is_not_a_wall():
    c = client()
    c.session = Session([Response(rss(rss_item(description="<p>A discussion about captcha and sign in to X.</p>")))])
    assert "captcha" in asyncio.run(c.get_timeline("example"))[0].text


def test_network_timeout_backoff_and_no_false_empty():
    _, _, _, Error = modules()
    c = client()
    c.session = Session([asyncio.TimeoutError(), Response(b"not RSS")])
    with pytest.raises(Error): asyncio.run(c.get_timeline("example"))
    assert all(item["failures"] == 1 for item in c.health.values())
    with pytest.raises(Error, match="退避"): asyncio.run(c.get_timeline("example"))
    assert len(c.session.calls) == 2


def test_media_redirect_mime_and_byte_limits():
    _, _, _, Error = modules()
    c = client()
    assert c.allowed_url("https://pbs.twimg.com/media/photo.jpg", media=True)
    assert not c.allowed_url("http://pbs.twimg.com/media/photo.jpg", media=True)
    assert not c.allowed_url("https://one.example:123/pic/photo.jpg", media=True)
    assert not c.allowed_url("https://127.0.0.1/photo.jpg", media=True)
    c.session = Session([Response(status=302, headers={"Location": "http://127.0.0.1/private"})])
    with pytest.raises(Error, match="允许范围"): asyncio.run(c.download_image("https://one.example/pic/a"))
    assert len(c.session.calls) == 1
    c.session = Session([Response(b"<html>", content_type="text/html")])
    with pytest.raises(Error, match="格式"): asyncio.run(c.download_image("https://one.example/pic/a"))
    c.session = Session([Response(b"123456", content_type="image/png")])
    with pytest.raises(Error, match="大小"): asyncio.run(c.download_image("https://one.example/pic/a", max_bytes=5))


@pytest.mark.parametrize("provider", ["model", "libretranslate"])
def test_translation_backend_contract_cache_and_singleflight(tmp_path, provider):
    Config, _, store, _ = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter.translation import Translator
    config = Config(twitter_model_base_url="https://model.example/v1", twitter_model_name="test-model",
                    twitter_model_api_key="test-only", twitter_libretranslate_url="https://translate.example",
                    twitter_libretranslate_api_key="test-only")
    translator = Translator(config, store)
    data = {"choices": [{"message": {"content": "中文译文"}}]} if provider == "model" else {"translatedText": "中文译文"}
    session = Session([Response(json.dumps(data).encode(), content_type="application/json")])
    translator.session = session
    async def run():
        results = await asyncio.gather(*(translator.text("original", provider) for _ in range(4)))
        assert results == ["中文译文"] * 4
        assert await translator.text("original", provider) == "中文译文"
        await asyncio.sleep(0)
        assert translator.inflight == {}
    asyncio.run(run())
    assert len(session.calls) == 1
    url, args = session.calls[0]
    assert not args["allow_redirects"]
    if provider == "model":
        assert url.endswith("/v1/chat/completions")
        assert args["json"]["messages"][1]["content"] == "original"
        assert args["headers"]["Authorization"] == "Bearer test-only"
    else:
        assert url.endswith("/translate")
        assert args["json"]["source"] == "auto" and args["json"]["target"] == "zh"


@pytest.mark.parametrize("response", [Response(b"{}"), Response(b"bad JSON"), Response(status=429), asyncio.TimeoutError()])
def test_translation_failure_preserves_original(tmp_path, response):
    Config, Post, store, _ = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter.translation import Translator
    translator = Translator(Config(twitter_model_base_url="https://model.example/v1", twitter_model_name="test-model"), store)
    translator.session = Session([response])
    original = Post("100", "example", text="original")
    result = asyncio.run(translator.post(original, "model"))
    assert result.text == original.text and result.translation_note
    assert not original.translation_note


def test_translation_truncation_quote_budget_empty_and_unconfigured(tmp_path, monkeypatch):
    Config, Post, store, _ = state(tmp_path)
    from src.nonebot_plugins.liteyuki_twitter.translation import Translator
    translator = Translator(Config(twitter_translation_limit=100), store)
    called = []
    async def text(value, _): called.append(value); return "translated"
    monkeypatch.setattr(translator, "text", text)
    original = Post("100", "example", text="x" * 80, quote=Post("50", "other", text="q" * 40))
    result = asyncio.run(translator.post(original, "model"))
    assert list(map(len, called)) == [80, 20] and result.quote.translation_note
    assert len(result.quote.text) == 40
    called.clear()
    asyncio.run(translator.post(Post("200", "example"), "model"))
    assert called == []
    actual = Translator(Config(), store)
    result = asyncio.run(actual.post(original, "libretranslate"))
    assert "尚未配置" in result.translation_note and result.text == original.text
