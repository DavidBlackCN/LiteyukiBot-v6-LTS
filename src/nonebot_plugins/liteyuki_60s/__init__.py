from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")

from .config import SixtyApiConfig

config = get_plugin_config(SixtyApiConfig)

__plugin_meta__ = PluginMetadata(
    name="60S 资讯与娱乐",
    description="通过可配置的 60s API 获取日报、资讯与随机娱乐内容。",
    usage="60s、ai资讯、历史上的今天、it资讯、摸鱼日报、一言、运势、发病文学、kfc、冷笑话",
    type="application",
    config=SixtyApiConfig,
    extra={"liteyuki": True, "lts_builtin": True, "toggleable": True, "default_enable": True, "help_category": "builtin"},
)

from . import commands  # noqa: E402,F401
from .scheduler import configure_jobs  # noqa: E402

configure_jobs(config)
