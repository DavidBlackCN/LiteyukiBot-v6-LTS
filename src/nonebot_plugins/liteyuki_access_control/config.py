from pydantic import BaseModel, Field


class AccessControlConfig(BaseModel):
    access_control_enabled: bool = True
    access_control_default_allow: bool = True
    access_control_superuser_bypass: bool = True
    access_control_reply_on_denied: bool = True
    access_control_reply_on_rate_limited: bool = True
    access_control_protected_plugins: list[str] = Field(
        default_factory=lambda: ["liteyuki_access_control", "liteyuki_group_manager"]
    )
    access_control_data_path: str = "data/liteyuki_access_control"
