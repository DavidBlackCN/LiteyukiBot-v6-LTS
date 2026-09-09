from __future__ import annotations

import re
import shlex

from .models import ImageQuery, SetuError, UnsafeQueryError


_ADULT_TOKEN = re.compile(r"^(?:-r|-r18|--r18(?:=.+)?|--nsfw|r18|nsfw)$", re.IGNORECASE)
_COUNT_TOKEN = re.compile(r"^(\d+)(?:张)?$")
_SIZES = {"original", "regular", "small", "thumb", "mini"}
_SOURCES = {"auto", "lolicon", "mirlkoi"}


def _tokens(raw: str) -> list[str]:
    try:
        return shlex.split(raw)
    except ValueError as exc:
        raise SetuError("参数格式不正确。") from exc


def is_r18_request(raw: str) -> bool:
    return any(_ADULT_TOKEN.fullmatch(token) for token in _tokens(raw))


def parse_query(raw: str, *, default_count: int = 3, max_count: int = 5,
                default_provider: str = "auto", default_size: str = "regular",
                default_exclude_ai: bool = True, allow_r18: bool = False) -> ImageQuery:
    tokens = _tokens(raw)
    r18 = any(_ADULT_TOKEN.fullmatch(token) for token in tokens)
    if r18 and not allow_r18:
        raise UnsafeQueryError("当前插件仅提供全年龄内容。")
    tokens = [token for token in tokens if not _ADULT_TOKEN.fullmatch(token)]
    tags: list[str] = []
    uids: list[int] = []
    words: list[str] = []
    count = default_count
    source = default_provider
    size = default_size
    exclude_ai = default_exclude_ai
    orientation: str | None = None
    count_seen = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"-t", "--tag"}:
            index += 1
            if index >= len(tokens) or not tokens[index].strip():
                raise SetuError("-t 需要一个标签。")
            tags.append(tokens[index].strip())
        elif token.startswith("--source="):
            source = token.split("=", 1)[1].lower()
        elif token == "--source":
            index += 1
            if index >= len(tokens):
                raise SetuError("--source 需要图片源名称。")
            source = tokens[index].lower()
        elif token.startswith("--size="):
            size = token.split("=", 1)[1].lower()
        elif token == "--size":
            index += 1
            if index >= len(tokens):
                raise SetuError("--size 需要尺寸。")
            size = tokens[index].lower()
        elif token == "--uid":
            index += 1
            if index >= len(tokens) or not tokens[index].isdigit():
                raise SetuError("--uid 需要 Pixiv UID。")
            uids.append(int(tokens[index]))
        elif token == "--no-ai":
            exclude_ai = True
        elif token == "--portrait":
            orientation = "portrait"
        elif token == "--landscape":
            if orientation == "portrait":
                raise SetuError("不能同时指定横图和竖图。")
            orientation = "landscape"
        elif (count_match := _COUNT_TOKEN.fullmatch(token)) and not count_seen:
            count = int(count_match.group(1))
            count_seen = True
        elif token.startswith("-"):
            raise SetuError(f"不支持的参数：{token}")
        else:
            words.append(token)
        index += 1
    if r18:
        count = 1
        source = "lolicon"
    if count < 1:
        raise SetuError("图片数量至少为 1。")
    if count > max_count:
        raise SetuError(f"单次最多获取 {max_count} 张图片。")
    if source not in _SOURCES:
        raise SetuError("不支持的图片源。")
    if size not in _SIZES:
        raise SetuError("不支持的图片尺寸。")
    return ImageQuery(count=count, keyword=" ".join(words) or None, tags=tags, uid=uids,
                      size=size, exclude_ai=exclude_ai, orientation=orientation,
                      provider=source, r18=r18)