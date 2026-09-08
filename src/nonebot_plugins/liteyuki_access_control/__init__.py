from nonebot.plugin import PluginMetadata

from .config import AccessControlConfig
from .api import (
    add_blacklist, check_rate_limit, config, disable_plugin, enable_plugin,
    is_allowed, remove_blacklist,
)

__plugin_meta__ = PluginMetadata(
    name="Liteyuki 权限控制",
    description="轻量插件访问规则与内存限流",
    usage="/access status；/access list（仅 SUPERUSER）",
    type="application",
    config=AccessControlConfig,
    extra={"liteyuki": True, "lts_builtin": True, "toggleable": True, "default_enable": True},
)

if config.access_control_enabled:
    from . import commands, hooks
