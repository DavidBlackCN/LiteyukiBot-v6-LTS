"""Chinese command surface using the repository's Bot ADMIN permission."""
from __future__ import annotations

from arclet.alconna import Alconna, Args, MultiVar
from nonebot import logger, on_message
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot_plugin_alconna import Arparma, on_alconna

from src.nonebot_plugins.liteyuki_group_manager.permission import ADMIN, is_superuser

from .config import FollowOptions, normalize_account
from . import group_settings
from .models import TwitterError
from .parser import parse_link
from .renderer import text_message
from .runtime import get_service


def register(name, *, admin=False):
    options = {"permission": ADMIN} if admin else {}
    return on_alconna(Alconna(name, Args["raw", MultiVar(str), []]), use_cmd_start=True,
                      priority=20, block=True, **options)


follow = register("推特关注", admin=True)
unfollow = register("推特取关", admin=True)
subscription_list = register("推特订阅列表", admin=True)
manage = register("推特管理", admin=True)
posts = register("推特推文")
parse = register("推特解析")
translate = register("推特翻译")
link_matcher = on_message(priority=90, block=False)


def tokens(result):
    return [str(item).strip() for item in result.main_args.get("raw", []) if str(item).strip()]


def event_group(event):
    value = getattr(event, "group_id", None)
    return str(value) if value is not None else None


async def target_group(config, args, event, bot, matcher):
    group = event_group(event)
    args = list(args)
    if "--群" in args:
        if not await is_superuser(bot, event):
            await matcher.finish("指定其他群仅 SUPERUSER 可用。")
        index = args.index("--群")
        if index + 1 >= len(args):
            await matcher.finish("请在 --群 后指定群号。")
        group = args[index + 1]
        del args[index:index + 2]
    if group is None:
        await matcher.finish("请在群内管理订阅，或由 SUPERUSER 使用 --群 指定群。")
    if group not in config.twitter_group_ids:
        await matcher.finish("目标群不在允许名单中，请联系 SUPERUSER 修改配置。")
    return group, args


async def send_post(service, post, bot, matcher, *, group=None, channel="commands"):
    if not await group_settings.allowed(service.config, group, channel,
                                         user_id=str(matcher._twitter_user_id)):
        return False
    message = await service.message(bot, post)
    if not await group_settings.allowed(service.config, group, channel,
                                         user_id=str(matcher._twitter_user_id)):
        return False
    try:
        await matcher.send(message)
    except Exception:
        if isinstance(message, str):
            raise
        await matcher.send(text_message(post))
    return True


