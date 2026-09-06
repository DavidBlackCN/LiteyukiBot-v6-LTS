from nonebot import get_plugin_config
from pydantic import BaseModel
from typing import Literal


class TrimoStatusConfig(BaseModel):
    yanlun_remote_enabled: bool = False
    """是否允许从旧 Liteyuki 远程服务获取言·论，默认关闭。"""
    yanlun_type: Literal["file", "url"] = "url"
    """言·论地址类型"""
    yanlun_path:str = "https://nd.liteyuki.icu/api/v3/share/content/Xpue?path=null"
    """言·论获取地址"""
    status_acknowledgement: str = ""
    """状态页致谢信息"""

status_config = get_plugin_config(TrimoStatusConfig)
