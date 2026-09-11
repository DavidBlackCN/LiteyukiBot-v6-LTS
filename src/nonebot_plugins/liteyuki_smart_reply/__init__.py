from nonebot.plugin import PluginMetadata
from .monitors import *
from .matchers import *


__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪智障回复",
    description="使用资源包词库进行关键词自动回复",
    usage="设置回复概率 <0-1>（当前群 Bot ADMIN）",
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
        "liteyuki": True,
        "toggleable": True,
        "default_enable": True,
        "help_category": "builtin"
    },
)
