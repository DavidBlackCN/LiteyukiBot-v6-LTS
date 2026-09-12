import threading

from liteyuki.comm import channel


def reload(delay: float = 0.0, receiver: str = "nonebot"):
    """
    重载 LiteyukiBot 的当前 NoneBot Worker。

    Args:
        receiver: 保留兼容参数。
        delay: 延迟发送重载信号的秒数。
    """

    if delay > 0:
        threading.Timer(
            delay,
            lambda: channel.active_channel.send(1),
        ).start()
        return

    channel.active_channel.send(1)