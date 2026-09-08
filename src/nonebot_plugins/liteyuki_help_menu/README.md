# Liteyuki 图片帮助中心

支持 `帮助`、`菜单`、`help`，也支持当前 `command_start` 配置的前缀。
例如 `/help`、`帮助 全部`、`帮助 系统插件 2`、`帮助 liteyuki_group_manager`、
`帮助 搜索 tianqi`。详情也支持尾部页码。没有匹配时输出空结果图片。

新 matcher 优先级为 0，处理后阻止旧 Pacman help 重复回复；总开关关闭
并重启后不注册 matcher，旧帮助继续工作。短错误提示为纯文字。

数据来自 `nonebot.get_loaded_plugins()`，不扫描未加载插件，不导入插件
源码来获取元数据，不请求 Registry。运行在 Liteyuki 独立进程而未注册为
NoneBot 插件的组件不在此列表中。

来源按顺序识别：`src.nonebot_plugins.*` 为 LTS 内置；其他带
`extra.liteyuki` 或 Liteyuki 路径的插件为 Liteyuki 原生；其余第三方 NoneBot。
缺少元数据时显示模块名和未知字段，版本仅采用 `extra.version`，不会猜测。
旧插件的名称/usage 原样作为文字呈现，Markdown 标记不会被当成 HTML 执行。

分类统一为系统、基础、内置、第三方。优先读取 extra.help_category，
其次 lts_builtin=True；然后识别 system/library/internal 和基础依赖模块，
旧 Liteyuki 路径或 liteyuki=True 归基础，其余归第三方。library 默认隐藏。

可选元数据示例：

```python
extra={
    "help_category": "builtin",
    "help_commands": [{"command": "/foo", "description": "功能说明"}],
    "hidden": False,
    "version": "1.0.0",
}
```

library、extra.hidden 和配置中的 module/name 自动隐藏。支持隐藏第三方。
搜索名称、模块名、description 和 usage，按精确、子串、拼音、近似排序。
拼音复用现有 pypinyin，缺失时保留普通搜索；名称支持全拼与首字母。

可选 `help_menu_filter_access` 只查询已加载 Access Control 的 is_allowed，
不强制加载它、不消耗限流额度。缺少该插件时正常展示。Pacman 已加载时
尽力读取会话启停状态；这不是业务权限校验，也不代表一定能执行命令。

模板放在独立资源包 `src/resources/liteyuki_help_menu`，沿用资源加载器
对新增包的排序加载和外部覆盖规则。复用 Base UI 的 card.css、fonts.css、
card.js；JSON 数据以 textContent 写入 DOM，等待字体与布局完成后截取 body。
html_tool → 官方 htmlrender → Playwright → UniMessage 图片发送，通过公共 get_card_background() 显式启用背景；与 Status 共享缓存和配置。

每页最多 12 个插件，长 usage 每 1800 字分页，结构化命令每 8 条分页。
为避免异常元数据生成无界图片，文本字段最多 12000 字、结构化命令最多
100 条。图片缓存最多 8 张（单张最多 4 MiB）、60 秒；可见数据或状态变化
重新生成，资源文件修改最多等 60 秒失效。并发渲染串行化以减少浏览器压力。

当前没有会话翻页状态、按钮、实时独立进程插件枚举或业务权限推断。
