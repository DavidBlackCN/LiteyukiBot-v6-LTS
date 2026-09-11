import asyncio

from src.nonebot_plugins.liteyuki_bilibili.credential import CredentialManager


class MemoryStore:
    def __init__(self, cookie: str = "") -> None:
        self.cookie = cookie

    def load(self) -> str:
        return self.cookie

    def save(self, cookie: str) -> None:
        self.cookie = cookie

    def clear(self) -> None:
        self.cookie = ""


def test_status_text_never_discloses_cookie_values() -> None:
    import nonebot

    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_bilibili.commands import login_status_text
    from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliNav

    class Client:
        async def start(self) -> None:
            pass

        async def get_nav(self):
            return BilibiliNav(is_login=True, mid="42", username="UP")

    text = asyncio.run(login_status_text(Client(), CredentialManager("SESSDATA=secret", MemoryStore())))
    assert "uid=42" in text
    assert "secret" not in text
    assert "config" in text


def test_status_text_handles_anonymous_mode() -> None:
    import nonebot

    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_bilibili.commands import login_status_text
    from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliNav

    class Client:
        async def start(self) -> None:
            pass

        async def get_nav(self):
            return BilibiliNav(is_login=False)

    assert asyncio.run(login_status_text(Client(), CredentialManager(store=MemoryStore()))) == "Bilibili 当前为匿名状态。"


def test_subscription_options_use_config_defaults_and_explicit_flags() -> None:
    import nonebot

    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_bilibili.commands import subscription_options
    from src.nonebot_plugins.liteyuki_bilibili.config import BilibiliConfig

    config = BilibiliConfig(bilibili_push_dynamic=True, bilibili_push_video=False, bilibili_push_live=True)
    assert subscription_options([], config) == (True, False, True)
    assert subscription_options(["--video"], config) == (False, True, False)
    assert subscription_options(["--all"], config) == (True, True, True)
