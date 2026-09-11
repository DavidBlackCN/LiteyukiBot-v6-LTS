"""UID-aggregated polling with per-target delivery confirmation."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from nonebot import logger

from .models import BilibiliEvent, BilibiliLiveStatus, BilibiliSubscription, BilibiliVideo
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
                    dynamic_id=dynamics[0].event_id if dynamics else "",
                    video_id=video_events[0].event_id if video_events else "",
                    live_state=_live_state(live_status),
                )

            if current.dynamic_enabled and not missing_dynamic:
                result = await self._deliver_events(current, _events_after(dynamics, current.last_dynamic_id))
                delivered += result[0]
                failed += result[1]
            if current.video_enabled and not missing_video:
                result = await self._deliver_events(current, _events_after(video_events, current.last_video_id))
                delivered += result[0]
                failed += result[1]
            if current.live_enabled and not missing_live and live_status is not None:
                event = _live_event(live_status)
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
    """Return unseen events oldest first; API lists are newest first."""
    unseen: list[BilibiliEvent] = []
    seen: set[str] = set()
    for event in events:
        if event.event_id == cursor:
            break
        if event.event_id and event.event_id not in seen:
            unseen.append(event)
            seen.add(event.event_id)
    unseen.reverse()
    return unseen


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
        cover_urls=[video.cover_url] if video.cover_url else [],
        timestamp=video.timestamp,
        metrics=video.metrics,
    )


def _live_state(status: BilibiliLiveStatus | None) -> str:
    if status is None:
        return "unknown"
    return "live" if status.live else "offline"


def _live_event(status: BilibiliLiveStatus) -> BilibiliEvent | None:
    if not status.room_id and not status.title:
        return None
    state = "live_start" if status.live else "live_end"
    return BilibiliEvent(
        kind=state,
        uid=status.uid,
        event_id=f"{status.room_id}:{state}",
        title=status.title or ("直播开始" if status.live else "直播结束"),
        url=status.url,
        cover_urls=[status.cover_url] if status.cover_url else [],
        metrics={"area": status.area_name},
    )
