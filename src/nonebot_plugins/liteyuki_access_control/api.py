"""Load this plugin with nonebot.require before importing its public API.

is_allowed is read-only; check_rate_limit consumes one quota on success.
Bare IDs share rules across adapters. Pass is_superuser explicitly when using
adapter-prefixed NoneBot SUPERUSER identities without an Event.
"""
from nonebot import get_driver, get_plugin_config

from .config import AccessControlConfig
from .engine import AccessController

config = get_plugin_config(AccessControlConfig)
controller = AccessController(config)
if config.access_control_enabled:
    controller.load()


def _superuser(user_id, explicit):
    return explicit or (user_id is not None and str(user_id) in get_driver().config.superusers)


async def is_allowed(plugin_name: str, user_id: str | None = None,
                     group_id: str | None = None, *, is_superuser: bool = False) -> bool:
    return controller.allowed(plugin_name, user_id, group_id, superuser=_superuser(user_id, is_superuser))


async def check_rate_limit(plugin_name: str, user_id: str | None = None,
                           group_id: str | None = None, *, is_superuser: bool = False) -> bool:
    return controller.rate_allowed(plugin_name, user_id, group_id, superuser=_superuser(user_id, is_superuser))


def enable_plugin(plugin_name: str, subject_id: str, *, scope: str = "group"):
    controller.set_plugin(plugin_name, subject_id, scope=scope, enabled=True)


def disable_plugin(plugin_name: str, subject_id: str, *, scope: str = "group"):
    controller.set_plugin(plugin_name, subject_id, scope=scope, enabled=False)


def add_blacklist(subject_id: str, *, scope: str = "user"):
    controller.set_list(subject_id, scope=scope)


def remove_blacklist(subject_id: str, *, scope: str = "user"):
    controller.set_list(subject_id, scope=scope, remove=True)
