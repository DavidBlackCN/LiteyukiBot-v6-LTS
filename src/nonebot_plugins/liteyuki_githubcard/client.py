from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx


GITHUB_API_BASE = "https://api.github.com"


class GitHubCardError(RuntimeError):
    user_message = "GitHub 仓库信息暂时不可用，请稍后重试。"


class GitHubRepositoryNotFound(GitHubCardError):
    user_message = "未找到该仓库，或它是当前无权访问的私有仓库。"


class GitHubRateLimited(GitHubCardError):
    user_message = "GitHub API 当前已限流，请稍后重试或配置 githubcard_token。"


class GitHubAccessDenied(GitHubCardError):
    user_message = "GitHub 拒绝了本次请求，请检查 Token 权限。"


class GitHubRequestFailed(GitHubCardError):
    user_message = "GitHub API 请求失败，请稍后重试。"


@dataclass(frozen=True)
class Repository:
    owner: str
    name: str
    full_name: str
    description: str
    stars: int
    forks: int
    issues: int
    language: str
    license_name: str
    updated_at: str
    html_url: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "Repository":
        owner_data = payload.get("owner")
        owner = str(owner_data.get("login", "")) if isinstance(owner_data, dict) else ""
        name = str(payload.get("name", ""))
        full_name = str(payload.get("full_name", ""))
        html_url = str(payload.get("html_url", ""))
        if not owner or not name or not full_name or not html_url:
            raise GitHubRequestFailed("GitHub API 返回的仓库数据不完整")
        license_data = payload.get("license")
        license_name = "未声明"
        if isinstance(license_data, dict):
            license_name = str(license_data.get("spdx_id") or license_data.get("name") or license_name)
        return cls(
            owner=owner,
            name=name,
            full_name=full_name,
            description=str(payload.get("description") or "暂无简介"),
            stars=_integer(payload.get("stargazers_count")),
            forks=_integer(payload.get("forks_count")),
            issues=_integer(payload.get("open_issues_count")),
            language=str(payload.get("language") or "未标注"),
            license_name=license_name,
            updated_at=_format_timestamp(payload.get("updated_at")),
            html_url=html_url,
        )


def _integer(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _format_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "未知"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


class GitHubClient:
    def __init__(
        self,
        token: str = "",
        timeout: float = 8.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = str(token or "").strip()
        self.timeout = timeout
        self._client = http_client
        self._owns_client = http_client is None

    async def __aenter__(self) -> "GitHubClient":
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": "LiteyukiBot-v6-LTS-GitHubCard",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 5.0)),
                headers=headers,
            )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def repository(self, owner: str, repo: str) -> Repository:
        if self._client is None:
            raise RuntimeError("GitHubClient must be used as an async context manager")
        try:
            response = await self._client.get(
                f"{GITHUB_API_BASE}/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
            )
        except httpx.TimeoutException as exc:
            raise GitHubRequestFailed("GitHub API 请求超时") from exc
        except httpx.HTTPError as exc:
            raise GitHubRequestFailed("GitHub API 网络请求失败") from exc

        if response.status_code == 404:
            raise GitHubRepositoryNotFound()
        if response.status_code in {403, 429}:
            if response.status_code == 429 or response.headers.get("X-RateLimit-Remaining") == "0":
                raise GitHubRateLimited()
            raise GitHubAccessDenied()
        if response.status_code == 401:
            raise GitHubAccessDenied()
        if response.is_error:
            raise GitHubRequestFailed(f"GitHub API 返回 HTTP {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GitHubRequestFailed("GitHub API 返回无效 JSON") from exc
        if not isinstance(payload, dict):
            raise GitHubRequestFailed("GitHub API 返回的数据格式无效")
        return Repository.from_api(payload)
