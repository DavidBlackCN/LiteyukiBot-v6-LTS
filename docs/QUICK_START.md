## 快速开始

```bash
git clone https://github.com/DavidBlackCN/LiteyukiBot-v6-LTS.git
cd LiteyukiBot-v6-LTS

python -m venv venv
# Linux/macOS
. venv/bin/activate
# Windows PowerShell
# .\venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m playwright install chromium
python main.py
```

首次启动时，程序会在缺失时从 `config.example.yml` 和 `third_party.example.yml` 分别创建 `config.yml`、`third_party.yml`。也可以先手动复制模板再启动：

```bash
# Linux/macOS
cp config.example.yml config.yml
cp third_party.example.yml third_party.yml

# Windows PowerShell
# Copy-Item config.example.yml config.yml
# Copy-Item third_party.example.yml third_party.yml
```

随后按你的 OneBot 实现填写反向 WebSocket、HTTP 或其他连接配置。应用启动入口是 `main.py`；Bot 是否已实际上线，应以 OneBot 客户端连接日志为准。

## 配置

`config.example.yml` 是本项目维护的公开模板，普通功能配置应放在 `config.yml`；`third_party.example.yml` 对应 `requirements.txt` 中的第三方 NoneBot 插件配置。两个文件会在启动时合并，重复键以 `config.yml` 为准。

开始部署时，至少检查以下项目：

- `superusers`：填入可信管理员 QQ 号；不要开放给普通用户。
- `command_start`、`nickname`：设置命令前缀和 Bot 昵称。
- OneBot 连接参数：按所使用客户端的反向连接方式配置。
- `safe_mode`：排障或限制动态插件加载时可启用。
- `weather_key`、`githubcard_token` 等密钥：仅写入本地配置，禁止提交。
- `card_background_*`：需要统一图片卡背景时再启用；默认关闭。

涉及群号、Token、Cookie、代理地址和账号密码的配置均属于部署私密数据。仓库已忽略 `config.yml`、`third_party.yml` 和 `data/`，但仍应自行做好访问控制与备份。