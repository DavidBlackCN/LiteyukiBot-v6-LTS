import asyncio
import datetime
import os
from pathlib import Path

import aiohttp
import nonebot
from nonebot import require
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from nonebot_plugin_alconna.typings import Event

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

blacklist_data: dict[str, set[str]] = {}
blacklist: set[str] = set()

BLACKLIST_URLS = {
    "qq": "https://cdn.liteyuki.icu/static/ubl/qq.txt",
}
CACHE_DIR = Path("data/liteyuki/uniblacklist")
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5, sock_read=10)


def _parse_blacklist(platform: str, content: str) -> set[str]:
    entries = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not entries:
        raise ValueError("黑名单响应为空")
    if platform == "qq" and any(
        not entry.isascii() or not entry.isdecimal() for entry in entries
    ):
        raise ValueError("QQ 黑名单包含非数字条目")
    return entries


def _cache_path(platform: str) -> Path:
    return CACHE_DIR / f"{platform}.txt"


def _load_cached_blacklist(platform: str) -> set[str] | None:
    path = _cache_path(platform)
    try:
        return _parse_blacklist(platform, path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError, ValueError) as e:
        nonebot.logger.warning(f"无法读取 {platform} 联合黑名单缓存 {path}: {e}")
        return None


def _save_cached_blacklist(platform: str, entries: set[str]) -> None:
    path = _cache_path(platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    try:
        temporary_path.write_text(
            "\n".join(sorted(entries)) + "\n", encoding="utf-8"
        )
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _refresh_combined_blacklist() -> None:
    blacklist.clear()
    blacklist.update(get_uni_set())


@scheduler.scheduled_job("interval", minutes=10, next_run_time=datetime.datetime.now())
async def update_blacklist():
    try:
        await request_for_blacklist()
    except Exception:
        # Scheduled jobs must not leak download failures to APScheduler.
        nonebot.logger.exception("更新轻雪联合黑名单时发生未预期错误，继续使用现有名单")


async def request_for_blacklist():
    updated_platforms = []
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as client:
        for platform, url in BLACKLIST_URLS.items():
            try:
                async with client.get(url) as response:
                    response.raise_for_status()
                    entries = _parse_blacklist(platform, await response.text())
            except (aiohttp.ClientError, asyncio.TimeoutError, UnicodeError, ValueError) as e:
                if platform not in blacklist_data:
                    if cached_entries := _load_cached_blacklist(platform):
                        blacklist_data[platform] = cached_entries
                if current_entries := blacklist_data.get(platform):
                    nonebot.logger.warning(
                        f"{platform} 联合黑名单更新失败，继续使用最后一次有效名单"
                        f"（{len(current_entries)} 条）: {type(e).__name__}: {e}"
                    )
                else:
                    nonebot.logger.warning(
                        f"{platform} 联合黑名单更新失败且无有效缓存，本次使用空名单: "
                        f"{type(e).__name__}: {e}"
                    )
                continue

            blacklist_data[platform] = entries
            updated_platforms.append(platform)
            try:
                _save_cached_blacklist(platform, entries)
            except OSError as e:
                nonebot.logger.warning(
                    f"{platform} 联合黑名单已更新，但写入本地缓存失败: {e}"
                )

    _refresh_combined_blacklist()
    if updated_platforms:
        nonebot.logger.info(
            f"轻雪联合黑名单已更新: {', '.join(updated_platforms)}，共 {len(blacklist)} 条"
        )


def get_uni_set() -> set:
    s = set()
    for new_set in blacklist_data.values():
        s.update(new_set)
    return s


for _platform in BLACKLIST_URLS:
    if _cached_entries := _load_cached_blacklist(_platform):
        blacklist_data[_platform] = _cached_entries
_refresh_combined_blacklist()


@event_preprocessor
async def pre_handle(event: Event):
    try:
        user_id = str(event.get_user_id())
    except:
        return

    if user_id in blacklist:
        raise IgnoredException("用户处于黑名单之中，无法使用轻雪。")
