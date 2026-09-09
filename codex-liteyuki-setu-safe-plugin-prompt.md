# Codex 任务：为 LiteyukiBot v6-LTS 制作全功能多源二次元图片插件（Safe-only）

请在当前仓库 **`DavidBlackCN/LiteyukiBot-v6-LTS`** 最新 `main` 分支上新增一个内置 NoneBot 插件，提供多 API 二次元图片检索、随机获取、群级白名单管理、管理员动态配置、自动撤回、数量/冷却限制、Provider 自动选择与故障回退等完整能力。

> **内容边界：本插件仅实现全年龄 / non-explicit 图片获取。**
>
> 不实现、不要预留可被简单配置开启的 R18/NSFW 图片检索或分发路径。
> 对 Lolicon / Anosu 等带年龄分级参数的 Provider，代码必须始终强制使用全年龄参数（如 `r18=0`），并在返回结果中再次拒绝任何被标记为成人内容的记录。
> 若用户命令中出现 `-r`、`--r18`、`r18`、`nsfw` 等成人内容请求，应直接友好拒绝，不得把这些参数传给 Provider。
>
> 本任务仍可以继续使用用户习惯的“色图 / 涩图”命令别名，但实际内容必须保持全年龄。

开始编码前必须先完整阅读仓库根目录 **`AGENTS.md`**，并以其中的 LTS 维护边界、依赖规则、OneBot V11/V12 优先级、配置风格、数据库约束与测试要求为最高项目规则。

随后自行阅读至少：

- `src/nonebot_plugins/`
- `src/nonebot_plugins/liteyuki_group_manager/`
- `src/nonebot_plugins/liteyuki_access_control/`
- `src/nonebot_plugins/liteyuki_pacman/`
- `src/nonebot_plugins/liteyuki_weather/`
- `src/utils/base/data_manager.py`
- `src/utils/base/config.py`
- `config.example.yml`
- `BUILTIN_PLUGINS.md`
- 当前 `tests/` 中的测试风格
- 当前已安装版本的 `nonebot-plugin-alconna` / `nonebot-plugin-uninfo` API

不要把此任务扩大成 Liteyuki v6 架构重构。

---

## 1. 目标插件

建议模块：

```text
src/nonebot_plugins/liteyuki_setu/
```

建议展示名：

```text
Liteyuki 二次元图片
```

主要职责：

1. 随机获取全年龄二次元图片；
2. 根据关键词 / Tag / Pixiv UID 等条件搜索（Provider 支持时）；
3. 支持一次 1~5 张图片；
4. 默认请求数量 3，硬上限 5；
5. 支持指定 Provider 或自动选择；
6. 支持图片尺寸、AI 作品过滤、横竖图等可选参数；
7. 群聊默认全部关闭，只有配置白名单或管理员动态开启后才能使用；
8. 私聊使用有独立全局开关；
9. 每个群拥有自己的运行时配置覆盖；
10. 支持自动撤回；
11. 支持用户冷却 / 防刷屏；
12. Provider 请求或图片下载失败时可以安全 fallback；
13. API Base URL / endpoint / Pixiv 图片反代均可配置；
14. 配置与动态群状态持久化；
15. 不新增 Satori 硬依赖。

插件元数据遵循当前 LTS 内置插件格式，例如：

```python
extra={
    "liteyuki": True,
    "lts_builtin": True,
    "toggleable": True,
    "default_enable": True,
    "help_category": "builtin",
}
```

注意：

> `default_enable=True` 仅代表插件模块被 Liteyuki 加载，不代表任意群可以使用图片命令。
> 本插件自身的群白名单仍必须默认全部关闭。

---

# 2. 调研参考与应借鉴的设计

实现时不要复制第三方插件代码；只借鉴职责拆分、交互和工程经验。

## 2.1 `nonebot-plugin-setu-now`

参考：

- https://github.com/kexue-z/nonebot-plugin-setu-now

值得借鉴：

- `on_alconna` 参数式命令；
- 数量 + 关键词 + 多 Tag 组合；
- Pixiv 图片反代；
- 图片尺寸；
- `excludeAI`；
- 自动撤回；
- 连续发送节流；
- API 获取与图片下载/发送职责分离；
- 图片发送失败不直接拖垮整个请求；
- 使用统一的数据模型封装 PID / title / author / tags / urls；
- 对 API 无结果提供明确提示。

该项目当前 Lolicon 请求结构可作为 v2 API 实际行为参考：

```text
keyword
tag
r18
proxy
num
size
excludeAI
```

响应对象包含类似：

```text
pid
p
uid
title
author
r18
width
height
tags
ext
aiType
uploadDate
urls
```

本项目不要照搬它的 ORM / localstore 依赖体系；优先复用 Liteyuki v6-LTS 自己已有的数据层和依赖。

