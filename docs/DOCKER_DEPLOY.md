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