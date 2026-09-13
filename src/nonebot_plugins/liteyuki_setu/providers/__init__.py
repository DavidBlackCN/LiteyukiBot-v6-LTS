from .duckmo import DuckMoProvider
from .liemoe import LieMoeProvider
from .lolicon import LoliconProvider
from .mirlkoi import MirlKoiProvider
from .random_mage import RandomMageProvider
from .waifuim import WaifuImProvider
from .registry import PROVIDER_REGISTRY, ProviderSpec, get_provider_spec, provider_names

__all__ = (
    "DuckMoProvider", "LieMoeProvider", "LoliconProvider",
    "MirlKoiProvider", "RandomMageProvider", "WaifuImProvider",
    "PROVIDER_REGISTRY", "ProviderSpec",
    "get_provider_spec", "provider_names",
)