## 2.2 `nonebot-plugin-simple-setu`

参考：

- https://github.com/nomdn/nonebot-plugin-simple-setu

值得借鉴：

- HTTP client、限流、发送层分离；
- 失败重试有上限；
- 不把网络请求全部写进 matcher；
- 使用统一消息能力减少 adapter-specific 代码。

不要为了复刻它而新增 `nonebot-plugin-saa`、`nonebot-plugin-limiter` 等额外依赖；当前 LTS 已有 Alconna / UniMessage / 自身数据层。

## 2.3 多 Provider 项目 `clovers-setu-collection`

参考：

- https://pypi.org/project/clovers-setu-collection/

该项目曾组合 Lolicon / MirlKoi / Anosu，并区分不同场景使用的 API，这一 Provider 思路值得借鉴。

需要特别注意：

> 该项目后续版本已经停止默认使用旧 MirlKoi Provider，并改为 Anosu。

因此本插件绝不能把 MirlKoi 当作唯一数据源；MirlKoi 必须可独立关闭，并通过 Provider health/fallback 机制隔离故障。

---

# 3. 首批 Provider

第一版必须实现：

1. **Lolicon API v2**
2. **MirlKoi / cnmiw**
3. **Anosu / Jitsu**（推荐备用 Provider）

统一设计 Provider interface，不允许三套 matcher 各自调用三套 API。

建议：

```text
providers/
├── base.py
├── lolicon.py
├── mirlkoi.py
└── anosu.py
```

---

# 4. Provider 统一模型

建议建立内部查询模型：

```python
ImageQuery(
    count: int,
    keyword: str | None,
    tags: list[str],
    uid: list[int],
    size: str,
    exclude_ai: bool,
    orientation: str | None,
    provider: str,
)
```

以及统一结果模型：

```python
ImageResult(
    provider: str,
    image_url: str,
    pid: int | str | None,
    uid: int | str | None,
    title: str | None,
    author: str | None,
    tags: list[str],
    width: int | None,
    height: int | None,
    ai_type: int | None,
    is_adult: bool | None,
    source_url: str | None,
)
```

可以使用 Pydantic 或 dataclass，以当前仓库风格为准。

每个 Provider 需要声明自己的 capability，例如：

```python
ProviderCapabilities(
    random=True,
    count=True,
    keyword=True,
    tags=True,
    uid=True,
    size=True,
    exclude_ai=True,
    orientation=True,
    metadata=True,
    safe_classification=True,
)
```

自动 fallback 前必须检查 capability。

不能出现：

```text
用户搜索“原神”
↓
Lolicon 超时
↓
MirlKoi 不支持关键词
↓
随便返回一张随机图并假装搜索成功
```

只有备用 Provider 能**等价表达当前 Query**时才能 fallback。

---

# 5. Lolicon Provider

官方接口：

```text
https://api.lolicon.app/setu/v2
```

文档：

- https://docs.api.lolicon.app/#/setu

Base URL / endpoint 必须可配置，不要把域名散落硬编码在业务文件。

建议使用 POST JSON（也可根据当前官方 API 验证后选择 GET），支持：

```text
num
uid
keyword
tag
size
proxy
excludeAI
aspectRatio
```

### 内容安全要求

无论配置、命令或内部 Query 如何：

```text
r18 = 0
```

必须由 Provider 强制写入。

不得允许调用方覆盖。

返回结果若：

```text
item.r18 == true
```

必须丢弃。

如果返回结构未来变化导致无法确认分级，不应把不确定结果当作全年龄安全结果发送。

### Tag

Lolicon v2 支持高级 Tag 匹配。

内部 Query 的多个 Tag 应正确映射，而不是用字符串拼接破坏 AND / OR 语义。

### 图片 URL

优先使用配置的 `size`：

```text
original
regular
small
thumb
mini
```

实际可用尺寸以当前官方 API 为准。

默认建议：

```text
regular
```

避免默认下载十几 MB 原图。

Pixiv 图片反代地址必须配置化，例如：

```yaml
setu_pixiv_proxy: "i.pixiv.re"
```

不要在代码里到处 `.replace()` 固定域名。

---

# 6. Anosu Provider

文档：

- https://docs.anosu.top/
- https://docs.anosu.top/intro/params.html

已知 JSON 接口：

```text
https://image.anosu.top/pixiv/json
```

公开参数包括：

```text
num
r18
size
keyword
proxy
db
```

其中：

- `num`: JSON 下支持多张；
- `size`: `original` / `regular` / `small`；
- `keyword`: 支持使用 `|` 分隔多个关键词；
- `proxy`: Pixiv 反代；
- `db`: 图库选择。

### 内容安全

强制：

```text
r18=0
```

调用方不可覆盖。

若 Anosu 返回结果存在分级字段，必须二次检查。

