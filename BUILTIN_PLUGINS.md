# LiteyukiBot-TriM 内置插件说明

本文档按当前 fork 仓库中的实际代码整理，范围包括 Liteyuki v6 主进程插件、由 NoneBot 自动发现的插件，以及由启动器显式加载的核心 NoneBot 插件。它不是上游 Liteyuki 最新版文档。

## 使用前说明

- 下文命令省略了部署者在 NoneBot 配置中设置的命令前缀；如实例要求 `/` 前缀，请相应输入 `/status`、`/npm list` 等。
- “超级用户”指 NoneBot 配置中的 `SUPERUSERS`。
- 部分插件依赖群聊、特定适配器、渲染器或外部网络；对应限制会在条目内注明。
- 插件启停与权限配置保存在 Liteyuki 的数据目录中。生产环境中应只向可信管理员开放插件管理、事件转发、API 调用等高权限功能。

## Liteyuki 主进程插件

### `liteyuki.plugins.plugin_loader` — 外部轻雪插件加载器

负责在 Liteyuki 主进程中发现并导入插件，是框架启动链的一部分，没有聊天命令。

- `liteyuki.plugins`：按 Python 模块名加载额外插件。
- `liteyuki.plugin_dirs`：扫描额外插件目录；本项目默认包含 `src/liteyuki_plugins`。
- 用法：在现有配置中填写模块名或目录，重启后由加载器导入。错误的模块名不会提供用户侧功能，应结合启动日志排查。

### `src.liteyuki_plugins.hello_liteyuki` — 你好轻雪

最小消息处理示例。收到完全匹配的 `你好轻雪` 后回复 `你好呀`。

### `src.liteyuki_plugins.lifespan_monitor` — 生命周期日志

监听 Liteyuki 启动、启动完成、进程关闭和进程重启事件并写入日志。无聊天命令，主要用于观察主进程生命周期。

### `src.liteyuki_plugins.liteyukibot_plugin_nonebot` — NoneBot2 启动器

在 Liteyuki 子进程中初始化 NoneBot2、注册驱动与适配器、加载 `src.liteyuki_main` 和 `src/nonebot_plugins`。开发模式下还负责监听 NoneBot 插件目录变化。它是基础设施插件，不提供聊天命令，也不应被普通插件启停功能关闭。

### `src.liteyuki_plugins.process_manager` — 进程管理器

声明并承载 Liteyuki 多进程管理能力，供框架启动、停止和重载子进程使用。无聊天命令。

### `src.liteyuki_plugins.register_service` — 远程注册服务

将实例基本状态注册到 Liteyuki 旧远程服务，并把服务响应保存到 `data/liteyuki/liteyuki.json`。无聊天命令。

- 配置项：`liteyuki.remote_register`。
- 当前 fork 默认值：`false`，即生产环境默认不连接旧服务。
- 需要保留原功能时可显式设为 `true`；连接失败会降级为警告，不阻止 Bot 启动。

### `src.liteyuki_plugins.resource_loader` — 资源加载器

资源包系统的主进程侧插件声明。资源的实际扫描与应用由核心加载流程及 `liteyuki_pacman` 的 `rpm` 命令协同完成。该插件本身无聊天命令。

### `src.liteyuki_plugins.scheduled_tasks` — 计划任务

在启动前记录 `startup_timestamp` 到共享内存，供状态统计等功能计算运行时间。无聊天命令。

### `liteyuki.plugins.liteecho` — Liteyuki 原生回声（默认未加载）

仓库内随框架提供，但当前默认插件目录配置不会自动加载；如需使用，可把 `liteyuki.plugins.liteecho` 加入 `liteyuki.plugins`。

- `ryounecho <文本>`
- `ryeco <文本>`

仅超级用户可用，回复命令后的文本。

## NoneBot 核心与管理插件

### `src.liteyuki_main` — 轻雪核心插件

