from __future__ import annotations

import asyncio
from typing import Any

try:
    from nonebot import logger
except ImportError:  # keeps pure logic tests importable without a running NoneBot
    import logging
    logger = logging.getLogger(__name__)


_tasks: set[asyncio.Task[Any]] = set()


def schedule_recall(receipt: Any, seconds: int) -> None:
    """Schedule best-effort recall. Bot restarts may discard these short tasks."""
    if receipt is None or not callable(getattr(receipt, "recall", None)):
        return
    task = asyncio.create_task(_recall_later(receipt, seconds))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _recall_later(receipt: Any, seconds: int) -> None:
    await asyncio.sleep(seconds)
    try:
        await receipt.recall()
    except Exception as exc:
        logger.debug(f"二次元图片撤回失败: {exc!r}")