如果当前响应没有可靠分级字段，则只能信任明确请求 `r18=0` 的官方接口行为，并把 provider 的 `safe_classification` 能力按实际情况声明，不要伪造元数据。

Anosu 可作为：

- 随机图 fallback；
- keyword fallback；
- count fallback；
- size fallback。

它不支持的 Lolicon 高级筛选（例如 UID、多组 Tag AND 组合等）不要假装支持。

---

# 7. MirlKoi / cnmiw Provider

当前站点：

- https://api.cnmiw.com/
- https://cnmiw.com/main.html

历史公开 API 文档曾使用：

```text
https://sese.iw233.top/iapi.php
```

并存在：

```text
sort=random
type=json
num=...
```

等形式。

但是 MirlKoi 域名、API 路径和图库分类历史上变化较多；旧多源项目也曾因其接口状态变化停用默认 Provider。

因此实现要求：

1. Codex 在编码时重新检查 **当前 `api.cnmiw.com` / `cnmiw.com` 实际文档**；
2. 将：
   - Base URL
   - endpoint
   - JSON 参数名
   - 图片字段
   全部隔离在 `MirlKoiProvider` 中；
3. 配置允许用户替换 Base URL / endpoint；
4. 不把历史 `sese.iw233.top` 写成唯一固定地址；
5. 若当前 API 只提供直接图片响应，则 Provider 正确处理 redirect / `Content-Type: image/*`；
6. 若支持 JSON，则统一转为 `ImageResult`。

### 重要安全限制

旧版 `sort=random` 曾表示“整个随机池”，不能证明只含全年龄内容。

因此：

> **禁止仅因为名字叫 random 就把该池当作 safe Provider。**

MirlKoi Provider 只有在当前官方接口能够明确选择全年龄 / 非露骨图库，或者当前 endpoint 本身被官方定义为全年龄时，才允许在 `safe-only` 插件中启用。

若实现时无法从当前文档可靠确认全年龄 endpoint：

- Provider 代码仍可完成；
- 配置默认 `setu_mirlkoi_enabled: false`；
- health/status 显示 `unavailable: safe endpoint not verified`；
- 不得静默使用旧 `sort=random`；
- 不影响 Lolicon / Anosu 正常工作。

这不是实现失败，而是安全的 Provider 降级设计。

---

# 8. Provider 配置

在 `config.example.yml` 增加一个独立区域。

保持项目现有**顶层 YAML 键**风格。

建议前缀：

```text
setu_
```

### 全局

建议：

```yaml
# -------------------- 二次元图片 --------------------

# 私聊是否允许使用全年龄图片命令。
setu_private_enabled: true

# 默认单次图片数。
setu_default_count: 3

# 单次硬上限，最大不得高于 5。
setu_max_count: 5

# 用户调用冷却时间，单位秒。
setu_cooldown_seconds: 30

# 多图逐条发送间隔，单位秒。
setu_send_interval_seconds: 1.0

# 默认开启自动撤回。
setu_auto_recall: true

# 默认撤回时间，单位秒。
setu_recall_seconds: 60

# 默认排除 AI 作品。
setu_exclude_ai: true

# 默认图片尺寸。
setu_image_size: "regular"

# 单张下载最大字节数，避免异常大图。
setu_image_max_bytes: 20971520

# HTTP 请求超时。
setu_request_timeout: 15

# API 失败的有限重试次数。
setu_request_retries: 2

# 初始启用群白名单；默认全部关闭。
setu_enabled_groups: []

# Provider 自动选择顺序。
setu_provider_order:
  - lolicon
  - anosu
  - mirlkoi

# 默认来源；auto 表示按 capability + health 自动选择。
setu_default_provider: "auto"

# Pixiv 图片反向代理。
setu_pixiv_proxy: "i.pixiv.re"
```

### Lolicon

```yaml
setu_lolicon_enabled: true
setu_lolicon_api_url: "https://api.lolicon.app/setu/v2"
```

### Anosu

```yaml
setu_anosu_enabled: true
setu_anosu_api_url: "https://image.anosu.top/pixiv/json"
setu_anosu_db: 0
```

### MirlKoi

最终字段以当前 API 实际情况确定，例如：

```yaml
setu_mirlkoi_enabled: false
setu_mirlkoi_base_url: "https://api.cnmiw.com"
setu_mirlkoi_endpoint: ""
```

如果 Codex 能确认当前稳定的全年龄 endpoint，可填安全默认值并解释来源；否则保留空 endpoint + disabled。

### Provider health

建议：

```yaml
setu_provider_failure_threshold: 3
setu_provider_cooldown_seconds: 120
```

health/circuit breaker 可只保存在进程内：

- 连续失败 N 次临时标记 unhealthy；
- cooldown 后允许再次探测；
- 不需要持久化。

---

# 9. 群级配置与持久化

这是本插件的核心要求。

