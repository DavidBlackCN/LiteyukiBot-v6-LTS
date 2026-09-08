"""Opt-in background downloading shared by public cards; never a render hook."""
import asyncio
import base64
import time

import aiohttp
from nonebot import get_driver, logger
from pydantic import BaseModel, Field, ValidationError


class CardBackgroundConfig(BaseModel):
    card_background_enabled: bool = False
    card_background_url: str = ""
    card_background_timeout: float = Field(default=6, ge=1, le=30)
    card_background_mask: float = Field(default=0.35, ge=0, le=1)


def resolve_config(raw=None) -> CardBackgroundConfig:
    """Per-key precedence: explicitly supplied card_* (even false/empty) wins."""
    if raw is None:
        driver_config = get_driver().config
        raw = driver_config.model_dump() if hasattr(driver_config, "model_dump") else driver_config.dict()
    values = {}
    for suffix in ("enabled", "url", "timeout", "mask"):
        new, old = f"card_background_{suffix}", f"status_background_{suffix}"
        if new in raw or old in raw:
            value = raw[new] if new in raw else raw[old]
            try:
                values[new] = getattr(CardBackgroundConfig(**{new: value}), new)
            except ValidationError:
                logger.warning(f"卡片背景配置 {new} 无效，使用默认值")
    return CardBackgroundConfig(**values)


CARD_BACKGROUND_MAX_BYTES = 12 * 1024 * 1024
CACHE_TTL = 60
RETRY_TTL = 10
_lock = asyncio.Lock()
_cache_url = None
_cache_image = None
_next_request = 0.0


async def get_card_background(*, config: CardBackgroundConfig | None = None) -> dict:
    global _cache_url, _cache_image, _next_request
    config = config or resolve_config()
    mask = config.card_background_mask
    url = config.card_background_url.strip()
    if not config.card_background_enabled or not url:
        return {"image": None, "mask": mask}
    async with _lock:
        if _cache_url != url:
            _cache_url, _cache_image, _next_request = url, None, 0.0
        if time.monotonic() < _next_request:
            return {"image": _cache_image, "mask": mask}
        try:
            timeout = aiohttp.ClientTimeout(total=config.card_background_timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    response.raise_for_status()
                    media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                    if not media_type.startswith("image/"):
                        raise ValueError("response is not an image")
                    if response.content_length and response.content_length > CARD_BACKGROUND_MAX_BYTES:
                        raise ValueError("image exceeds 12 MiB")
                    content = bytearray()
                    async for chunk in response.content.iter_chunked(64 * 1024):
                        if len(content) + len(chunk) > CARD_BACKGROUND_MAX_BYTES:
                            raise ValueError("image exceeds 12 MiB")
                        content.extend(chunk)
                    if not content:
                        raise ValueError("empty image")
                    final_url = str(response.url)
            _cache_image = f"data:{media_type};base64,{base64.b64encode(content).decode('ascii')}"
            _next_request = time.monotonic() + CACHE_TTL
            logger.debug(f"Card background loaded: url={final_url}, content_type={media_type}, size={len(content)} bytes")
        except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError, ValueError) as error:
            _next_request = time.monotonic() + RETRY_TTL
            logger.debug(f"Card background unavailable, using {'cached image' if _cache_image else 'fallback'}: {error}")
        return {"image": _cache_image, "mask": mask}
