from pydantic import BaseModel, Field


class HelpMenuConfig(BaseModel):
    help_menu_enabled: bool = True
    help_menu_page_size: int = Field(default=10, ge=1, le=12)
    help_menu_show_third_party: bool = True
    help_menu_enable_pinyin_search: bool = True
    help_menu_filter_access: bool = False
    help_menu_hidden_plugins: list[str] = Field(default_factory=lambda: [
        "nonebot_plugin_htmlrender", "nonebot_plugin_apscheduler",
        "nonebot_plugin_localstore", "to_liteyuki", "liteyuki_eventpush",
    ])
