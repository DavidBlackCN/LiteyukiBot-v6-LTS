# LiteyukiBot-v6-LTS 性能稳定性修复：Codex 执行任务书

> 目标仓库：`DavidBlackCN/LiteyukiBot-v6-LTS`  
> 工作分支：基于当前 `main` 创建独立修复分支  
> 任务性质：**性能稳定性修复 / 最小改动 / 不做架构重写**  
> 主要运行环境：Debian / Python 3.13 / NoneBot2 / OneBot V11 / `nonebot-plugin-htmlrender 0.8.x` / Playwright / Chromium  
> 典型部署：腾讯云轻量应用服务器 4C4G，与 QQ 客户端、MCSM 和少量其它服务共机运行

---

## 1. 背景与故障现象

当前 Liteyuki v6-LTS 在 4C4G 生产服务器上长期运行时，常驻内存基线较高；当多人短时间内同时调用 Bot 命令，尤其是涉及图片渲染的命令时，出现过整台服务器完全失去响应的情况：

- Bot 不再回复；
- 同机所有 Web 服务无法访问；
- SSH 无法连接；
- 腾讯云监控面板出现监控数据缺失，甚至提示“获取监控组件状态请求失败”；
- 必须从云控制台强制重启实例才能恢复。

现有代码审查后，优先怀疑的不是传统的持续性内存泄漏，而是：

1. **HTML/Markdown 图片渲染没有全局并发上限**；
2. `/status` 等缓存失效时存在**缓存击穿 / 多协程重复渲染**；
3. 部分渲染使用过高 DPR；
4. 随机背景只限制下载字节数，没有限制**解码后的像素规模**；
5. 猜成语插件在 import 阶段一次性加载数 MB JSON，并复制大型列表，抬高常驻内存基线。

本任务优先解决以上五项，不做无关大规模重构。

---

# 2. 总体目标

完成一组适合作为 v6-LTS 长期维护补丁的性能稳定性改动，使 Bot 在低内存机器上遇到多人并发调用时表现为：

> 后续图片任务排队、超时或友好失败，而不是无限叠加 Chromium/Page/位图内存，最终拖死整台主机。

要求：

- 保持现有对外 API 和插件调用方式尽可能兼容；
- 不重写 Liteyuki v6 的 ProcessManager；
- 不替换 htmlrender / Playwright；
- 不引入新的大型第三方依赖；
- 优先复用当前已有依赖；
- 所有改动都必须有测试或可复现验证；
- 避免“为了优化而重构整个仓库”。

---

# 3. 开始编码前必须先检查

Codex 首先阅读当前 `main` 的实际代码，不要根据本文件假设行号固定。

重点检查：

```text
src/utils/message/html_tool.py
src/nonebot_plugins/liteyuki_status/status.py
src/nonebot_plugins/liteyuki_status/api.py
src/utils/message/card_background.py
src/nonebot_plugins/trimo_plugin_handle/utils.py
src/nonebot_plugins/trimo_plugin_handle/
src/nonebot_plugins/liteyuki_bilibili/renderer.py
src/liteyuki_plugins/liteyukibot_plugin_nonebot/__init__.py
config.example.yml
requirements.txt
constraints-lts.txt
tests/
```

确认当前：

- `md_to_pic()` 使用 `render_markdown()`；
- `template2image()` 使用 `render_template()`；
- `template2image_element()` 直接通过 Playwright provider 获取 page；
- `/status` 使用 300 秒缓存；
- `generate_status_card_markdown()` 当前 DPR 较高；
- 背景图通过 `aiohttp` 下载并转 data URI；
- 猜成语词库在模块 import 阶段直接 `json.load()`；
- htmlrender provider 当前仍为 Playwright，且 startup 默认为 warmup。

如果当前代码已经发生变化，以**当前 main 的实际实现**为准，但保持本文目标不变。

---

# 4. P0：为所有 Liteyuki 图片渲染增加全局并发闸门

## 4.1 目标

所有通过 `src/utils/message/html_tool.py` 进入的真实浏览器渲染操作，都必须共享一个 Liteyuki 层面的并发限制。

