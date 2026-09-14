"""LTS-compatible Komari probe screenshot plugin."""

from nonebot.plugin import PluginMetadata

from .config import Config


__plugin_meta__ = PluginMetadata(
    name="Komari 探针状态截图",
    description="渲染 Komari 探针面板并发送 1080p 截图到群聊",
    usage="群聊发送 /ks 或 /komari-status",
    type="application",
    homepage="https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS",
    config=Config,
    supported_adapters={"~onebot.v11"},
    extra={"liteyuki": True, "lts_builtin": True},
)

from . import handler as handler
