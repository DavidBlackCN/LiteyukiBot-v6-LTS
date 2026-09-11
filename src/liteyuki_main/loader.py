import asyncio

import nonebot.plugin
from nonebot import get_driver
from src.utils import init_log
from src.utils.base.config import get_config
from src.utils.base.data_manager import InstalledPlugin, plugin_db
from src.utils.base.resource import load_resources
from src.utils.message.tools import check_for_package

load_resources()
init_log()

driver = get_driver()

# These packages are installed by requirements.txt and deliberately use the
# existing third-party loading path below. Pacman-managed records are appended
# afterwards so locally installed extra plugins keep their current behaviour.
DEFAULT_THIRD_PARTY_PLUGINS = (
    "nonebot_plugin_remind",
    "nonebot_plugin_rollpig_plus",
    "nonebot_plugin_manosaba_memes",
    "nonebot_plugin_wordcloud",
    "nonebot_plugin_memes",
    "nonebot_plugin_group_historian",
    "nonebot_plugin_cnrail",
    "nonebot_plugin_komari_status",
)


@driver.on_startup
async def load_plugins():
    nonebot.plugin.load_plugins("src/nonebot_plugins")
    # 从数据库读取已安装的插件
    if not get_config("safe_mode", False):
        # 安全模式下，不加载插件
        installed_plugins: list[InstalledPlugin] = (
            plugin_db.where_all(InstalledPlugin()) or []
        )
        plugin_modules = dict.fromkeys(
            (*DEFAULT_THIRD_PARTY_PLUGINS, *(item.module_name for item in installed_plugins))
        )
        for module_name in plugin_modules:
            if not check_for_package(module_name):
                nonebot.logger.error(
                    f"加载列表中的 {module_name} 插件无法安装，可能是未找到对应依赖。"
                )
            else:
                nonebot.load_plugin(module_name)
        nonebot.plugin.load_plugins("plugins")
    else:
        nonebot.logger.info("当前处于安全模式，未加载任何插件。")