### 默认状态

```text
所有群：关闭
自动撤回：开启
默认数量：3
最大数量：5
成人内容：不支持
```

`setu_enabled_groups` 仅作为初始/静态配置来源。

管理员通过命令修改的运行时状态必须持久化。

不要让管理命令直接编辑 `config.yml`。

优先使用当前仓库：

```python
src.utils.base.data_manager.Group
group_db
Group.config
```

或者经审阅后使用与现有数据层一致的最小持久化方式。

推荐在：

```python
Group.config["liteyuki_setu"]
```

存储：

```json
{
  "enabled": true,
  "auto_recall": true,
  "recall_seconds": 60,
  "default_count": 3,
  "provider": "auto",
  "exclude_ai": true,
  "cooldown_seconds": 30
}
```

只存储与全局默认值不同的 override 也可以。

必须：

- 重启后仍生效；
- 不创建任意格式散落 JSON；
- 不破坏现有 `Group.config` 其他插件的数据；
- 对旧记录缺字段使用全局默认值；
- reset 时只删除本插件命名空间。

配置优先级：

```text
群运行时 DB override
        ↓
config.yml 全局默认
        ↓
Pydantic 安全默认
```

群 `enabled` 例外：

```text
DB 显式值
        ↓
setu_enabled_groups 初始白名单
        ↓
false
```

---

# 10. 管理权限

群级管理命令允许：

- SUPERUSER；
- 当前群群主；
- 当前群管理员。

如果现有 `src.utils.base.permission.GROUP_ADMIN / GROUP_OWNER` 可直接复用，应优先复用。

SUPERUSER 可指定目标群 ID。

普通群管理员只能管理**当前群**，不能输入任意群号修改其他群。

私聊全局开关、Provider 全局配置等仅 SUPERUSER 可管理。

---

# 11. 管理命令

建议独立命令：

```text
色图管理
```

别名可包括：

```text
图片管理
setu-admin
```

至少实现：

```text
/色图管理 状态
/色图管理 开启
/色图管理 关闭

/色图管理 撤回 开
/色图管理 撤回 关
/色图管理 撤回时间 60

/色图管理 数量 3
/色图管理 来源 auto
/色图管理 来源 lolicon
/色图管理 来源 anosu
/色图管理 来源 mirlkoi

/色图管理 AI过滤 开
/色图管理 AI过滤 关

/色图管理 冷却 30

/色图管理 重置
```

SUPERUSER 可以：

```text
/色图管理 开启 123456789
/色图管理 状态 123456789
```

私聊中 SUPERUSER 可：

```text
/色图管理 私聊 开
/色图管理 私聊 关
```

如果“动态修改全局配置”需要写入 `config.yml` 才能持久化，则不要这么做。

私聊动态开关可以：

- 只允许配置文件修改；或
- 存入 `common_db` 的本插件命名空间。

优先选择后者时必须保持实现很小且清晰。

---

# 12. 用户图片命令

主命令建议：

```text
色图
```

别名：

```text
setu
涩图
来点色图
来张色图
二次元图
```

命令本身仍使用 `on_alconna` 或当前 LTS 推荐的 matcher 注册方式。

用户要求允许“命令前缀后的参数内容采用正则匹配”，因此：

> 不要把所有语法硬塞成极复杂 Alconna grammar。

推荐：

```text
Alconna / command matcher
       ↓
提取 raw args
       ↓
小型 SetuQueryParser
       ↓
ImageQuery
```

Parser 可以使用几个清晰正则，但不要做一个无法维护的超级正则。

---

# 13. 参数语法

至少支持：

### 无参数

```text
/色图
```

默认：

```text
count = 当前群 default_count / 全局 setu_default_count
provider = 当前群 provider / auto
```

### 数量

```text
/色图 1
/色图 3
/色图 5
```

超过 `setu_max_count`：

- clamp 到最大值，或
- 友好提示并拒绝；

选择一种一致行为。

推荐直接提示：

```text
单次最多获取 5 张图片。
```

### 关键词

```text
/色图 原神
/色图 明日方舟
```

### 数量 + 关键词

```text
/色图 3 原神
```

### Tag

```text
/色图 -t 原神
/色图 -t 原神 -t 甘雨 2
```

### Provider

```text
/色图 --source lolicon 原神
/色图 --source anosu 原神
/色图 --source auto 原神
```

### 尺寸

```text
/色图 --size regular 原神
/色图 --size original 风景
```

仅 Provider 支持时生效。

### AI

```text
/色图 --no-ai 原神
```

可作为当前群 `exclude_ai` 的单次强化。

不要提供“强制包含 AI”的复杂模式；只需允许排除。

### Pixiv UID

仅 Provider 支持时：

```text
/色图 --uid 123456
```

### 横竖图

可以提供：

```text
/色图 --portrait
/色图 --landscape
```

