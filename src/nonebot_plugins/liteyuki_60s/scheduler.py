from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import nonebot
from nonebot import require
from nonebot_plugin_alconna import UniMessage

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .client import SixtyApiError
from .config import SixtyApiConfig
from .service import enabled, fetch_content, group_allowed

DAILY_FEATURES = ("world", "ai", "history", "it", "moyu")


def parse_clock(value: str) -> tuple[int, int]:
    hour, minute = value.strip().split(":")
    hour_i, minute_i = int(hour), int(minute)
    if not 0 <= hour_i <= 23 or not 0 <= minute_i <= 59:
        raise ValueError("时间必须为 HH:MM")
    return hour_i, minute_i


def _remove_job(job_id: str) -> None:
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)


def choose_push_bot(config: SixtyApiConfig):
    bots = nonebot.get_bots()
    if config.sixty_api_push_bot_id:
        bot = bots.get(str(config.sixty_api_push_bot_id))
        if bot is None:
            nonebot.logger.warning("60s 主动推送指定 Bot 未连接：%s", config.sixty_api_push_bot_id)
        return bot
    if len(bots) == 1:
        return next(iter(bots.values()))
    if not bots:
        nonebot.logger.warning("60s 主动推送跳过：当前没有已连接 Bot")
    else:
        nonebot.logger.warning("60s 主动推送跳过：存在多个 Bot，请配置 sixty_api_push_bot_id")
    return None


def _group_id(value) -> int | None:
    group_id = value.get("group_id") if isinstance(value, dict) else getattr(value, "group_id", None)
    try:
        return int(group_id)
    except (TypeError, ValueError):
        return None


async def push_target_groups(config: SixtyApiConfig, bot) -> list[int]:
    if config.sixty_api_group_mode == "whitelist":
        return list(dict.fromkeys(int(group_id) for group_id in config.sixty_api_group_ids))
    try:
        groups = await bot.get_group_list()
    except Exception as exc:
        nonebot.logger.warning("60s 黑名单模式无法获取当前群列表，跳过本次推送：%s", exc)
        return []
    return list(dict.fromkeys(
        group_id for item in groups
        if (group_id := _group_id(item)) is not None and group_allowed(config, group_id)
    ))


async def push_content(config: SixtyApiConfig, feature: str) -> bool:
    if not enabled(config, feature):
        return False
    bot = choose_push_bot(config)
    if bot is None:
        return False
    target_groups = await push_target_groups(config, bot)
    if not target_groups:
        return False
    try:
        content = await fetch_content(config, feature)
    except SixtyApiError as exc:
        nonebot.logger.warning("60s %s 推送获取失败：%s", feature, exc)
        return False
    if feature == "ai" and content.empty:
        nonebot.logger.info("60s AI 资讯为空，跳过本次自动推送")
        return False
    message = UniMessage.image(raw=content.value) if content.kind == "image" else str(content.value)
    for group_id in target_groups:
        try:
            await bot.send_group_msg(group_id=int(group_id), message=message)
        except Exception as exc:
            nonebot.logger.warning("60s 推送到群 %s 失败：%s", group_id, exc)
    return True


def next_random_time(now: datetime, start: str, end: str, min_minutes: int, max_minutes: int) -> datetime:
    if min_minutes > max_minutes:
        min_minutes, max_minutes = max_minutes, min_minutes
    start_hour, start_minute = parse_clock(start)
    end_hour, end_minute = parse_clock(end)
    candidate = now + timedelta(minutes=random.randint(min_minutes, max_minutes))
    start_at = candidate.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end_at = candidate.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if (end_hour, end_minute) > (start_hour, start_minute):
        if candidate < start_at:
            return start_at
        if candidate > end_at:
            return start_at + timedelta(days=1)
        return candidate
    if end_at < candidate < start_at:
        return start_at
    return candidate


def _schedule_random(config: SixtyApiConfig, feature: str) -> None:
    job_id = f"liteyuki_60s.{feature}_random"
    _remove_job(job_id)
    if not getattr(config, f"sixty_api_{feature}_random_push_enabled") or not enabled(config, feature):
        return
    try:
        run_at = next_random_time(datetime.now(ZoneInfo(config.sixty_api_timezone)), getattr(config, f"sixty_api_{feature}_random_start"), getattr(config, f"sixty_api_{feature}_random_end"), getattr(config, f"sixty_api_{feature}_random_min_interval_minutes"), getattr(config, f"sixty_api_{feature}_random_max_interval_minutes"))
    except (ValueError, KeyError) as exc:
        nonebot.logger.warning("60s %s 随机推送配置无效：%s", feature, exc)
        return

    async def run_once() -> None:
        try:
            await push_content(config, feature)
        finally:
            _schedule_random(config, feature)

    scheduler.add_job(run_once, "date", run_date=run_at, id=job_id, replace_existing=True, max_instances=1, coalesce=True)


def configure_jobs(config: SixtyApiConfig) -> None:
    try:
        timezone = ZoneInfo(config.sixty_api_timezone)
    except Exception:
        nonebot.logger.warning("60s 时区无效：%s", config.sixty_api_timezone)
        return
    for feature in DAILY_FEATURES:
        job_id = f"liteyuki_60s.{feature}"
        _remove_job(job_id)
        if not enabled(config, feature) or not getattr(config, f"sixty_api_{feature}_push_enabled"):
            continue
        try:
            hour, minute = parse_clock(getattr(config, f"sixty_api_{feature}_push_time"))
        except ValueError as exc:
            nonebot.logger.warning("60s %s 定时推送时间无效：%s", feature, exc)
            continue
        scheduler.add_job(push_content, "cron", args=[config, feature], hour=hour, minute=minute, timezone=timezone, id=job_id, replace_existing=True, max_instances=1, coalesce=True)
    job_id = "liteyuki_60s.kfc"
    _remove_job(job_id)
    if enabled(config, "kfc") and config.sixty_api_kfc_push_enabled:
        try:
            hour, minute = parse_clock(config.sixty_api_kfc_push_time)
            scheduler.add_job(push_content, "cron", args=[config, "kfc"], day_of_week="thu", hour=hour, minute=minute, timezone=timezone, id=job_id, replace_existing=True, max_instances=1, coalesce=True)
        except ValueError as exc:
            nonebot.logger.warning("60s KFC 定时推送时间无效：%s", exc)
    _schedule_random(config, "fabing")
    _schedule_random(config, "dad_joke")
