from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import nonebot



from .client import SixtyApiClient, SixtyApiError
from .config import SixtyApiConfig


TEXT_FEATURES = {"fabing", "kfc", "dad_joke"}
PATHS = {
    "world": "/v2/60s", "ai": "/v2/ai-news", "history": "/v2/today-in-history",
    "it": "/v2/it-news", "moyu": "/v2/moyu", "hitokoto": "/v2/hitokoto",
    "luck": "/v2/luck", "fabing": "/v2/fabing", "kfc": "/v2/kfc", "dad_joke": "/v2/dad-joke",
}
TITLES = {"world": "每天 60 秒读懂世界", "ai": "AI 资讯快报", "history": "历史上的今天", "it": "实时 IT 资讯", "moyu": "摸鱼日报", "hitokoto": "随机一言", "luck": "随机运势"}


@dataclass
class Content:
    kind: str
    value: str | bytes
    empty: bool = False


def enabled(config: SixtyApiConfig, feature: str) -> bool:
    return bool(getattr(config, f"sixty_api_{feature}_enabled"))


def _escape(value: Any) -> str:
    return str(value or "").replace("\\", "\\\\").replace("*", "\\*").replace("#", "\\#").replace("[", "\\[").replace("]", "\\]")


def _list_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("news", "items", "list", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def markdown_for(feature: str, data: Any) -> str:
    title = TITLES[feature]
    if feature == "hitokoto":
        return f"# {title}\n\n> {_escape(data.get('hitokoto') if isinstance(data, dict) else data)}"
    if feature == "luck":
        value = data if isinstance(data, dict) else {}
        return f"# {title}\n\n## {_escape(value.get('luck_desc'))}\n\n- 运势指数：{_escape(value.get('luck_rank'))}\n- 建议：{_escape(value.get('luck_tip'))}"
    if feature == "moyu":
        value = data if isinstance(data, dict) else {}
        lines = [f"# {title}"]
        for key, label in (("date", "日期"), ("week", "星期"), ("lunar", "农历"), ("moyuQuote", "摸鱼语录")):
            if value.get(key): lines.append(f"\n- {label}：{_escape(value[key])}")
        for key, value_item in value.items():
            if key not in {"date", "week", "lunar", "moyuQuote", "image"} and isinstance(value_item, (str, int, float)):
                lines.append(f"\n- {_escape(key)}：{_escape(value_item)}")
        return "".join(lines)
    value = data if isinstance(data, dict) else {}
    date = value.get("date", "")
    lines = [f"# {title}", f"\n{_escape(date)}" if date else ""]
    for index, item in enumerate(_list_items(data)[:20], 1):
        heading = item.get("title") or item.get("name") or item.get("description") or "资讯"
        detail = item.get("detail") or item.get("description") or item.get("content") or ""
        source = item.get("source") or ""
        lines.append(f"\n\n{index}. **{_escape(heading)}**")
        if detail: lines.append(f"\n{_escape(detail)[:300]}")
        if source: lines.append(f"\n来源：{_escape(source)}")
    if feature == "world" and value.get("tip"):
        lines.append(f"\n\n> {_escape(value['tip'])}")
    return "".join(lines)


def text_for(feature: str, data: Any) -> str:
    value = data if isinstance(data, dict) else {}
    key = {"fabing": "saying", "kfc": "kfc", "dad_joke": "content"}[feature]
    return str(value.get(key) or "").strip()


async def fetch_content(config: SixtyApiConfig, feature: str, *, name: str | None = None) -> Content:
    params = {"name": name} if feature == "fabing" and name else None
    async with SixtyApiClient(config.sixty_api_base_url, config.sixty_api_timeout) as client:
        data = await client.get_data(PATHS[feature], params=params)
        if feature in TEXT_FEATURES:
            text = text_for(feature, data)
            if not text: raise SixtyApiError("API 返回内容为空")
            return Content("text", text)
        if feature == "ai" and not _list_items(data):
            return Content("text", "今日暂无重要 AI 资讯。", empty=True)
        if feature == "world" and isinstance(data, dict) and isinstance(data.get("image"), str):
            try:
                return Content("image", await client.download_image(data["image"]))
            except SixtyApiError as exc:
                nonebot.logger.info("60s 日报原图不可用，回退本地渲染：%s", exc)
    try:
        from .cards import render_card

        return Content("image", await render_card(feature, data))
    except SixtyApiError:
        raise
    except Exception as exc:
        raise SixtyApiError("图片生成失败") from exc
