"""Local card rendering; remote images become bounded, verified data URLs."""
from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image
from nonebot import logger

from .client import IMAGE_LIMIT
from .models import Post, TwitterError


def clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + "…\n（完整内容请查看原链接）"


def view_model(post: Post, limit=600) -> dict:
    def section(part):
        return {"author": part.author or part.account, "account": "@" + part.account,
                "body": clip(part.text, limit), "translation": clip(part.translation, limit),
                "translation_note": part.translation_note, "url": part.url,
                "media": [{"src": "", "kind": item.kind, "portrait": False} for item in part.media]}
    view = section(post)
    view.update(time=post.published_at.replace("T", " ").replace("+00:00", " UTC"),
                kind="转推" if post.repost else "回复" if post.reply else "引用推文" if post.quote else "推文",
                quote=section(post.quote) if post.quote else None)
    return view


async def render_card(post: Post, client, config) -> bytes:
    from src.utils.base.resource import get_path
    from src.utils.message.html_tool import template2image_element

    view = view_model(post, config.twitter_card_body_limit)
    remaining = 30 * 1024 * 1024
    for part, target in ((post, view), (post.quote, view["quote"])):
        if part is None:
            continue
        for media, item in zip(part.media, target["media"]):
            if remaining <= 0:
                break
            reservation = min(remaining, IMAGE_LIMIT)
            remaining -= reservation
            try:
                raw, _ = await client.download_image(media.url, max_bytes=reservation)
                remaining += max(0, reservation - len(raw))
                with Image.open(BytesIO(raw)) as image:
                    if image.width * image.height > 40_000_000:
                        raise TwitterError("图片像素超过限制")
                    image.seek(0)
                    item["portrait"] = image.height > image.width * 1.6
                    if image.format == "GIF":
                        item["kind"] = "gif"
                    output = BytesIO()
                    image.convert("RGB").save(output, format="JPEG", quality=90)
                item["src"] = "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode()
            except Exception as error:
                logger.debug("X 图片降级：{}", type(error).__name__)
    return await template2image_element(get_path("templates/twitter_card.html"), {"data": view},
                                        ".twitter-page", wait_for="window.twitterCardReady === true", wait_timeout=15000)


def text_message(post: Post) -> str:
    lines = [f"X · {post.author or post.account} (@{post.account})", clip(post.text, 4000)]
    if post.translation:
        lines += ["机器翻译", clip(post.translation, 4000)]
    if post.translation_note:
        lines.append(post.translation_note)
    if post.quote:
        lines += [f"引用 · @{post.quote.account}", clip(post.quote.text, 2000)]
        if post.quote.translation:
            lines += ["机器翻译", clip(post.quote.translation, 2000)]
        if post.quote.translation_note:
            lines.append(post.quote.translation_note)
    if post.media or (post.quote and post.quote.media):
        lines.append("图片或视频封面不可用时，请查看原链接。")
    lines.append(post.url)
    return "\n".join(line for line in lines if line)
