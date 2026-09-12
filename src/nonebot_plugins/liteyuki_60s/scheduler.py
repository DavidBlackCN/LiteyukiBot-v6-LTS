from __future__ import annotations

import asyncio
import hashlib
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
from .group_settings import (PUSH_FEATURES, RANDOM_FEATURES, feature_allowed,
                             resolve_push_settings, resolve_random_push_settings)
from .service import enabled, fetch_content, group_allowed
from .state import random_push_plan_store

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
            nonebot.logger.warning("60s 主动推送指定 Bot 未连接：{}", config.sixty_api_push_bot_id)
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
        nonebot.logger.warning("60s 黑名单模式无法获取当前群列表，跳过本次推送：{}", repr(exc))
        return []
    return list(dict.fromkeys(
        group_id for item in groups
        if (group_id := _group_id(item)) is not None and group_allowed(config, group_id)
    ))


async def _send_content_to_group(bot, group_id: int, content) -> bool:
    try:
        message = (
            await UniMessage.image(raw=content.value).export(bot)
            if content.kind == "image"
            else str(content.value)
        )
        await bot.send_group_msg(group_id=int(group_id), message=message)
    except Exception as exc:
        nonebot.logger.warning("60s 推送到群 {} 失败：{}", group_id, repr(exc))
        return False
    return True


async def _wait_for_next_group(config: SixtyApiConfig, index: int, target_groups: list[int]) -> None:
    if index < len(target_groups) - 1:
        await asyncio.sleep(config.sixty_api_push_interval_seconds)


async def push_content(config: SixtyApiConfig, feature: str, *, per_group_random: bool = False, target_group_id: int | None = None) -> bool:
    if not enabled(config, feature):
        return False
    bot = choose_push_bot(config)
    if bot is None:
        return False
    target_groups = [group_id for group_id in await push_target_groups(config, bot) if feature_allowed(config, group_id, feature)]
    if target_group_id is not None:
        target_group_id = int(target_group_id)
        if target_group_id not in target_groups:
            return False
        target_groups = [target_group_id]
    if not target_groups:
        return False
    if per_group_random:
        sent = False
        fabing_name = str(config.sixty_api_fabing_default_name or "").strip() or None
        for index, group_id in enumerate(target_groups):
            try:
                if feature == "fabing":
                    content = await fetch_content(config, feature, name=fabing_name)
                else:
                    content = await fetch_content(config, feature)
            except SixtyApiError as exc:
                nonebot.logger.warning("60s {} 随机推送获取失败（群 {}）：{}", feature, group_id, repr(exc))
            else:
                sent = await _send_content_to_group(bot, group_id, content) or sent
            await _wait_for_next_group(config, index, target_groups)
        return sent
    try:
        content = await fetch_content(config, feature)
    except SixtyApiError as exc:
        nonebot.logger.warning("60s {} 推送获取失败：{}", feature, repr(exc))
        return False
    if feature == "ai" and content.empty:
        nonebot.logger.info("60s AI 资讯为空，跳过本次自动推送")
        return False
    sent = False
    for index, group_id in enumerate(target_groups):
        sent = await _send_content_to_group(bot, group_id, content) or sent
        await _wait_for_next_group(config, index, target_groups)
    return sent


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


def _random_group_job_id(feature: str, group_id: int) -> str:
    return f"liteyuki_60s.{feature}_random.{group_id}"


def _daily_slot_job_id(feature: str, group_id: int, run_at: datetime) -> str:
    return f"{_random_group_job_id(feature, group_id)}.{run_at.strftime('%Y%m%d%H%M')}"


def _daily_refresh_job_id(feature: str) -> str:
    return f"liteyuki_60s.{feature}_random_daily_refresh"


def _remove_random_group_jobs(feature: str, group_id: int | None = None) -> None:
    prefix = f"liteyuki_60s.{feature}_random."
    group_prefix = f"{prefix}{group_id}" if group_id is not None else None
    for job in scheduler.get_jobs():
        if not job.id.startswith(prefix):
            continue
        if group_prefix is None or job.id == group_prefix or job.id.startswith(f"{group_prefix}."):
            scheduler.remove_job(job.id)


def _next_random_run_at(config: SixtyApiConfig, feature: str, settings: dict | None = None) -> datetime:
    timezone = ZoneInfo(config.sixty_api_timezone)
    settings = settings or {}
    return next_random_time(
        datetime.now(timezone),
        str(settings.get("start", getattr(config, f"sixty_api_{feature}_random_start"))),
        str(settings.get("end", getattr(config, f"sixty_api_{feature}_random_end"))),
        getattr(config, f"sixty_api_{feature}_random_min_interval_minutes"),
        getattr(config, f"sixty_api_{feature}_random_max_interval_minutes"),
    )


