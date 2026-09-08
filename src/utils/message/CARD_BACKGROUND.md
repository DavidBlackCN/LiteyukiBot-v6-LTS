# 公共卡片背景

卡片主动调用 `await get_card_background()`，获得 `{image, mask}`，放入自己的
渲染上下文。当前 Status、帮助菜单和天气卡显式使用；模块不注册全局 hook，
管理卡片默认不使用背景。

推荐配置为 `card_background_enabled/url/timeout/mask`。按字段判断是否显式
存在于 NoneBot Driver 配置：新字段优先，否则兼容旧 `status_background_*`。
显式 false 或空 URL 会覆盖旧值。缺失字段使用模型默认值；非法值记录 warning
并回退该字段默认值。示例中的新字段填写后会覆盖同名旧字段。

内存只保留当前 URL 的最后成功图片：60 秒内复用，过期在下次请求时刷新；
失败保留同 URL 的图片，并在 10 秒内停止重试。URL 改变时清空，避免串图。
异步锁合并同进程并发请求；不同进程不共享。默认关闭，不在启动时访问网络。
请求保持 TLS 验证，HTTP/Content-Type 校验后流式读取，最多 12 MiB。

公共样式在 vanilla_resource 的 `templates/css/card_background.css`，需显式
加载。它兼容 Status 现有类名和 `.card-background-page`，沿用原 blur、
brightness、mask 乘数和玻璃卡片参数；没有修改全局 card.css。
新模板可使用 `.card-background`、`#card-background-image`、`.card-mask`、
`.card-content`，并等待 `window.applyCardBackground(background)`。
脚本有 decode/load/error 和 1 秒超时回退，不应直接以未解码图片截图。

Status 保留现有 statusBackgroundReady 链，Help 等待公共图片助手和字体后
设置 helpMenuReady。背景不能由浏览器解码时使用蓝色默认背景。
Content-Type 校验不保证实际图像可解码，最终由浏览器回退处理。
