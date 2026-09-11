"""Expected Bilibili service failures with safe user-facing boundaries."""


class BilibiliError(RuntimeError):
    """Base class for recoverable Bilibili feature errors."""

    user_message = "Bilibili 服务暂时不可用，请稍后重试。"


class BilibiliNetworkError(BilibiliError):
    user_message = "Bilibili 网络请求失败，请稍后重试。"


class BilibiliAPIError(BilibiliError):
    user_message = "Bilibili API 返回异常，请稍后重试。"


class BilibiliCredentialError(BilibiliError):
    user_message = "Bilibili 登录凭据已失效，请联系管理员重新登录。"


class BilibiliCookieFormatError(BilibiliCredentialError):
    user_message = "Bilibili Cookie 配置格式无效，请联系管理员检查配置。"


class BilibiliQRCodeExpiredError(BilibiliCredentialError):
    user_message = "Bilibili 登录二维码已失效，请重新发送 /B站登录。"


class BilibiliQRCodeTimeoutError(BilibiliCredentialError):
    user_message = "等待 Bilibili 扫码确认超时，请重新发送 /B站登录。"


class BilibiliRateLimitError(BilibiliAPIError):
    user_message = "Bilibili 当前请求受限，请稍后重试。"


class BilibiliRenderError(BilibiliError):
    user_message = "Bilibili 卡片渲染失败。"
