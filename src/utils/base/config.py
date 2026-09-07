import os
import platform
from typing import List

import nonebot
import yaml
from pydantic import BaseModel

from liteyuki.config import get_loaded_config, load_from_yaml as primary_load_from_yaml

from ..message.tools import random_hex_string


config = {}  # 全局配置，确保加载后读取


class SatoriNodeConfig(BaseModel):
    host: str = ""
    port: str = "5500"
    path: str = ""
    token: str = ""


class SatoriConfig(BaseModel):
    comment: str = "此皆正处于开发之中，切勿在生产环境中启用。"
    enable: bool = False
    hosts: List[SatoriNodeConfig] = [SatoriNodeConfig()]


class BasicConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 20247
    superusers: list[str] = []
    command_start: list[str] = ["/", ""]
    nickname: list[str] = [f"灵温-{random_hex_string(6)}"]
    default_language: str = "zh-WY"
    default_interact_language: str = "zh-CN"
    satori: SatoriConfig = SatoriConfig()
    data_path: str = "data/liteyuki"
    chromium_path: str = (
        "/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome" # pyright: ignore[reportInvalidStringEscapeSequence]
        if platform.system() == "Darwin"
        else (
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"
            if platform.system() == "Windows"
            else "/usr/bin/chromium-browser"
        )
    )


def load_from_yaml(file_: str) -> dict:
    """Legacy wrapper around Liteyuki's primary YAML loader."""
    global config
    nonebot.logger.debug("正在从 {} 中加载配置项".format(file_))
    if not os.path.exists(file_):
        nonebot.logger.warning(
            f"未寻得配置文件 {file_} ，已以默认配置创建，请在重启后更改为你所需的内容。"
        )
        with open(file_, "w", encoding="utf-8") as f:
            yaml.dump(BasicConfig().dict(), f, default_flow_style=False)

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
