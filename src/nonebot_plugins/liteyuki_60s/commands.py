from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from arclet.alconna import Alconna, Args
from nonebot_plugin_alconna import Arparma, UniMessage, on_alconna

from .client import SixtyApiError
from .config import SixtyApiConfig
from .service import enabled, fetch_content
from .state import begin_luck_request, record_luck_result


async def _send_feature(matcher, feature: str, config: SixtyApiConfig, *, name: str | None = None, user_id: str | None = None):
    if not enabled(config, feature):
        await matcher.finish("此功能已关闭。")
    date = datetime.now(ZoneInfo(config.sixty_api_timezone)).date().isoformat()
    if feature == "luck" and user_id:
        request = begin_luck_request(user_id, date, config.sixty_api_luck_daily_limit)
        if request.cached_result:
            await matcher.finish(UniMessage.image(raw=request.cached_result))
        if not request.should_fetch:
            await matcher.finish("今日运势暂无可复用结果，请明日再试。")
    try:
        content = await fetch_content(config, feature, name=name)
        await matcher.send(UniMessage.image(raw=content.value) if content.kind == "image" else str(content.value))
        if feature == "luck" and user_id and isinstance(content.value, bytes):
            record_luck_result(user_id, date, content.value)
    except (SixtyApiError, ValueError):
        await matcher.finish("获取内容失败，请稍后再试。")


def _register(feature: str, command: str, aliases: set[str], *, accepts_name: bool = False):
    alc = Alconna(command, Args["name", str, None]) if accepts_name else Alconna(command)
    matcher = on_alconna(alc, aliases=aliases)

    @matcher.handle()
    async def handler(result: Arparma, event):
        from . import config
        name = result.main_args.get("name") if accepts_name else None
        user_id = str(getattr(event, "user_id", ""))
        await _send_feature(matcher, feature, config, name=name, user_id=user_id)
    return matcher


world_command = _register("world", "60s", {"每日新闻", "60秒读懂世界", "60秒看世界"})
ai_command = _register("ai", "ai资讯", {"AI资讯", "AI资讯快报", "AI咨询快报"})
history_command = _register("history", "历史上的今天", {"历史今天"})
it_command = _register("it", "it资讯", {"IT资讯", "实时IT资讯", "实时IT咨询"})
moyu_command = _register("moyu", "摸鱼日报", {"摸鱼"})
hitokoto_command = _register("hitokoto", "一言", {"随机一言"})
luck_command = _register("luck", "运势", {"今日运势", "随机运势"})
fabing_command = _register("fabing", "发病文学", {"随机发病文学"}, accepts_name=True)
kfc_command = _register("kfc", "kfc", {"KFC", "疯狂星期四", "随机KFC文案"})
dad_joke_command = _register("dad_joke", "冷笑话", {"随机冷笑话"})
