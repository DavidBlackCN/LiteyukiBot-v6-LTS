"""Shared, bounded HTTP client for Bilibili read APIs and QR login."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import md5
import time
import json
from typing import Any
from urllib.parse import urlencode, urljoin, urlsplit

import httpx
from nonebot import logger

from .config import BilibiliConfig
from .credential import CredentialManager, parse_cookie, serialize_cookie
from .errors import (
    BilibiliAPIError,
    BilibiliCredentialError,
    BilibiliNetworkError,
    BilibiliRateLimitError,
)
from .models import (
    BilibiliEvent,
    BilibiliLiveStatus,
    BilibiliLiveDisplay,
    BilibiliOriginalContent,
    BilibiliNav,
    BilibiliQRCode,
    BilibiliQRLoginResult,
    BilibiliUser,
    BilibiliVideo,
)


API_BASE = "https://api.bilibili.com"
PASSPORT_API_BASE = "https://passport.bilibili.com"
LIVE_API_BASE = "https://api.live.bilibili.com"
_SHORT_LINK_HOSTS = {"b23.tv", "www.b23.tv"}
_ALLOWED_HOSTS = _SHORT_LINK_HOSTS | {
    "bilibili.com",
    "www.bilibili.com",
    "m.bilibili.com",
    "live.bilibili.com",
    "t.bilibili.com",
    "space.bilibili.com",
}
_IMAGE_HOSTS = {"i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com"}
_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_WBI_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)


@dataclass(frozen=True)
class DownloadedImage:
    data: bytes
    content_type: str


class BilibiliClient:
    """Long-lived client. Construct once in the future service lifecycle."""

    def __init__(
        self,
        config: BilibiliConfig,
        credentials: CredentialManager,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self.credentials = credentials
        self._client = http_client
        self._owns_client = http_client is None
        self._wbi_mixin_key: str | None = None

    async def __aenter__(self) -> "BilibiliClient":
        await self.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def start(self) -> None:
        if self._client is not None:
            return
        options: dict[str, Any] = {
            "timeout": httpx.Timeout(self.config.bilibili_api_timeout),
            "follow_redirects": False,
        }
        if self.config.bilibili_proxy.strip():
            options["proxy"] = self.config.bilibili_proxy.strip()
        self._client = httpx.AsyncClient(**options)

    async def close(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
        self._client = None

    async def get_nav(self) -> BilibiliNav:
        data = await self._api_get(f"{API_BASE}/x/web-interface/nav")
        return BilibiliNav(
            is_login=bool(data.get("isLogin", False)),
            mid=str(data.get("mid") or ""),
            username=str(data.get("uname") or ""),
        )

    async def get_user_info(self, uid: str) -> BilibiliUser:
        data = await self._wbi_api_get(
            f"{API_BASE}/x/space/wbi/acc/info", {"mid": str(uid)}
        )
        return BilibiliUser(
            uid=str(data.get("mid") or uid),
            name=str(data.get("name") or ""),
            avatar_url=str(data.get("face") or ""),
        )

    async def get_latest_videos(self, uid: str) -> list[BilibiliVideo]:
        data = await self._wbi_api_get(
            f"{API_BASE}/x/space/wbi/arc/search",
            {"mid": str(uid), "pn": 1, "ps": 3, "order": "pubdate"},
        )
        listing = data.get("list") if isinstance(data.get("list"), dict) else {}
        videos = listing.get("vlist") if isinstance(listing.get("vlist"), list) else []
        return [self._video_from_api(video) for video in videos if isinstance(video, dict)]

    async def get_latest_dynamics(self, uid: str) -> list[BilibiliEvent]:
        data = await self._api_get(
            f"{API_BASE}/x/polymer/web-dynamic/v1/feed/space",
            {"host_mid": str(uid)},
        )
        items = data.get("items") if isinstance(data.get("items"), list) else []
        return [
            self._dynamic_from_api(item, fallback_uid=str(uid))
            for item in items
            if isinstance(item, dict)
        ]

    async def get_live_status(self, uid: str) -> BilibiliLiveStatus:
        data = await self._api_get(
            f"{LIVE_API_BASE}/room/v1/Room/getRoomInfoOld", {"mid": str(uid)}
        )
        room_id = str(data.get("room_id") or "")
        return BilibiliLiveStatus(
            uid=str(uid),
            room_id=room_id,
            live=bool(data.get("live_status")),
            title=str(data.get("title") or ""),
            area_name=str(data.get("area_name") or ""),
            cover_url=str(data.get("user_cover") or data.get("cover") or ""),
            url=f"https://live.bilibili.com/{room_id}" if room_id else "",
        )

    async def get_live_room_status(self, room_id: str) -> BilibiliLiveStatus:
        data = await self._api_get(
            f"{LIVE_API_BASE}/room/v1/Room/get_info", {"room_id": str(room_id)}
        )
        resolved_room_id = str(data.get("room_id") or room_id)
        return BilibiliLiveStatus(
            uid=str(data.get("uid") or ""),
            room_id=resolved_room_id,
            live=bool(data.get("live_status")),
            title=str(data.get("title") or ""),
            area_name=str(data.get("area_name") or ""),
            cover_url=str(data.get("user_cover") or data.get("keyframe") or ""),
            url=f"https://live.bilibili.com/{resolved_room_id}",
        )

    async def get_video_info(self, *, bvid: str = "", aid: str = "") -> BilibiliVideo:
        if not bvid and not aid:
            raise ValueError("bvid or aid is required")
        params = {"bvid": bvid} if bvid else {"aid": aid}
        return self._video_from_api(
            await self._api_get(f"{API_BASE}/x/web-interface/view", params)
        )

    async def get_dynamic_detail(self, dynamic_id: str) -> BilibiliEvent:
        data = await self._api_get(
            f"{API_BASE}/x/polymer/web-dynamic/v1/detail", {"id": str(dynamic_id)}
        )
        item = data.get("item")
        if not isinstance(item, dict):
            raise BilibiliAPIError("Bilibili dynamic detail was incomplete")
        return self._dynamic_from_api(item)

    async def create_qr_login(self) -> BilibiliQRCode:
        data = await self._api_get(f"{PASSPORT_API_BASE}/x/passport-login/web/qrcode/generate")
        url = str(data.get("url") or "")
        key = str(data.get("qrcode_key") or "")
        if not url or not key:
            raise BilibiliAPIError("QR login response was incomplete")
        return BilibiliQRCode(url=url, key=key)

    async def poll_qr_login(self, key: str) -> BilibiliQRLoginResult:
        response = await self._request(
            "GET",
            f"{PASSPORT_API_BASE}/x/passport-login/web/qrcode/poll",
            {"qrcode_key": key},
        )
        payload = self._json(response)
        self._raise_api_code(payload.get("code"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliAPIError("QR login response data was invalid")
        code = data.get("code")
        if code == 86101:
            return BilibiliQRLoginResult(status="waiting")
        if code == 86090:
            return BilibiliQRLoginResult(status="scanned")
        if code == 86038:
            return BilibiliQRLoginResult(status="expired")
        if code != 0:
            raise BilibiliAPIError("Bilibili QR login returned an unknown status")
        cookies: dict[str, str] = {}
        for header in response.headers.get_list("set-cookie"):
            cookies.update(parse_cookie(header.split(";", 1)[0]))
        return BilibiliQRLoginResult(
            status="confirmed",
            cookie=serialize_cookie(cookies),
            refresh_token=str(data.get("refresh_token") or ""),
        )

    async def resolve_short_url(self, url: str, max_redirects: int = 3) -> str:
        current = self._validate_short_url(url, require_short_host=True)
        for _ in range(max_redirects):
            response = await self._request("GET", current)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise BilibiliAPIError("Bilibili short link did not provide a location")
                current = self._validate_short_url(urljoin(current, location))
                continue
            if response.is_success:
                return current
            raise BilibiliNetworkError(f"Short link returned HTTP {response.status_code}")
        raise BilibiliAPIError("Bilibili short link exceeded redirect limit")

    async def download_image(self, url: str, max_bytes: int = 4 * 1024 * 1024) -> DownloadedImage:
        """Download only trusted Bilibili CDN images for local card embedding."""
        if url.startswith("//"):
            url = f"https:{url}"
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "http" and host in _IMAGE_HOSTS:
            url = parsed._replace(scheme="https").geturl()
            parsed = urlsplit(url)
        if parsed.scheme != "https" or host not in _IMAGE_HOSTS:
            logger.debug(f"Bilibili 图片下载跳过: host={host or '<empty>'} stage=host_validation")
            raise BilibiliAPIError("Bilibili image host was not allowed")
        if self._client is None:
            raise RuntimeError("BilibiliClient must be started before use")
        try:
            stage = "request"
            async with self._client.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 LiteyukiBot-v6-LTS Bilibili Service",
                    "Referer": "https://www.bilibili.com/",
                },
            ) as response:
                if response.is_error:
                    stage = "http_status"
                    raise BilibiliNetworkError(f"Bilibili image returned HTTP {response.status_code}")
                stage = "content_type"
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type not in _IMAGE_CONTENT_TYPES:
                    raise BilibiliAPIError("Bilibili image returned an unsupported content type")
                stage = "content_length"
                declared_size = response.headers.get("content-length")
                if declared_size and int(declared_size) > max_bytes:
                    raise BilibiliAPIError("Bilibili image exceeded size limit")
                stage = "read"
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > max_bytes:
                        raise BilibiliAPIError("Bilibili image exceeded size limit")
        except (BilibiliAPIError, BilibiliNetworkError) as exc:
            logger.debug(
                f"Bilibili 图片下载失败: host={host} stage={stage} error={type(exc).__name__}"
            )
            raise
        except ValueError as exc:
            logger.debug(f"Bilibili 图片下载失败: host={host} stage=content_length error=ValueError")
            raise BilibiliAPIError("Bilibili image returned an invalid content length") from exc
        except httpx.HTTPError as exc:
            logger.debug(f"Bilibili 图片下载失败: host={host} stage={stage} error={type(exc).__name__}")
            raise BilibiliNetworkError("Bilibili image request failed") from exc
        return DownloadedImage(bytes(chunks), content_type)

    async def _api_get(
        self, url: str, params: Mapping[str, str | int] | None = None
    ) -> dict[str, Any]:
        response = await self._request("GET", url, params)
        payload = self._json(response)
        self._raise_api_code(payload.get("code"))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise BilibiliAPIError("Bilibili API returned invalid data")
        return data

    async def _wbi_api_get(
        self, url: str, params: Mapping[str, str | int]
    ) -> dict[str, Any]:
        """Request a WBI endpoint, refreshing signing material once if it rotated."""
        for refresh in range(2):
            mixin_key = await self._get_wbi_mixin_key()
            try:
                return await self._api_get(url, _sign_wbi_params(params, mixin_key))
            except BilibiliAPIError as exc:
                if refresh or "code -403" not in str(exc):
                    raise
                self._wbi_mixin_key = None
        raise AssertionError("unreachable")

    async def _get_wbi_mixin_key(self) -> str:
        if self._wbi_mixin_key is not None:
            return self._wbi_mixin_key
        data = await self._api_get(f"{API_BASE}/x/web-interface/nav")
        wbi_img = data.get("wbi_img") if isinstance(data.get("wbi_img"), dict) else {}
        img_key = _wbi_key_from_url(wbi_img.get("img_url"))
        sub_key = _wbi_key_from_url(wbi_img.get("sub_url"))
        key_material = img_key + sub_key
        if len(key_material) < max(_WBI_MIXIN_KEY_ENC_TAB) + 1:
            raise BilibiliAPIError("Bilibili WBI signing material was invalid")
        self._wbi_mixin_key = "".join(
            key_material[index] for index in _WBI_MIXIN_KEY_ENC_TAB
        )[:32]
        return self._wbi_mixin_key

    async def _request(
        self,
        method: str,
        url: str,
        params: Mapping[str, str | int] | None = None,
    ) -> httpx.Response:
        if self._client is None:
            raise RuntimeError("BilibiliClient must be started before use")
        headers = {
            "User-Agent": "Mozilla/5.0 LiteyukiBot-v6-LTS Bilibili Service",
            "Referer": "https://www.bilibili.com/",
            "Accept": "application/json, text/plain, */*",
        }
        cookie = self.credentials.get().cookie_header
        if cookie:
            headers["Cookie"] = cookie
        try:
            response = await self._client.request(method, url, params=params, headers=headers)
        except httpx.TimeoutException as exc:
            raise BilibiliNetworkError("Bilibili request timed out") from exc
        except httpx.HTTPError as exc:
            raise BilibiliNetworkError("Bilibili request failed") from exc
        if response.status_code == 412:
            raise BilibiliRateLimitError("Bilibili anti-crawling response")
        if response.status_code in {401, 403}:
            raise BilibiliCredentialError(f"Bilibili returned HTTP {response.status_code}")
        if response.is_error:
            raise BilibiliNetworkError(f"Bilibili returned HTTP {response.status_code}")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise BilibiliAPIError("Bilibili returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise BilibiliAPIError("Bilibili returned a non-object JSON payload")
        return payload

    @staticmethod
    def _raise_api_code(code: object) -> None:
        if code == 0:
            return
        if code == -101:
            raise BilibiliCredentialError("Bilibili credential is invalid")
        if code == -412:
            raise BilibiliRateLimitError("Bilibili API anti-crawling response")
        raise BilibiliAPIError(f"Bilibili API returned code {code!r}")

    @staticmethod
    def _validate_short_url(url: str, require_short_host: bool = False) -> str:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host:
            raise BilibiliAPIError("Bilibili short link URL was invalid")
        if require_short_host and host not in _SHORT_LINK_HOSTS:
            raise BilibiliAPIError("URL is not a Bilibili short link")
        if host not in _ALLOWED_HOSTS:
            raise BilibiliAPIError("Bilibili short link redirected to an untrusted host")
        return url

    @staticmethod
    def _video_from_api(data: Mapping[str, Any]) -> BilibiliVideo:
        owner = data.get("owner") if isinstance(data.get("owner"), dict) else {}
        stat = data.get("stat") if isinstance(data.get("stat"), dict) else {}
        bvid = str(data.get("bvid") or "")
        aid = str(data.get("aid") or data.get("id") or "")
        timestamp = _timestamp(data.get("pubdate") or data.get("created"))
        return BilibiliVideo(
            aid=aid,
            bvid=bvid,
            title=str(data.get("title") or ""),
            description=str(data.get("desc") or data.get("description") or ""),
            url=f"https://www.bilibili.com/video/{bvid}" if bvid else "",
            cover_url=str(data.get("pic") or data.get("cover") or ""),
            author_name=str(owner.get("name") or data.get("author") or ""),
            author_uid=str(owner.get("mid") or data.get("mid") or ""),
            avatar_url=str(owner.get("face") or ""),
            timestamp=timestamp,
            metrics={
                key: _integer(stat.get(key) if stat else data.get(key))
                for key in ("view", "like", "reply", "coin")
            },
        )

    @staticmethod
    def _dynamic_from_api(
        data: Mapping[str, Any], fallback_uid: str = ""
    ) -> BilibiliEvent:
        modules = _mapping(data.get("modules"))
        author = _mapping(modules.get("module_author"))
        content = _dynamic_content(data)
        original = None
        if isinstance(data.get("orig"), dict):
            source = data["orig"]
            original = BilibiliOriginalContent(
                **_dynamic_content(source),
                author_name=str(_mapping(_mapping(source.get("modules")).get("module_author")).get("name") or ""),
                url=f"https://t.bilibili.com/{source['id_str']}" if source.get("id_str") else "",
                unavailable=source.get("type") == "DYNAMIC_TYPE_NONE" or not source.get("modules"),
            )
        event_id = str(data.get("id_str") or data.get("id") or "")
        if not event_id:
            raise BilibiliAPIError("Bilibili dynamic item did not contain an id")
        # Keep source kind dynamic: the subscription cursor depends on it.
        return BilibiliEvent(
            kind="dynamic",
            uid=str(author.get("mid") or fallback_uid),
            event_id=event_id,
            title=content["title"] or (original.title if original else "") or "动态更新",
            body=content["body"],
            cover_urls=list(dict.fromkeys([
                *content["cover_urls"], *(original.cover_urls if original else [])
            ])),
            live=content["live"],
            display_type="forward" if original else "live" if content["live"] else "dynamic",
            original=original,
            url=f"https://t.bilibili.com/{event_id}",
            author_name=str(author.get("name") or ""),
            avatar_url=str(author.get("face") or ""),
            timestamp=_timestamp(author.get("pub_ts")),
        )


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _plain_text(value: object) -> str:
    if isinstance(value, str):
        return value
    content = _mapping(value)
    if isinstance(content.get("text"), str) and content["text"]:
        return content["text"]
    nodes = content.get("rich_text_nodes")
    if not isinstance(nodes, list):
        return ""
    return "".join(str(node.get("text") or node.get("orig_text") or "") for node in nodes if isinstance(node, dict))


def _dynamic_content(data: Mapping[str, Any]) -> dict[str, Any]:
    dynamic = _mapping(_mapping(data.get("modules")).get("module_dynamic"))
    major = _mapping(dynamic.get("major"))
    opus = _mapping(major.get("opus"))
    archive = _mapping(major.get("archive"))
    ugc = _mapping(_mapping(dynamic.get("additional")).get("ugc"))
    live_data = _mapping(major.get("live"))
    recommendation = _mapping(major.get("live_rcmd")).get("content")
    if isinstance(recommendation, str):
        try:
            recommendation = json.loads(recommendation)
        except (ValueError, TypeError):
            recommendation = {}
    recommendation = _mapping(recommendation)
    live_data = _mapping(recommendation.get("live_play_info")) or live_data
    live = None
    if live_data:
        room_id = str(live_data.get("room_id") or live_data.get("id") or "")
        live = BilibiliLiveDisplay(
            title=str(live_data.get("title") or "直播分享"),
            cover_url=str(live_data.get("cover") or live_data.get("user_cover") or ""),
            area_name=str(live_data.get("area_name") or live_data.get("area") or ""),
            url=f"https://live.bilibili.com/{room_id}" if room_id.isdecimal() else "",
            state="已下播" if str(live_data.get("live_status")) == "0" else "正在直播" if str(live_data.get("live_status")) == "1" else "直播分享",
        )
    covers: list[str] = []
    for media in (archive, ugc):
        if media.get("cover"):
            covers.append(str(media["cover"]))
    for media, field in ((_mapping(major.get("draw")), "items"), (opus, "pics")):
        for item in media.get(field, []) if isinstance(media.get(field), list) else []:
            source = _mapping(item).get("src") or _mapping(item).get("url")
            if source and str(source) not in covers:
                covers.append(str(source))
    if live and live.cover_url and live.cover_url not in covers:
        covers.append(live.cover_url)
    return {
        "title": str(opus.get("title") or archive.get("title") or ugc.get("title") or (live.title if live else "")),
        "body": _plain_text(dynamic.get("desc")) or _plain_text(opus.get("summary")),
        "cover_urls": covers,
        "live": live,
    }


def _integer(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _timestamp(value: object) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), UTC)
    except (TypeError, ValueError, OSError):
        return None


def _wbi_key_from_url(value: object) -> str:
    if not isinstance(value, str):
        return ""
    filename = urlsplit(value).path.rsplit("/", 1)[-1]
    return filename.rsplit(".", 1)[0] if "." in filename else ""


def _sign_wbi_params(
    params: Mapping[str, str | int], mixin_key: str, timestamp: int | None = None
) -> dict[str, str | int]:
    signed: dict[str, str | int] = dict(params)
    signed["wts"] = int(time.time()) if timestamp is None else timestamp
    query = urlencode(
        sorted(
            (key, "".join(char for char in str(value) if char not in "!'()*"))
            for key, value in signed.items()
        )
    )
    signed["w_rid"] = md5(f"{query}{mixin_key}".encode()).hexdigest()
    return signed
