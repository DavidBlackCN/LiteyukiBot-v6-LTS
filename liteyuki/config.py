"""
该模块用于常用配置文件的加载
多配置文件编写原则：
1. 尽量不要冲突: 一个键不要多次出现
2. 分工明确: 每个配置文件给一个或一类服务提供配置
3. 扁平化编写: 配置文件尽量扁平化，不要出现过多的嵌套
4. 注意冲突时的优先级: 项目目录下的配置文件优先级高于config目录下的配置文件
5. 请不要将需要动态加载的内容写入配置文件，你应该使用其他储存方式
"""

import os
import json
import copy
import shutil
import toml
import yaml

from typing import Any

from pydantic import BaseModel, Field

from liteyuki.log import logger

_SUPPORTED_CONFIG_FORMATS = (".yaml", ".yml", ".json", ".toml")
_loaded_config: dict[str, Any] = {}


class SatoriNodeConfig(BaseModel):
    host: str = ""
    port: str = "5500"
    path: str = ""
    token: str = ""


class SatoriConfig(BaseModel):
    comment: str = "此皆正处于开发之中，切勿在生产环境中启用。"
    enable: bool = False
    hosts: list[SatoriNodeConfig] = Field(default_factory=lambda: [SatoriNodeConfig()])


class BasicConfig(BaseModel):
    """Program defaults and fallback validation model, not the YAML layout."""

    host: str = "127.0.0.1"
    port: int = 20247
    superusers: list[str] = Field(default_factory=list)
    command_start: list[str] = Field(default_factory=lambda: ["/"])
    nickname: list[str] = Field(default_factory=lambda: ["Liteyuki"])
    default_language: str = "zh-CN"
    default_interact_language: str = "zh-CN"
    satori: SatoriConfig = Field(default_factory=SatoriConfig)
    data_path: str = "data/liteyuki"


def ensure_config_file(
    config_path: str = "config.yml", template_path: str = "config.example.yml"
) -> bool:
    """Create the primary config from its maintained template when absent."""
    if os.path.exists(config_path):
        return False

    if os.path.isfile(template_path):
        shutil.copyfile(template_path, config_path)
        logger.warning(
            f"未发现 {config_path}，已根据 {template_path} 创建默认配置，请按需修改后重启。"
        )
        return True

    defaults = BasicConfig().model_dump()
    defaults["satori"] = {"enable": defaults["satori"]["enable"]}
    with open(config_path, "w", encoding="utf-8") as file:
        yaml.safe_dump(defaults, file, allow_unicode=True, sort_keys=False)
    logger.warning(
        f"未发现 {config_path}，且模板 {template_path} 不存在，"
        "已使用程序默认值创建配置，请按需修改后重启。"
    )
    return True


def get_loaded_config() -> dict[str, Any]:
    """Return a copy of the configuration loaded by the Liteyuki entrypoint."""
    return _loaded_config.copy()


def flat_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    扁平化配置文件

    {a:{b:{c:1}}} -> {"a.b.c": 1}
    Args:
        config: 配置项目

    Returns:
        扁平化后的配置文件，但也包含原有的键值对
    """
    new_config = copy.deepcopy(config)
    for key, value in config.items():
        if isinstance(value, dict):
            for k, v in flat_config(value).items():
                new_config[f"{key}.{k}"] = v
    return new_config


def load_from_yaml(file_: str) -> dict[str, Any]:
    """
    Load config from yaml file

    """
    logger.debug("正在从 {} 中加载 YAML 配置".format(file_))
    config = yaml.safe_load(open(file_, "r", encoding="utf-8"))
    return flat_config(config if config is not None else {})


def load_from_json(file_: str) -> dict[str, Any]:
    """
    Load config from json file
    """
    logger.debug("正在从 {} 中加载 JSON 配置".format(file_))
    config = json.load(open(file_, "r", encoding="utf-8"))
    return flat_config(config if config is not None else {})


def load_from_toml(file_: str) -> dict[str, Any]:
    """
    Load config from toml file
    """
    logger.debug("正在从 {} 中加载 TOML 配置".format(file_))
    config = toml.load(open(file_, "r", encoding="utf-8"))
    return flat_config(config if config is not None else {})


def load_from_files(*files: str, no_warning: bool = False) -> dict[str, Any]:
    """
    从指定文件加载配置项，会自动识别文件格式
    默认执行扁平化选项
    """
    config = {}
    for file in files:
        if os.path.exists(file):
            if file.endswith((".yaml", "yml")):
                config.update(load_from_yaml(file))
            elif file.endswith(".json"):
                config.update(load_from_json(file))
            elif file.endswith(".toml"):
                config.update(load_from_toml(file))
            else:
                if not no_warning:
                    logger.warning(f"不支持配置文件 {file} 的类型")
        else:
            if not no_warning:
                logger.warning(f"配置文件 {file} 未寻得")
    return config


def load_configs_from_dirs(
    *directories: str, no_waring: bool = False
) -> dict[str, Any]:
    """
    从目录下加载配置文件，不递归
    按照读取文件的优先级反向覆盖
    默认执行扁平化选项
    """
    config = {}
    for directory in directories:
        if not os.path.exists(directory):
            if not no_waring:
                logger.warning(f"目录 {directory} 未寻得")
            continue
        for file in os.listdir(directory):
            if file.endswith(_SUPPORTED_CONFIG_FORMATS):
                config.update(
                    load_from_files(os.path.join(directory, file), no_warning=no_waring)
                )
    return config


def load_config_in_default(no_waring: bool = False) -> dict[str, Any]:
    """
    从一个标准的轻雪项目加载配置文件
    项目目录下的config.*和config目录下的所有配置文件
    项目目录下的配置文件优先
    """
    ensure_config_file()
    config = load_configs_from_dirs("config", no_waring=no_waring)
    config.update(
        load_from_files(
            "config.yaml",
            "config.toml",
            "config.json",
            "config.yml",
            no_warning=no_waring,
        )
    )
    _loaded_config.clear()
    _loaded_config.update(config)
    return config.copy()