默认：

```yaml
liteyuki_render_max_concurrency: 1
liteyuki_render_queue_timeout: 15
```

含义：

- `liteyuki_render_max_concurrency`：同时允许执行的真实渲染任务数量；
- `liteyuki_render_queue_timeout`：仅限制“等待获取渲染槽位”的时间，单位秒；
- 默认值必须对 4G 小机器安全；
- 用户可以在配置中手动改成 2 或更高，但默认保持 1。

在 `config.example.yml` 中补充说明。

---

## 4.2 必须覆盖的入口

至少覆盖：

```python
md_to_pic(...)
template2image(...)
template2image_element(...)
```

注意：

- `template2html()` 只是模板转 HTML，不需要占用渲染槽位；
- 只在**真正进入 Playwright/htmlrender 渲染的位置** acquire；
- **同一渲染调用链严禁重复 acquire**；
- `Semaphore(1)` 下绝不能出现自身嵌套导致死锁。

当前三个入口彼此基本独立，保持这种结构，不要为了抽象而强行互调。

---

## 4.3 实现要求

推荐在 `html_tool.py` 内实现一个很小的共享 guard。

可采用：

```python
asyncio.Semaphore
```

但注意事件循环生命周期：

- 不要因为模块 import 时机而创建绑定错误 event loop 的对象；
- 推荐在第一次真正渲染时惰性初始化；
- 保持 NoneBot 子进程内全局共享；
- 不跨进程共享 semaphore。

等待队列应支持 timeout，例如：

```text
等待 semaphore.acquire()
↓
超过 liteyuki_render_queue_timeout
↓
抛出明确的 RenderQueueTimeout / RenderBusy 类异常
```

超时只针对**排队时间**，不要粗暴地把整个截图过程也限制在 15 秒。

新增一个轻量、明确的异常类型，例如：

```python
class RenderQueueTimeoutError(RuntimeError):
    ...
```

命名可调整，但请保持语义清楚。

日志至少包含：

- 当前 max concurrency；
- queue timeout；
- 超时发生时的 warning；
- 不要在正常每次渲染时刷 INFO 日志。

---

## 4.4 用户体验

至少更新 `/status` 和帮助菜单等直接暴露给用户的主要入口：

遇到渲染排队超时时，不要打印 traceback 给用户，返回类似：

```text
当前图片渲染任务较多，请稍后再试。
```

内部仍应保留 warning/debug 日志。

如果其它插件已经有统一异常处理，不必逐个增加重复代码。

---

# 5. P0：修复 `/status` 缓存击穿

## 5.1 当前问题

当前状态图缓存大致为：

```text
缓存不存在 / 缓存过期 / --refresh
↓
重新采集状态
↓
重新渲染
↓
写回 cache
```

若 10 个请求在缓存失效瞬间同时进入，则可能 10 个请求都判断为“需要刷新”，随后并发执行完整渲染。

这必须改成 **single-flight**：

> 同一语言、同一轮缓存刷新只允许一个协程真正生成图片，其它请求等待结果并复用新缓存。

---

## 5.2 推荐实现

按 `lang_code` 建立 lock，例如：

```python
_status_render_locks: dict[str, asyncio.Lock]
```

逻辑必须是“双重检查”：

```text
第一次检查 cache
↓
发现需要更新
↓
进入该 lang 的 lock
↓
再次检查 cache
↓
如果前一个请求已经完成刷新，则直接复用
↓
只有仍然确实需要刷新时才生成
```

### 对 `--refresh` 的特殊要求

不能因为多个用户同时 `--refresh` 就在锁内连续刷新 N 次。

建议：

1. 请求进入时记录 `request_started_at`；
2. 当前请求若要求 refresh：
   - 如果拿到锁后发现 cache 的生成时间已经晚于 `request_started_at`，
   - 说明已经有并发请求替它刷新完成，
   - 此时直接复用即可。

这样既保留“手动刷新”的语义，又能合并同一批并发 refresh。

缓存时间建议改为：

```python
time.monotonic()
```

而不是墙钟时间；如果改动会过大，可保持原实现，但 single-flight 必须完成。

