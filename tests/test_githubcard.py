from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import httpx
import nonebot
import pytest


PAYLOAD = {
    "owner": {"login": "LiteyukiStudio"},
    "name": "LiteyukiBot-v6-LTS",
    "full_name": "LiteyukiStudio/LiteyukiBot-v6-LTS",
    "description": "Liteyuki LTS",
    "stargazers_count": 1532,
    "forks_count": 42,
    "open_issues_count": 7,
    "language": "Python",
    "license": {"spdx_id": "MIT"},
    "updated_at": "2026-09-10T12:34:56Z",
    "html_url": "https://github.com/LiteyukiStudio/LiteyukiBot-v6-LTS",
}


def _plugin():
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    plugin = nonebot.get_plugin("liteyuki_githubcard")
    return plugin or nonebot.load_plugin("src.nonebot_plugins.liteyuki_githubcard")


def test_repository_link_extraction_ignores_subpages_and_duplicates() -> None:
    _plugin()
    from src.nonebot_plugins.liteyuki_githubcard import extract_repository_links

    text = """
    https://github.com/Owner/repo https://github.com/owner/repo/
    https://github.com/Owner/repo/issues/1
    https://github.com/Owner/repo/releases/tag/v1
    https://github.com/Owner/repo/commit/abcdef
    https://github.com/Owner/repo/tree/main
    (https://github.com/Another/project?tab=readme).
    """
    assert extract_repository_links(text) == [("Owner", "repo"), ("Another", "project")]


def test_card_template_uses_shared_liteyuki_assets() -> None:
    template = Path("src/resources/liteyuki_githubcard/templates/github_card.html").read_text(
        encoding="utf-8"
    )
    for asset in ("./css/card.css", "./css/fonts.css", "./js/card.js"):
        assert asset in template
    assert '{{ data | tojson }}' in template
    assert "window.githubCardReady" in template
    assert "http://" not in template and "https://" not in template


def test_anonymous_request_and_repository_normalization() -> None:
    from src.nonebot_plugins.liteyuki_githubcard.client import GitHubClient

    async def run() -> None:
        async with GitHubClient() as client:
            assert client._client is not None
            assert "authorization" not in client._client.headers
            assert client._client.headers["accept"] == "application/vnd.github+json"

        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=PAYLOAD))
        async with httpx.AsyncClient(transport=transport) as http_client:
            async with GitHubClient(http_client=http_client) as client:
                repository = await client.repository("LiteyukiStudio", "LiteyukiBot-v6-LTS")
        assert repository.full_name == PAYLOAD["full_name"]
        assert repository.stars == 1532
        assert repository.license_name == "MIT"
        assert repository.updated_at == "2026-09-10 12:34 UTC"

    asyncio.run(run())


@pytest.mark.parametrize(
    ("status", "headers", "error_type"),
    [
        (404, {}, "GitHubRepositoryNotFound"),
        (403, {"X-RateLimit-Remaining": "0"}, "GitHubRateLimited"),
        (429, {}, "GitHubRateLimited"),
    ],
)
def test_not_found_and_rate_limit_are_friendly(status: int, headers: dict[str, str], error_type: str) -> None:
    from src.nonebot_plugins.liteyuki_githubcard import client as github_client

    async def run() -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(status, headers=headers))
        async with httpx.AsyncClient(transport=transport) as http_client:
            async with github_client.GitHubClient(http_client=http_client) as client:
                with pytest.raises(getattr(github_client, error_type)) as error:
                    await client.repository("owner", "repo")
        if status == 404:
            assert "私有仓库" in error.value.user_message

    asyncio.run(run())


def test_network_failure_and_render_fallback_do_not_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    _plugin()
    import src.nonebot_plugins.liteyuki_githubcard as githubcard
    from src.nonebot_plugins.liteyuki_githubcard.client import GitHubRequestFailed, Repository

    async def check_network() -> None:
        def failing_transport(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(failing_transport)) as http_client:
            async with githubcard.GitHubClient(http_client=http_client) as client:
                with pytest.raises(GitHubRequestFailed):
                    await client.repository("owner", "repo")

    asyncio.run(check_network())

    repository = Repository.from_api(PAYLOAD)

    class FakeClient:
        def __init__(self, *args: object):
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def repository(self, owner: str, repo: str) -> Repository:
            return repository

    class FakeMatcher:
        def __init__(self) -> None:
            self.messages: list[object] = []

        async def send(self, message: object) -> None:
            self.messages.append(message)

    async def render_failure(repo: Repository) -> bytes:
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr(githubcard, "GitHubClient", FakeClient)
    monkeypatch.setattr(githubcard, "render_repository_card", render_failure)
    matcher = FakeMatcher()
    event = SimpleNamespace(get_plaintext=lambda: "https://github.com/LiteyukiStudio/LiteyukiBot-v6-LTS")
    asyncio.run(githubcard.handle_github_link(event, matcher))
    assert "GitHub 仓库：LiteyukiStudio/LiteyukiBot-v6-LTS" in str(matcher.messages[0])


def test_image_is_sent_through_unimessage_not_regular_matcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _plugin()
    import src.nonebot_plugins.liteyuki_githubcard as githubcard
    from src.nonebot_plugins.liteyuki_githubcard.client import Repository

    repository = Repository.from_api(PAYLOAD)
    sent: list[bytes] = []

    class FakeClient:
        def __init__(self, *args: object):
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def repository(self, owner: str, repo: str) -> Repository:
            return repository

    class OutgoingImage:
        async def send(self) -> None:
            sent.append(b"png")

    class FakeUniMessage:
        @staticmethod
        def image(*, raw: bytes) -> OutgoingImage:
            assert raw == b"png"
            return OutgoingImage()

    class FakeMatcher:
        async def send(self, message: object) -> None:
            raise AssertionError(f"image must not be passed to Matcher.send: {message!r}")

    async def render_success(repo: Repository) -> bytes:
        return b"png"

    monkeypatch.setattr(githubcard, "GitHubClient", FakeClient)
    monkeypatch.setattr(githubcard, "UniMessage", FakeUniMessage)
    monkeypatch.setattr(githubcard, "render_repository_card", render_success)
    event = SimpleNamespace(get_plaintext=lambda: "https://github.com/LiteyukiStudio/LiteyukiBot-v6-LTS")
    asyncio.run(githubcard.handle_github_link(event, FakeMatcher()))
    assert sent == [b"png"]
