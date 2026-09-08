# Liteyuki 权限控制

仅 SUPERUSER 可执行 `/access` 管理命令，回复为纯文字。

```text
/access status
/access list
/access disable plugin foo       # 当前群禁用 foo
/access enable plugin foo        # 当前群显式允许 foo
/access disable-user 123 foo
/access enable-user 123 foo
/access blacklist-user 123
/access unblacklist-user 123
/access blacklist-group 456
/access unblacklist-group 456
/access whitelist-user 123
/access unwhitelist-user 123
/access whitelist-group 456
/access unwhitelist-group 456
/access limit set foo 5 60
/access limit remove foo
```

插件名使用 NoneBot `Plugin.name`（通常为模块最后一段），不是显示名称。
允许预先配置尚未安装的插件。限流参数是次数和秒数；全局按用户与插件
累计，用户在不同群调用也共享额度，无用户 ID 时退回群级计数。

规则顺序集中于 `engine.py`：关闭总开关 → protected 插件 → SUPERUSER
绕过 → 用户黑名单 → 群黑名单 → 用户/群插件显式禁用 → 显式启用或
用户/群白名单 → `access_control_default_allow`。
任何显式禁用均优先于其他作用域的启用；黑白名单同时存在时黑名单优先。
白名单是默认拒绝模式下的例外，并不会因为列表非空就自动切换为拒绝模式。
`liteyuki_access_control` 永久 protected，其他 protected 项由配置指定。
protected 绕过本插件全部规则和限流，但不能提升业务命令自身的权限。

统一 `run_preprocessor` 只处理消息事件和具有 plugin 元数据的 matcher。
插件的 rule/permission 判断通过后、handler 执行前检查；一条事件同一插件
多个 matcher 共用一次判断及额度。调用计数不代表最终业务执行成功次数。
事件处理结束清除判断缓存，启动后台任务每 60 秒清理过期限流记录。
Bot 重启清空计数，JSON 更新限流参数也重置该插件计数。

本插件规则叠加在 Pacman 的启停机制上。SUPERUSER/protected 绕过只在
本插件内有效，不能绕过 Pacman 和业务插件自身权限。NoneBot 并发运行
各 preprocessor，因此其他 preprocessor 拒绝的事件可能已占用一次额度。
事件预处理器、定时任务、API hook、通知事件和脱离 matcher 的业务不被
统一拦截；需要时由业务显式调用 API。多适配器的相同裸用户/群 ID 共用规则。

JSON 存储为 `<access_control_data_path>/rules.json`，通过同目录临时文件、
flush/fsync 和 os.replace 更新，写入失败保持内存和旧文件不变。
损坏文件保留，记录错误并回退空规则（默认允许；若配置默认拒绝则拒绝），
同时拒绝覆盖保存。修复或备份移走损坏文件后重启。仅支持单 NoneBot
进程写入，同一路径不可供多个实例并发使用。

内部 API 使用前先正式加载插件：

```python
from nonebot import require
require("src.nonebot_plugins.liteyuki_access_control")
from src.nonebot_plugins.liteyuki_access_control.api import (
    is_allowed, check_rate_limit, enable_plugin, disable_plugin,
    add_blacklist, remove_blacklist,
)

allowed = await is_allowed("foo", user_id="123", group_id="456")
if allowed:
    allowed = await check_rate_limit("foo", user_id="123", group_id="456")

disable_plugin("foo", "456", scope="group")
enable_plugin("foo", "123", scope="user")
add_blacklist("123", scope="user")
remove_blacklist("123", scope="user")
```

API 调用者负责管理权限。`is_allowed` 不扣额度，`check_rate_limit` 成功会
扣额度，已被统一拦截的 handler 不应重复调用后者。无 Event 的 API 支持
显式 `is_superuser=True`，用于调用者已核验带适配器前缀的超级用户身份；
普通裸 ID 自动匹配当前 NoneBot superusers 配置。

总开关关闭后重启：不注册 matcher、拦截器或清理任务，不创建数据文件，
访问检查 API 全部放行。Pacman 的 matcher 停用不等同卸载全局 hook，
彻底停用访问控制请使用 `access_control_enabled: false` 并重启。