由 NoneBot 启动器显式加载，负责资源初始化、基础管理命令、重载状态记录、定时更新及适配器相关初始化；不可通过普通插件开关停用。

- `ryounecho [文本]`：超级用户回声测试；不带文本时返回当前 Bot ID。
- `liteecho`：返回实例问候语与当前 Bot ID。
- `update-ryoun`，别名 `更新灵温`：超级用户拉取项目更新并生成结果卡片。
- `reload-ryoun`，别名 `重启灵温`、`重启尹灵温`、`重载灵温`：超级用户重载 Liteyuki，并在连接恢复后回报耗时。
- `/function <函数名> [参数...]`：超级用户调用已注册的 Liteyuki 函数。`key=value` 形式作为关键字参数传入。
- `/api <API名> [key=value ...]`：超级用户直接调用当前适配器 API。
- 配置 `auto_update` 默认为 `true` 时，每日 04:00 会检查更新、安装依赖并在成功后重载。生产部署应按维护策略决定是否关闭。

`/function` 和 `/api` 能执行高权限操作，只应供可信超级用户诊断使用。

### `liteyuki_pacman` — 插件、群聊与资源包管理

统一管理插件启停、插件商店操作、群聊开关、帮助和资源包。多数全局、安装和资源管理操作仅限超级用户；群内启停允许超级用户、群主或群管理员按代码中的权限规则操作。

插件命令：

- `npm enable <插件名> [-g|--group <群号>]`：在当前群或指定群启用插件。
- `npm disable <插件名> [-g|--group <群号>]`：在当前群或指定群停用插件。
- `npm enable-global <插件名>`：全局启用；别名 `eg`、`全局启用`。
- `npm disable-global <插件名>`：全局停用；别名 `dg`、`全局停用`。
- `npm update`：更新插件商店索引。
- `npm search <关键词...>`：搜索插件。
- `npm install <插件名>` / `npm uninstall <插件名>`：安装或卸载插件。
- `npm list [页码] [每页数量] [-m|--markdown]`：列出插件，默认第 1 页、每页 10 项。
- 主命令别名：`插件`。

其他管理命令：

- `gm enable [群号]` / `gm disable [群号]`：启用或停用群聊；别名主命令 `群聊`。只有超级用户可操作任意指定群。
- `help [插件名]`：查看总帮助或指定插件帮助；别名 `帮助`。
- `rpm list [页码] [每页数量]`：列出资源包。
- `rpm load <名称>` / `rpm unload <名称>`：加载或卸载资源包。
- `rpm up <名称>` / `rpm down <名称>` / `rpm top <名称>`：调整资源包优先级。
- `rpm reload`：重新载入资源。
- `rpm` 的别名为 `资源包`，整组资源包命令仅限超级用户。

### `liteyuki_user` — 用户资料管理

提供用户语言、昵称、时区和位置资料的查看与修改。

- `profile`：显示当前用户资料卡。
- `profile set <字段> [值]`：设置资料；`set` 也可写作 `s`、`设置`。
- `profile get <字段>`：查询字段；`get` 也可写作 `g`、`查询`。
- 主命令别名：`用户信息`。
- 常用字段：`lang`、`nickname`、`timezone`、`location`。省略语言或时区的值时，插件会给出可选项。

### `liteyuki_statistics` — 消息统计

记录消息并生成时段统计图和排行；同时为项目内的统计接口提供数据。

- `statistic message`：生成消息统计，别名 `statistic msg`、`statistic m`，主命令也可写作 `stat`。
- 常用参数：`-d|--duration`（默认 `2d`）、`-p|--period`（默认 `60s`）、`-b|--bot`、`-g|--group`、`-u|--user`。
- `statistic rank`：生成排行，子命令别名 `r`。
- 排行参数：`-u|--user` 或 `-g|--group` 选择排行维度，`-l|--limit key=value...` 过滤，`-d|--duration` 默认 `1d`，`-r|--rank` 默认显示 20 项。

