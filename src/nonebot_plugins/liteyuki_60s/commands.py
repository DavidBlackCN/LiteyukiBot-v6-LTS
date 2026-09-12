from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from arclet.alconna import Alconna, Args, MultiVar
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Arparma, UniMessage, on_alconna

from src.nonebot_plugins.liteyuki_group_manager.permission import ADMIN

from .client import SixtyApiError
from .config import SixtyApiConfig
from .group_settings import (FEATURE_ALIASES, PUSH_FEATURES, RANDOM_FEATURES,
                             feature_allowed, get_group_settings,
                             reset_group_settings, update_group_settings)
from .service import fetch_content, group_allowed
from .state import begin_luck_request, record_luck_result


async def _send_feature(
    matcher,
    feature: str,
    config: SixtyApiConfig,
    *,
    name: str | None = None,
    user_id: str | None = None,
):
    if not feature_allowed(config, getattr(matcher, "_liteyuki_group_id", None), feature):
        await matcher.finish("此功能已关闭。")

    date = datetime.now(
        ZoneInfo(config.sixty_api_timezone)
    ).date().isoformat()

    if feature == "luck" and user_id:
        request = begin_luck_request(
            user_id,
            date,
            config.sixty_api_luck_daily_limit,
        )

        if request.cached_result:
            await matcher.finish(
                UniMessage.image(raw=request.cached_result)
            )

        if not request.should_fetch:
            await matcher.finish(
                "今日运势暂无可复用结果，请明日再试。"
            )

    try:
        content = await fetch_content(
            config,
            feature,
            name=name,
        )

        await matcher.send(
            UniMessage.image(raw=content.value)
            if content.kind == "image"
            else str(content.value)
        )

        if (
            feature == "luck"
            and user_id
            and isinstance(content.value, bytes)
        ):
            record_luck_result(
                user_id,
                date,
                content.value,
            )

    except (SixtyApiError, ValueError):
        await matcher.finish(
            "获取内容失败，请稍后再试。"
        )


def _register(
    feature: str,
    command: str,
    aliases: set[str],
    *,
    accepts_name: bool = False,
):
    # 自动将内部 feature 名作为英文命令别名。
    #
    # 例如：
    #   feature="world", command="60s"
    #
    # 可同时触发：
    #   /60s
    #   /world
    aliases = set(aliases)
    aliases.add(feature)

    alc = (
        Alconna(
            command,
            Args["name", str, None],
        )
        if accepts_name
        else Alconna(command)
    )

    matcher = on_alconna(
        alc,
        aliases=aliases,
    )

    @matcher.handle()
    async def handler(
        result: Arparma,
        event: Event,
        matcher: Matcher,
    ):
        # 运行时读取当前插件配置，
        # 避免在注册阶段绑定旧配置对象。
        from . import config

        if not group_allowed(
            config,
            getattr(event, "group_id", None),
        ):
            return

        matcher._liteyuki_group_id = getattr(event, "group_id", None)

        name = (
            result.main_args.get("name")
            if accepts_name
            else None
        )

        user_id = str(
            getattr(event, "user_id", "")
        )

        await _send_feature(
            matcher,
            feature,
            config,
            name=name,
            user_id=user_id,
        )

    return matcher


world_command = _register(
    "world",
    "60s",
    {
        "每日新闻",
        "60秒读懂世界",
        "60秒看世界",
    },
)

ai_command = _register(
    "ai",
    "ai资讯",
    {
        "AI资讯",
        "AI资讯快报",
        "AI咨询快报",
    },
)

history_command = _register(
    "history",
    "历史上的今天",
    {
        "历史今天",
    },
)

it_command = _register(
    "it",
    "it资讯",
    {
        "IT资讯",
        "实时IT资讯",
        "实时IT咨询",
    },
)

moyu_command = _register(
    "moyu",
    "摸鱼日报",
    {
        "摸鱼",
    },
)

hitokoto_command = _register(
    "hitokoto",
    "一言",
    {
        "随机一言",
    },
)

luck_command = _register(
    "luck",
    "运势",
    {
        "今日运势",
        "随机运势",
    },
)

fabing_command = _register(
    "fabing",
    "发病文学",
    {
        "发病",
        "随机发病文学",
    },
    accepts_name=True,
)

kfc_command = _register(
    "kfc",
    "kfc",
    {
        "KFC",
        "疯狂星期四",
        "随机KFC文案",
    },
)

dad_joke_command = _register(
    "dad_joke",
    "冷笑话",
    {
        "随机冷笑话",
        "dad-joke",
    },
)

def _tokens(result: Arparma) -> list[str]:
    return [str(value).strip() for value in result.main_args.get("raw", []) if str(value).strip()]


def _feature(value: str) -> str | None:
    return FEATURE_ALIASES.get(value) or (value if value in FEATURE_ALIASES.values() else None)


