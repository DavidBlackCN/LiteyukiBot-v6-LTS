from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from ..models import ProviderCapabilities
from .base import ImageProvider
from .duckmo import DuckMoProvider
from .liemoe import LieMoeProvider
from .lolicon import LoliconProvider
from .mirlkoi import MirlKoiProvider
from .random_mage import RandomMageProvider
from .waifuim import WaifuImProvider


RatingMode = Literal["filterable", "bucketed", "sfw_only", "unclassified"]
ProviderFactory = Callable[[Any, Any], ImageProvider]


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    display_name: str
    factory: ProviderFactory
    rating_mode: RatingMode
    capabilities: ProviderCapabilities


PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
    "lolicon": ProviderSpec(
        name="lolicon",
        display_name="Lolicon",
        factory=lambda client, config: LoliconProvider(
            client, config.setu_lolicon_api_url, config.setu_pixiv_proxy,
            config.setu_lolicon_api_http_proxy,
        ),
        rating_mode="filterable",
        capabilities=LoliconProvider.capabilities,
    ),
    "mirlkoi": ProviderSpec(
        name="mirlkoi",
        display_name="MirlKoi",
        factory=lambda client, config: MirlKoiProvider(
            client, config.setu_mirlkoi_base_url, config.setu_mirlkoi_endpoint,
            config.setu_mirlkoi_sfw_sort, config.setu_mirlkoi_r18_sort,
            config.setu_mirlkoi_random_sort, config.setu_mirlkoi_portrait_sort,
            config.setu_mirlkoi_landscape_sort,
        ),
        rating_mode="bucketed",
        capabilities=MirlKoiProvider.capabilities,
    ),
    "duckmo": ProviderSpec(
        name="duckmo",
        display_name="DuckMo Pixiv",
        factory=lambda client, config: DuckMoProvider(client, config.setu_duckmo_base_url),
        rating_mode="filterable",
        capabilities=DuckMoProvider.capabilities,
    ),
    "random_mage": ProviderSpec(
        name="random_mage",
        display_name="Random Mage",
        factory=lambda client, config: RandomMageProvider(
            client, config.setu_random_mage_base_url, config.setu_random_mage_api_key,
        ),
        rating_mode="filterable",
        capabilities=RandomMageProvider.capabilities,
    ),
    "liemoe": ProviderSpec(
        name="liemoe",
        display_name="LieMoe",
        factory=lambda client, config: LieMoeProvider(client, config.setu_liemoe_base_url),
        rating_mode="sfw_only",
        capabilities=LieMoeProvider.capabilities,
    ),
    "waifuim": ProviderSpec(
        name="waifuim",
        display_name="Waifu.im",
        factory=lambda client, config: WaifuImProvider(
            client, config.setu_waifuim_base_url, config.setu_waifuim_api_key,
        ),
        rating_mode="filterable",
        capabilities=WaifuImProvider.capabilities,
    ),
}


def provider_names(*, include_auto: bool = False) -> frozenset[str]:
    names = frozenset(PROVIDER_REGISTRY)
    return names | {"auto"} if include_auto else names


def get_provider_spec(name: str) -> ProviderSpec | None:
    return PROVIDER_REGISTRY.get(name)
