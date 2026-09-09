from __future__ import annotations

from .client import Repository
from src.utils.base.resource import get_path
from src.utils.message.html_tool import template2image_element


def _number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(value)


def repository_view(repo: Repository) -> dict[str, str]:
    return {
        "full_name": repo.full_name,
        "description": repo.description,
        "stars": _number(repo.stars),
        "forks": _number(repo.forks),
        "issues": _number(repo.issues),
        "language": repo.language,
        "license": repo.license_name,
        "updated_at": repo.updated_at,
        "url": repo.html_url,
    }


def repository_text(repo: Repository) -> str:
    return (
        f"GitHub 仓库：{repo.full_name}\n"
        f"{repo.description}\n"
        f"★ {repo.stars}  Fork {repo.forks}  Issues {repo.issues}\n"
        f"语言：{repo.language}｜许可证：{repo.license_name}\n"
        f"更新：{repo.updated_at}\n{repo.html_url}"
    )


async def render_repository_card(repo: Repository) -> bytes:
    template = get_path("templates/github_card.html", abs_path=True)
    if not template:
        raise FileNotFoundError("GitHub 仓库卡片模板尚未加载")
    return await template2image_element(
        template,
        {"data": repository_view(repo)},
        "body",
        wait_for="window.githubCardReady === true",
        wait_timeout=3000,
    )
