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

### `trimo_plugin_msctconverter` — 伶伦转换器

面向 Minecraft 音乐与命令数据的转换工具。插件会缓存用户上传的受支持文件，并按点数及缓存限制执行较重的转换任务。

基础命令：

- `查看帮助`：显示转换帮助；别名包括 `转换帮助`、`cvt_help`、`convert_help`。
- `查看缓存`：列出自己的缓存文件；别名包括 `listCache`、`查看文件缓存`。
- `清除缓存`：清理自己的转换缓存；另有大小写不同的英文别名。
- 上传文件后，根据适配器提供的文件事件自动加入当前用户缓存。

音乐命令：

- `llmscvt`：把 MIDI 等输入转换为 Minecraft 可用格式；别名包括 `linglun_convert`、`音乐转换`、`midi转换`、`转换音乐`。
- 常用选项包括 `-f|--file`、`-ps|--play-speed`、`-dftp|--default-tempo`、`-t|-type`、`-s|--scoreboard-name`、`-p|--player-selector`、`-l|--height-limit`、`-a|--author`、`--debug`。
- `音乐合成`：把音乐文件合成为试听音频；别名包括 `midi合成`、`音乐预览`、`mscprv`、`music_preview`。常用选项为 `-n|-f|--file-name`、`-m|--mode`、`-g|--get-value-method`、`-o|--output-file`。

命令与结构工具：

- `写入文本文件 [文件名]`：把命令消息首行之后的内容写入缓存文件；首行带 `-a` 时追加。
- `指令转结构`：把 Minecraft 指令文件转换为结构；别名包括 `函数转结构`、`cmd2struct`、`command2structure`、`mcfunction2struct`。
- 常用选项：`-n|-f|--file-name`、`-t|-type`、`-e|-x|--expand-axis`、`-l|--length-limit`、`-a|--author`、`--debug`。
- `指令自动更新`：切换当前会话的 Minecraft `execute` 指令自动转换；开启后，以 `execute` 开头的消息会被处理。
- `设置点数 -p|--people <用户> -v|--value <数值> -i|--item <项目>`：超级用户调整转换点数。

该插件选项较多，实际使用时优先执行 `查看帮助` 获取当前版本的完整格式。音频预览依赖 `librosa`、`soundfile`、`mido`、`numpy`、`scipy` 等音频栈，首次处理大型文件可能耗时较长。

### `trimo_status` — 状态、言论与实用查询

提供实例状态卡、随机言论、中文日期时间和数字读法。

- `status`：生成状态卡；别名 `状态`。
- `status -r|--refresh`：绕过状态卡缓存重新生成。
- `status -t|-md|--markdown`：使用 Markdown 路径生成状态卡。
- `status memory` 与 `status process` 已注册，但当前处理器是占位实现。
- `言论 [-r|--refresh] [-s|--special] [-c|--count] [-l|--length <数量>]`：随机言论、刷新或统计言论库；别名 `yanlun`、`言·论`、`yan_lun`。
- `时间`：返回中文历法时间；别名 `时间查询`、`timeq`、`timequery`。
- `读数 <整数> [-g|--group]`：把整数转换为中文读法；`--group` 使用分组读法，别名 `readout_number`、`number_read`。

远程言论配置：`yanlun_remote_enabled` 默认 `false`；关闭或远程不可用时使用内置言论。`yanlun_type` 可为 `file` 或 `url`，数据位置由 `yanlun_path` 指定。

### `liteyuki_uniblacklist` — 联合黑名单（测试中）

启动后定期从远端下载 QQ 号黑名单，并在事件预处理阶段拒绝命中用户的消息。无聊天命令。

- 远端地址当前为 `https://cdn.liteyuki.icu/static/ubl/qq.txt`。
- 更新周期约 10 分钟。
- 这是标记为测试中的网络功能；部署前应评估外部名单来源、网络可用性和误封风险，不需要时可停用插件。

### `liteyuki_satori_user_info` — Satori 用户资料同步

Satori 适配器的临时用户数据维护插件：在消息预处理阶段更新好友/成员资料和消息计数。无聊天命令；未启用 Satori 时没有面向用户的用途。

### `pasyaut_plugin_upskin` — 皮肤投稿（未完成）

仓库中保留了皮肤投稿命令骨架，但当前元数据、帮助处理和投稿处理均被注释、留空或提前返回，因此暂不可用。

- 已注册但无有效结果的帮助入口：`投稿帮助`，别名包括 `查看投稿帮助`、`投稿help`、`submit_help`。
- 关键词入口包括 `皮肤投稿`、`皮肤上传`、`皮肤代投`、`皮肤代发`，当前不会执行投稿。

### `webdash` — 网页监控面板（基础骨架）

向支持 ASGI/FastAPI 的 NoneBot 驱动注册网页接口，无聊天命令。

- `GET /ping`：返回存活响应 `pong`。
- `GET /api/device-info/`：当前为设备信息占位响应。
- `GET /api/bot-info/`：当前为 Bot 信息占位响应。

插件元数据描述了本地网页监控面板，但当前 fork 的接口实现仍是基础骨架，不能视为完整的生产监控系统。

## 适配器与运行限制速查

- `trimo_plugin_handle`、`trimo_plugin_dockdragon` 使用 `nonebot-plugin-alconna` 与 `nonebot-plugin-session` 的统一会话能力，具体支持范围取决于这两个插件和当前适配器。
- `liteyuki_satori_user_info` 仅服务于 Satori；核心同时包含 OneBot V11、OneBot V12 与 Satori 的分支处理。
- 文件上传、群文件和富媒体渲染在不同适配器实现上可能有差异，`trimo_plugin_msctconverter` 与 Markdown 测试插件尤其依赖适配器能力。
- `webdash` 需要支持 HTTP 路由注册的驱动。
- 插件商店、联合黑名单、远程注册和远程言论均涉及外部网络；其中远程注册与远程言论在当前 fork 默认关闭，其他网络功能应按部署需求单独启停。
