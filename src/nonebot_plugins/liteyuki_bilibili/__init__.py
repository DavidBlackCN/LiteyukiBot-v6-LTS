"""Liteyuki v6 LTS built-in Bilibili service.

The feature modules are deliberately kept separate so credential management,
subscriptions, parsing and rendering can share one client without making this
plugin's import path a second application entry point.
"""

from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")

from .config import BilibiliConfig


__plugin_meta__ = PluginMetadata(
    name="Bilibili 服务",
    description="统一提供 Bilibili 订阅推送、链接解析与登录凭据管理。",
    usage="/B站订阅 <UID>\n/B站取消 <UID>\n/B站订阅列表\n/B站登录（SUPERUSER 私聊）\n/B站登录状态（SUPERUSER）\n/B站登出（SUPERUSER）\n/B站迁移（SUPERUSER）",
    type="application",
    homepage="https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS",
    config=BilibiliConfig,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "liteyuki": True,
        "lts_builtin": True,
        "toggleable": True,
        "default_enable": True,
        "help_category": "builtin",
    },
)

try:
    config = get_plugin_config(BilibiliConfig)
except ValueError:
    # Pure model/client tests import submodules through this package before
    # NoneBot is initialized. Runtime loading always takes the normal branch.
    config = BilibiliConfig()
else:
    from .runtime import configure_jobs  # noqa: E402

    configure_jobs(config)
    from . import commands  # noqa: E402,F401
    from . import link_matcher  # noqa: E402,F401
