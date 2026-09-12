"""Liteyuki v6 LTS built-in OneBot V11 friend request management."""

from nonebot import get_plugin_config, require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")

from .config import FriendRequestConfig


__plugin_meta__ = PluginMetadata(
    name="好友申请管理",
    description="由 SUPERUSER 私聊审核 OneBot V11 QQ 好友申请。",
    usage="好友申请\n好友申请列表\n好友同意 <编号> [备注]\n好友拒绝 <编号>",
    type="application",
    homepage="https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS",
    config=FriendRequestConfig,
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
    config = get_plugin_config(FriendRequestConfig)
except ValueError:
    config = FriendRequestConfig()
else:
    if config.friend_request_enabled:
        from .service import default_service

        default_service.store.cleanup_history(config.friend_request_history_days)
        from . import commands  # noqa: E402,F401