---

## 5.3 错误处理

若本轮渲染失败：

- 不要写入损坏缓存；
- 如果存在仍可用的上一张缓存，可考虑回退使用旧缓存；
- 如果没有可用缓存，则给用户友好错误；
- lock 必须正常释放。

---

# 6. P1：降低状态 Markdown 渲染 DPR，并配置化

当前状态 Markdown 渲染中存在过高 DPR。

将默认值改为：

```yaml
status_render_device_scale_factor: 2
```

要求：

- 默认从 4 降到 2；
- 配置范围建议限制为合理值，例如 `1.0 ~ 3.0`；
- 非法配置回退到默认 2；
- 不改变普通 HTML 状态卡已有视觉布局；
- 如果当前项目已有统一配置模型，优先接入现有方式；
- 不为一个参数新建复杂配置系统。

需要同步 `config.example.yml`。

---

# 7. P1：限制随机背景图的解码规模，并主动缩图

目标文件：

```text
src/utils/message/card_background.py
```

当前已有：

- 下载超时；
- Content-Type 检查；
- 最大下载字节数；
- cache；
- `_lock`；
- base64 data URI。

这些现有机制保留，不重写。

---

## 7.1 新增像素级保护

继续保留当前：

```text
最大下载体积：12 MiB
```

同时增加两层保护：

### 硬拒绝上限

建议：

```python
CARD_BACKGROUND_HARD_MAX_PIXELS = 16_777_216
```

即约 16.7MP。

如果图片尺寸超过该值：

- 不进行完整解码；
- 直接拒绝本次图片；
- 使用缓存旧图或 fallback。

### 目标缩放上限

建议：

```python
CARD_BACKGROUND_TARGET_MAX_PIXELS = 4_194_304
CARD_BACKGROUND_TARGET_MAX_DIMENSION = 2560
```

如果图片：

- 总像素超过约 4.2MP；
- 或任一边超过 2560；

则等比例缩小。

不允许放大原图。

---

## 7.2 使用 Pillow，但不要阻塞事件循环

Pillow 已经是项目依赖，不要新增图像库。

推荐：

```python
await asyncio.to_thread(...)
```

将以下同步 CPU 操作放到线程中：

- 打开图片；
- 读取尺寸；
- EXIF 方向纠正；
- 必要时缩放；
- 静态重新编码。

不要直接在 asyncio 主事件循环里解码大型图片。

---

## 7.3 动图处理

状态卡背景没有保留动画的必要。

如果返回：

- GIF；
- animated WebP；
- 其它多帧格式；

只取第一帧作为静态背景。

不要把完整动画 data URI 塞进 Chromium。

---

## 7.4 编码要求

目标是减少内存，不是追求无损归档。

要求：

- 保持视觉质量足够作为状态卡背景；
- MIME 必须与最终实际编码一致；
- JPEG 可保持 JPEG；
- PNG 有透明需求时可保留 PNG；
- 不要因为“优化”引入极高压缩等级，导致 CPU 反而暴涨；
- 如果原格式无法安全重编码，可回退到 PNG/JPEG。

处理完成后再：

```text
bytes -> base64 -> data URI
```

避免把超大原图直接传给 Chromium。

---

# 8. P1：猜成语大型 JSON 改为 Lazy Load

目标：

```text
src/nonebot_plugins/trimo_plugin_handle/utils.py
```

当前 import 阶段会直接加载：

```text
common_idioms.json
idioms.json
answers.json
```

并立即复制部分列表。

改为：

> 插件模块被 import 时不解析大型 JSON，第一次真正使用猜成语词库时才加载一次。

---

## 8.1 兼容性要求

尽量保留现有公开变量：

```python
HANDLE_COMMON_PHRASES
HANDLE_LEGAL_PHRASES
HANDLE_ANSWER_PHRASES
```

避免大范围改其它文件。

推荐方式：

```python
HANDLE_COMMON_PHRASES = []
HANDLE_LEGAL_PHRASES = []
HANDLE_ANSWER_PHRASES = {}
```

再实现：

```python
_ensure_wordbase_loaded()
```

首次调用时：

