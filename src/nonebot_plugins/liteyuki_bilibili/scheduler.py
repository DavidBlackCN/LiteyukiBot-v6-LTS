"""UID-aggregated polling with per-target delivery confirmation."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from nonebot import logger

from .models import (
    BilibiliEvent,
    BilibiliLiveStatus,
    BilibiliSubscription,
    BilibiliUser,
    BilibiliVideo,
)
from .storage import SubscriptionStore


Delivery = Callable[[BilibiliSubscription, BilibiliEvent], Awaitable[bool]]


@dataclass(frozen=True)
class PollResult:
    uid_count: int = 0
    delivered_count: int = 0
    failed_deliveries: int = 0


class SubscriptionPoller:
    """Fetch an UP once, then fan out independently to every subscribed target."""

    def __init__(
        self,
        client,
        store: SubscriptionStore,
        deliver: Delivery,
        *,
        concurrency: int = 4,
    ) -> None:
        self.client = client
        self.store = store
        self.deliver = deliver
        self.concurrency = max(1, concurrency)

    async def poll(self) -> PollResult:
        grouped: dict[str, list[BilibiliSubscription]] = defaultdict(list)
        for subscription in self.store.list_active():
            grouped[subscription.uid].append(subscription)
        if not grouped:
            return PollResult()

        semaphore = asyncio.Semaphore(self.concurrency)

        async def poll_one(uid: str, subscriptions: list[BilibiliSubscription]) -> PollResult:
            async with semaphore:
                return await self._poll_uid(uid, subscriptions)

        results = await asyncio.gather(
            *(poll_one(uid, subscriptions) for uid, subscriptions in grouped.items()),
            return_exceptions=True,
        )
        delivered = failed = 0
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Bilibili 轮询任务异常，已隔离: {result!r}")
                continue
            delivered += result.delivered_count
            failed += result.failed_deliveries
        return PollResult(len(grouped), delivered, failed)

    async def _poll_uid(
        self, uid: str, subscriptions: Sequence[BilibiliSubscription]
    ) -> PollResult:
        dynamic_task = asyncio.create_task(self.client.get_latest_dynamics(uid))
        video_task = asyncio.create_task(self.client.get_latest_videos(uid))
        live_task = asyncio.create_task(self.client.get_live_status(uid))
        dynamic_result, video_result, live_result = await asyncio.gather(
            dynamic_task, video_task, live_task, return_exceptions=True
        )
        dynamics = _safe_result("动态", uid, dynamic_result, [])
        videos = _safe_result("视频", uid, video_result, [])
        live_status = _safe_result("直播", uid, live_result, None)
        video_events = [_video_event(video, uid) for video in videos]
        delivered = failed = 0
        live_user: BilibiliUser | None = None
        live_transition = live_status is not None and any(
            subscription.live_enabled
            and subscription.last_live_state != "unknown"
            and subscription.last_live_state != _live_state(live_status)
            for subscription in subscriptions
        )
        if live_transition:
            try:
                live_user = await self.client.get_user_info(uid)
            except Exception as exc:
                logger.warning(
                    f"Bilibili 直播 UP 信息获取失败，使用 UID 回退: uid={uid} error={exc!r}"
                )

        for subscription in subscriptions:
            current = subscription
            missing_dynamic = current.last_dynamic_id == ""
            missing_video = current.last_video_id == ""
            missing_live = current.last_live_state == "unknown"
            if missing_dynamic or missing_video or missing_live:
                current = self.store.initialize_baseline(
                    current.target_type,
                    current.target_id,
                    current.uid,
                    dynamic_id=latest_dynamic_id(dynamics),
                    video_id=latest_video_id(video_events),
                    live_state=_live_state(live_status),
                )
                logger.debug(f"Bilibili 轮询 baseline 初始化: uid={uid}")

            if current.dynamic_enabled and not missing_dynamic:
                dynamic_events, rebase_id, reason = _dynamic_events_after(
                    dynamics, current.last_dynamic_id
                )
                if reason:
                    logger.warning(
                        f"Bilibili 动态游标丢失，已安全 rebase: uid={uid} "
                        f"old={current.last_dynamic_id} new={rebase_id or current.last_dynamic_id}"
                    )
                    if rebase_id:
                        current = self.store.rebase_dynamic_cursor(
                            current.target_type, current.target_id, current.uid, rebase_id
                        )
                result = await self._deliver_events(current, dynamic_events)
                delivered += result[0]
                failed += result[1]
            if current.video_enabled and not missing_video:
                video_ids = {event.event_id for event in video_events if event.event_id}
                if current.last_video_id not in video_ids:
                    rebase_id = latest_video_id(video_events)
                    logger.warning(
                        f"Bilibili 视频游标丢失，已安全 rebase: uid={uid} "
                        f"old={current.last_video_id} new={rebase_id or current.last_video_id}"
                    )
                    if rebase_id:
                        current = self.store.rebase_video_cursor(
                            current.target_type, current.target_id, current.uid, rebase_id
                        )
                    video_events_after: list[BilibiliEvent] = []
                else:
                    video_events_after = _events_after(video_events, current.last_video_id)
                result = await self._deliver_events(current, video_events_after)
                delivered += result[0]
                failed += result[1]
            if current.live_enabled and not missing_live and live_status is not None:
                event = _live_event(live_status, live_user)
                if event is not None and current.last_live_state != _live_state(live_status):
                    result = await self._deliver_events(current, [event])
                    delivered += result[0]
                    failed += result[1]
        return PollResult(uid_count=1, delivered_count=delivered, failed_deliveries=failed)

    async def _deliver_events(
        self, subscription: BilibiliSubscription, events: Sequence[BilibiliEvent]
    ) -> tuple[int, int]:
        delivered = failed = 0
        for event in events:
            try:
                sent = await self.deliver(subscription, event)
            except Exception as exc:
                logger.warning(
                    "Bilibili 推送失败: uid=%s target=%s:%s event=%s:%s error=%r",
                    subscription.uid,
                    subscription.target_type,
                    subscription.target_id,
                    event.kind,
                    event.event_id,
                    exc,
                )
                failed += 1
                continue
            if not sent:
                failed += 1
                continue
            self.store.record_delivery(
                subscription.target_type, subscription.target_id, subscription.uid, event
            )
            delivered += 1
        return delivered, failed


def _safe_result(label: str, uid: str, result, fallback):
    if isinstance(result, Exception):
        logger.warning(f"Bilibili {label}轮询失败: uid={uid} error={result!r}")
        return fallback
    return result


def _events_after(events: Sequence[BilibiliEvent], cursor: str) -> list[BilibiliEvent]:
    """Return unseen events only when the cursor is present in this API page."""
    unseen: list[BilibiliEvent] = []
    seen: set[str] = set()
    cursor_found = False
    for event in events:
        if event.event_id == cursor:
            cursor_found = True
            break
        if event.event_id and event.event_id not in seen:
            unseen.append(event)
            seen.add(event.event_id)
    return list(reversed(unseen)) if cursor_found else []


def latest_dynamic_id(events: Sequence[BilibiliEvent]) -> str:
    """Return the highest valid Bilibili dynamic ID, ignoring pinned list order."""
    ids = [event.event_id for event in events if event.event_id.isdecimal()]
    return max(ids, key=int, default="")


def latest_video_id(events: Sequence[BilibiliEvent]) -> str:
    return next((event.event_id for event in events if event.event_id), "")


def _dynamic_events_after(
    events: Sequence[BilibiliEvent], cursor: str
) -> tuple[list[BilibiliEvent], str, str]:
    """Use monotonic numeric IDs so missing pages cannot replay old dynamics."""
    newest = latest_dynamic_id(events)
    if not cursor.isdecimal():
        return [], newest, "invalid cursor"
    if not newest or any(not event.event_id.isdecimal() for event in events):
        return [], newest, "invalid API data"
    cursor_value = int(cursor)
    unseen = {
        event.event_id: event
        for event in events
        if int(event.event_id) > cursor_value
    }
    return sorted(unseen.values(), key=lambda event: int(event.event_id)), "", ""


def _video_event(video: BilibiliVideo, fallback_uid: str) -> BilibiliEvent:
    event_id = video.bvid or video.aid
    return BilibiliEvent(
        kind="video",
        uid=video.author_uid or fallback_uid,
        event_id=event_id,
        title=video.title,
        body=video.description,
        url=video.url,
        author_name=video.author_name,
        avatar_url=video.avatar_url,
        cover_urls=[video.cover_url] if video.cover_url else [],
        timestamp=video.timestamp,
        metrics=video.metrics,
    )


def _live_state(status: BilibiliLiveStatus | None) -> str:
    if status is None:
        return "unknown"
    return "live" if status.live else "offline"


def _live_event(
    status: BilibiliLiveStatus, user: BilibiliUser | None = None
) -> BilibiliEvent | None:
    if not status.room_id and not status.title:
        return None
    state = "live_start" if status.live else "live_end"
    return BilibiliEvent(
        kind=state,
        uid=status.uid,
        event_id=f"{status.room_id}:{state}",
        title=status.title or ("直播开始" if status.live else "直播结束"),
        url=status.url,
        author_name=user.name if user and user.name else f"UP {status.uid}",
        avatar_url=user.avatar_url if user else "",
        cover_urls=[status.cover_url] if status.cover_url else [],
        timestamp=datetime.now(UTC),
        metrics={"area": status.area_name},
    )