映射到 Provider 的 aspect ratio 能力。

如果 Provider 不支持，自动模式可以切换到支持该条件的 Provider；用户强制指定某 Provider 时则明确提示“不支持此筛选”。

---

# 14. 成人内容请求处理

即使用户使用：

```text
/色图 --r18
/色图 -r
/色图 r18
/色图 nsfw
```

也不得进入 Provider。

Parser 应识别这些成人内容参数/关键词并直接终止，例如：

```text
当前插件仅提供全年龄内容。
```

不需要在用户提示中做长篇解释。

也不要把这些关键字当普通 Tag 继续搜索。

代码中不要存在：

```python
if config.r18_enabled:
    ...
```

这种未来只改一个配置就能开启成人图片分发的完整路径。

---

# 15. 群聊启用检查

群聊消息进入 handler 后，在执行：

- cooldown；
- 参数解析后的 API 请求；
- 图片下载；

之前就检查当前群是否启用。

未启用：

```text
本群未开启此功能。
```

不要消耗 API 请求。

群白名单只控制本插件自身，不要绕过 Liteyuki 全局插件启停 / access_control。

也就是说最终允许条件应同时尊重：

```text
Liteyuki 插件本身处于可用状态
+
access_control 没有拒绝
+
本插件 group enabled
```

不要复制一套新的全局权限系统。

---

# 16. 私聊

配置：

```yaml
setu_private_enabled: true
```

私聊仅允许全年龄内容。

私聊：

- 不依赖群白名单；
- 仍受 cooldown；
- 仍受 max_count；
- 仍支持 auto recall（如果当前 adapter 支持私聊撤回）；
- 仍强制 safe-only；
- 仍尊重 Liteyuki access_control。

如果 adapter 不支持私聊撤回：

- 图片仍正常发送；
- 记录 debug/warning；
- 不把撤回失败当发送失败。

---

# 17. 自动撤回

默认：

```yaml
setu_auto_recall: true
setu_recall_seconds: 60
```

群可独立 override。

要求：

1. 发送成功后获取对应 receipt/message id；
2. 每张图片独立撤回；
3. 一张撤回失败不影响其他图片；
4. 不要在 handler 中简单：

```python
await asyncio.sleep(60)
```

然后卡住整个命令。

应使用：

- `asyncio.create_task()` + 受管理 task set；或
- 当前 `UniMessage` receipt 提供的可靠非阻塞 recall 机制；或
- 其他最小后台调度方式。

不要为几十秒的短期撤回任务引入数据库持久化。

Bot 重启导致未执行的撤回任务丢失可以接受，并在代码注释中说明。

撤回异常只记日志。

---

# 18. 图片发送方式

优先使用当前 LTS 已安装的：

```python
UniMessage
```

建议一张结果一条消息：

```text
作品信息（可选）
图片
```

而不是默认把 5 张图塞进一个 adapter-specific 合并转发。

理由：

- OneBot V11/V12 行为更可控；
- 自动撤回可以逐条处理；
- 单张失败不会影响全部；
- 私聊与群聊逻辑统一。

发送间隔使用：

```yaml
setu_send_interval_seconds: 1.0
```

不要出现 setu-now 旧实现里错误计算 sleep 的问题；正确 sleep 应是：

```text
remaining = interval - elapsed
```

而不是 sleep 已经过的时间。

---

# 19. 图片信息

建议每张图片可带简洁元信息：

```text
标题：...
画师：...
PID：...
来源：Lolicon
```

默认不要把完整 tags 全部刷屏。

增加：

```yaml
setu_show_metadata: true
```

可以显示：

- title
- author
- PID
- source

如果 metadata 不存在，只发送图片。

Pixiv 来源链接可生成：

```text
https://www.pixiv.net/artworks/{pid}
```

但必须确认 PID 有效。

不要把 Provider API 地址暴露给普通用户。

---

# 20. HTTP / 图片下载层

统一一个 HTTP client/service。

不要每个 Provider 自己创建大量无复用 session。

优先使用仓库已存在的 `aiohttp` 或 `httpx`；不新增 HTTP 依赖。

建议：

```text
network.py
```

职责：

- timeout；
- redirect；
- JSON GET/POST；
- image stream download；
- proxy；
- User-Agent；
- Content-Type 检查；
- 最大下载大小；
- 错误包装。

图片下载必须：

1. 要求 2xx；
2. 跟随合理 redirect；
3. `Content-Type` 应为 `image/*`，无法确认时用 Pillow verify 兜底；
4. 不超过 `setu_image_max_bytes`；
5. 可使用 Pillow 验证图片；
6. 不把 HTML 错误页当图片发；
7. 不无限重试。

下载后优先发送 bytes：

```python
UniMessage.image(raw=image_bytes)
```

不需要为了发送强制持久化图片文件。

---

