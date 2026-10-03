"""One fetch per account, durable discovery and independent per-group delivery."""
from __future__ import annotations

import asyncio

from nonebot import logger

from . import group_settings
from .models import Post, TwitterError


class TwitterPoller:
    def __init__(self, config, client, store, deliver, *, can_push=None):
        self.config, self.client, self.store, self.deliver = config, client, store, deliver
        self.can_push = can_push or (lambda group: group_settings.allowed(config, group, "push"))
        self.lock = asyncio.Lock()

    async def poll(self):
        async with self.lock:
            return await self._poll()

    async def _poll(self):
        grouped, active = {}, {}
        result = {"accounts": 0, "queued": 0, "sent": 0, "failed": 0}
        for group in self.config.twitter_group_ids:
            enabled = await self.can_push(group)
            self.store.set_active(group, enabled)
            if not enabled:
                continue
            follows = self.store.follows(self.config, group)
            self.store.prune_accounts(group, follows)
            active[group] = follows
            for account, (options, _) in follows.items():
                grouped.setdefault(account, []).append((group, options))
        slots = asyncio.Semaphore(self.config.twitter_concurrency)

        async def fetch(account, targets):
            async with slots:
                try:
                    posts = await self.client.get_timeline(account)
                except TwitterError as error:
                    logger.warning("X 账号 {} 获取失败：{}", account, str(error))
                    return 0
                queued = 0
                for group, options in targets:
                    if self.store.window_gap(group, account, posts):
                        logger.warning("X 账号 {} 时间线窗口没有覆盖上次记录，可能存在未获取的历史", account)
                    queued += self.store.ingest(group, options, posts)
                return queued

        values = await asyncio.gather(*(fetch(account, targets) for account, targets in grouped.items()), return_exceptions=True)
        result["accounts"] = len(grouped)
        for value in values:
            if isinstance(value, Exception):
                logger.warning("X 轮询异常已隔离：{}", type(value).__name__)
            else:
                result["queued"] += value
        for group, follows in active.items():
            for row in self.store.pending(group):
                current = self.store.follows(self.config, group)
                if row["account"] not in current:
                    self.store.finish(row, True)
                    continue
                if not await self.can_push(group):
                    self.store.set_active(group, False)
                    break
                post = Post.loads(row["payload"])
                options = current[row["account"]][0]
                if (post.reply and not options.replies) or (post.repost and not options.reposts) or (options.media_only and not (post.media or (post.quote and post.quote.media))):
                    self.store.finish(row, True)
                    continue
                try:
                    success = await self.deliver(group, post, row["account"])
                except Exception as error:
                    logger.warning("X 群发送异常已隔离：{}", type(error).__name__)
                    success = False
                self.store.finish(row, success)
                result["sent" if success else "failed"] += 1
        self.store.cleanup()
        return result
