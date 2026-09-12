from __future__ import annotations

import time
from typing import Any


RELOAD_RECEIPT_TTL_SECONDS = 180


def begin_reload(
    data: dict[str, Any],
    *,
    bot_id: object,
    session_type: str,
    session_id: object,
    now: float | None = None,
) -> None:
    data.update(
        {
            "reload": True,
            "reload_time": time.time() if now is None else now,
            "reload_bot_id": str(bot_id),
            "reload_session_type": session_type,
            "reload_session_id": session_id,
            "delta_time": 0,
        }
    )


def clear_reload(data: dict[str, Any]) -> None:
    data.update(
        {
            "reload": False,
            "reload_time": 0,
            "reload_bot_id": "",
            "reload_session_type": "",
            "reload_session_id": 0,
            "delta_time": 0,
        }
    )


def _elapsed(data: dict[str, Any], now: float) -> float | None:
    try:
        reload_time = float(data["reload_time"])
    except (KeyError, TypeError, ValueError):
        return None
    if reload_time <= 0:
        return None
    return max(0.0, now - reload_time)


def mark_worker_started(data: dict[str, Any], now: float | None = None) -> tuple[str, float | None]:
    """Return pending/expired/none and store the worker startup duration."""
    if not data.get("reload", False):
        return "none", None
    elapsed = _elapsed(data, time.time() if now is None else now)
    if elapsed is None or elapsed > RELOAD_RECEIPT_TTL_SECONDS:
        clear_reload(data)
        return "expired", elapsed
    data["delta_time"] = elapsed
    return "pending", elapsed


def prepare_reload_receipt(
    data: dict[str, Any], bot_id: object, now: float | None = None
) -> tuple[str, dict[str, Any]]:
    """Return receipt/mismatch/expired/none; clear only after a matching receipt is ready."""
    if not data.get("reload", False):
        return "none", {}
    expected_bot_id = str(data.get("reload_bot_id", ""))
    actual_bot_id = str(bot_id)
    if expected_bot_id != actual_bot_id:
        return "mismatch", {}
    elapsed = _elapsed(data, time.time() if now is None else now)
    if elapsed is None or elapsed > RELOAD_RECEIPT_TTL_SECONDS:
        clear_reload(data)
        return "expired", {}
    receipt = {
        "reload_time": data.get("reload_time", 0),
        "session_type": data.get("reload_session_type", "private"),
        "session_id": data.get("reload_session_id", 0),
        "delta_time": data.get("delta_time", 0),
    }
    clear_reload(data)
    return "receipt", receipt