# 21. 请求重试

配置：

```yaml
setu_request_retries: 2
```

只对：

- timeout；
- connection error；
- 5xx；
- 图片 CDN 临时失败；

做有限重试。

不要对：

- 4xx 参数错误；
- 无搜索结果；
- Provider 不支持；
- safe filter 拒绝；

重复请求。

重试建议加小幅 backoff。

---

# 22. Provider health / circuit breaker

为防止一个挂掉的 API 每次用户请求都拖慢全部流程：

进程内维护简单状态：

```text
consecutive_failures
unhealthy_until
last_error
```

失败达到：

```yaml
setu_provider_failure_threshold: 3
```

则临时跳过：

```yaml
setu_provider_cooldown_seconds: 120
```

成功后 reset。

只统计：

- 网络失败；
- Provider 5xx；
- malformed response；
- 图片 endpoint 持续失败。

“没有搜索结果”不算 Provider unhealthy。

---

# 23. Fallback 规则

`--source auto`：

1. 按 `setu_provider_order`；
2. 过滤 disabled；
3. 过滤 unhealthy；
4. 检查 capability；
5. 检查 safe availability；
6. 调用；
7. 失败时考虑下一个等价 Provider。

用户显式：

```text
--source lolicon
```

则不要暗中换源。

失败就明确回复：

```text
Lolicon 当前不可用，请稍后重试或使用 --source auto。
```

这样用户才能知道指定源没有被偷偷替换。

---

# 24. Cooldown / 防刷屏

实现轻量 per-user cooldown。

配置：

```yaml
setu_cooldown_seconds: 30
```

群可 override。

SUPERUSER 是否绕过 cooldown：

建议：

```yaml
setu_superuser_bypass_cooldown: true
```

使用 monotonic time + 内存即可，不要求持久化 cooldown。

关键：

> 被拒绝、无结果、API 整体失败且没有发送任何图片时，不应让用户承担完整 cooldown。

可以在第一次成功发送后正式提交 cooldown，或者失败时清除 reservation。

防止并发双击：

- 对同一 user/session 做短期锁或 reservation；
- 不允许同一用户同时开启多个 5 图下载任务。

---

# 25. 并发

多图片请求不要无限并发。

建议：

```yaml
setu_download_concurrency: 3
```

使用 Semaphore。

Provider 返回 5 张时：

- 最多 3 个并行下载；
- 发送仍按稳定顺序/节流进行。

同一个 Bot 的整体图片下载并发也应有合理上限。

---

# 26. Safe-only 二次校验

除了 Provider 请求强制全年龄外，再做统一层检查：

```python
def is_result_safe(result: ImageResult) -> bool:
    ...
```

规则至少：

1. `is_adult is True` → 拒绝；
2. Lolicon `r18=true` → 拒绝；
3. Provider 当前 endpoint 无法证明是全年龄 → Provider 不进入 safe auto pool；
4. 不因为字段缺失就把明确成人分类改成 False；
5. 不下载/发送被拒绝结果。

可以设置一个很小的 blocked query token 集合用于识别用户直接请求成人模式，但不要构建成人内容 Tag 搜索功能。

---

# 27. 推荐代码结构

根据仓库风格可微调：

```text
src/nonebot_plugins/liteyuki_setu/
├── __init__.py
├── config.py
├── models.py
├── parser.py
├── commands.py
├── admin.py
├── service.py
├── storage.py
├── network.py
├── recall.py
└── providers/
    ├── __init__.py
    ├── base.py
    ├── lolicon.py
    ├── anosu.py
    └── mirlkoi.py
```

不要继续拆成二三十个文件。

职责：

### `__init__.py`

- metadata；
- config；
- require；
- 导入 user/admin handlers。

### `config.py`

- Pydantic config；
- field bounds；
- Provider URL 校验；
- 安全默认值。

### `models.py`

- `ImageQuery`
- `ImageResult`
- `ProviderCapabilities`
- error classes

### `parser.py`

- raw command args → ImageQuery；
- 正则解析；
- 成人模式参数拒绝。

### `commands.py`

- 用户命令；
- group/private enable check；
- 调 service；
- user-facing error。

### `admin.py`

- 群管理；
- 权限；
- status；
- DB override。

### `storage.py`

- Group.config namespace；
- 可选 common runtime settings；
- 不直接操纵无关表。

### `service.py`

- provider select；
- fallback；
- safe filter；
- download；
- send；
- cooldown；
- metadata。

### `network.py`

- 共享 HTTP client；
- image download。

### `recall.py`

- background recall task management。

---

# 28. Pydantic 配置约束

不要相信 YAML。

例如：

```text
setu_default_count: 1..5
setu_max_count: 1..5
setu_recall_seconds: 5..600
setu_cooldown_seconds: 0..3600
setu_send_interval_seconds: 0..10
setu_request_timeout: 1..60
setu_request_retries: 0..5
setu_download_concurrency: 1..5
setu_image_max_bytes: 合理范围
```

