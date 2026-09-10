from __future__ import annotations

import asyncio
from types import SimpleNamespace

import nonebot
import pytest


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


def test_query_parser_safe_only_and_sources() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import UnsafeQueryError
    from src.nonebot_plugins.liteyuki_setu.parser import parse_query

    assert parse_query("3 原神").count == 3
    assert parse_query("-t 原神 -t 甘雨 2").tags == ["原神", "甘雨"]
    assert parse_query("--source lolicon --size regular 2 原神").provider == "lolicon"
    assert parse_query("--source mirlkoi --portrait", default_exclude_ai=False).orientation == "portrait"
    with pytest.raises(Exception, match="不支持"):
        parse_query("--source removed-provider")
    for unsafe in ("-r", "--r18", "--r18=1", "r18", "nsfw"):
        with pytest.raises(UnsafeQueryError):
            parse_query(unsafe)


class _Client:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_lolicon_forces_safe_request_and_filters_adult_result() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.lolicon import LoliconProvider

    client = _Client({"data": [
        {"pid": 1, "r18": True, "urls": {"regular": "https://image/adult"}},
        {"pid": 2, "r18": False, "urls": {"regular": "https://image/safe"}},
    ]})
    result = asyncio.run(LoliconProvider(client, "https://api.example/setu", "i.pixiv.re").fetch(ImageQuery(count=2)))
    assert [item.pid for item in result] == [2]
    assert client.calls[0][2]["json"]["r18"] == 0


def test_mirlkoi_uses_verified_safe_json_category() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.mirlkoi import MirlKoiProvider

    client = _Client({"pic": ["https://setu.iw233.top/large/example.jpg"]})
    result = asyncio.run(MirlKoiProvider(client, "https://api.cnmiw.com", "/api.php").fetch(
        ImageQuery(count=1, exclude_ai=False)))
    assert result[0].image_url.endswith("/bmiddle/example.jpg")
    assert client.calls[0][1] == "https://api.cnmiw.com/api.php"
    assert client.calls[0][2]["params"] == {"sort": "CDNiw233", "type": "json", "num": 1}


def test_provider_selection_never_falls_back_to_incompatible_source() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery, ProviderCapabilities, UnsupportedQueryError
    from src.nonebot_plugins.liteyuki_setu.service import choose_providers

    provider = SimpleNamespace(name="mirlkoi", safe_available=True,
                               capabilities=ProviderCapabilities(random=True, count=True, size=True),
                               supports=lambda query: False)
    config = SetuConfig(setu_exclude_ai=False, setu_provider_order=["mirlkoi"])
    with pytest.raises(UnsupportedQueryError):
        choose_providers(ImageQuery(uid=[123456], exclude_ai=False), config, {"mirlkoi": provider})


def test_group_storage_daily_limit_and_reset_preserves_other_plugin_configuration() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.storage import (default_settings, get_group_settings,
                                                            group_allowed, reset_group_settings,
                                                            update_group_settings)
    from src.utils.base.data_manager import Group, group_db

    group_id = "pytest-setu-group"
    group_db.delete(Group(), "group_id = ?", group_id)
    config = SetuConfig(setu_daily_image_limit_per_user=0)
    assert not default_settings(config, group_id).enabled
    whitelist = SetuConfig(setu_enabled_groups=[10001])
    assert group_allowed(whitelist, 10001)
    assert not group_allowed(whitelist, 10002)
    blacklist = SetuConfig(setu_group_mode="blacklist", setu_enabled_groups=[10001])
    assert not group_allowed(blacklist, 10001)
    assert default_settings(blacklist, "10002").enabled
    assert get_group_settings(group_id, config).daily_image_limit_per_user == 0
    assert update_group_settings(group_id, config, daily_image_limit_per_user=10).daily_image_limit_per_user == 10
    group = group_db.where_one(Group(), "group_id = ?", group_id)
    group.config["other_plugin"] = {"keep": True}
    group_db.save(group)
    assert reset_group_settings(group_id, config).daily_image_limit_per_user == 0
    group = group_db.where_one(Group(), "group_id = ?", group_id)
    assert group.config["other_plugin"] == {"keep": True}


