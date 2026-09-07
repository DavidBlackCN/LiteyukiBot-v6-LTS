import os

import nonebot

from liteyuki.config import (
    BasicConfig,
    ensure_config_file,
    get_loaded_config,
    load_from_yaml as primary_load_from_yaml,
)


config = {}  # 全局配置，确保加载后读取


def load_from_yaml(file_: str) -> dict:
    """Legacy wrapper around Liteyuki's primary YAML loader."""
    global config
    nonebot.logger.debug("正在从 {} 中加载配置项".format(file_))
    if not os.path.exists(file_):
        ensure_config_file(file_)

    conf = init_conf(primary_load_from_yaml(file_))
    if not conf:
        nonebot.logger.warning(
            f"配置文件 {file_} 为空，已使用默认配置，请在重启后更改为你所需的内容。"
        )
        conf = BasicConfig().dict()
    config.clear()
    config.update(conf)
    return config.copy()


def get_config(key: str, default=None):
    """Legacy config API backed by NoneBot and Liteyuki's loaded config."""
    try:
        driver_config = nonebot.get_driver().config
        if hasattr(driver_config, "model_dump"):
            current_config = driver_config.model_dump()
        else:
            current_config = driver_config.dict()
    except (RuntimeError, ValueError):
        current_config = {}

    if key in current_config:
        return current_config[key]
    if key in config:
        return config[key]
    return get_loaded_config().get(key, default)


def init_conf(conf: dict) -> dict:
    """
    初始化配置文件，确保配置文件中的必要字段存在，且不会冲突
    Args:
        conf:

    Returns:

    """
    # 若command_start中无""，则添加必要命令头，开启alconna_use_command_start防止冲突
    # 以下内容由于issue #53 被注释
    # if "" not in conf.get("command_start", []):
    #     conf["alconna_use_command_start"] = True
    return conf
    pass
