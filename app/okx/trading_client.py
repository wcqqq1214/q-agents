"""OKX交易客户端"""
import logging
from typing import Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .exceptions import OKXRateLimitError

logger = logging.getLogger(__name__)


class OKXTradingClient:
    """OKX交易客户端，封装OKX SDK调用"""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        is_demo: bool = False
    ):
        """初始化客户端

        Args:
            api_key: API密钥
            secret_key: Secret密钥
            passphrase: API密码
            is_demo: 是否为模拟盘
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.is_demo = is_demo

        # 初始化SDK客户端
        self._init_sdk_clients()

        logger.info(f"[OKX-{'DEMO' if is_demo else 'LIVE'}] Client initialized")

    def _init_sdk_clients(self):
        """初始化OKX SDK客户端

        注意：此方法需要根据实际SDK API调整
        参考sdk_poc.py中验证的初始化方式
        """
        # TODO: 根据SDK POC结果实现
        # 示例：
        # import okx
        # self.account_api = okx.Account(...)
        # self.trade_api = okx.Trade(...)
        # self.market_api = okx.MarketData(...)
        pass

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(OKXRateLimitError),
        reraise=True
    )
    async def _call_with_retry(self, func, *args, **kwargs):
        """带重试的API调用

        Args:
            func: 要调用的函数
            *args, **kwargs: 函数参数

        Returns:
            函数返回值
        """
        try:
            return await func(*args, **kwargs)
        except OKXRateLimitError as e:
            logger.warning(
                f"[OKX-{'DEMO' if self.is_demo else 'LIVE'}] "
                f"Rate limit hit, retrying... {e}"
            )
            raise
