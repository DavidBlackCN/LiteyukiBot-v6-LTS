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


def test_qr_login_rejects_group_messages_before_creating_a_session() -> None:
    import nonebot

    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_bilibili.commands import handle_login

    class GroupEvent:
        group_id = 12345

    class Matcher:
        def __init__(self) -> None:
            self.message = ""

        async def finish(self, message: str) -> None:
            self.message = message

    matcher = Matcher()
    asyncio.run(handle_login(GroupEvent(), matcher))
    assert matcher.message == "为防止登录凭据泄露，请私聊 Bot 使用 /B站登录。"


def test_qr_login_refuses_to_mask_an_explicit_config_cookie(monkeypatch) -> None:
    import nonebot

    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    import src.nonebot_plugins.liteyuki_bilibili.commands as commands

    class PrivateEvent:
        pass

    class Matcher:
        def __init__(self) -> None:
            self.message = ""

        async def send(self, message: str) -> None:
            raise AssertionError("a QR session must not be created")

        async def finish(self, message: str) -> None:
            self.message = message

    monkeypatch.setattr(commands, "get_credentials", lambda: CredentialManager("SESSDATA=config", MemoryStore()))
    matcher = Matcher()
    asyncio.run(commands.handle_login(PrivateEvent(), matcher))
    assert matcher.message == "当前优先使用 config.yml 中的 bilibili_cookie；请先清空该配置后再使用 /B站登录。"
