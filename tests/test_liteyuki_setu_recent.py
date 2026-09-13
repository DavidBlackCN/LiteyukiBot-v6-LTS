from __future__ import annotations

import asyncio
from io import BytesIO

import nonebot
import pytest


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


def _image(provider: str, name: str, pid=None, source_url=None):
    from src.nonebot_plugins.liteyuki_setu.models import ImageResult

    return ImageResult(
        provider=provider, image_url=f"https://image.example/{name}.jpg",
        pid=pid, source_url=source_url, is_adult=False,
    )


def _png(invert: bool = False) -> bytes:
    from PIL import Image

    image = Image.new("L", (16, 16))
    image.putdata([
        (255 - ((x * 13 + y * 7) % 256)) if invert else ((x * 13 + y * 7) % 256)
        for y in range(16) for x in range(16)
    ])
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_cross_provider_pixiv_pid_and_release_reservation() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.recent import RecentDeduplicator

    dedup = RecentDeduplicator()
    first = dedup.reserve(_image("lolicon", "a", pid=123), ttl_seconds=3600, max_entries=10)
    assert first is not None
    assert dedup.reserve(_image("duckmo", "b", pid=123), ttl_seconds=3600, max_entries=10) is None
    dedup.release(first)
    second = dedup.reserve(_image("random_mage", "c", pid=123), ttl_seconds=3600, max_entries=10)
    assert second is not None
    dedup.commit(second, ttl_seconds=3600, max_entries=10)
    assert dedup.reserve(_image("lolicon", "d", pid=123), ttl_seconds=3600, max_entries=10) is None


def test_same_canonical_url_and_small_hash_distance_are_duplicates() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.models import ImageResult
    from src.nonebot_plugins.liteyuki_setu.recent import RecentDeduplicator, hamming_distance

    dedup = RecentDeduplicator()
    first = ImageResult(provider="mirlkoi", image_url="https://IMAGE.example/a.jpg#first")
    lease = dedup.reserve(first, ttl_seconds=3600, max_entries=10)
    assert lease is not None
    dedup.commit(lease, ttl_seconds=3600, max_entries=10)
    second = ImageResult(provider="liemoe", image_url="https://image.example/a.jpg#second")
    assert dedup.reserve(second, ttl_seconds=3600, max_entries=10) is None
    assert hamming_distance(0b1010, 0b0101) == 4
    assert hamming_distance(0, 0b111) <= 3


def test_visual_hash_rejects_same_pixels_from_different_urls() -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu.recent import RecentDeduplicator

    dedup = RecentDeduplicator()
    first = dedup.reserve(_image("mirlkoi", "a"), ttl_seconds=3600, max_entries=10)
    assert first is not None and dedup.reserve_hash(first, _png())
    dedup.commit(first, ttl_seconds=3600, max_entries=10)
    second = dedup.reserve(_image("liemoe", "b"), ttl_seconds=3600, max_entries=10)
    assert second is not None
    assert not dedup.reserve_hash(second, _png())
    dedup.release(second)


def test_recent_ttl_and_max_entries(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import recent

    clock = [100.0]
    monkeypatch.setattr(recent.time, "monotonic", lambda: clock[0])
    dedup = recent.RecentDeduplicator()
    first_image = _image("mirlkoi", "a")
    first = dedup.reserve(first_image, ttl_seconds=10, max_entries=1)
    assert first is not None
    dedup.commit(first, ttl_seconds=10, max_entries=1)
    assert dedup.reserve(first_image, ttl_seconds=10, max_entries=1) is None

    second = dedup.reserve(_image("mirlkoi", "b"), ttl_seconds=10, max_entries=1)
    assert second is not None
    dedup.commit(second, ttl_seconds=10, max_entries=1)
    assert dedup.reserve(first_image, ttl_seconds=10, max_entries=1) is not None

    clock[0] = 200.0
    assert dedup.reserve(_image("mirlkoi", "b"), ttl_seconds=10, max_entries=1) is not None


def test_recent_duplicate_triggers_refill(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import service
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery
    from src.nonebot_plugins.liteyuki_setu.recent import RecentDeduplicator

    duplicate = _image("lolicon", "old", pid=123)
    fresh = _image("lolicon", "fresh", pid=456)
    dedup = RecentDeduplicator()
    old_lease = dedup.reserve(duplicate, ttl_seconds=3600, max_entries=10)
    assert old_lease is not None
    dedup.commit(old_lease, ttl_seconds=3600, max_entries=10)
    monkeypatch.setattr(service, "recent_dedup", dedup)
    monkeypatch.setattr(service, "_dedup_leases", {})

    requests = []

    class Provider:
        name = "lolicon"

        async def fetch(self, query):
            requests.append(query.count)
            return [duplicate] if len(requests) == 1 else [fresh]

    async def download(results, _config, *, client):
        return [(item, _png()) for item in results]

    monkeypatch.setattr(service, "download_results", download)
    config = SetuConfig(setu_recent_dedup_refill_attempts=2)
    result = asyncio.run(service._fetch_with_refills(
        Provider(), ImageQuery(count=1), config, object(),
    ))
    assert requests == [1, 1]
    assert result[0][0].pid == 456
    service.release_results(result)


def test_explicit_pid_bypasses_recent_dedup_but_random_does_not(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import service
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery, NoResultError
    from src.nonebot_plugins.liteyuki_setu.recent import RecentDeduplicator

    image = _image("duckmo", "same", pid=132660681)
    dedup = RecentDeduplicator()
    lease = dedup.reserve(image, ttl_seconds=3600, max_entries=10)
    assert lease is not None
    dedup.commit(lease, ttl_seconds=3600, max_entries=10)
    monkeypatch.setattr(service, "recent_dedup", dedup)
    monkeypatch.setattr(service, "_dedup_leases", {})

    class Provider:
        name = "duckmo"

        async def fetch(self, _query):
            return [image]

    async def download(results, _config, *, client):
        return [(item, _png()) for item in results]

    monkeypatch.setattr(service, "download_results", download)
    config = SetuConfig(setu_recent_dedup_refill_attempts=0)
    with pytest.raises(NoResultError, match="近期未发送"):
        asyncio.run(service._fetch_with_refills(
            Provider(), ImageQuery(count=1), config, object(),
        ))

    result = asyncio.run(service._fetch_with_refills(
        Provider(), ImageQuery(count=1, pid=[132660681]), config, object(),
    ))
    assert result[0][0].pid == 132660681
