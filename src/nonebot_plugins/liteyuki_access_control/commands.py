import json
import shlex

from nonebot import logger, on_command
from nonebot.adapters import Event, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from .api import config, controller

access = on_command("access", permission=SUPERUSER, priority=5, block=True)


def execute_command(text: str, group_id=None) -> str:
    args = shlex.split(text)
    if args in ([], ["status"]):
        return (
            f"访问控制：{'启用' if config.access_control_enabled else '关闭'}\n"
            f"默认：{'允许' if config.access_control_default_allow else '拒绝'}\n"
            f"规则存储：{'异常，请修复后重启' if controller.storage_error else '正常'}\n"
            f"保护插件：{', '.join(sorted(controller.protected))}"
        )
    if args == ["list"]:
        return json.dumps(controller.rules, ensure_ascii=False, indent=2)
    if len(args) == 3 and args[0] in ("enable", "disable") and args[1] == "plugin":
        if group_id is None:
            raise ValueError("请在目标群聊中使用此命令")
        controller.set_plugin(args[2], str(group_id), enabled=args[0] == "enable")
    elif len(args) == 3 and args[0] in ("enable-user", "disable-user"):
        controller.set_plugin(args[2], args[1], scope="user", enabled=args[0] == "enable-user")
    elif len(args) == 2 and args[0] in {
        f"{prefix}{kind}-{scope}"
        for prefix in ("", "un") for kind in ("blacklist", "whitelist") for scope in ("user", "group")
    }:
        controller.set_list(args[1], scope=args[0].rsplit("-", 1)[1],
                            whitelist="whitelist" in args[0], remove=args[0].startswith("un"))
    elif len(args) == 5 and args[:2] == ["limit", "set"]:
        controller.set_limit(args[2], int(args[3]), float(args[4]))
    elif len(args) == 3 and args[:2] == ["limit", "remove"]:
        controller.set_limit(args[2])
    else:
        raise ValueError(
            "用法：/access status|list；enable/disable plugin <插件>；"
            "enable-user/disable-user <用户> <插件>；"
            "[un]blacklist-user/group <ID>；[un]whitelist-user/group <ID>；"
            "limit set <插件> <次数> <秒数>；limit remove <插件>"
        )
    return "访问规则已保存，立即生效"


@access.handle()
async def handle_access(event: Event, args: Message = CommandArg()):
    try:
        reply = execute_command(args.extract_plain_text(), getattr(event, "group_id", None))
    except ValueError as error:
        reply = str(error)
    except OSError as error:
        logger.error(f"访问控制规则保存失败：{error}")
        reply = "规则保存失败，原规则保持不变，请检查文件权限"
    await access.finish(reply)
