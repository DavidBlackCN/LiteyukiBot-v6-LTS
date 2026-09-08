from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class GroupManagerConfig(BaseModel):
    group_manager_enabled: bool = True
    group_manager_join_notice_enabled: bool = True
    group_manager_leave_notice_enabled: bool = True
    group_manager_join_message: str = "欢迎 {nickname}（{user_id}）加入本群"
    group_manager_leave_message: str = "{nickname}（{user_id}）离开了本群"
    group_manager_default_ban_seconds: int = Field(default=600, ge=1, le=2592000)
    group_manager_max_ban_seconds: int = Field(default=2592000, ge=1, le=2592000)
    group_manager_allow_admin_kick: bool = True


group_manager_config = get_plugin_config(GroupManagerConfig)
