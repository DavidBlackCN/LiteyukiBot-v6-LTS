from typing import Any


def is_satori_object(value: Any) -> bool:
    """Check a Satori object without importing the optional adapter."""
    return type(value).__module__.startswith("nonebot.adapters.satori")
