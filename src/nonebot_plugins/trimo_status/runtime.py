from nonebot import Bot
from nonebot.adapters import Event, satori
from nonebot.message import event_preprocessor

from src.utils.base.runtime import record_message_received, record_message_sent


MESSAGE_SEND_APIS = {
    "send_msg",
    "send_group_msg",
    "send_private_msg",
    "send_message",
    "send_group_forward_msg",
    "send_private_forward_msg",
}


@event_preprocessor
async def count_received_message(bot: Bot, event: Event) -> None:
    if event.get_type() != "message":
        return

    # Satori may report the bot's own outgoing messages as events.
    if isinstance(event, satori.MessageEvent) and event.user.id == event.self_id:
        record_message_sent(bot.self_id)
    else:
        record_message_received(bot.self_id)


@Bot.on_called_api
async def count_sent_message(
    bot: Bot,
    exception: Exception | None,
    api: str,
    data: dict,
    result: object,
) -> None:
    if exception is None and api in MESSAGE_SEND_APIS:
        record_message_sent(bot.self_id)
