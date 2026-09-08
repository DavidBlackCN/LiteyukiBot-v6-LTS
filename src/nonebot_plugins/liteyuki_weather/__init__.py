from nonebot.plugin import PluginMetadata

from .qweather import *

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪天气",
    description="基于和风天气 API 的天气插件",
    usage="/weather 深圳\n天气 深圳\n深圳天气怎么样",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
        "liteyuki": True,
        "toggleable": True,
        "default_enable": True,
        "help_category": "builtin"
    },
)