def _resolved_random_config(config: SixtyApiConfig, feature: str, group_id: int) -> SixtyApiConfig:
    settings = resolve_random_push_settings(config, group_id, feature)
    return config.model_copy(update={
        f"sixty_api_{feature}_random_push_enabled": settings["enabled"],
        f"sixty_api_{feature}_random_start": settings["start"],
        f"sixty_api_{feature}_random_end": settings["end"],
        f"sixty_api_{feature}_random_daily_min": settings["daily_min"],
        f"sixty_api_{feature}_random_daily_max": settings["daily_max"],
    })


def _staggered_random_run_at(feature: str, group_id: int, run_at: datetime) -> datetime:
    job_id = _random_group_job_id(feature, group_id)
    occupied = set()
    for job in scheduler.get_jobs():
        if job.id == job_id:
            continue
        next_run = getattr(job, "next_run_time", None)
        if next_run is not None:
            occupied.add(next_run.replace(microsecond=0))
    candidate = run_at.replace(microsecond=0) + timedelta(seconds=random.randint(1, 59))
    while candidate in occupied:
        candidate += timedelta(seconds=random.randint(1, 59))
    return candidate


def _schedule_random_group(config: SixtyApiConfig, feature: str, group_id: int) -> None:
    settings = resolve_random_push_settings(config, group_id, feature)
    if not settings["enabled"]:
        return
    try:
        run_at = _staggered_random_run_at(feature, group_id, _next_random_run_at(config, feature, settings))
    except (ValueError, KeyError) as exc:
        nonebot.logger.warning("60s {} 随机推送配置无效：{}", feature, repr(exc))
        return
    job_id = _random_group_job_id(feature, group_id)

    async def run_once() -> None:
        try:
            await push_content(config, feature, per_group_random=True, target_group_id=group_id)
        finally:
            _schedule_random_group(config, feature, group_id)

    scheduler.add_job(run_once, "date", run_date=run_at, id=job_id,
                      replace_existing=True, max_instances=1, coalesce=True)


def _daily_signature(config: SixtyApiConfig, feature: str) -> str:
    values = (
        feature,
        getattr(config, f"sixty_api_{feature}_random_start"),
        getattr(config, f"sixty_api_{feature}_random_end"),
        getattr(config, f"sixty_api_{feature}_random_daily_min"),
        getattr(config, f"sixty_api_{feature}_random_daily_max"),
        config.sixty_api_random_global_cooldown_minutes,
        config.sixty_api_random_edge_padding_minutes,
    )
    return hashlib.sha256(repr(values).encode()).hexdigest()


def _daily_window(config: SixtyApiConfig, feature: str, now: datetime) -> tuple[datetime, datetime]:
    start_hour, start_minute = parse_clock(getattr(config, f"sixty_api_{feature}_random_start"))
    end_hour, end_minute = parse_clock(getattr(config, f"sixty_api_{feature}_random_end"))
    start = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    if end <= start:
        end += timedelta(days=1)
    padding = timedelta(minutes=config.sixty_api_random_edge_padding_minutes)
    return start + padding, end - padding


def _parse_plan_time(value: str, timezone: ZoneInfo) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone) if parsed.tzinfo else parsed.replace(tzinfo=timezone)
    except (TypeError, ValueError):
        return None


def _daily_occupied_times(date: str, group_id: int, timezone: ZoneInfo, exclude_feature: str) -> list[datetime]:
    occupied: list[datetime] = []
    for other_feature in ("fabing", "dad_joke"):
        if other_feature == exclude_feature:
            continue
        plan = random_push_plan_store.get(date, group_id, other_feature)
        if plan is None:
            continue
        scheduled = plan["scheduled_times"]
        assert isinstance(scheduled, list)
        occupied.extend(
            parsed for value in scheduled
            if (parsed := _parse_plan_time(str(value), timezone)) is not None
        )
    return occupied


