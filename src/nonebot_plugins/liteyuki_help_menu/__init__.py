from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from .config import HelpMenuConfig

config = get_plugin_config(HelpMenuConfig)
__plugin_meta__ = PluginMetadata(
    name="Liteyuki 帮助菜单", description="自动发现插件的分类、搜索和图片帮助中心",
    usage="帮助 / help / 菜单\n帮助 <分类或插件名> [页码]\n帮助 搜索 <关键词>\n帮助 全部",
    type="application", config=HelpMenuConfig,
    extra={"liteyuki": True, "lts_builtin": True, "toggleable": True, "default_enable": True, "category": "system"},
)
if config.help_menu_enabled:
    from . import handlers
