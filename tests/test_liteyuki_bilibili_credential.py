from src.nonebot_plugins.liteyuki_bilibili.credential import (
    CredentialManager,
    describe_cookie,
    parse_cookie,
)
from src.nonebot_plugins.liteyuki_bilibili.errors import BilibiliCookieFormatError


class MemoryCredentialStore:
    def __init__(self, cookie: str = "") -> None:
        self.cookie = cookie

    def load(self) -> str:
        return self.cookie

    def save(self, cookie: str) -> None:
        self.cookie = cookie

    def clear(self) -> None:
        self.cookie = ""


def test_parse_cookie_tolerates_separators_and_equals_in_values() -> None:
    cookies = parse_cookie(" SESSDATA=value=with=equals; ; bili_jct=csrf; ")

    assert cookies == {"SESSDATA": "value=with=equals", "bili_jct": "csrf"}


def test_parse_cookie_ignores_invalid_fragments_without_leaking_them() -> None:
    cookies = parse_cookie("SESSDATA=secret; malformed; =empty; DedeUserID=42")

    assert cookies == {"SESSDATA": "secret", "DedeUserID": "42"}
    assert describe_cookie(cookies) == "SESSDATA, DedeUserID"
    assert "secret" not in describe_cookie(cookies)


def test_parse_cookie_rejects_nonempty_invalid_input() -> None:
    try:
        parse_cookie("this is not a cookie")
    except BilibiliCookieFormatError:
        pass
    else:
        raise AssertionError("invalid Cookie should be rejected")


def test_config_cookie_has_priority_over_persisted_qr_cookie() -> None:
    store = MemoryCredentialStore("SESSDATA=database")
    manager = CredentialManager("SESSDATA=config", store)

    assert manager.get().source == "config"
    assert manager.get().cookie_header == "SESSDATA=config"


def test_qr_cookie_persists_and_logout_only_removes_database_cookie() -> None:
    store = MemoryCredentialStore()
    manager = CredentialManager(store=store)

    manager.save_qr_cookie("SESSDATA=qr; bili_jct=csrf")
    assert manager.get().source == "database"
    manager.logout()
    assert manager.get().is_anonymous
