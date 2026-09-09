from __future__ import annotations

from dataclasses import dataclass, field


class SetuError(RuntimeError):
    """A controlled error which may be presented to a user."""


class UnsafeQueryError(SetuError):
    pass


class UnsupportedQueryError(SetuError):
    pass


class ProviderError(SetuError):
    pass


class ProviderUnavailableError(ProviderError):
    pass


class NoResultError(ProviderError):
    pass


@dataclass(frozen=True)
class ImageQuery:
    count: int = 3
    keyword: str | None = None
    tags: list[str] = field(default_factory=list)
    uid: list[int] = field(default_factory=list)
    size: str = "regular"
    exclude_ai: bool = True
    orientation: str | None = None
    provider: str = "auto"
    r18: bool = False


@dataclass(frozen=True)
class ImageResult:
    provider: str
    image_url: str
    pid: int | str | None = None
    uid: int | str | None = None
    title: str | None = None
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    width: int | None = None
    height: int | None = None
    ai_type: int | None = None
    is_adult: bool | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    random: bool = True
    count: bool = True
    keyword: bool = False
    tags: bool = False
    uid: bool = False
    size: bool = False
    exclude_ai: bool = False
    orientation: bool = False
    metadata: bool = False
    safe_classification: bool = False
    r18: bool = False


def is_result_allowed(result: ImageResult, *, r18: bool) -> bool:
    """Require an explicit classification whenever the request is R18."""
    if not result.image_url:
        return False
    return result.is_adult is True if r18 else result.is_adult is not True