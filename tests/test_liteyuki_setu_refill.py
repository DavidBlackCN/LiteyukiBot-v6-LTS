from __future__ import annotations

import asyncio
from types import SimpleNamespace

import nonebot


def _init() -> None:
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()


class _HttpClient:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def _image(name: str, pid: int | None = None):
    from src.nonebot_plugins.liteyuki_setu.models import ImageResult

    return ImageResult(provider="lolicon", image_url=f"https://image.example/{name}.jpg", pid=pid,
                       is_adult=False)


def _run_refill(monkeypatch, batches, *, fail_once: set[str] | None = None):
    _init()
    from src.nonebot_plugins.liteyuki_setu import service
    from src.nonebot_plugins.liteyuki_setu.config import SetuConfig
    from src.nonebot_plugins.liteyuki_setu.models import ImageQuery

    requests = []
    downloaded_candidates = []
    pending = list(batches)
    failed = set(fail_once or set())

    class Provider:
        name = "lolicon"
        safe_available = True

        def supports(self, _query):
            return True

        async def fetch(self, query):
            requests.append(query.count)
            return pending.pop(0)

    async def download_results(results, _config, *, client):
        downloaded_candidates.append([item.image_url for item in results])
        output = []
        for item in results:
            if item.image_url in failed:
                failed.remove(item.image_url)
                continue
            output.append((item, item.image_url.encode()))
        return output

    monkeypatch.setattr(service, "HttpClient", _HttpClient)
    monkeypatch.setattr(service, "build_providers", lambda *_args: {"lolicon": Provider()})
    monkeypatch.setattr(service, "download_results", download_results)
    monkeypatch.setattr(service, "health", service.ProviderHealth())
    result = asyncio.run(service.fetch_and_download(
        ImageQuery(count=3, provider="lolicon"), SetuConfig(setu_provider_order=["lolicon"]),
    ))
    return result, requests, downloaded_candidates


def test_three_images_all_download_on_first_request(monkeypatch) -> None:
    result, requests, candidates = _run_refill(monkeypatch, [[_image("a"), _image("b"), _image("c")]])
    assert len(result) == 3
    assert requests == [3]
    assert len(candidates) == 1


def test_failed_download_is_refilled_by_the_same_provider(monkeypatch) -> None:
    failed = _image("c")
    result, requests, _ = _run_refill(
        monkeypatch,
        [[_image("a"), _image("b"), failed], [_image("d")]],
        fail_once={failed.image_url},
    )
    assert [item.image_url for item, _ in result] == ["https://image.example/a.jpg", "https://image.example/b.jpg", "https://image.example/d.jpg"]
    assert requests == [3, 1]


def test_short_api_response_is_refilled(monkeypatch) -> None:
    result, requests, _ = _run_refill(monkeypatch, [[_image("a"), _image("b")], [_image("c")]])
    assert len(result) == 3
    assert requests == [3, 1]


def test_refill_deduplicates_pid_and_url(monkeypatch) -> None:
    first = [_image("a", pid=1), _image("b")]
    repeated_pid = _image("different-url", pid=1)
    repeated_url = _image("b")
    result, requests, candidates = _run_refill(
        monkeypatch, [first, [repeated_pid, repeated_url, _image("c")]],
    )
    assert len(result) == 3
    assert requests == [3, 1]
    assert candidates[1] == ["https://image.example/c.jpg"]


def test_two_refills_stop_and_return_partial_result(monkeypatch) -> None:
    result, requests, _ = _run_refill(
        monkeypatch,
        [[_image("a"), _image("b")], [_image("a")], [_image("b")]],
    )
    assert len(result) == 2
    assert requests == [3, 1, 1]


class _Message:
    @classmethod
    def image(cls, raw):
        return cls()

    @classmethod
    def text(cls, text):
        return cls()

    def __add__(self, _other):
        return self


class _Matcher:
    def __init__(self, receipts=None) -> None:
        self.messages = []
        self._receipts = iter(receipts or [])

    async def send(self, message):
        self.messages.append(message)
        if isinstance(message, str):
            return _Receipt(["notice"])
        return next(self._receipts, _Receipt([len(self.messages)]))

    async def finish(self, message):
        raise AssertionError(f"unexpected finish: {message}")


class _Receipt:
    def __init__(self, msg_ids) -> None:
        self.msg_ids = msg_ids