def _status(group_id: str, config: SixtyApiConfig) -> str:
    settings = get_group_settings(group_id, config)
    raw = settings["overrides"]

    def source(section: str, feature: str | None = None) -> str:
        if feature is None:
            return "群级覆盖" if "enabled" in raw else "继承全局"
        return "群级覆盖" if isinstance(raw.get(section), dict) and feature in raw[section] else "继承全局"

    lines = [
        f"实例允许范围：{'是' if settings['allowed'] else '否'}",
        f"总开关：{'开' if settings['enabled'] else '关'}（{source('enabled')}）",
        "功能：" + "、".join(
            f"{name}{'开' if settings['features'][key] else '关'}（{source('features', key)}）"
            for name, key in FEATURE_ALIASES.items()
        ),
        "固定推送：",
    ]
    for name, feature in FEATURE_ALIASES.items():
        if feature in PUSH_FEATURES:
            item = settings["push"][feature]
            lines.append(f"- {name}：{'开' if item['enabled'] else '关'} {item['time']}（{source('push', feature)}）")
    lines.append("随机推送：")
    for name, feature in FEATURE_ALIASES.items():
        if feature in RANDOM_FEATURES:
            item = settings["random_push"][feature]
            lines.append(f"- {name}：{'开' if item['enabled'] else '关'}，{item['daily_min']}-{item['daily_max']} 次，{item['start']}-{item['end']}（{source('random_push', feature)}）")
    return "\n".join(lines)


sixty_admin = on_alconna(
    Alconna("60s管理", Args["raw", MultiVar(str), []]),
    aliases={"60s设置", "60s-admin"}, permission=ADMIN, priority=20, block=True,
)


@sixty_admin.handle()
async def handle_sixty_admin(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    from . import config
    from .scheduler import parse_clock, reschedule_group

    group_id = getattr(event, "group_id", None)
    if group_id is None:
        await matcher.finish("60s管理只能在群聊中使用。")
    group_id = str(group_id)
    if not group_allowed(config, group_id):
        await matcher.finish("当前群不在实例允许范围内，请联系 SUPERUSER。")
    args = _tokens(result)
    if not args:
        await matcher.finish("用法：60s管理 状态|开启|关闭|重置；功能/推送/随机 <项目> …")
    if args[0] == "状态":
        await matcher.finish(_status(group_id, config))
    if args[0] in {"开启", "关闭"}:
        update_group_settings(group_id, config, enabled=args[0] == "开启")
    elif args[0] == "重置":
        reset_group_settings(group_id, config)
    elif len(args) >= 3 and args[0] == "功能" and args[2] in {"开", "关"}:
        feature = _feature(args[1])
        if feature is None:
            await matcher.finish("未知功能。")
        update_group_settings(group_id, config, features={feature: {"enabled": args[2] == "开"}})
    elif len(args) >= 3 and args[0] == "推送":
        feature = _feature(args[1])
        if feature not in PUSH_FEATURES:
            await matcher.finish("该内容不支持固定推送。")
        if args[2] in {"开", "关"}:
            update_group_settings(group_id, config, push={feature: {"enabled": args[2] == "开"}})
        elif args[2] == "时间" and len(args) >= 4:
            try:
                parse_clock(args[3])
            except ValueError:
                await matcher.finish("时间必须为 HH:MM。")
            update_group_settings(group_id, config, push={feature: {"time": args[3]}})
        else:
            await matcher.finish("用法：60s管理 推送 <项目> 开|关|时间 HH:MM")
    elif len(args) >= 3 and args[0] == "随机":
        feature = _feature(args[1])
        if feature not in RANDOM_FEATURES:
            await matcher.finish("仅发病文学和冷笑话支持随机推送。")
        if args[2] in {"开", "关"}:
            values = {"enabled": args[2] == "开"}
        elif args[2] == "次数" and len(args) >= 5 and args[3].isdigit() and args[4].isdigit():
            low, high = int(args[3]), int(args[4])
            if low < 0 or high < low or high > 100:
                await matcher.finish("次数必须是 0 到 100 的递增范围。")
            values = {"daily_min": low, "daily_max": high}
        elif args[2] == "时段" and len(args) >= 5:
            try:
                parse_clock(args[3]); parse_clock(args[4])
            except ValueError:
                await matcher.finish("时间必须为 HH:MM。")
            values = {"start": args[3], "end": args[4]}
        else:
            await matcher.finish("用法：60s管理 随机 <发病文学|冷笑话> 开|关|次数 <最小> <最大>|时段 <开始> <结束>")
        update_group_settings(group_id, config, random_push={feature: values})
    else:
        await matcher.finish("参数不正确，请使用：状态、开启、关闭、重置、功能、推送或随机。")
    reschedule_group(config, int(group_id))
    await matcher.finish("本群 60s 设置已更新并重新调度。")
