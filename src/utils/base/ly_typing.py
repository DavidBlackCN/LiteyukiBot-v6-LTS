from nonebot.adapters.onebot import v11, v12

try:
    from nonebot.adapters import satori
except ImportError:
    satori = None

if satori is None:
    T_Bot = v11.Bot | v12.Bot
    T_MessageEvent = v11.MessageEvent | v12.MessageEvent
    T_Message = v11.Message | v12.Message
else:
    T_Bot = v11.Bot | v12.Bot | satori.Bot
    T_MessageEvent = v11.MessageEvent | v12.MessageEvent | satori.MessageEvent
    T_Message = v11.Message | v12.Message | satori.Message
T_GroupMessageEvent = v11.GroupMessageEvent | v12.GroupMessageEvent
T_PrivateMessageEvent = v11.PrivateMessageEvent | v12.PrivateMessageEvent
