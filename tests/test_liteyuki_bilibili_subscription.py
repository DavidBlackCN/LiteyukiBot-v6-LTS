from src.nonebot_plugins.liteyuki_bilibili.models import BilibiliEvent
from src.nonebot_plugins.liteyuki_bilibili.storage import SubscriptionStore


def test_add_update_and_remove_subscription(tmp_path) -> None:
    store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
    subscription, created = store.add(
        target_type="group", target_id="100", uid="42", created_by="admin"
    )
    assert created and subscription.dynamic_enabled

    updated, created = store.add(
        target_type="group",
        target_id="100",
        uid="42",
        dynamic_enabled=False,
        video_enabled=True,
        live_enabled=False,
        at_all=True,
    )
    assert not created
    assert not updated.dynamic_enabled and updated.video_enabled
    assert not updated.live_enabled and updated.at_all
    assert store.remove("group", "100", "42")
    assert not store.remove("group", "100", "42")


def test_baseline_is_per_target_and_never_overwrites_existing_cursor(tmp_path) -> None:
    store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
    for target_id in ("group-a", "group-b"):
        store.add(target_type="group", target_id=target_id, uid="42")
    first = store.initialize_baseline(
        "group", "group-a", "42", dynamic_id="d1", video_id="BV1", live_state="offline"
    )
    second = store.initialize_baseline(
        "group", "group-b", "42", dynamic_id="d2", video_id="BV2", live_state="live"
    )
    unchanged = store.initialize_baseline(
        "group", "group-a", "42", dynamic_id="old", video_id="old", live_state="live"
    )
    assert (first.last_dynamic_id, first.last_video_id, first.last_live_state) == ("d1", "BV1", "offline")
    assert (second.last_dynamic_id, second.last_video_id, second.last_live_state) == ("d2", "BV2", "live")
    assert (unchanged.last_dynamic_id, unchanged.last_video_id, unchanged.last_live_state) == ("d1", "BV1", "offline")


def test_delivery_advances_only_the_confirmed_target_and_persists_after_reopen(tmp_path) -> None:
    database = str(tmp_path / "bilibili.ldb")
    store = SubscriptionStore(database)
    store.add(target_type="group", target_id="a", uid="42")
    store.add(target_type="group", target_id="b", uid="42")
    event = BilibiliEvent(kind="dynamic", uid="42", event_id="new-dynamic")

    store.record_delivery("group", "a", "42", event)
    assert store.get("group", "a", "42").last_dynamic_id == "new-dynamic"
    assert store.get("group", "b", "42").last_dynamic_id == ""
    assert SubscriptionStore(database).get("group", "a", "42").last_dynamic_id == "new-dynamic"


def test_active_subscriptions_can_be_aggregated_by_uid(tmp_path) -> None:
    store = SubscriptionStore(str(tmp_path / "bilibili.ldb"))
    store.add(target_type="group", target_id="a", uid="42")
    store.add(target_type="private", target_id="b", uid="42", dynamic_enabled=False, video_enabled=False, live_enabled=False)
    store.add(target_type="group", target_id="c", uid="99")

    assert [item.target_id for item in store.list_uid("42")] == ["a", "b"]
    assert [(item.uid, item.target_id) for item in store.list_active()] == [("42", "a"), ("99", "c")]
