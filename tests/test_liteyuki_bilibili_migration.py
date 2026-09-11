import json

from src.nonebot_plugins.liteyuki_bilibili.credential import CredentialManager
from src.nonebot_plugins.liteyuki_bilibili.migration import migrate_legacy_data
from src.nonebot_plugins.liteyuki_bilibili.storage import SubscriptionStore


class MemoryStore:
    def __init__(self) -> None:
        self.cookie = ""

    def load(self) -> str:
        return self.cookie

    def save(self, cookie: str) -> None:
        self.cookie = cookie

    def clear(self) -> None:
        self.cookie = ""


def test_json_subscription_migration_is_idempotent_and_keeps_source(tmp_path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    subscribers = legacy / "subscribers.json"
    subscribers.write_text(
        json.dumps({"100": {"uids": [42, "99"], "sub_time": {"42": 1710000000}, "atall": {"42": ["all"]}}}),
        encoding="utf-8",
    )
    store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
    credentials = CredentialManager(store=MemoryStore())

    first = migrate_legacy_data(store, credentials, legacy)
    second = migrate_legacy_data(store, credentials, legacy)
    assert (first.imported, first.updated, first.baseline_pending) == (2, 0, 2)
    assert (second.imported, second.updated) == (0, 2)
    assert subscribers.is_file()
    imported = store.get("group", "100", "42")
    assert imported.at_all and imported.last_dynamic_id == "" and imported.last_live_state == "unknown"


def test_cookie_migration_respects_explicit_config_and_never_needs_output(tmp_path) -> None:
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "cookie.json").write_text(json.dumps({"cookie": "SESSDATA=legacy; bili_jct=csrf"}), encoding="utf-8")
    database_store = MemoryStore()
    report = migrate_legacy_data(SubscriptionStore(str(tmp_path / "bilibili.ldb")), CredentialManager(store=database_store), legacy)
    assert report.credential_imported and "SESSDATA=legacy" in database_store.cookie

    configured_store = MemoryStore()
    report = migrate_legacy_data(SubscriptionStore(str(tmp_path / "bilibili2.ldb")), CredentialManager("SESSDATA=config", configured_store), legacy)
    assert report.credential_skipped and configured_store.cookie == ""


def test_migration_without_source_is_a_noop(tmp_path) -> None:
    report = migrate_legacy_data(
        SubscriptionStore(str(tmp_path / "bilibili.ldb")), CredentialManager(store=MemoryStore()), tmp_path / "missing"
    )
    assert not report.source_found and report.imported == 0
