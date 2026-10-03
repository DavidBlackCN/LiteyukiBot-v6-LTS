"""Built-in X subscriptions, Nitter link parsing and optional translation."""
import sys

from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
# Older built-ins may have imported this permission package before registration.
# Register it ourselves only when it has not already been imported.
if "src.nonebot_plugins.liteyuki_group_manager" not in sys.modules:
    require("src.nonebot_plugins.liteyuki_group_manager")

from .config import TwitterConfig

config = get_plugin_config(TwitterConfig)
__plugin_meta__ = PluginMetadata(
    name="X 订阅与转发",
    description="按群订阅 X 账号，通过 Nitter 转发推文并提供可选翻译。",
    usage="推特关注/推特取关 <账号>；推特订阅列表；推特管理 状态；推特推文 <账号> [数量]；推特解析/推特翻译 <链接>。订阅管理限 ADMIN / SUPERUSER，无需 @Bot。",
    type="application", config=TwitterConfig,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"liteyuki": True, "lts_builtin": True, "toggleable": True,
           "default_enable": True, "help_category": "builtin"},
)

from . import commands
from .runtime import configure_jobs

configure_jobs(config)