- 读取 JSON；
- 使用 `.extend()` / `.update()` 填充原容器；
- 初始化 `handle_now_common_idioms`；
- 初始化 `handle_now_all_idioms`；
- 标记 loaded。

这样其它模块已经持有的 list/dict 引用仍然有效。

---

## 8.2 并发安全

首次触发时可能有多个用户同时调用。

因此 lazy loader 必须防止重复加载。

可用：

```python
threading.Lock
```

加双重检查。

由于当前大量词库辅助函数是同步函数，不要为了 lazy load 把整套插件强行改成 async。

允许第一次调用出现少量一次性加载延迟，但不能重复解析 JSON。

---

## 8.3 必须检查所有入口

至少检查这些函数是否在访问词库前执行 ensure：

```text
wordbase_updater
remove_idiom
legal_idiom
random_idiom
get_pinyin
```

以及其它任何直接依赖词库内容的函数。

同时检查 `main.py`/其它模块是否在 import 后、首次 ensure 前直接依赖：

```python
len(HANDLE_LEGAL_PHRASES)
idiom in HANDLE_LEGAL_PHRASES
```

若存在，做最小兼容修复。

---

# 9. P2：顺手硬化 Bilibili 图片并发，但保持小改动

如果当前 `liteyuki_bilibili/renderer.py` 仍然使用：

```python
asyncio.gather(...)
```

一次并发下载头像 + 多张封面，则增加一个非常小的下载并发限制。

建议默认：

```python
BILIBILI_IMAGE_DOWNLOAD_CONCURRENCY = 2
```

或等价的私有 semaphore。

要求：

- 单张卡片最多同时下载 2 张图片；
- 不需要新增用户配置，除非现有插件已经有成熟配置模型；
- 不改变最终卡片内容；
- 真实 HTML 渲染仍由全局 render semaphore 控制；
- 不重复实现第二套“浏览器渲染 semaphore”。

这是次级优化，不应扩大任务范围。

---

# 10. 明确不做的内容

本次不要做以下事情：

- 不重写 `ProcessManager`；
- 不把 Liteyuki v6 改造成单进程架构；
- 不替换 NoneBot；
- 不替换 htmlrender；
- 不替换 Playwright；
- 不默认关闭 Chromium warmup；
- 不大改插件加载器；
- 不在本次实现完整的 builtin-plugin allowlist/denylist；
- 不删除现有功能；
- 不为了省几 MB 去大规模重构所有插件；
- 不修改与本问题无关的业务逻辑；
- 不进行纯格式化导致巨大 diff；
- 不升级一整套无关依赖。

如果发现真实 memory leak，请单独记录证据，不要顺手把任务扩大成大重构。

---

# 11. 配置兼容要求

在 `config.example.yml` 中加入并解释：

```yaml
# Liteyuki 图片渲染最大并发数。
# 4G 或更小机器建议保持 1。
liteyuki_render_max_concurrency: 1

# 等待图片渲染槽位的最长时间（秒）。
# 仅限制排队时间，不是整个截图操作的超时时间。
liteyuki_render_queue_timeout: 15

# /status Markdown 图片的设备像素比。
# 2 在清晰度与内存占用之间更均衡。
status_render_device_scale_factor: 2
```

要求：

- 缺省配置不报错；
- 老用户不改配置即可继续运行；
- 非法值必须安全回退；
- 不允许 0、负数、NaN 等值破坏 semaphore 或渲染。

建议约束：

```text
liteyuki_render_max_concurrency: 1..8
liteyuki_render_queue_timeout: 1..120
status_render_device_scale_factor: 1.0..3.0
```

不需要为了三个参数引入新的配置依赖。

---

# 12. 测试要求

如果仓库已有 pytest，补充自动化测试；如果测试框架薄弱，也至少新增针对核心逻辑的轻量测试。

---

## 12.1 全局 render semaphore

通过 monkeypatch/fake renderer 模拟多个并发任务。

测试：

### Case A：默认 concurrency=1

同时启动 5 个任务：

```text
实际同时进入 fake render 的最大数量必须 == 1
```

### Case B：concurrency=2

