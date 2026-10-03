from __future__ import annotations

import nonebot
import pytest


def modules():
    try:
        nonebot.get_driver()
    except ValueError:
        nonebot.init()
    from src.nonebot_plugins.liteyuki_twitter import parser
    from src.nonebot_plugins.liteyuki_twitter.config import TwitterConfig
    from src.nonebot_plugins.liteyuki_twitter.models import Post, SourceError
    return parser, TwitterConfig, Post, SourceError


def html_post(post_id="100", *, extra="", body="正文<br>第二行", quote=""):
    return f'''<div class="timeline-item">{extra}<a class="tweet-link" href="/example/status/{post_id}"></a>
    <a class="fullname">示例作者</a><a class="username">@example</a>
    <span class="tweet-date"><a title="Sep 30, 2026 · 1:00 PM UTC" href="/example/status/{post_id}">昨天</a></span>
    <div class="tweet-content">{body}</div>{quote}
    <div class="attachments"><img src="/pic/photo.jpg"><video poster="/pic/video.jpg"></video></div></div>'''


def rss(items=""):
    return f'<rss version="2.0"><channel><title>Example / @example</title>{items}</channel></rss>'.encode()


def rss_item(post_id="100", title="测试", description="<p>正文<br>第二行</p>", account="example"):
    return f'''<item><title>{title}</title><link>https://nitter.example/{account}/status/{post_id}</link>
    <pubDate>Wed, 30 Sep 2026 13:00:00 GMT</pubDate><description><![CDATA[{description}]]></description></item>'''


def test_config_safe_defaults_and_normalization():
    _, Config, _, _ = modules()
    config = Config(twitter_group_ids=[101, "101"], twitter_follows=["@Example"], twitter_group_follows={202: ["Other"]})
    assert not config.twitter_enabled and config.twitter_nitter_instances == []
    assert config.twitter_group_mode == "whitelist"
    assert config.twitter_group_ids == ["101"]
    assert config.twitter_follows[0].account == "example"
    assert config.twitter_group_follows["202"][0].account == "other"
    for values in ({"twitter_model_base_url": "https://secret:password@example.org"},
                   {"twitter_follows": ["bad-account"]}, {"twitter_poll_interval": 1},
                   {"twitter_group_mode": "invalid"}):
        with pytest.raises(ValueError):
            Config(**values)


def test_html_author_and_quote_avatars_are_separate_and_not_media():
    parser, _, Post, _ = modules()
    quote = html_post("50", body="引用").replace('class="timeline-item"', 'class="quote"').replace('/example/', '/other/')
    quote = quote.replace('<div class="tweet-content">', '<img class="avatar mini" src="/pic/quote.jpg"><div class="tweet-content">')
    html = html_post(quote=quote).replace('<div class="tweet-content">正文', '<a class="tweet-avatar"><img src="/pic/author.jpg"></a><div class="tweet-content">正文')
    post = parser.parse_html(html, "https://nitter.example", "example")[0]
    assert post.avatar_url == "https://nitter.example/pic/author.jpg"
    assert post.quote.avatar_url == "https://nitter.example/pic/quote.jpg"
    assert all("author.jpg" not in media.url for media in post.media)
    assert Post.loads(post.dumps()).quote.avatar_url == post.quote.avatar_url
    assert Post.loads('{"post_id":"1","account":"example"}').avatar_url == ""


def test_rss_channel_avatar_only_applies_to_its_author():
    parser, _, _, _ = modules()
    raw = rss(rss_item() + rss_item("200", account="other", title="RT by @example"))
    raw = raw.replace(b'<channel>', b'<channel><image><url>/pic/avatar.jpg</url></image>')
    posts = parser.parse_rss(raw, "https://nitter.example", "example")
    assert posts[0].avatar_url == "https://nitter.example/pic/avatar.jpg"
    assert posts[1].avatar_url == ""  # A repost belongs to a different author.


@pytest.mark.parametrize("url,expected", [
    ("https://x.com/Example/status/123?s=20", ("example", "123")),
    ("https://twitter.com/example/status/123/photo/1", ("example", "123")),
    ("https://x.com/i/web/status/123", ("i", "123")),
    ("https://nitter.example/example/status/123", ("example", "123")),
    ("https://evil.example/example/status/123", None),
    ("https://x.com.evil.example/example/status/123", None),
    ("https://x.com:bad/example/status/123", None),
    ("https://user:pass@x.com/example/status/123", None),
    ("https://t.co/example", None),
])
def test_link_recognition(url, expected):
    parser, _, _, _ = modules()
    assert parser.parse_link(url, ["https://nitter.example"]) == expected


def test_html_separates_quote_and_ignores_other_statuses():
    parser, _, Post, _ = modules()
    quote = '''<div class="quote"><a class="tweet-link" href="/other/status/50"></a><a class="fullname">引用作者</a>
    <div class="tweet-content">引用正文</div><div class="attachments"><img src="/pic/quote.jpg"></div></div>'''
    html = '<div class="timeline">' + html_post(quote=quote) + html_post("200", extra='<span class="pinned">置顶</span>') + '</div>'
    posts = parser.parse_html(html, "https://nitter.example", "example")
    assert len(posts) == 2
    post = posts[0]
    assert post.text == "正文\n第二行" and post.author == "示例作者"
    assert post.quote.text == "引用正文" and post.quote.account == "other"
    assert [m.url for m in post.media] == ["https://nitter.example/pic/photo.jpg", "https://nitter.example/pic/video.jpg"]
    assert post.media[1].kind == "video" and posts[1].pinned
    assert Post.loads(post.dumps()) == post
    main = '<div class="main-tweet">' + html_post(quote=quote) + '</div>' + html_post("300", body="评论")
    assert parser.parse_html(main, "https://nitter.example", "example", status_id="100")[0].text == post.text


def test_rss_full_body_flags_and_empty():
    parser, _, _, _ = modules()
    posts = parser.parse_rss(rss(rss_item(description='<p>一行<br>二行</p><p>三行</p><img src="/pic/photo.jpg">') +
                                 rss_item("200", title="RT by @example", account="other") +
                                 rss_item("300", title="R to @other")), "https://nitter.example", "example")
    assert posts[0].text == "一行\n二行\n三行"
    assert posts[0].media[0].url.endswith("/pic/photo.jpg")
    assert posts[1].repost and posts[2].reply
    assert parser.parse_rss(rss(), "https://nitter.example", "example") == []
    assert parser.parse_html('<div class="timeline"></div>', "https://nitter.example", "example") == []


@pytest.mark.parametrize("raw", [b"broken", b"<html>login</html>", b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss/>', b"<rss/>"])
def test_invalid_rss_is_failure_not_empty(raw):
    parser, _, _, Error = modules()
    with pytest.raises(Error):
        parser.parse_rss(raw, "https://nitter.example", "example")


def test_invalid_html_is_failure_not_empty():
    parser, _, _, Error = modules()
    for html in ("<html>login</html>", '<div class="error-panel">unavailable</div>'):
        with pytest.raises(Error):
            parser.parse_html(html, "https://nitter.example", "example")
