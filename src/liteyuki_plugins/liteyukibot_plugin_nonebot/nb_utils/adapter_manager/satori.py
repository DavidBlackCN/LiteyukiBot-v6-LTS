import json
import os

import nonebot


_satori_enabled = False


def init(config: dict):
    global _satori_enabled
    _satori_enabled = False
    if config.get("satori", None) is None:
        nonebot.logger.info("未寻得 Satori 设定信息，跳过初始化")
        return None
    satori_config = config.get("satori")
    if not satori_config.get("enable", False):
        nonebot.logger.info("Satori 未启用，跳过初始化")
        return None
    _satori_enabled = True
    if os.getenv("SATORI_CLIENTS", None) is not None:
        nonebot.logger.info("Satori 客户端已在环境变量中配置，跳过初始化")
    os.environ["SATORI_CLIENTS"] = json.dumps(satori_config.get("hosts", []), ensure_ascii=False)
    config['satori_clients'] = satori_config.get("hosts", [])
    return


def register():
    if not _satori_enabled or os.getenv("SATORI_CLIENTS", None) is None:
        return
    try:
        from nonebot.adapters import satori
    except ImportError as error:
        message = (
            "Satori 已启用，但未安装可选依赖 nonebot-adapter-satori；"
            "请安装兼容版本后重启。"
        )
        nonebot.logger.error(message)
        raise RuntimeError(message) from error
    driver = nonebot.get_driver()
    driver.register_adapter(satori.Adapter)
