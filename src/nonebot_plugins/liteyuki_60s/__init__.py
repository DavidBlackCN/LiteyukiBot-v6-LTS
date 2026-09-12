from nonebot import get_driver, get_plugin_config, require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")

from .config import SixtyApiConfig

config = get_plugin_config(SixtyApiConfig)

__plugin_meta__ = PluginMetadata(
    name="60S 资讯与娱乐",
    description="通过可配置的 60s API 获取日报、资讯与随机娱乐内容。",
    usage="可用命令：\n60s、ai资讯、历史上的今天、it资讯、摸鱼日报、一言、运势、发病文学、kfc、冷笑话",
    type="application",
    config=SixtyApiConfig,
    extra={"liteyuki": True, "lts_builtin": True, "toggleable": True, "default_enable": True, "help_category": "builtin"},
)

from . import commands  # noqa: E402,F401
from .scheduler import configure_jobs, initialize_random_pushes_after_connect  # noqa: E402

configure_jobs(config)


@get_driver().on_bot_connect
async def _initialize_random_pushes_on_bot_connect(bot) -> None:
    await initialize_random_pushes_after_connect(config, bot)