时间参数接受项目解析器支持的单位写法，例如 `60s`、`2h`、`1d`。

### `liteyuki_eventpush` — 跨会话事件推送

把一个 Bot/会话中收到的消息转发到另一个 Bot/会话，支持单向和双向关系。

- 节点格式：`bot_id.session_type.session_id`，其中会话类型通常为 `private` 或 `group`。
- `lep add <源节点> <目标节点>`：添加单向推送。
- `lep add <源节点> <目标节点> bidirectional true`：同时添加反向推送。
- `lep list`：列出现有推送及索引。
- `lep rm <索引>`：删除推送。

当前命令注册未声明显式权限限制。它可能跨群、跨账号传播消息，生产环境应通过插件启停、命令权限或访问策略限制为管理员使用。

### `liteyuki_markdowntest` — Markdown 渲染测试

用于验证统一消息、按钮及 LaTeX 渲染能力，全部仅限超级用户。

- `mdts`：Markdown 图片/消息测试。
- `btnts`：按钮测试。
- `latex`：LaTeX 渲染测试。

### `to_liteyuki` — NoneBot 到 Liteyuki 事件桥

把 NoneBot 收到的消息事件投递到 Liteyuki 主框架通道，供 Liteyuki 原生处理器消费。无直接聊天命令；停用会影响原生 Liteyuki 消息插件。

## 功能插件

### `liteyuki_60s` — 60S 资讯与娱乐

通过可配置的 60s API 获取每日资讯与随机娱乐内容。`sixty_api_base_url` 可替换为自建或其他公共实例；十个手动功能默认开启，自动推送默认关闭且必须显式配置 `sixty_api_push_groups`。

- `60s`（`每日新闻`、`60秒读懂世界`、`60秒看世界`）：优先发送 API 整张日报图，下载失败时生成本地新闻卡。
- `ai资讯`、`历史上的今天`、`it资讯`、`摸鱼日报`、`一言`、`运势`：发送本地图片卡；AI 当日无资讯时提示而不发空卡。
- `发病文学 [名字]`、`kfc`（`疯狂星期四`）、`冷笑话`：直接发送 API 返回的纯文字。
- 运势按用户和 `sixty_api_timezone` 持久化记录，默认每天 1 次；请求或发送失败不会消耗次数。
- 可分别设置五项日报/资讯的每日推送、每周四 KFC 推送，以及发病文学/冷笑话在指定时间窗内的随机推送。多 Bot 时请设置 `sixty_api_push_bot_id`，否则仅会在唯一在线 Bot 时主动发送，避免重复群发。

### `liteyuki_weather` — 轻雪天气

使用和风天气的自定义 API Host 查询城市天气，并生成包含实时、逐小时、七日预报、日出日落和当地 AQI 的天气卡。需在 `config.yml` 配置 `weather_api_host` 与 `weather_key`；用户可通过 `profile set location <城市>` 保存默认地点，并沿用资料中的公制/英制设置。

- `/weather 深圳` 或 `天气 深圳`：查询指定地点；不提供地点时使用用户资料中的默认 `location`。
- 自然语言支持：`深圳天气`、`深圳今天天气`、`深圳天气怎么样`、`查一下深圳天气`、`广东 深圳天气` 等能明确提取地点的表达。
- `今天天气真好`、`天气不错`、`这天气太热了` 等不含明确地点的普通聊天不会触发。
- 天气 API 或 AQI 不可用时会给出友好提示或省略 AQI，不影响 NoneBot 启动。

### `trimo_plugin_handle` — 猜成语

提供四字成语 Wordle 游戏，按汉字、声母、韵母和声调给出提示。