def _daily_plan(config: SixtyApiConfig, feature: str, group_id: int, now: datetime) -> tuple[str, list[datetime], set[str]]:
    timezone = ZoneInfo(config.sixty_api_timezone)
    date = now.date().isoformat()
    signature = _daily_signature(config, feature)
    current = random_push_plan_store.get(date, group_id, feature)
    if current is not None and current["signature"] == signature:
        scheduled = current["scheduled_times"]
        sent = current["sent_times"]
        assert isinstance(scheduled, list) and isinstance(sent, list)
        return date, [parsed for value in scheduled if (parsed := _parse_plan_time(str(value), timezone)) is not None], set(map(str, sent))

    sent_values: list[str] = [] if current is None else list(map(str, current["sent_times"]))
    sent_times = [parsed for value in sent_values if (parsed := _parse_plan_time(value, timezone)) is not None]
    try:
        window_start, window_end = _daily_window(config, feature, now)
    except ValueError as exc:
        nonebot.logger.warning("60s {} daily_slots 时间配置无效：{}", feature, repr(exc))
        return date, [], set(sent_values)
    earliest = max(window_start, (now + timedelta(minutes=config.sixty_api_random_startup_grace_minutes)).replace(second=0, microsecond=0))
    if earliest > window_end:
        candidates: list[datetime] = []
    else:
        minutes = int((window_end - earliest).total_seconds() // 60)
        candidates = [earliest + timedelta(minutes=offset) for offset in range(minutes + 1)]
    minimum = getattr(config, f"sixty_api_{feature}_random_daily_min")
    maximum = getattr(config, f"sixty_api_{feature}_random_daily_max")
    wanted = random.randint(minimum, maximum)
    occupied = _daily_occupied_times(date, group_id, timezone, feature)
    cooldown = timedelta(minutes=config.sixty_api_random_global_cooldown_minutes)
    random.shuffle(candidates)
    selected = list(sent_times)
    for candidate in candidates:
        if len(selected) >= wanted:
            break
        if any(abs(candidate - other) < cooldown for other in [*occupied, *selected]):
            continue
        selected.append(candidate)
    selected.sort()
    scheduled_values = [value.isoformat() for value in selected]
    random_push_plan_store.save(date, group_id, feature, {
        "scheduled_times": scheduled_values,
        "sent_times": sent_values,
        "signature": signature,
    })
    return date, selected, set(sent_values)


def _schedule_daily_group(config: SixtyApiConfig, feature: str, group_id: int) -> None:
    config = _resolved_random_config(config, feature, group_id)
    if not getattr(config, f"sixty_api_{feature}_random_push_enabled"):
        return
    try:
        timezone = ZoneInfo(config.sixty_api_timezone)
        now = datetime.now(timezone)
        date, scheduled_times, sent_times = _daily_plan(config, feature, group_id, now)
    except (ValueError, KeyError) as exc:
        nonebot.logger.warning("60s {} daily_slots 配置无效：{}", feature, repr(exc))
        return
    _remove_random_group_jobs(feature, group_id)
    for run_at in scheduled_times:
        scheduled_value = run_at.isoformat()
        if scheduled_value in sent_times or run_at <= now:
            continue
        job_id = _daily_slot_job_id(feature, group_id, run_at)

        async def run_once(slot: str = scheduled_value, plan_date: str = date) -> None:
            if await push_content(config, feature, per_group_random=True, target_group_id=group_id):
                random_push_plan_store.mark_sent(plan_date, group_id, feature, slot)

        scheduler.add_job(run_once, "date", run_date=run_at, id=job_id,
                          replace_existing=True, max_instances=1, coalesce=True)


def _schedule_daily_refresh(config: SixtyApiConfig, feature: str) -> None:
    timezone = ZoneInfo(config.sixty_api_timezone)

    async def refresh() -> None:
        bot = choose_push_bot(config)
        if bot is None:
            return
        for group_id in await push_target_groups(config, bot):
            _schedule_daily_group(config, feature, group_id)

    scheduler.add_job(refresh, "cron", hour=0, minute=1, timezone=timezone,
                      id=_daily_refresh_job_id(feature), replace_existing=True,
                      max_instances=1, coalesce=True)


def _schedule_daily_random(config: SixtyApiConfig, feature: str, *, initial: bool) -> None:
    try:
        _schedule_daily_refresh(config, feature)
    except (ValueError, KeyError) as exc:
        nonebot.logger.warning("60s {} daily_slots 配置无效：{}", feature, repr(exc))
        return
    if config.sixty_api_group_mode == "whitelist":
        for group_id in dict.fromkeys(int(group_id) for group_id in config.sixty_api_group_ids):
            _schedule_daily_group(config, feature, group_id)
        return
    if not initial:
        return
    job_id = f"liteyuki_60s.{feature}_random"
    timezone = ZoneInfo(config.sixty_api_timezone)

    async def bootstrap() -> None:
        bot = choose_push_bot(config)
        if bot is None:
            return
        for group_id in await push_target_groups(config, bot):
            _schedule_daily_group(config, feature, group_id)

    scheduler.add_job(bootstrap, "date", run_date=datetime.now(timezone) + timedelta(seconds=1),
                      id=job_id, replace_existing=True, max_instances=1, coalesce=True)


def _schedule_random(config: SixtyApiConfig, feature: str, *, initial: bool = True) -> None:
    job_id = f"liteyuki_60s.{feature}_random"
    _remove_job(job_id)
    if initial:
        _remove_random_group_jobs(feature)
        _remove_job(_daily_refresh_job_id(feature))
    if not enabled(config, feature):
        return
    if config.sixty_api_random_push_mode == "daily_slots":
        _schedule_daily_random(config, feature, initial=initial)
        return
    if initial and config.sixty_api_group_mode == "whitelist":
        for group_id in dict.fromkeys(int(group_id) for group_id in config.sixty_api_group_ids):
            _schedule_random_group(config, feature, group_id)
        return
    try:
        timezone = ZoneInfo(config.sixty_api_timezone)
        run_at = datetime.now(timezone) + timedelta(seconds=1) if initial else _next_random_run_at(config, feature)
    except (ValueError, KeyError) as exc:
        nonebot.logger.warning("60s {} 随机推送配置无效：{}", feature, repr(exc))
        return

    async def bootstrap() -> None:
        bot = choose_push_bot(config)
        if bot is None:
            _schedule_random(config, feature, initial=False)
            return
        for group_id in await push_target_groups(config, bot):
            _schedule_random_group(config, feature, group_id)

    scheduler.add_job(bootstrap, "date", run_date=run_at, id=job_id,
                      replace_existing=True, max_instances=1, coalesce=True)


async def initialize_random_pushes_after_connect(config: SixtyApiConfig, bot) -> None:
    """Populate blacklist random jobs once the configured Bot has connected."""
    if config.sixty_api_group_mode != "blacklist":
        return
    if config.sixty_api_push_bot_id and str(getattr(bot, "self_id", "")) != str(config.sixty_api_push_bot_id):
        return
    if not config.sixty_api_push_bot_id and len(nonebot.get_bots()) != 1:
        return
    for group_id in await push_target_groups(config, bot):
        reschedule_group(config, group_id)

def _fixed_group_job_id(feature: str, group_id: int) -> str:
    return f"liteyuki_60s.{feature}.{group_id}"


def _remove_group_jobs(group_id: int) -> None:
    suffix = f".{group_id}"
    for job in scheduler.get_jobs():
        if job.id.startswith("liteyuki_60s.") and (job.id.endswith(suffix) or job.id.startswith(f"liteyuki_60s.fabing_random.{group_id}.") or job.id.startswith(f"liteyuki_60s.dad_joke_random.{group_id}.")):
            scheduler.remove_job(job.id)


def _schedule_fixed_group(config: SixtyApiConfig, feature: str, group_id: int) -> None:
    settings = resolve_push_settings(config, group_id, feature)
    if not settings["enabled"]:
        return
    try:
        hour, minute = parse_clock(settings["time"])
    except ValueError as exc:
        nonebot.logger.warning("60s {} 群 {} 定时推送时间无效：{}", feature, group_id, repr(exc))
        return
    kwargs = {"hour": hour, "minute": minute, "timezone": ZoneInfo(config.sixty_api_timezone),
              "id": _fixed_group_job_id(feature, group_id), "replace_existing": True,
              "max_instances": 1, "coalesce": True}
    if feature == "kfc":
        kwargs["day_of_week"] = "thu"
    scheduler.add_job(push_content, "cron", args=[config, feature], kwargs={"target_group_id": group_id}, **kwargs)


def reschedule_group(config: SixtyApiConfig, group_id: int) -> None:
    """Replace only one group's 60s jobs after an ADMIN setting change."""
    _remove_group_jobs(group_id)
    if not group_allowed(config, group_id):
        return
    for feature in PUSH_FEATURES:
        _schedule_fixed_group(config, feature, group_id)
    for feature in RANDOM_FEATURES:
        if config.sixty_api_random_push_mode == "daily_slots":
            _schedule_daily_group(config, feature, group_id)
        else:
            _schedule_random_group(config, feature, group_id)


def configure_jobs(config: SixtyApiConfig) -> None:
    try:
        ZoneInfo(config.sixty_api_timezone)
    except Exception:
        nonebot.logger.warning("60s 时区无效：{}", config.sixty_api_timezone)
        return
    # Remove legacy global fixed jobs, then create per-group jobs where the
    # whitelist already provides the complete target set.
    for feature in PUSH_FEATURES:
        _remove_job(f"liteyuki_60s.{feature}")
    if config.sixty_api_group_mode == "whitelist":
        for group_id in dict.fromkeys(int(value) for value in config.sixty_api_group_ids):
            reschedule_group(config, group_id)
    _schedule_random(config, "fabing")
    _schedule_random(config, "dad_joke")
