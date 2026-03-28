"""OKX API错误类型定义"""

from typing import Optional


class OKXError(Exception):
    """OKX API错误基类"""

    def __init__(self, message: str, code: Optional[str] = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class OKXAuthError(OKXError):
    """认证错误（API密钥无效、签名错误等）"""

    pass


class OKXRateLimitError(OKXError):
    """频率限制错误"""

    pass


class OKXInsufficientBalanceError(OKXError):
    """余额不足错误"""

    pass


class OKXOrderError(OKXError):
    """订单相关错误（下单失败、撤单失败等）"""

    pass


class OKXConfigError(OKXError):
    """配置错误（缺少API密钥等）"""

    pass