- `@Bot handle [-s|--strict] [-d|--difficult]`：开始游戏；别名 `猜成语`。当前默认要求提及 Bot。
- 游戏中发送恰好四个汉字进行猜测。
- `handle_hint`：获取提示；别名 `提示`、`猜成语提示`。
- `handle_stop`：结束当前游戏；别名 `结束`、`结束游戏`、`结束猜成语`。

超级用户词库命令：

- `更正拼音 <成语> <拼音1> <拼音2> <拼音3> <拼音4>`
- `新成语 <成语> [-e|--explanation <释义>] [-d|--difficult]`
- `删除成语 <成语>`
- `成语答案 [-s|--specify <会话>] [-l|--list]`

相关配置及默认值：`handle_strict_mode=false`、`handle_color_enhance=false`、`handle_superuser_get_answer=true`、`handle_require_tome=true`。

### `trimo_plugin_dockdragon` — 成语接龙

当前可用部分是四字成语自动接续：在群会话中收到合法四字成语时，自动回复可接续的成语及信息。

- `自动接龙`：切换当前群的自动接龙回复；别名 `自动成语接龙`。
- 代码中注册了 `dockdragon`（别名 `接龙`）、`提示`、`结束`（别名 `结束游戏`、`结束接龙`）匹配器，但完整的开局、提示和结束处理器目前被注释或未挂载，不能视为可用的回合制游戏功能。

自动接龙默认在会话内开启，可能响应任意用户发送的合法四字成语；不需要时应通过上述命令关闭或停用插件。

### `trimo_status` — 状态与实用查询

提供实例状态卡、中文日期时间和数字读法。状态卡底部的一言按需获取，失败时使用固定本地文案。

- `status`：生成状态卡；别名 `状态`。
- `status -r|--refresh`：绕过状态卡缓存重新生成。
- `status -t|-md|--markdown`：使用 Markdown 路径生成状态卡。
- `status memory` 与 `status process` 已注册，但当前处理器是占位实现。
- `时间`：返回中文历法时间；别名 `时间查询`、`timeq`、`timequery`。
- `读数 <整数> [-g|--group]`：把整数转换为中文读法；`--group` 使用分组读法，别名 `readout_number`、`number_read`。

### `liteyuki_access_control` — 本地权限控制与限流

统一提供本地用户/群黑名单、白名单、插件访问规则和内存限流。规则保存到本地 JSON，不访问联合黑名单或其他外部服务。

- `/access blacklist-user <用户 ID>`、`/access unblacklist-user <用户 ID>`：管理用户黑名单。
- `/access blacklist-group <群 ID>`、`/access unblacklist-group <群 ID>`：管理群黑名单。
- 黑名单优先于白名单和插件显式启用；管理命令仅限 SUPERUSER。

### `webdash` — 网页监控面板（基础骨架）

向支持 ASGI/FastAPI 的 NoneBot 驱动注册网页接口，无聊天命令。

- `GET /ping`：返回存活响应 `pong`。
- `GET /api/device-info/`：当前为设备信息占位响应。
- `GET /api/bot-info/`：当前为 Bot 信息占位响应。

插件元数据描述了本地网页监控面板，但当前 fork 的接口实现仍是基础骨架，不能视为完整的生产监控系统。

## 适配器与运行限制速查

- `trimo_plugin_handle`、`trimo_plugin_dockdragon` 使用 `nonebot-plugin-alconna` 与 `nonebot-plugin-session` 的统一会话能力，具体支持范围取决于这两个插件和当前适配器。
- `liteyuki_satori_user_info` 仅服务于 Satori；核心同时包含 OneBot V11、OneBot V12 与 Satori 的分支处理。
- 文件上传、群文件和富媒体渲染在不同适配器实现上可能有差异，Markdown 测试插件尤其依赖适配器能力。
- `webdash` 需要支持 HTTP 路由注册的驱动。
- 插件商店、远程注册和状态卡一言涉及外部网络；其中远程注册默认关闭，状态卡一言失败时会使用本地文案，其他网络功能应按部署需求单独启停。