@follow.handle()
async def handle_follow(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    from . import config
    group, args = await target_group(config, tokens(result), event, bot, matcher)
    flags = {item for item in args if item.startswith("--")}
    if flags - {"--仅媒体", "--回复", "--转推"} or len([item for item in args if not item.startswith("--")]) != 1:
        await matcher.finish("用法：推特关注 <账号> [--仅媒体] [--回复] [--转推] [--群 <群号>]")
    try:
        options = FollowOptions(account=next(item for item in args if not item.startswith("--")),
                                media_only="--仅媒体" in flags, replies="--回复" in flags, reposts="--转推" in flags)
    except ValueError:
        await matcher.finish("账号格式无效。")
    service = get_service()
    current = service.store.follows(config, group)
    if options.account not in current and len(current) >= 50:
        await matcher.finish("每群最多关注 50 个账号。")
    service.store.follow(group, options)
    await matcher.finish(f"本群已关注 @{options.account}；首次成功获取仅建立基线，不推送历史。")


@unfollow.handle()
async def handle_unfollow(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    from . import config
    group, args = await target_group(config, tokens(result), event, bot, matcher)
    if len(args) != 1:
        await matcher.finish("用法：推特取关 <账号> [--群 <群号>]")
    try:
        account = normalize_account(args[0])
    except ValueError:
        await matcher.finish("账号格式无效。")
    get_service().store.unfollow(group, account)
    await matcher.finish(f"已取关 @{account}，配置默认关注也不会在重启后重新加入。")


@subscription_list.handle()
async def handle_list(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    from . import config
    group, args = await target_group(config, tokens(result), event, bot, matcher)
    if args:
        await matcher.finish("用法：推特订阅列表 [--群 <群号>]")
    follows = get_service().store.follows(config, group)
    lines = [f"群 {group} 的 X 订阅："]
    for account, (item, source) in sorted(follows.items()):
        lines.append(f"@{account} · {'仅媒体' if item.media_only else '全部媒体类型'} · 回复{'开' if item.replies else '关'} · 转推{'开' if item.reposts else '关'} · {source}")
    await matcher.finish("\n".join(lines) if follows else "本群暂无 X 订阅。")


@manage.handle()
async def handle_manage(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    from . import config
    group, args = await target_group(config, tokens(result), event, bot, matcher)
    service = get_service()
    values = group_settings.settings(config, group)
    labels = {"enabled": "总开关", "commands": "手动命令", "push": "自动播报", "links": "自动链接识别",
              "translate_push": "播报翻译", "translate_links": "链接翻译"}
    if args == ["状态"]:
        lines = [f"X 全局：{'开' if config.twitter_enabled else '关'}", f"Nitter 实例：{len(config.twitter_nitter_instances)} 个",
                 f"轮询间隔：{config.twitter_poll_interval} 秒", f"关注：{len(service.store.follows(config, group))} 个",
                 f"待发送：{service.store.pending_count(group)} 条"]
        lines += [f"{label}：{'开' if values[key] else '关'}" for key, label in labels.items()]
        lines += [f"翻译服务：{values['provider']}（{'已配置' if service.translator.configured(values['provider']) else '未配置'}）",
                  f"核心允许发送：{'是' if await group_settings.core_allowed(group) else '否'}"]
        for index, base in enumerate(config.twitter_nitter_instances, 1):
            health = service.client.health.get(base, {})
            lines.append(f"实例 {index}：{health.get('error') or '尚无失败记录'}")
        await matcher.finish("\n".join(lines))
    if args == ["订阅重置"]:
        service.store.reset(group)
        await matcher.finish("本群订阅已恢复配置继承，下次成功获取重新建立基线。")
    changes = {}
    if args in (["开启"], ["关闭"]):
        changes["enabled"] = args[0] == "开启"
    elif len(args) == 2 and args[0] in {"命令", "播报", "链接"} and args[1] in {"开", "关"}:
        changes[{"命令": "commands", "播报": "push", "链接": "links"}[args[0]]] = args[1] == "开"
    elif len(args) == 3 and args[:2] in (["翻译", "播报"], ["翻译", "链接"]) and args[2] in {"开", "关"}:
        changes["translate_push" if args[1] == "播报" else "translate_links"] = args[2] == "开"
    elif len(args) == 3 and args[:2] == ["翻译", "服务"]:
        provider = {"模型": "model", "LibreTranslate": "libretranslate", "libretranslate": "libretranslate"}.get(args[2])
        if not provider or not service.translator.configured(provider):
            await matcher.finish("所选翻译服务尚未配置，请由 SUPERUSER 在配置文件中设置。")
        changes["provider"] = provider
    else:
        await matcher.finish("用法：推特管理 状态|开启|关闭|订阅重置；命令/播报/链接 开|关；翻译 播报/链接 开|关；翻译 服务 模型|LibreTranslate")
    group_settings.update(config, group, **changes)
    if "enabled" in changes or "push" in changes:
        service.store.set_active(group, group_settings.locally_allowed(config, group, "push"))
    await matcher.finish("本群 X 设置已更新。暂停后恢复不会补发历史。")


async def query(result, event, bot, matcher, mode):
    from . import config
    group, user = event_group(event), str(event.get_user_id())
    if not await group_settings.allowed(config, group, "commands", user_id=user):
        await matcher.finish("此会话的 X 手动命令未启用或不在允许范围内。")
    args = tokens(result)
    service = get_service()
    matcher._twitter_user_id = user
    try:
        if mode == "posts":
            if not args or len(args) > 2:
                raise TwitterError("用法：推特推文 <账号> [1-5]")
            count = int(args[1]) if len(args) == 2 else 1
            if not 1 <= count <= 5:
                raise TwitterError("数量须为 1-5。")
            items = await service.client.get_timeline(normalize_account(args[0]))
            items = sorted(items, key=lambda p: (p.published_at, int(p.post_id)), reverse=True)[:count]
        else:
            link = parse_link(" ".join(args), config.twitter_nitter_instances)
            if not link:
                raise TwitterError("请提供有效的 X、Twitter 或已配置 Nitter 推文链接。")
            if mode == "translate" and not await is_superuser(bot, event) and not service.cooldown(user, group or "private", translate=True):
                raise TwitterError(f"翻译请求过于频繁，请等待 {config.twitter_translation_cooldown} 秒。")
            items = [await service.status_post(*link)]
        if not items:
            await matcher.finish("该账号暂无可获取的推文。")
        values = group_settings.settings(config, group)
        for post in items:
            if mode == "translate" or (mode == "parse" and values["translate_links"]):
                post = await service.translator.post(post, values["provider"])
            await send_post(service, post, bot, matcher, group=group)
    except (TwitterError, ValueError) as error:
        await matcher.finish(str(error) if isinstance(error, TwitterError) else "账号或数量格式无效。")


@posts.handle()
async def handle_posts(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    await query(result, event, bot, matcher, "posts")


@parse.handle()
async def handle_parse(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    await query(result, event, bot, matcher, "parse")


@translate.handle()
async def handle_translate(result: Arparma, event: Event, bot: Bot, matcher: Matcher):
    await query(result, event, bot, matcher, "translate")


@link_matcher.handle()
async def handle_link(event: Event, bot: Bot, matcher: Matcher):
    from . import config
    group = event_group(event)
    user = str(event.get_user_id())
    if not await group_settings.allowed(config, group, "links", user_id=user):
        return
    link = parse_link(event.get_plaintext(), config.twitter_nitter_instances)
    if link is None:
        return
    service = get_service()
    scope = group or "private:" + user
    if not service.cooldown(link[1], scope):
        return
    matcher._twitter_user_id = user
    try:
        post = await service.status_post(*link)
        values = group_settings.settings(config, group)
        if values["translate_links"]:
            post = await service.translator.post(post, values["provider"])
        await send_post(service, post, bot, matcher, group=group, channel="links")
    except TwitterError as error:
        service.link_times.pop((link[1], scope), None)
        logger.warning("X 链接解析失败：{}", str(error))