如果：

```text
default_count > max_count
```

应在 config validation 后安全修正或报清晰配置错误。

Provider URL 必须 HTTP/HTTPS。

---

# 29. config.example.yml

最终完整加入该章节。

安全默认值必须是：

```text
群聊：全部关闭
私聊：可配置（建议 true）
自动撤回：开启
默认请求：3
硬上限：5
AI过滤：开启
成人内容：完全不支持
```

不要在示例里写真实群号。

---

# 30. BUILTIN_PLUGINS.md

补充：

- 插件用途；
- 默认所有群关闭；
- 私聊设置；
- 用户命令；
- 参数；
- 管理员命令；
- Provider；
- auto fallback；
- 自动撤回；
- 每群独立设置；
- safe-only；
- MirlKoi 可能因接口变化默认关闭；
- 图片版权属于原作者。

不要重写整个文件。

---

# 31. 用户帮助

`PluginMetadata.usage` 不要塞成巨长文档。

建议简版：

```text
/色图 [数量] [关键词]
/色图 -t 标签 [-t 标签] [数量]
/色图 --source lolicon|anosu|mirlkoi|auto
/色图 --size regular|original
/色图 --no-ai
/色图管理 状态
```

详细内容放 `BUILTIN_PLUGINS.md`。

---

# 32. 错误提示

普通用户只看到短消息。

示例：

```text
本群未开启此功能。
正在冷却中，请稍后再试。
没有找到符合条件的图片。
该图片源不支持此筛选条件。
图片源暂时不可用，请稍后再试。
当前插件仅提供全年龄内容。
```

网络 traceback / URL / response body 写日志。

日志不要输出：

- 私密代理凭据；
- token；
- 带用户名密码的 proxy URL。

---

# 33. OneBot / Adapter

目标优先：

```text
OneBot V11
OneBot V12
```

使用 UniMessage / Uninfo 能力减少分支。

不要新增 Satori dependency。

不要在新插件顶层：

```python
from nonebot.adapters.onebot.v11 import ...
```

除非某个撤回 fallback 确实只能用 OneBot API，并且代码有安全 adapter capability check。

核心用户功能应尽可能 adapter-neutral。

---

# 34. 不允许做的事

不要：

- 实现成人/R18/NSFW 图片检索或分发；
- 提供可通过一个配置开关恢复成人内容的完整路径；
- 使用 MirlKoi 未验证安全的随机池；
- 把 `r18` 从用户参数直接传给 Provider；
- 硬编码 API URL 到 matcher；
- 每个 Provider 自己重复业务发送逻辑；
- 为 fallback 返回不符合查询条件的随机图；
- 默认在所有群启用；
- 管理员命令直接修改 `config.yml`；
- 新建散落 JSON 保存群设置；
- 长时间 `sleep` 阻塞 matcher 做撤回；
- 默认下载 original 大图；
- 单次超过 5 张；
- 无限并发；
- 无限重试；
- 自动下载并永久保存所有作品；
- 引入 LLM；
- 新增 ORM / limiter / SAA 等非必要依赖；
- 修改 Pacman / htmlrender / adapter 启动链；
- 修改 `requirements.txt` / `constraints-lts.txt`，除非确实需要新依赖并先证明无法复用现有包。

---

# 35. 测试

为插件增加真实有价值的 pytest。

全部网络测试必须 mock，不依赖真实图片 API。

## 35.1 Parser

测试：

```text
/色图
/色图 3
/色图 原神
/色图 3 原神
/色图 -t 原神 -t 甘雨 2
/色图 --source lolicon --size regular 2 原神
/色图 --uid 123456
/色图 --portrait
```

以及：

```text
-r
--r18
r18
nsfw
```

全部进入 safe-only 拒绝。

测试 count > 5。

## 35.2 Lolicon

mock：

- POST/GET 参数强制 `r18=0`；
- count；
- tag；
- keyword；
- uid；
- size；
- excludeAI；
- response model；
- empty data；
- `error`；
- malformed response；
- 返回 `r18=true` 被 filter。

## 35.3 Anosu

mock：

- 强制 `r18=0`；
- keyword；
- `|` 多关键词；
- num；
- size；
- proxy；
- empty response；
- malformed JSON。

## 35.4 MirlKoi

至少测试：

- direct image response；
- redirect；
- JSON response（如果当前 API 支持）；
- endpoint disabled；
- safe endpoint 未验证时 provider 不进入 auto pool；
- API 改版/字段缺失不会导致整个插件 import 失败。

## 35.5 Provider auto

验证：

```text
Lolicon down + query=random → Anosu
Lolicon down + UID query → 不允许 fallback 到不支持 UID 的 Provider
指定 --source lolicon → 不自动换源
unhealthy provider → 暂时跳过
cooldown 到期 → 恢复探测
```

