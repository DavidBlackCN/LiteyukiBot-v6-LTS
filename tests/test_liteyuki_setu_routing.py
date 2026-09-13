from __future__ import annotations

import nonebot
import pytest


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


def _selected(monkeypatch, raw: str, *, allow_r18: bool = False) -> set[str]:
    from src.nonebot_plugins.liteyuki_setu import service
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.parser import parse_query

    config = SetuConfig()
    monkeypatch.setattr(service, "health", service.ProviderHealth())
    monkeypatch.setattr(service.random, "choices", lambda population, **_kwargs: [population[0]])
    providers = service.build_providers(config, object())
    query = parse_query(raw, allow_r18=allow_r18)
    return {provider.name for provider in service.choose_providers(query, config, providers)}


def test_routing_capability_matrix(monkeypatch) -> None:
    _init()
    assert _selected(monkeypatch, "3") == {
        "lolicon", "random_mage", "duckmo", "mirlkoi", "liemoe", "waifuim",
    }
    assert _selected(monkeypatch, "-t waifu") == {"lolicon", "random_mage", "waifuim"}
    assert _selected(monkeypatch, "genshin") == {"lolicon", "waifuim"}
    assert _selected(monkeypatch, "--uid 123") == {"lolicon", "random_mage", "duckmo"}
    assert _selected(monkeypatch, "--pid 123") == {"random_mage", "duckmo"}
    assert _selected(monkeypatch, "--author artist") == {"duckmo"}
    assert _selected(monkeypatch, "--no-ai") == {"lolicon", "random_mage", "duckmo"}
    assert _selected(monkeypatch, "--r18", allow_r18=True) == {
        "lolicon", "random_mage", "duckmo", "mirlkoi", "waifuim",
    }


def test_registry_contains_only_supported_providers() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.providers.registry import provider_names

    expected = {
        "lolicon", "random_mage", "duckmo", "mirlkoi", "liemoe", "waifuim",
    }
    config = SetuConfig()
    assert provider_names() == expected
    assert set(config.setu_provider_order) == expected
    assert set(config.setu_provider_weights) == expected


def test_removed_source_is_rejected() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.parser import parse_query

    removed_source = "duckmo" + "_x"
    with pytest.raises(Exception, match="不支持"):
        parse_query(f"--source {removed_source}")


def test_disabled_and_unhealthy_providers_are_not_selected(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import service
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery, ProviderError

    config = SetuConfig(setu_lolicon_enabled=False, setu_provider_failure_threshold=1)
    test_health = service.ProviderHealth()
    test_health.failure("duckmo", config, ProviderError("offline"))
    monkeypatch.setattr(service, "health", test_health)
    monkeypatch.setattr(service.random, "choices", lambda population, **_kwargs: [population[0]])
    selected = service.choose_providers(
        ImageQuery(), config, service.build_providers(config, object()),
    )
    assert "lolicon" not in {provider.name for provider in selected}
    assert "duckmo" not in {provider.name for provider in selected}


def test_config_normalizes_weights_and_ignores_unknown_provider() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig

    with pytest.warns(UserWarning) as warnings:
        config = SetuConfig(setu_provider_weights={
            " LOLICON ": -2, "mirlkoi": 0, "missing": 9,
        })
    assert len(warnings) == 2
    assert config.setu_provider_weights == {"lolicon": 0, "mirlkoi": 0}


def test_http_proxy_config_accepts_empty_or_http_urls_only() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig

    assert SetuConfig().setu_api_http_proxy == ""
    config = SetuConfig(
        setu_api_http_proxy=" http://user:pass@proxy.example:7890/ ",
        setu_image_http_proxy="https://proxy.example:8443",
    )
    assert config.setu_api_http_proxy == "http://user:pass@proxy.example:7890"
    assert config.setu_image_http_proxy == "https://proxy.example:8443"
    with pytest.raises(ValueError, match="HTTP/HTTPS"):
        SetuConfig(setu_api_http_proxy="socks5://proxy.example:1080")
