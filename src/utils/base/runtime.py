import time
from collections import defaultdict


_process_started_at = time.monotonic()
_message_sent: defaultdict[str, int] = defaultdict(int)
_message_received: defaultdict[str, int] = defaultdict(int)


def mark_process_started() -> None:
    """Reset metrics for the current NoneBot process."""
    global _process_started_at
    _process_started_at = time.monotonic()
    _message_sent.clear()
    _message_received.clear()


def get_process_uptime() -> float:
    return max(0.0, time.monotonic() - _process_started_at)


def record_message_sent(bot_id: str) -> None:
    _message_sent[str(bot_id)] += 1


def record_message_received(bot_id: str) -> None:
    _message_received[str(bot_id)] += 1


def get_message_counts(bot_id: str) -> tuple[int, int]:
    bot_id = str(bot_id)
    return _message_sent[bot_id], _message_received[bot_id]
