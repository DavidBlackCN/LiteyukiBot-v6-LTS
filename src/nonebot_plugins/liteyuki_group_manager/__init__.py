from nonebot.plugin import PluginMetadata

from .config import GroupManagerConfig, group_manager_config


__plugin_meta__ = PluginMetadata(
    name="Liteyuki 群管理",
    description="面向 OneBot V11 的轻量基础群管理",
    usage=(
        "禁言 @用户 10m / 解禁 @用户\n"
        "踢出 @用户 [--reject]\n"
        "回复消息后发送：撤回\n"
        "全员禁言 / 解除全员禁言\n"
        "设置管理员 @用户 / 取消管理员 @用户"
    ),
    type="application",
    homepage="https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS",
    config=GroupManagerConfig,
    extra={
        "liteyuki": True, "lts_builtin": True,
        "toggleable": True,
        "default_enable": True,
    },
)


if group_manager_config.group_manager_enabled:
    from .handlers import *
