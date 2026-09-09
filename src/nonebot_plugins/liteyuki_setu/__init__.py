from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")

from .config import SetuConfig

__plugin_meta__ = PluginMetadata(
    name="Liteyuki 二次元图片",
    description="多来源二次元图片获取；群聊仅全年龄，私聊 R18 需显式授权。",
    usage=("/色图 [数量] [关键词]（数量可写 3 或 3张）\n/色图 -t 标签 [-t 标签] [数量]\n"
           "/色图 --source lolicon|mirlkoi|auto\n/色图 --size regular|original\n"
           "/色图 --no-ai\n/色图 --r18（仅已授权私聊，固定 1 张）\n/色图管理 状态"),
    type="application", homepage="https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS",
    config=SetuConfig,
    extra={"liteyuki": True, "lts_builtin": True, "toggleable": True,
           "default_enable": True, "help_category": "builtin"},
)

config = get_plugin_config(SetuConfig)

from . import admin, commands  # noqa: E402,F401
