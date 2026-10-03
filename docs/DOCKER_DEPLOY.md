## 容器部署

仓库提供 `Dockerfile` 作为基础镜像方案。构建前请根据自身网络、Python 版本、OneBot 连接方式和 Chromium 运行要求审阅镜像内容；运行时通过挂载本地 `config.yml`、`third_party.yml` 与 `data/` 保留实例配置和状态。

```bash
docker build -t liteyukibot-v6-lts .
docker run --rm -it \
  -v "$(pwd)/config.yml:/liteyukibot/config.yml" \
  -v "$(pwd)/third_party.yml:/liteyukibot/third_party.yml" \
  -v "$(pwd)/data:/liteyukibot/data" \
  liteyukibot-v6-lts
```

Windows PowerShell 请将 `$(pwd)` 改为 `${PWD}` 或绝对路径。端口暴露与网络模式需要按所选 OneBot 连接方案设置。

## X 订阅插件的部署条件

`liteyuki_twitter` 默认关闭。需在 `config.yml` 配置可访问的 Nitter 实例、允许群及关注列表后开启；插件不会自动部署实例，公共实例与已归档的 Nitter 上游可用性需要单独验证。容器里的 `localhost` 指容器自身，宿主机代理或 Nitter 请使用实际可达的容器网络地址。`twitter_proxy` 同时用于内容和翻译请求。

```yaml
twitter_enabled: true
twitter_nitter_instances: ["https://nitter.example.org"]
twitter_group_mode: "whitelist"
twitter_group_ids: ["<群号>"]
twitter_follows: [example_account]
twitter_group_follows:
  "<群号>":
    - account: another_account
      media_only: true
      replies: false
      reposts: false
```

将示例域名、群号和账号替换为自己的值。按群列表替代默认关注，群命令的增删覆盖保存在 `data/liteyuki/twitter.ldb`，总开关和翻译选项保存在现有群数据库，因此必须持久挂载整个 `data/`。

`twitter_group_mode` 支持 `whitelist`（默认，仅 `twitter_group_ids` 内群可用）和 `blacklist`（排除名单内群）。白名单为空时群功能关闭；黑名单为空时允许所有群。黑名单播报从所选 Bot 的实际群列表获取目标，获取失败时跳过本轮。该范围同时限制群管理、手动查询、自动链接解析和播报，私聊手动查询不受群名单影响。

启用后，在允许群直接发送 `https://x.com/example/status/123456789` 即可自动解析为图片，无需 @Bot。使用 `推特管理 链接 关/开` 按群控制；此功能使用配置的 Nitter 实例，不直接抓取 X 网页。

翻译可选择兼容模型服务或 LibreTranslate；密钥仅写入部署本地配置，不在群内设置或显示。自动翻译默认关闭，配置完成后用 `推特管理 翻译 播报 开` 或 `推特管理 翻译 链接 开` 按群启用。首版仅使用视频封面，不需要 ffmpeg；图片卡片使用现有 htmlrender / Playwright 环境，不新增依赖。