def test_daily_quota_is_scoped_persistent_and_counts_successes_only() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.quota import DailyImageUsage, get_usage, has_quota, quota_db, record_success

    for group_id, user_id, day in (("g1", "u1", "2099-01-01"), ("g1", "u2", "2099-01-01"), ("g2", "u1", "2099-01-01"), ("g1", "u1", "2099-01-02")):
        quota_db.delete(DailyImageUsage(), "group_id = ? AND user_id = ? AND date = ?", group_id, user_id, day)
    assert has_quota("g1", "u1", "2099-01-01", limit=0, requested=99)
    record_success("g1", "u1", "2099-01-01", 8)
    assert has_quota("g1", "u1", "2099-01-01", limit=10, requested=2)
    assert not has_quota("g1", "u1", "2099-01-01", limit=10, requested=3)
    assert get_usage("g1", "u2", "2099-01-01") == 0
    assert get_usage("g2", "u1", "2099-01-01") == 0
    assert get_usage("g1", "u1", "2099-01-02") == 0
    record_success("g1", "u1", "2099-01-01", 2)
    assert get_usage("g1", "u1", "2099-01-01") == 10
    from src.utils.base.data import Database
    reopened = Database("data/liteyuki/setu.ldb")
    reopened.auto_migrate(DailyImageUsage())
    persisted = reopened.where_one(DailyImageUsage(), "group_id = ? AND user_id = ? AND date = ?", "g1", "u1", "2099-01-01")
    assert persisted is not None and persisted.count == 10
    reopened.conn.close()


def test_same_user_request_reservation_blocks_concurrent_quota_bypass() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.service import Cooldown

    gate = Cooldown()
    assert gate.reserve("u:g", 0)
    assert not gate.reserve("u:g", 0)
    gate.finish("u:g", False)
    assert gate.reserve("u:g", 0)

def test_r18_parser_is_private_opt_in_and_forces_one_image() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import UnsafeQueryError
    from src.nonebot_plugins.liteyuki_setu.parser import parse_query

    with pytest.raises(UnsafeQueryError):
        parse_query("--r18")
    query = parse_query("--r18 5 原神", allow_r18=True)
    assert query.r18 and query.count == 1 and query.keyword == "原神" and query.provider == "lolicon"


def test_lolicon_r18_requires_adult_result_and_forces_grade() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.providers.lolicon import LoliconProvider

    client = _Client({"data": [
        {"pid": 1, "r18": False, "urls": {"regular": "https://image/safe"}},
        {"pid": 2, "r18": True, "urls": {"regular": "https://image/adult"}},
    ]})
    result = asyncio.run(LoliconProvider(client, "https://api.example/setu", "").fetch(
        ImageQuery(count=1, r18=True)))
    assert [item.pid for item in result] == [2]
    assert client.calls[0][2]["json"]["r18"] == 1


def test_private_r18_settings_are_persistent_and_whitelisted() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.quota import (
        PrivateR18Settings, add_private_r18_user, get_private_r18_access,
        quota_db, remove_private_r18_user, set_private_r18_enabled,
    )

    original = quota_db.where_one(PrivateR18Settings(), "setting_key = ?", "default")
    config = SetuConfig(setu_private_r18_enabled=False, setu_private_r18_user_ids=[10001])
    try:
        set_private_r18_enabled(True, config)
        add_private_r18_user("10002", config)
        access = get_private_r18_access(config)
        assert access.enabled and access.allowed_user_ids == {"10001", "10002"}
        remove_private_r18_user("10002", config)
        assert get_private_r18_access(config).allowed_user_ids == {"10001"}
    finally:
        if original is None:
            quota_db.delete(PrivateR18Settings(), "setting_key = ?", "default")
        else:
            quota_db.save(original)