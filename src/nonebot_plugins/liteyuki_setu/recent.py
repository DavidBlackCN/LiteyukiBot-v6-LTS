from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

from .models import ImageResult


_PIXIV_PROVIDERS = {"lolicon", "duckmo", "random_mage"}


@dataclass
class _RecentEntry:
    keys: tuple[str, ...]
    dhash: int | None
    created_at: float


@dataclass
class DedupLease:
    lease_id: int
    keys: tuple[str, ...]
    dhash: int | None = None


class RecentDeduplicator:
    def __init__(self) -> None:
        self._entries: OrderedDict[int, _RecentEntry] = OrderedDict()
        self._key_index: dict[str, int] = {}
        self._leases: dict[int, DedupLease] = {}
        self._reserved_keys: set[str] = set()
        self._next_id = 1

    def reserve(self, result: ImageResult, *, ttl_seconds: float,
                max_entries: int) -> DedupLease | None:
        self._cleanup(ttl_seconds, max_entries)
        keys = result_identity_keys(result)
        if any(key in self._key_index or key in self._reserved_keys for key in keys):
            return None
        lease = DedupLease(self._next_id, keys)
        self._next_id += 1
        self._leases[lease.lease_id] = lease
        self._reserved_keys.update(keys)
        return lease

    def reserve_hash(self, lease: DedupLease, raw: bytes, *, distance: int = 3) -> bool:
        value = image_dhash(raw)
        if value is None:
            return True
        committed = (entry.dhash for entry in self._entries.values() if entry.dhash is not None)
        reserved = (item.dhash for item in self._leases.values()
                    if item.lease_id != lease.lease_id and item.dhash is not None)
        if any(hamming_distance(value, other) <= distance for other in (*committed, *reserved)):
            return False
        lease.dhash = value
        return True

    def commit(self, lease: DedupLease, *, ttl_seconds: float, max_entries: int) -> None:
        if self._leases.pop(lease.lease_id, None) is None:
            return
        self._reserved_keys.difference_update(lease.keys)
        entry = _RecentEntry(lease.keys, lease.dhash, time.monotonic())
        self._entries[lease.lease_id] = entry
        for key in entry.keys:
            self._key_index[key] = lease.lease_id
        self._cleanup(ttl_seconds, max_entries)

    def release(self, lease: DedupLease) -> None:
        if self._leases.pop(lease.lease_id, None) is None:
            return
        self._reserved_keys.difference_update(lease.keys)

    def _cleanup(self, ttl_seconds: float, max_entries: int) -> None:
        cutoff = time.monotonic() - ttl_seconds
        while self._entries:
            entry_id, entry = next(iter(self._entries.items()))
            if entry.created_at >= cutoff and len(self._entries) <= max_entries:
                break
            self._entries.pop(entry_id)
            for key in entry.keys:
                if self._key_index.get(key) == entry_id:
                    self._key_index.pop(key, None)


def result_identity_keys(result: ImageResult) -> tuple[str, ...]:
    keys: list[str] = []
    if result.pid is not None:
        if result.provider in _PIXIV_PROVIDERS or _is_pixiv_artwork(result.source_url):
            keys.append(f"pixiv:{result.pid}")
        else:
            keys.append(f"{result.provider}:pid:{result.pid}")
    if result.source_url:
        keys.append(f"source:{_canonical_url(result.source_url)}")
    keys.append(f"image:{_canonical_url(result.image_url)}")
    return tuple(dict.fromkeys(keys))


def image_dhash(raw: bytes) -> int | None:
    try:
        from PIL import Image

        with Image.open(BytesIO(raw)) as image:
            resampling = getattr(Image, "Resampling", Image).LANCZOS
            resized = image.convert("L").resize((9, 8), resampling)
            pixel_reader = getattr(resized, "get_flattened_data", resized.getdata)
            pixels = list(pixel_reader())
    except Exception:
        return None
    value = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            value = (value << 1) | int(pixels[offset + column] > pixels[offset + column + 1])
    return value


def hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))


def _is_pixiv_artwork(url: str | None) -> bool:
    return bool(url and "pixiv.net/artworks/" in url.lower())
