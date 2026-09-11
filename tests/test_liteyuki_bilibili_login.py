import asyncio
import io

import pytest
from PIL import Image

from src.nonebot_plugins.liteyuki_bilibili.credential import CredentialManager
from src.nonebot_plugins.liteyuki_bilibili.errors import (
    BilibiliQRCodeExpiredError,
    BilibiliQRCodeTimeoutError,
)
from src.nonebot_plugins.liteyuki_bilibili.login import make_qr_png, wait_for_qr_login
from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliQRCode, BilibiliQRLoginResult


class MemoryStore:
    def __init__(self) -> None:
        self.cookie = ""

    def load(self) -> str:
        return self.cookie

    def save(self, cookie: str) -> None:
        self.cookie = cookie

    def clear(self) -> None:
        self.cookie = ""


def test_qr_png_is_a_local_readable_png() -> None:
    image = Image.open(io.BytesIO(make_qr_png("https://passport.bilibili.com/login?key=one-time")))
    assert image.format == "PNG"
    assert image.width == image.height
    assert image.width >= 200


def test_confirmed_qr_login_persists_cookie_without_returning_it() -> None:
    class Client:
        async def poll_qr_login(self, key: str) -> BilibiliQRLoginResult:
            assert key == "one-time-key"
            return BilibiliQRLoginResult(status="confirmed", cookie="SESSDATA=secret; bili_jct=csrf")

    store = MemoryStore()
    credential = asyncio.run(wait_for_qr_login(Client(), CredentialManager(store=store), "one-time-key"))
    assert credential.source == "database"
    assert credential.cookie_header == "SESSDATA=secret; bili_jct=csrf"
    assert store.cookie == "SESSDATA=secret; bili_jct=csrf"


def test_expired_qr_login_stops_without_persisting_cookie() -> None:
    class Client:
        async def poll_qr_login(self, key: str) -> BilibiliQRLoginResult:
            return BilibiliQRLoginResult(status="expired")

    store = MemoryStore()
    with pytest.raises(BilibiliQRCodeExpiredError):
        asyncio.run(wait_for_qr_login(Client(), CredentialManager(store=store), "one-time-key"))
    assert store.cookie == ""


def test_scanned_qr_login_reports_confirmation_once(monkeypatch) -> None:
    class Client:
        def __init__(self) -> None:
            self.results = iter(
                [
                    BilibiliQRLoginResult(status="scanned"),
                    BilibiliQRLoginResult(status="scanned"),
                    BilibiliQRLoginResult(status="confirmed", cookie="SESSDATA=secret"),
                ]
            )

        async def poll_qr_login(self, key: str) -> BilibiliQRLoginResult:
            return next(self.results)

    async def no_wait(seconds: float) -> None:
        pass

    notices: list[str] = []

    async def notify() -> None:
        notices.append("scanned")

    import src.nonebot_plugins.liteyuki_bilibili.login as login

    monkeypatch.setattr(login.asyncio, "sleep", no_wait)
    asyncio.run(
        wait_for_qr_login(
            Client(), CredentialManager(store=MemoryStore()), "one-time-key", on_scanned=notify
        )
    )
    assert notices == ["scanned"]


def test_qr_login_timeout_does_not_poll_or_persist() -> None:
    class Client:
        async def poll_qr_login(self, key: str) -> BilibiliQRLoginResult:
            raise AssertionError("timeout=0 must not poll")

    with pytest.raises(BilibiliQRCodeTimeoutError):
        asyncio.run(wait_for_qr_login(Client(), CredentialManager(store=MemoryStore()), "one-time-key", timeout=0))


def test_start_qr_login_uses_text_link_only_when_image_send_fails() -> None:
    import nonebot

    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_bilibili.commands import start_qr_login

    class Client:
        async def start(self) -> None:
            pass

        async def create_qr_login(self) -> BilibiliQRCode:
            return BilibiliQRCode(url="https://passport.bilibili.com/login?key=one-time", key="one-time-key")

        async def poll_qr_login(self, key: str) -> BilibiliQRLoginResult:
            return BilibiliQRLoginResult(status="confirmed", cookie="SESSDATA=secret")

    messages: list[str] = []

    async def send_image(image: bytes) -> None:
        assert image.startswith(b"\x89PNG")
        raise RuntimeError("adapter image failure")

    async def send_text(text: str) -> None:
        messages.append(text)

    asyncio.run(start_qr_login(Client(), CredentialManager(store=MemoryStore()), send_image, send_text))
    assert messages == [
        "二维码图片发送失败，请在 3 分钟内打开以下 Bilibili 登录链接：\n"
        "https://passport.bilibili.com/login?key=one-time"
    ]
