## 架构与插件

```text
main.py
  └─ LiteyukiBot v6 主进程
      ├─ 生命周期、进程、资源包与本地主进程插件
      └─ NoneBot2 受管子进程
          ├─ OneBot V11 / V12（Satori 可选）
          ├─ htmlrender + Alconna
          ├─ src/liteyuki_main 核心插件
          └─ src/nonebot_plugins 内置与本地插件
```

- `src/nonebot_plugins/`：本地维护的 NoneBot 插件。
- `src/liteyuki_plugins/`：运行在 Liteyuki 主进程中的插件。
- `src/resources/`：内置资源包和图片卡模板。
- `plugins/`：非安全模式下允许加载的本地扩展目录。
- `data/`：运行期数据库、插件状态和缓存，不应提交。

## 开发与验证

本仓库不是普通 nb-cli 项目：运行时依赖以 `requirements.txt` 为准，`pyproject.toml` 仅用于 Liteyuki 框架的构建元数据。修改后建议优先运行最小相关测试，再进行基础检查：

```bash
python -m compileall -q liteyuki src
python -m pip check
python -m pytest -q <相关测试文件>
```

涉及启动顺序、适配器或渲染器的修改，应额外验证 NoneBot 初始化、OneBot V11/V12 注册，以及 htmlrender 的 Playwright 提供器加载。未接入真实客户端时，不应把启动 smoke test 表述为真实 Bot 连接测试。

第三方插件通过 `liteyuki_pacman` 安装时会应用 `constraints-lts.txt`，防止替换受保护的核心依赖。安装、更新第三方插件后请重启 Bot，不要在已有进程中强制热加载新分发包。