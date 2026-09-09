from nonebot.adapters import onebot
from src.utils.base.ly_typing import T_MessageEvent, T_GroupMessageEvent
from src.utils.satori_utils.compat import is_satori_object


def get_user_id(event: T_MessageEvent):
    if is_satori_object(event):
        return event.user.id
    else:
        return event.user_id


def get_group_id(event: T_GroupMessageEvent):
    if is_satori_object(event):
        return event.guild.id
    elif isinstance(
        event, (onebot.v11.GroupMessageEvent, onebot.v12.GroupMessageEvent)
    ):
        return event.group_id
    else:
        return None


def get_message_type(event: T_MessageEvent) -> str:
    if is_satori_object(event):
        return "private" if event.guild is None else "group"
    elif isinstance(event, onebot.v12.MessageEvent):
        return event.detail_type
    else:
        return event.message_type
