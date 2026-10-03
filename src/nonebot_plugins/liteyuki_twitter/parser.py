"""Small HTML tree and RSS parser, with no browser or additional dependency."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

from .config import normalize_account
from .models import Media, Post, SourceError

STATUS_PATH = re.compile(r"/(?:([a-zA-Z0-9_]{1,15})/status|i/(?:web/)?status)/(\d+)(?:/|$)")
LINK_PATH = re.compile(r"/(?:([a-zA-Z0-9_]{1,15})/status|i/(?:web/)?status)/(\d+)(?:/(?:photo|video)/\d+)?/?")


def parse_link(text: str, instances: list[str]) -> tuple[str, str] | None:
    hosts = {"x.com", "www.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
    hosts.update(urlsplit(item).hostname for item in instances)
    for candidate in re.findall(r"https?://[^\s<>]+", text):
        try:
            parts = urlsplit(candidate.rstrip("。，,.!！;；)）]"))
            valid = parts.hostname in hosts and not parts.username and not parts.password and parts.port in {None, 80, 443}
        except ValueError:
            continue
        if not valid:
            continue
        match = LINK_PATH.fullmatch(parts.path)
        if match:
            return (normalize_account(match[1]) if match[1] else "i", match[2])
    return None


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def has(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def find(self, predicate, *, exclude_quote: bool = False):
        result = []
        for item in self.children:
            if isinstance(item, Node):
                if exclude_quote and item.has("quote"):
                    continue
                if predicate(item):
                    result.append(item)
                result.extend(item.find(predicate, exclude_quote=exclude_quote))
        return result

    def text(self) -> str:
        parts = []
        for item in self.children:
            if isinstance(item, str):
                parts.append(item)
            elif item.tag == "br":
                parts.append("\n")
            elif item.tag == "img":
                parts.append(item.attrs.get("alt", ""))
            else:
                parts.append(item.text())
                if item.tag in {"p", "blockquote"}:
                    parts.append("\n")
        return "".join(parts).strip()


class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        if len(self.stack) > 80:
            raise SourceError("HTML 嵌套层级超过限制")
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {"img", "br", "hr", "meta", "link", "input", "source", "wbr", "area", "embed"}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack[-1].tag == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def tree(html: str) -> Node:
    parser = TreeParser()
    parser.feed(html)
    return parser.root


def _first(node: Node, class_name: str, *, exclude_quote=False) -> Node | None:
    return next(iter(node.find(lambda n: n.has(class_name), exclude_quote=exclude_quote)), None)


def _status(value: str) -> tuple[str, str] | None:
    match = STATUS_PATH.search(urlsplit(value).path)
    return (match[1] or "i", match[2]) if match else None


def _time(value: str) -> str:
    try:
        return parsedate_to_datetime(value).astimezone(UTC).isoformat()
    except (ValueError, TypeError, OverflowError):
        pass
    for fmt in ("%b %d, %Y · %I:%M %p %Z", "%b %d, %Y · %I:%M %p", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC).isoformat()
        except ValueError:
            pass
    return ""


def _media(node: Node, base: str, *, exclude_quote=True) -> list[Media]:
    result, seen = [], set()
    attachments = node.find(lambda n: n.has("attachments") or n.has("attachment") or n.tag == "video", exclude_quote=exclude_quote)
    for attachment in attachments:
        images = attachment.find(lambda n: n.tag == "img")
        for image in images:
            raw = image.attrs.get("src", "")
            if raw and raw not in seen:
                seen.add(raw)
                result.append(Media(urljoin(base, raw), "video" if attachment.tag == "video" or attachment.find(lambda n: n.tag == "video" or n.has("video-overlay")) else "image"))
        poster = attachment.attrs.get("poster", "")
        if poster and poster not in seen:
            seen.add(poster)
            result.append(Media(urljoin(base, poster), "video"))
    return result


def _html_post(node: Node, base: str, fallback_account: str) -> Post | None:
    link = _first(node, "tweet-link", exclude_quote=True) or _first(node, "tweet-date", exclude_quote=True)
    candidates = [link] if link else []
    candidates += node.find(lambda n: n.tag == "a" and "/status/" in n.attrs.get("href", ""), exclude_quote=True)
    status = next((parsed for n in candidates if n and (parsed := _status(n.attrs.get("href", "")))), None)
    if not status:
        return None
    account, post_id = status
    username = _first(node, "username", exclude_quote=True)
    if account == "i":
        account = username.text().lstrip("@") if username else fallback_account
    author = _first(node, "fullname", exclude_quote=True)
    content = _first(node, "tweet-content", exclude_quote=True)
    date = _first(node, "tweet-date", exclude_quote=True)
    dates = date.find(lambda n: n.tag == "a") if date else []
    value = (dates[0].attrs.get("title", "") if dates else "") or (date.attrs.get("title", "") if date else "")
    post = Post(post_id, normalize_account(account), author.text() if author else account,
                content.text() if content else "", _time(value), _media(node, base))
    post.reply = bool(_first(node, "replying-to", exclude_quote=True))
    post.repost = bool(_first(node, "retweet-header", exclude_quote=True))
    post.pinned = bool(_first(node, "pinned", exclude_quote=True))
    quote = _first(node, "quote")
    if quote:
        post.quote = _html_post(quote, base, account)
    return post


def parse_html(html: str, base: str, account: str, *, status_id: str | None = None) -> list[Post]:
    root = tree(html)
    errors = root.find(lambda n: n.has("error-panel"))
    if errors:
        blocked = any(word in " ".join(n.text().lower() for n in errors) for word in ("rate limit", "login", "log in", "captcha", "429"))
        raise SourceError("Nitter 返回错误页面", blocked=blocked)
    if status_id:
        nodes = root.find(lambda n: n.has("main-tweet"))
    else:
        nodes = root.find(lambda n: n.has("timeline-item"))
    posts = [post for n in nodes if (post := _html_post(n, base, account))]
    if status_id:
        posts = [p for p in posts if p.post_id == status_id]
        if not posts:
            raise SourceError("推文不存在、不可见或页面格式已变化")
    elif not posts and not root.find(lambda n: n.has("timeline") or n.has("timeline-container")):
        raise SourceError("Nitter 时间线格式无效")
    return list({p.post_id: p for p in posts}.values())


def parse_rss(raw: bytes, base: str, account: str) -> list[Post]:
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise SourceError("RSS 包含不支持的 XML 声明")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise SourceError("Nitter RSS 格式无效") from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise SourceError("Nitter 返回的内容不是 RSS")
    posts = []
    for item in channel.findall("item"):
        link = item.findtext("link", "")
        status = _status(link)
        if not status:
            continue
        author_account, post_id = status
        description = tree(item.findtext("description", ""))
        contents = description.find(lambda n: n.has("tweet-content"), exclude_quote=True)
        quote_node = _first(description, "quote")
        quote = _html_post(quote_node, base, account) if quote_node else None
        # RSS descriptions contain attachments below the first body paragraph.
        paragraphs = description.find(lambda n: n.tag == "p", exclude_quote=True)
        text = contents[0].text() if contents else ("\n".join(p.text() for p in paragraphs if p.text()) if paragraphs else description.text())
        media = _media(description, base)
        if not media:
            media = [Media(urljoin(base, n.attrs["src"])) for n in description.find(lambda n: n.tag == "img" and "src" in n.attrs, exclude_quote=True) if not n.has("emoji")]
        creator = next((n.text or "" for n in item if n.tag.endswith("creator")), "")
        title = item.findtext("title", "")
        post = Post(post_id, normalize_account(author_account if author_account != "i" else account), creator.lstrip("@") or author_account,
                    text, _time(item.findtext("pubDate", "")), media, quote)
        post.repost = title.startswith(("RT by ", "RT @")) or post.account != account
        post.reply = title.startswith(("R to ", "Reply to "))
        posts.append(post)
    return list({p.post_id: p for p in posts}.values())