最大并发必须：

```text
<= 2
```

### Case C：queue timeout

第一个任务长期占用槽位，第二个任务等待超过 timeout：

- 抛出预期的 render queue 异常；
- semaphore 不泄漏；
- 后续任务仍能继续获取槽位。

### Case D：无嵌套死锁

分别测试：

```text
md_to_pic
template2image
template2image_element
```

确认每个真实渲染调用只 acquire 一次。

---

## 12.2 `/status` single-flight

构造缓存失效。

并发调用 10 次同一 `lang_code`：

```text
真正的 generate_status_card 只允许执行 1 次
```

其它 9 次复用结果。

再测试：

- 正常 fresh cache 不重新生成；
- cache 过期重新生成一次；
- 多个同时 `--refresh` 只合并成一次本轮刷新；
- 渲染失败不会写入坏缓存；
- 锁不会永久卡死。

---

## 12.3 背景图

使用本地生成的小测试图片，不依赖公网。

至少测试：

1. 小尺寸 JPEG/PNG：
   - 不放大；
   - 正常返回。
2. 大于 target、小于 hard limit：
   - 自动缩小；
   - 最终尺寸满足限制。
3. 超过 hard max pixels：
   - 拒绝；
   - 不完整解码。
4. animated GIF/WebP：
   - 最终只保留静态第一帧。
5. MIME 与最终编码一致。
6. 非图片响应仍安全 fallback。
7. 12MiB 下载上限仍有效。

---

## 12.4 猜成语 Lazy Load

测试：

### Import 阶段

仅 import：

```python
src.nonebot_plugins.trimo_plugin_handle.utils
```

时不应立即读取/解析三个大型 JSON。

可通过 monkeypatch `open/json.load` 或等价方式验证。

### 第一次使用

第一次调用：

```text
random_idiom / legal_idiom / get_pinyin
```

触发且只触发一次加载。

### 并发第一次使用

多个线程/调用同时触发 ensure：

```text
JSON 只解析一次
```

### 兼容性

加载后：

- `HANDLE_*` 内容正常；
- 原有猜成语流程正常；
- 更新/删除词条仍能写回 JSON；
- `handle_now_*` 轮换行为保持原逻辑。

---

# 13. 实机/手工验收步骤

完成自动化测试后，给出一套可直接在 Debian 生产机执行的验收步骤。

至少包括：

## 13.1 启动前

```bash
free -h
swapon --show
ps -eo pid,ppid,comm,rss,vsz,%mem,%cpu --sort=-rss | head -30
```

记录：

- Liteyuki 主进程 RSS；
- NoneBot worker RSS；
- Chromium/Playwright 相关进程 RSS；
- 全机 available memory；
- Swap 使用量。

---

## 13.2 并发压测

不要依赖真正几十个 QQ 用户。

如果仓库没有现成测试入口，可写一个仅用于开发验证的临时脚本/测试，通过 mock 并发触发渲染辅助函数。

目标：

```text
10 个并发 render request
```

默认 concurrency=1 时：

- 只能有 1 个真实渲染执行；
- 其它排队；
- 超过 queue timeout 的请求友好失败；
- Chromium Page 数不会随请求数线性同时增长；
- 整机仍能 SSH；
- Web 服务仍可访问。

临时压测脚本不要提交到仓库，除非放在明确的 `tests/` 或 `scripts/dev/` 且有价值。

---

## 13.3 生产观测

建议同时运行：

```bash
watch -n 1 'cat /proc/pressure/memory; echo; free -h; echo; swapon --show'
```

以及：

```bash
watch -n 1 'ps -eo pid,ppid,comm,rss,%mem,%cpu --sort=-rss | head -25'
```

验收关注：

- `/proc/pressure/memory` 的 `full` 不应在普通并发命令下持续高位；
- Chromium RSS 峰值应明显更可控；
- 不应再出现一批同时活跃的截图任务；
- Bot 可以变慢，但机器不能整体失联。

---

# 14. 代码质量要求

必须遵守：

