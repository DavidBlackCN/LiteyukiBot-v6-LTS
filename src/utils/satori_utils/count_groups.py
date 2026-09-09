from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nonebot.adapters.satori import Bot


async def count_groups(bot: Bot) -> int:
    cnt: int = 0

    group_response = await bot.guild_list()
    while group_response.next is not None:
        cnt += len(group_response.data)
        group_response = await bot.friend_list(next_token=group_response.next)

    cnt += len(group_response.data)
    return cnt - 1
