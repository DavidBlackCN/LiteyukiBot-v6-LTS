"""Application lifecycle wiring for the single Bilibili polling job."""

from __future__ import annotations

from nonebot import get_driver, logger, require

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .client import BilibiliClient
from .config import BilibiliConfig
from .credential import CredentialManager
from .delivery import deliver_event
from .scheduler import SubscriptionPoller
from .storage import SubscriptionStore


JOB_ID = "liteyuki_bilibili.poll"
_active_client: BilibiliClient | None = None
_active_credentials: CredentialManager | None = None
_active_store: SubscriptionStore | None = None
_shutdown_registered = False


def configure_jobs(config: BilibiliConfig) -> None:
    """Register exactly one coalesced job; disabled configuration removes it."""
    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    if not config.bilibili_enabled:
        return

    global _active_client, _active_credentials, _active_store, _shutdown_registered
    credentials = CredentialManager(config.bilibili_cookie)
    client = BilibiliClient(config, credentials)
    _active_client = client
    _active_credentials = credentials
    _active_store = SubscriptionStore()
    async def deliver(subscription, event) -> bool:
        return await deliver_event(subscription, event, client, config.bilibili_render_scale)

    poller = SubscriptionPoller(client, _active_store, deliver)

    if not config.bilibili_push_enabled:
        return

    if not _shutdown_registered:
        _shutdown_registered = True

        @get_driver().on_shutdown
        async def close_bilibili_client() -> None:
            if _active_client is not None:
                await _active_client.close()

    async def run_poll() -> None:
        await client.start()
        try:
            result = await poller.poll()
        except Exception as exc:
            logger.warning(f"Bilibili 轮询失败，等待下次恢复: {exc!r}")
            return
        if result.uid_count:
            logger.info(
                "Bilibili 轮询完成: uid=%s delivered=%s failed=%s",
                result.uid_count,
                result.delivered_count,
                result.failed_deliveries,
            )

    scheduler.add_job(
        run_poll,
        "interval",
        seconds=config.bilibili_poll_interval,
        jitter=min(5, max(0, config.bilibili_poll_interval - 1)),
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def get_client() -> BilibiliClient:
    if _active_client is None:
        raise RuntimeError("Bilibili service is disabled or has not initialized")
    return _active_client


def get_credentials() -> CredentialManager:
    if _active_credentials is None:
        raise RuntimeError("Bilibili service is disabled or has not initialized")
    return _active_credentials


def get_store() -> SubscriptionStore:
    if _active_store is None:
        raise RuntimeError("Bilibili service is disabled or has not initialized")
    return _active_store
