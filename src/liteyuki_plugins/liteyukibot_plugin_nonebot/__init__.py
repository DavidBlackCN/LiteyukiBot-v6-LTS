# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/11 下午5:24
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : __init__.py.py
@Software: PyCharm
"""

import nonebot
from liteyuki.utils import IS_MAIN_PROCESS
from liteyuki.plugin import PluginMetadata, PluginType
from .nb_utils import adapter_manager, driver_manager  # type: ignore
from liteyuki.log import logger

__plugin_meta__ = PluginMetadata(
    name="NoneBot2启动器",
    type=PluginType.APPLICATION,
)


def _load_htmlrender_plugin():
    """Ensure htmlrender is registered with NoneBot's PluginManager."""
    plugin_name = "nonebot_plugin_htmlrender"
    plugin = nonebot.get_plugin(plugin_name)
    if plugin is not None:
        return plugin

    try:
        nonebot.load_plugin(plugin_name)
    except Exception as e:
        logger.exception(
            "无法通过 NoneBot PluginManager 加载核心兼容插件 "
            f"{plugin_name}: {e}"
        )
        raise RuntimeError(
            f"Failed to load required NoneBot plugin: {plugin_name}"
        ) from e

    plugin = nonebot.get_plugin(plugin_name)
    if plugin is None:
        logger.error(
            "核心兼容插件 nonebot_plugin_htmlrender 导入后未注册到 "
            "NoneBot PluginManager"
        )
        raise RuntimeError(
            "nonebot_plugin_htmlrender was not registered with NoneBot PluginManager"
        )
    return plugin


def _load_alconna_plugin():
    """Register the command framework before built-ins import its API types."""
    plugin_name = "nonebot_plugin_alconna"
    plugin = nonebot.get_plugin(plugin_name)
    if plugin is not None:
        return plugin

    try:
        nonebot.load_plugin(plugin_name)
    except Exception as e:
        logger.exception(
            f"无法通过 NoneBot PluginManager 加载核心命令插件 {plugin_name}: {e}"
        )
        raise RuntimeError(
            f"Failed to load required NoneBot plugin: {plugin_name}"
        ) from e

    plugin = nonebot.get_plugin(plugin_name)
    if plugin is None:
        logger.error(
            "核心命令插件 nonebot_plugin_alconna 导入后未注册到 NoneBot PluginManager"
        )
        raise RuntimeError(
            "nonebot_plugin_alconna was not registered with NoneBot PluginManager"
        )
    return plugin


def nb_run(*args, **kwargs):
    """
    初始化NoneBot并运行在子进程
    Args:
        **kwargs:

    Returns:
    """
    # 给子进程传递通道对象
    kwargs.update(kwargs.get("nonebot", {}))  # nonebot配置优先
    nonebot.init(**kwargs)

    driver_manager.init(config=kwargs)
    adapter_manager.init(kwargs)
    adapter_manager.register()

    # LTS compatibility fix for Liteyuki v6 Issue #90: register htmlrender
    # before Liteyuki, built-in, or dynamically installed NoneBot plugins.
    _load_htmlrender_plugin()
    _load_alconna_plugin()

    try:
        # nonebot.load_plugin("nonebot-plugin-lnpm")  # 尝试加载轻雪NoneBot插件加载器（Nonebot插件）
        nonebot.load_plugin("src.liteyuki_main")  # 尝试加载轻雪主插件（Nonebot插件）
    except Exception as e:
        pass
    nonebot.run()


if IS_MAIN_PROCESS:
    from liteyuki import get_bot
    from .dev_reloader import *

    liteyuki = get_bot()
    liteyuki.process_manager.add_target(name="nonebot", target=nb_run, args=(), kwargs=liteyuki.config)
