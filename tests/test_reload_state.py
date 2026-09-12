from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    path = Path("src/liteyuki_main/reload_state.py")
    spec = importlib.util.spec_from_file_location("reload_state_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reload_bot_id_is_normalized_and_matching_receipt_clears_state() -> None:
    state = _load_module()
    data: dict[str, object] = {}
    state.begin_reload(
        data,
        bot_id=12345,
        session_type="group",
        session_id=10001,
        now=1000,
    )

    assert data["reload_bot_id"] == "12345"
    # 兼容旧记录可能遗留的整数 self_id。
    data["reload_bot_id"] = 12345
    assert state.mark_worker_started(data, now=1010) == ("pending", 10)
    status, receipt = state.prepare_reload_receipt(data, "12345", now=1012)
    assert status == "receipt"
    assert receipt["session_id"] == 10001
    assert receipt["delta_time"] == 10
    assert data == {
        "reload": False,
        "reload_time": 0,
        "reload_bot_id": "",
        "reload_session_type": "",
        "reload_session_id": 0,
        "delta_time": 0,
    }


def test_mismatched_bot_does_not_clear_other_bot_reload_state() -> None:
    state = _load_module()
    data: dict[str, object] = {}
    state.begin_reload(data, bot_id="one", session_type="private", session_id=1, now=1000)

    assert state.prepare_reload_receipt(data, "two", now=1010) == ("mismatch", {})
    assert data["reload"] is True
    assert data["reload_bot_id"] == "one"


def test_expired_reload_is_cleared_without_a_receipt() -> None:
    state = _load_module()
    data: dict[str, object] = {}
    state.begin_reload(data, bot_id="one", session_type="group", session_id=1, now=1000)

    assert state.mark_worker_started(data, now=1000 + state.RELOAD_RECEIPT_TTL_SECONDS + 1) == (
        "expired",
        state.RELOAD_RECEIPT_TTL_SECONDS + 1,
    )
    assert state.prepare_reload_receipt(data, "one", now=9999) == ("none", {})
    assert data["reload"] is False
    assert data["delta_time"] == 0