- Python 3.13；
- 现有项目格式与类型风格；
- 新增异常、helper、config 名称要清晰；
- 不吞掉真正异常；
- 不写裸 `except:`；
- 新增 lock/semaphore 必须保证异常路径能释放；
- 对 CPU 密集图片处理使用 `asyncio.to_thread`；
- 不能因为限流导致永久等待；
- 不能在 semaphore 持有期间做无关的慢网络下载，除非该下载本来就是渲染不可分割的一部分；
- 浏览器渲染槽位只覆盖真正需要占用 Playwright/htmlrender 的阶段。

---

# 15. 推荐提交拆分

尽量拆成少量、清晰的提交，例如：

```text
fix(render): add global Liteyuki render concurrency guard
fix(status): coalesce concurrent status card refreshes
perf(status): reduce configurable markdown render scale
fix(background): bound decoded image size before card rendering
perf(handle): lazy-load large idiom wordbase
perf(bilibili): limit concurrent card image downloads
test(perf): cover render guard and status single-flight
```

如果实际改动较少，可合并相近提交。

不要生成大量只有格式变化的 commit。

---

# 16. 最终交付内容

Codex 完成后，最终回复必须包含：

## A. 改动摘要

按文件列出：

```text
文件
修改内容
为什么修改
```

## B. 新增配置

列出默认值与意义。

## C. 测试结果

明确给出实际运行过的命令，例如：

```bash
pytest ...
python ...
```

以及：

```text
passed / failed / skipped
```

不要只说“理论上可行”。

## D. 并发模型说明

简要解释最终状态：

```text
用户请求
→ 插件业务逻辑
→ 等待 Liteyuki render semaphore
→ 获取槽位
→ htmlrender / Playwright
→ screenshot
→ 释放槽位
```

以及 `/status`：

```text
请求
→ 检查 cache
→ per-lang single-flight lock
→ 二次检查 cache
→ 最多一个真实刷新
→ 其它请求复用
```

## E. 兼容性说明

说明：

- 是否影响旧配置；
- 是否影响 htmlrender 0.8；
- 是否影响现有插件调用 `md_to_pic/template2image/template2image_element`；
- 是否有值得我上线前特别关注的风险。

## F. 未完成项

如果某项无法安全完成：

- 不要假装完成；
- 明确说明原因；
- 给出最小后续方案。

---

# 17. 验收标准

只有满足以下条件才能认为任务完成。

- [ ] 所有 Liteyuki 核心图片渲染入口共享同一并发限制；
- [ ] 默认最大真实渲染并发为 1；
- [ ] 排队有明确 timeout，不会无限等待；
- [ ] 不存在嵌套 semaphore 死锁；
- [ ] `/status` 缓存失效时多人并发只生成一次；
- [ ] 并发 `--refresh` 可合并；
- [ ] Markdown 状态图默认 DPR 从 4 降到 2；
- [ ] 随机背景增加解码像素上限；
- [ ] 大背景会等比缩小后再送入 Chromium；
- [ ] 动态背景只取静态第一帧；
- [ ] 大图处理不阻塞 asyncio 主事件循环；
- [ ] 猜成语大型 JSON 不再在 import 阶段解析；
- [ ] lazy load 只执行一次且并发安全；
- [ ] 原猜成语增删改逻辑仍正常；
- [ ] Bilibili 图片下载并发得到轻量限制（若当前实现仍有该风险）；
- [ ] `config.example.yml` 已更新；
- [ ] 无无关依赖升级；
- [ ] 无大规模格式化 diff；
- [ ] 测试真实执行并通过；
- [ ] 给出生产机手工验收步骤。

---

# 18. 最重要的实现原则

本次修复的核心不是“让 Liteyuki 绝对不占内存”，而是：

> **给最昂贵的资源操作加背压。**

在 4C4G 机器上，当 10 个用户同时请求图片时，正确行为应是：

```text
1 个渲染
+ 若干等待
+ 超时后友好失败
```

而不是：

```text
10 个 Playwright Page
+ 10 份 DOM
+ 10 份背景位图
+ 10 次 screenshot buffer
+ 整机 OOM / swap thrashing
```

请围绕这个目标做最小、清晰、可测试、可长期维护的修复。
