from nonebot import get_plugin_config
from pydantic import BaseModel, Field
from typing import Literal


class TrimoStatusConfig(BaseModel):
    yanlun_remote_enabled: bool = False
    """是否允许从旧 Liteyuki 远程服务获取言·论，默认关闭。"""
    yanlun_type: Literal["file", "url"] = "url"
    """言·论地址类型"""
    yanlun_path:str = "https://nd.liteyuki.icu/api/v3/share/content/Xpue?path=null"
    """言·论获取地址"""
    status_acknowledgement: str = ""
    status_background_enabled: bool = False
    """Enable a remote background for the public status card."""
    status_background_url: str = ""
    """Direct image URL or an image API that returns/redirects to image bytes."""
    status_background_timeout: float = Field(default=6.0, ge=1.0, le=30.0)
    """Maximum time in seconds spent fetching a status background."""
    status_background_mask: float = Field(default=0.35, ge=0.0, le=1.0)
    """Opacity of the readability mask above the background."""
    """状态页致谢信息"""

status_config = get_plugin_config(TrimoStatusConfig)