## 35.6 Group storage

验证：

- 默认群关闭；
- `setu_enabled_groups` 初始白名单；
- admin 开启；
- 重启/重新读取仍开启；
- auto recall override；
- recall seconds override；
- count override；
- provider override；
- reset 后恢复全局默认；
- 不破坏 `Group.config` 其他 key。

## 35.7 Admin permission

验证：

- SUPERUSER；
- 当前群 owner；
- 当前群 admin；
- 普通成员拒绝；
- 群 admin 不可修改别的 group id；
- SUPERUSER 可以指定 group id。

## 35.8 Recall

mock receipt：

- enabled → schedule；
- disabled → 不 schedule；
- recall success；
- recall failure 不影响 handler；
- 多图独立；
- 不阻塞主 handler。

## 35.9 Cooldown

- success 后 cooldown；
- cooldown 中拒绝；
- 无结果不消耗完整 cooldown；
- 所有下载失败不消耗；
- concurrent double invocation 被抑制。

## 35.10 Download

- image content type；
- redirect；
- HTML 伪装；
- oversized；
- timeout；
- 404；
- Pillow verify failure。

---

# 36. 全项目验证

至少：

```bash
python -m compileall -q liteyuki src
python -m pip check
python -m pytest -q <liteyuki_setu相关测试>
python -m pytest -q
```

具备正式 runtime 时：

```bash
python main.py
```

确认：

- Liteyuki 正常；
- NoneBot 正常；
- htmlrender 正常；
- OneBot V11/V12 注册；
- 新插件加载；
- 无新 import traceback。

真实 API smoke 可选，但不要让 pytest 依赖公网。

如果测试真实 API：

> 只能测试全年龄请求。

---

# 37. 实际验收场景

## A：默认群

没有配置：

```text
/色图
```

回复：

```text
本群未开启此功能。
```

且没有 API 请求。

## B：管理员启用

```text
/色图管理 开启
```

随后：

```text
/色图
```

默认得到 3 张全年龄图片。

## C：搜索

```text
/色图 2 原神
```

返回最多 2 张符合条件图片。

## D：Tag

```text
/色图 -t 原神 -t 甘雨 2
```

Lolicon 正确使用 Tag 能力。

## E：指定源

```text
/色图 --source anosu 原神
```

使用 Anosu。

## F：自动 fallback

Lolicon 临时不可用：

```text
/色图 --source auto 原神
```

如果 Anosu 能等价表达 query，则 fallback。

## G：不允许错误 fallback

```text
/色图 --uid 123456
```

Lolicon 不可用，而其他 Provider 不支持 UID：

```text
没有可用图片源支持当前筛选条件。
```

不能随机回一张图。

## H：撤回

群配置：

```text
auto_recall=true
recall_seconds=60
```

图片发送成功后约 60 秒各自撤回。

## I：群独立

群 A：

```text
enabled=true
count=3
recall=true
```

群 B：

```text
enabled=false
```

互不影响。

## J：成人模式请求

```text
/色图 --r18
```

直接：

```text
当前插件仅提供全年龄内容。
```

不访问 Provider。

---

# 38. 最终交付

直接实现代码，不只写计划。

最后汇报：

1. 新增/修改文件；
2. 插件结构；
3. 用户命令语法；
4. 管理员命令；
5. 群级 DB 配置结构；
6. 三个 Provider 的 capabilities；
7. MirlKoi 当前安全 endpoint 的核验结果；
8. fallback 规则；
9. safe-only 实现点；
10. recall 机制；
11. cooldown / concurrency；
12. tests；
13. `config.example.yml` / `BUILTIN_PLUGINS.md` 更新；
14. 是否修改依赖；若有，必须说明原因；
15. 未能真实验证的环境项。

---

# 39. 参考链接

## 当前项目

- https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS

## 参考 NoneBot 插件

- `nonebot-plugin-setu-now`  
  https://github.com/kexue-z/nonebot-plugin-setu-now

- `nonebot-plugin-simple-setu`  
  https://github.com/nomdn/nonebot-plugin-simple-setu

- `clovers-setu-collection`  
  https://pypi.org/project/clovers-setu-collection/

## 图片 API

- Lolicon API  
  https://docs.api.lolicon.app/#/setu  
  https://api.lolicon.app/setu/v2

- MirlKoi / cnmiw  
  https://api.cnmiw.com/  
  https://cnmiw.com/main.html

- Anosu / Jitsu  
  https://docs.anosu.top/  
  https://docs.anosu.top/intro/params.html  
  https://image.anosu.top/pixiv/json

实现时必须重新核对 API 当前文档和真实响应；第三方 API 的字段和可用域名可能变化，不要仅根据历史示例硬编码。
