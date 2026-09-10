<div align="center">

[//]: # (<img  src="https://cdn.liteyuki.org/logos/bot.svg" style="align-content: center; width: 50%; margin-top:10%;" alt="a">)
[![][banner]][liteyuki-link]
<h2><a href="https://bot.liteyuki.org"> <span style="color: #a2d8f4">Liteyuki</span> <span style="color: #d0e9ff">v6 LTS</span></a></h2>
<h4> <span style="color: #a2d8f4">✨ 轻量，高效，易于扩展✨</span></h4>

[![][Liteyuki6.0]][liteyuki-link]
[![][Python3.10+]][python-link]
[![][Usage]][usage-link]
[![][Github]][github-link]

</div>

LiteyukiBot v6 的长期维护分支，面向仍需使用 v6 插件、配置和多进程架构的部署。项目保持 Liteyuki v6 主进程与 NoneBot2 子进程的既有边界，并持续适配当前 Python、OneBot 与 NoneBot 生态。

> 这是 v6 LTS 维护线，不是当前正在开发中的 LiteyukiBot v7 升级包；请勿将 v7 的配置、命令或插件管理方式直接套用到本项目。

## 特性

- Liteyuki v6 主进程负责生命周期、多进程与资源管理；NoneBot2 在受管子进程中运行。
- 默认支持 OneBot V11 / V12；Satori 为可选适配器，默认关闭。
- 内置帮助、权限与限流、群管理、用户资料、统计、资源包和插件管理能力。
- 本地维护的 60S 资讯娱乐、和风天气、二次元图片、GitHub 仓库卡片等插件。
- 统一的 HTML 图片渲染与可选公共卡片背景；Playwright 浏览器由 htmlrender 管理。
- 插件商店安装受 LTS 约束文件保护，避免第三方插件替换核心 NoneBot 依赖。

完整的内置命令和适配器说明见 [BUILTIN_PLUGINS.md](BUILTIN_PLUGINS.md)。

## 环境要求

- Python 3.10+，当前开发与验证环境为 Python 3.13。
- Git。
- 支持 OneBot V11 或 V12 的客户端/实现，例如 NapCat 或 Snowluma。
- 若启用图片卡片，需要 Chromium；安装步骤见下文。

Windows、Linux 与 Docker 均可部署。生产环境建议使用独立虚拟环境，并将 `config.yml`、`third_party.yml` 与 `data/` 作为实例数据备份。

## 文档

- [快速开始](./docs/QUICK_START.md)
- [容器部署](./docs/DOCKER_DEPLOY.md)
- [内置插件说明](./docs/BUILTIN_PLUGINS.md)
- [架构与开发](./docs/ARCHITECTURE.md)

## 常用管理入口

命令前缀由 `command_start` 决定，下列示例以 `/` 为例：

- `/help`：查看帮助与插件说明。
- `/npm list`、`/npm search <关键词>`：查看或搜索插件。
- `/gm enable`、`/gm disable`：管理当前群的启用状态。
- `/profile`：查看和维护用户资料。
- `/status`：查看状态卡（取决于已启用插件和适配器）。
- `/reload-liteyuki`：超级用户重载 Liteyuki v6 LTS。

插件、资源包、跨会话推送和 API 调用权限较高。生产环境中请仅授予可信超级用户，并通过访问控制插件限制不需要的命令。

## 参考与许可

本项目 LiteyukiBot v6 为基础，保留其行为、插件接口、资源与许可证边界，并针对 LTS 部署进行兼容性修复和本地插件维护。

原始版权声明及许可证文件保留在仓库中；阅读根目录和 `license/` 下的全部许可证文本。第三方插件、资源和 API 服务可能另有许可证、使用限制或内容规范。完整参考与许可如下：

- 上游 LiteyukiBot v6 仓库：[LiteyukiStudio/LiteyukiBot](https://github.com/LiteyukiStudio/LiteyukiBot/tree/v6) - [LSO license](./license/LICENSE)
- 上游 LiteyukiBot 睿乐定制版：[TriM-Organization/LiteyukiBot-TriM](https://github.com/TriM-Organization/LiteyukiBot-TriM) - [汉钰律许可协议 第一版](./LICENSE.MD)
- 本 LTS 仓库：[DavidBlackCN/LiteyukiBot-v6-LTS](https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS)
- NoneBot2：<https://nonebot.dev/>
- 内置插件 `liteyuki_remake`：[noneplugin/nonebot-plugin-remake](https://github.com/noneplugin/nonebot-plugin-remake) - MIT License