from __future__ import annotations

import re
from urllib.parse import urlsplit

from nonebot import get_plugin_config, logger, on_message, require
from nonebot.adapters import Event
from nonebot.matcher import Matcher
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import UniMessage

from .client import GitHubCardError, GitHubClient
from .config import GitHubCardConfig
from .render import render_repository_card, repository_text


__plugin_meta__ = PluginMetadata(
    name="GitHub 仓库卡片",
    description="自动识别 GitHub 仓库主页链接并展示仓库信息。",
    usage="发送 GitHub 仓库主页链接，例如 https://github.com/owner/repo",
    type="application",
    homepage="https://github.com/ElainaFanBoy/nonebot_plugin_githubcard",
    config=GitHubCardConfig,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"liteyuki": True, "lts_builtin": True, "help_category": "builtin"},
)

config = get_plugin_config(GitHubCardConfig)

_URL_CANDIDATE = re.compile(r"https?://(?:www\.)?github\.com/[^\s<>]+", re.IGNORECASE)
_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+\Z")
_TRAILING_PUNCTUATION = ".,!?;:，。！？；：)]}>\"'”’"


def extract_repository_links(text: str) -> list[tuple[str, str]]:
    """Return unique GitHub repository roots, excluding all sub-pages."""
    repositories: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in _URL_CANDIDATE.finditer(text):
        candidate = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        parsed = urlsplit(candidate)
        if parsed.hostname not in {"github.com", "www.github.com"}:
            continue
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            continue
        owner, repo = parts
        if not _OWNER.fullmatch(owner) or not _REPO.fullmatch(repo):
            continue
        key = (owner.lower(), repo.lower())
        if key not in seen:
            seen.add(key)
            repositories.append((owner, repo))
    return repositories


github_card = on_message(priority=80, block=False)


@github_card.handle()
async def handle_github_link(event: Event, matcher: Matcher) -> None:
    repositories = extract_repository_links(event.get_plaintext())
    if not repositories:
        return
    owner, repo = repositories[0]
    try:
        async with GitHubClient(config.githubcard_token, config.githubcard_timeout) as client:
            repository = await client.repository(owner, repo)
    except GitHubCardError as exc:
        logger.info(f"GitHub 仓库卡片请求失败: {owner}/{repo}: {exc}")
        await matcher.send(exc.user_message)
        return

    try:
        image = await render_repository_card(repository)
    except Exception as exc:
        logger.warning(f"GitHub 仓库卡片渲染失败，改用文本: {owner}/{repo}: {exc!r}")
        await matcher.send(repository_text(repository))
        return
    await matcher.send(UniMessage.image(raw=image))
