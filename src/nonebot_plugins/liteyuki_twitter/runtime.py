"""Lazy service lifecycle and adapter-aware delivery, with no startup requests."""
from __future__ import annotations

import time
from pathlib import Path

import nonebot
from nonebot_plugin_alconna import UniMessage

from .client import NitterClient
from .config import TwitterConfig
from . import group_settings
from .renderer import render_card, text_message
from .scheduler import TwitterPoller
from .storage import DATABASE_PATH, TwitterStore
from .translation import Translator

JOB_ID = "liteyuki_twitter.poll"
_service = None


def choose_bot(config):
    bots = nonebot.get_bots()
    if config.twitter_push_bot_id:
        return bots.get(config.twitter_push_bot_id)
    if len(bots) == 1:
        return next(iter(bots.values()))
    if len(bots) > 1:
        nonebot.logger.warning("X 播报跳过：多个 Bot 在线，请配置 twitter_push_bot_id")
    return None


class TwitterService:
    def __init__(self, config, store=None):
        self.config = config
        self.store = store or TwitterStore()
        self.client = NitterClient(config)
        self.translator = Translator(config, self.store)
        self.link_times = {}
        self.translation_times = {}
        self.poller = TwitterPoller(config, self.client, self.store, self.deliver)

    async def close(self):
        await self.translator.close()
        await self.client.close()

    async def status_post(self, account, post_id):
        cached = self.store.cached_post(post_id)
        if cached:
            return cached
        post = await self.client.get_status(account, post_id)
        self.store.cache_post(post)
        return post

    def cooldown(self, user_id, session, *, translate=False):
        values = self.translation_times if translate else self.link_times
        now = time.monotonic()
        lifetime = self.config.twitter_translation_cooldown if translate else 60
        for key in [key for key, timestamp in values.items() if timestamp + lifetime <= now]:
            values.pop(key, None)
        key = (user_id, session)
        if key in values:
            return False
        values[key] = now
        return True

    async def message(self, bot, post):
        try:
            image = await render_card(post, self.client, self.config)
            return await UniMessage.image(raw=image).export(bot)
        except Exception as error:
            nonebot.logger.warning("X 卡片生成失败，改用原文：{}", type(error).__name__)
            return text_message(post)

    async def deliver(self, group, post, subscription_account=None):
        bot = choose_bot(self.config)
        if bot is None:
            return False
        values = group_settings.settings(self.config, group)
        if values["translate_push"]:
            post = await self.translator.post(post, values["provider"])
        message = await self.message(bot, post)
        if not await group_settings.allowed(self.config, group, "push"):
            return False
        account = subscription_account or post.account
        follows = self.store.follows(self.config, group)
        if account not in follows:
            return False
        options = follows[account][0]
        if (post.reply and not options.replies) or (post.repost and not options.reposts) or (options.media_only and not (post.media or (post.quote and post.quote.media))):
            return False
        async def send(content):
            if hasattr(bot, "send_group_msg"):
                await bot.send_group_msg(group_id=int(group), message=content)
            else:
                await bot.call_api("send_message", detail_type="group", group_id=str(group), message=content)
        try:
            await send(message)
            return True
        except Exception:
            if not isinstance(message, str) and await group_settings.allowed(self.config, group, "push"):
                try:
                    await send(text_message(post))
                    return True
                except Exception:
                    pass
            nonebot.logger.warning("X 推文发送失败，保留队列等待重试")
            return False


def get_service() -> TwitterService:
    global _service
    if _service is None:
        from . import config
        _service = TwitterService(config)
    return _service


def configure_jobs(config: TwitterConfig):
    nonebot.require("nonebot_plugin_apscheduler")
    from nonebot_plugin_apscheduler import scheduler

    if scheduler.get_job(JOB_ID):
        scheduler.remove_job(JOB_ID)
    if not config.twitter_enabled:
        if Path(DATABASE_PATH).is_file():
            with TwitterStore().connect() as db:
                db.execute("UPDATE activity SET active=0")
        return

    async def poll():
        if choose_bot(config) is None:
            return
        try:
            result = await get_service().poller.poll()
            if result["sent"] or result["failed"]:
                nonebot.logger.info("X 播报完成：{}", result)
        except Exception as error:
            nonebot.logger.warning("X 轮询失败，等待恢复：{}", type(error).__name__)

    scheduler.add_job(poll, "interval", seconds=config.twitter_poll_interval, id=JOB_ID,
                      replace_existing=True, max_instances=1, coalesce=True)


@nonebot.get_driver().on_shutdown
async def close_service():
    global _service
    if _service:
        await _service.close()
        _service = None