def test_partial_result_notifies_and_records_only_successful_sends(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import commands
    from src.nonebot_plugins.liteyuki_setu.service import Cooldown
    from src.nonebot_plugins.liteyuki_setu.storage import GroupSettings

    settings = GroupSettings(True, False, 60, 3, "auto", False, 0, 10)
    images = [(_image("a"), b"a"), (_image("b"), b"b")]
    usage = []

    async def allow_access(*_args, **_kwargs):
        return True

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(commands, "_access_allowed", allow_access)
    monkeypatch.setattr(commands, "group_allowed", lambda *_args: True)
    monkeypatch.setattr(commands, "get_group_settings", lambda *_args: settings)
    monkeypatch.setattr(commands, "fetch_and_download", lambda *_args: _immediate(images))
    monkeypatch.setattr(commands, "has_quota", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(commands, "record_success", lambda *_args: usage.append(1))
    monkeypatch.setattr(commands, "cooldown", Cooldown())
    monkeypatch.setattr(commands, "UniMessage", _Message)
    monkeypatch.setattr(commands.asyncio, "sleep", no_sleep)
    matcher = _Matcher()
    event = SimpleNamespace(group_id=10001, user_id=20002)
    bot = SimpleNamespace(config=SimpleNamespace(superusers=set()))
    asyncio.run(commands.handle_setu(SimpleNamespace(main_args={"raw": ["3"]}), event, bot, matcher))

    assert len(usage) == 2
    assert matcher.messages[-1] == "本次仅成功获取 2/3 张图片。"


async def _immediate(value):
    return value


def test_send_counts_only_confirmed_receipts_and_recalls_them(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import commands
    from src.nonebot_plugins.liteyuki_setu.service import Cooldown
    from src.nonebot_plugins.liteyuki_setu.storage import GroupSettings

    settings = GroupSettings(True, True, 60, 3, "auto", False, 0, 10)
    images = [(_image("a", 1), b"a"), (_image("b", 2), b"b"), (_image("c", 3), b"c")]
    usage = []
    recalls = []

    async def allow_access(*_args, **_kwargs):
        return True

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(commands, "_access_allowed", allow_access)
    monkeypatch.setattr(commands, "group_allowed", lambda *_args: True)
    monkeypatch.setattr(commands, "get_group_settings", lambda *_args: settings)
    monkeypatch.setattr(commands, "fetch_and_download", lambda *_args: _immediate(images))
    monkeypatch.setattr(commands, "has_quota", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(commands, "record_success", lambda *_args: usage.append(1))
    monkeypatch.setattr(commands, "schedule_recall", lambda receipt, *_args: recalls.append(receipt))
    monkeypatch.setattr(commands, "cooldown", Cooldown())
    monkeypatch.setattr(commands, "UniMessage", _Message)
    monkeypatch.setattr(commands.asyncio, "sleep", no_sleep)
    matcher = _Matcher([_Receipt([101]), _Receipt([]), _Receipt([103])])
    event = SimpleNamespace(group_id=10001, user_id=20002)
    bot = SimpleNamespace(config=SimpleNamespace(superusers=set()))

    asyncio.run(commands.handle_setu(SimpleNamespace(main_args={"raw": ["3"]}), event, bot, matcher))

    assert len(matcher.messages) == 4  # all three images are attempted, then the partial-result notice
    assert matcher.messages[-1] == "本次仅成功获取 2/3 张图片。"
    assert len(usage) == 2
    assert [receipt.msg_ids for receipt in recalls] == [[101], [103]]


def test_confirmed_send_waits_after_send_completion(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import commands
    from src.nonebot_plugins.liteyuki_setu.service import Cooldown
    from src.nonebot_plugins.liteyuki_setu.storage import GroupSettings

    settings = GroupSettings(True, False, 60, 3, "auto", False, 0, 10)
    images = [(_image("a"), b"a"), (_image("b"), b"b")]
    clock = [0.0]
    send_starts = []
    sleeps = []

    class SlowMatcher(_Matcher):
        async def send(self, message):
            if not isinstance(message, str):
                send_starts.append(clock[0])
                clock[0] += 5.0  # the upload itself exceeds the configured interval
            return await super().send(message)

    async def allow_access(*_args, **_kwargs):
        return True

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(commands, "_access_allowed", allow_access)
    monkeypatch.setattr(commands, "group_allowed", lambda *_args: True)
    monkeypatch.setattr(commands, "get_group_settings", lambda *_args: settings)
    monkeypatch.setattr(commands, "fetch_and_download", lambda *_args: _immediate(images))
    monkeypatch.setattr(commands, "has_quota", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(commands, "record_success", lambda *_args: None)
    monkeypatch.setattr(commands, "cooldown", Cooldown())
    monkeypatch.setattr(commands, "UniMessage", _Message)
    monkeypatch.setattr(commands.asyncio, "sleep", fake_sleep)
    matcher = SlowMatcher([_Receipt([101]), _Receipt([102])])
    event = SimpleNamespace(group_id=10001, user_id=20002)
    bot = SimpleNamespace(config=SimpleNamespace(superusers=set()))

    asyncio.run(commands.handle_setu(SimpleNamespace(main_args={"raw": ["2"]}), event, bot, matcher))

    assert sleeps == [1.0]
    assert send_starts == [0.0, 6.0]

def test_three_valid_receipts_are_all_confirmed(monkeypatch) -> None:
    _init()
    from src.nonebot_plugins.liteyuki_setu import commands
    from src.nonebot_plugins.liteyuki_setu.service import Cooldown
    from src.nonebot_plugins.liteyuki_setu.storage import GroupSettings

    settings = GroupSettings(True, False, 60, 3, "auto", False, 0, 10)
    images = [(_image("a"), b"a"), (_image("b"), b"b"), (_image("c"), b"c")]
    usage = []

    async def allow_access(*_args, **_kwargs):
        return True

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(commands, "_access_allowed", allow_access)
    monkeypatch.setattr(commands, "group_allowed", lambda *_args: True)
    monkeypatch.setattr(commands, "get_group_settings", lambda *_args: settings)
    monkeypatch.setattr(commands, "fetch_and_download", lambda *_args: _immediate(images))
    monkeypatch.setattr(commands, "has_quota", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(commands, "record_success", lambda *_args: usage.append(1))
    monkeypatch.setattr(commands, "cooldown", Cooldown())
    monkeypatch.setattr(commands, "UniMessage", _Message)
    monkeypatch.setattr(commands.asyncio, "sleep", no_sleep)
    matcher = _Matcher([_Receipt([101]), _Receipt([102]), _Receipt([103])])
    event = SimpleNamespace(group_id=10001, user_id=20002)
    bot = SimpleNamespace(config=SimpleNamespace(superusers=set()))

    asyncio.run(commands.handle_setu(SimpleNamespace(main_args={"raw": ["3"]}), event, bot, matcher))

    assert len(matcher.messages) == 3
    assert len(usage) == 3
