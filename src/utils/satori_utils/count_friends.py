from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nonebot.adapters.satori import Bot


async def count_friends(bot: Bot) -> int:
    cnt: int = 0

    friend_response = await bot.friend_list()
    while friend_response.next is not None:
        cnt += len(friend_response.data)
        friend_response = await bot.friend_list(next_token=friend_response.next)

    cnt += len(friend_response.data)
    return cnt - 1
