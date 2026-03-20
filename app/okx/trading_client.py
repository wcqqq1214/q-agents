"""OKX交易客户端"""
import asyncio
import logging
from typing import Dict, List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .exceptions import OKXRateLimitError

logger = logging.getLogger(__name__)


class OKXTradingClient:
    """OKX交易客户端，封装OKX SDK调用

    Note: API credentials are stored in memory as private attributes.
    This is necessary for SDK operations but should be handled with care.
    """

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

        Raises:
            ValueError: 如果任何凭证为空字符串
        """
        # 输入验证
        if not api_key:
            raise ValueError("api_key cannot be empty")
        if not secret_key:
            raise ValueError("secret_key cannot be empty")
        if not passphrase:
            raise ValueError("passphrase cannot be empty")

        # 使用私有属性存储凭证
        self._api_key = api_key
        self._secret_key = secret_key
        self._passphrase = passphrase
        self.is_demo = is_demo

        # 初始化SDK客户端
        self._init_sdk_clients()

        logger.info(f"[OKX-{'DEMO' if is_demo else 'LIVE'}] Client initialized")

    def _init_sdk_clients(self):
        """初始化OKX SDK客户端"""
        from okx.Account import AccountAPI
        from okx.Trade import TradeAPI
        from okx.MarketData import MarketAPI

        # flag: "1" = demo, "0" = live
        flag = "1" if self.is_demo else "0"

        # 初始化账户API
        self.account_api = AccountAPI(
            api_key=self._api_key,
            api_secret_key=self._secret_key,
            passphrase=self._passphrase,
            flag=flag,
            debug=False
        )

        # 初始化交易API
        self.trade_api = TradeAPI(
            api_key=self._api_key,
            api_secret_key=self._secret_key,
            passphrase=self._passphrase,
            flag=flag,
            debug=False
        )

        # 初始化市场数据API
        self.market_api = MarketAPI(
            api_key=self._api_key,
            api_secret_key=self._secret_key,
            passphrase=self._passphrase,
            flag=flag,
            debug=False
        )

        logger.info(
            f"[OKX-{'DEMO' if self.is_demo else 'LIVE'}] "
            f"SDK clients initialized (Account, Trade, Market)"
        )

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

    async def get_account_balance(self, currency: Optional[str] = None) -> List[Dict]:
        """获取账户余额（异步）

        Args:
            currency: 币种，如BTC、USDT，不传则返回所有币种

        Returns:
            余额信息列表，格式：
            [
                {
                    "currency": "USDT",
                    "available": "1000.5",
                    "frozen": "100.0",
                    "total": "1100.5"
                }
            ]

        Raises:
            OKXAuthError: 认证错误
            OKXError: 其他API错误
        """
        return await asyncio.to_thread(self._get_account_balance_sync, currency)

    def _get_account_balance_sync(self, currency: Optional[str] = None) -> List[Dict]:
        """获取账户余额的同步实现"""
        # 构建请求参数
        params = {}
        if currency:
            params['ccy'] = currency

        # 调用SDK
        response = self.account_api.get_account_balance(**params)

        # 验证响应
        self._validate_response(response)

        # 解析余额数据
        balances = []
        data = response.get('data', [])
        if data and len(data) > 0:
            details = data[0].get('details', [])
            for detail in details:
                balances.append({
                    'currency': detail.get('ccy'),
                    'available': detail.get('availBal'),
                    'frozen': detail.get('frozenBal'),
                    'total': detail.get('bal')
                })

        return balances

    def _validate_response(self, response: Dict) -> None:
        """验证OKX API响应

        Args:
            response: OKX API响应

        Raises:
            OKXAuthError: 认证错误
            OKXRateLimitError: 频率限制错误
            OKXError: 其他错误
        """
        from .exceptions import (
            OKXError, OKXAuthError, OKXRateLimitError,
            OKXInsufficientBalanceError, OKXOrderError
        )

        code = response.get('code')
        if code != '0':
            msg = response.get('msg', 'Unknown error')

            # 认证错误
            if code in ['50113', '50101', '50102', '50103']:
                raise OKXAuthError(msg, code=code)
            # 频率限制
            elif code == '50011':
                raise OKXRateLimitError(msg, code=code)
            # 业务错误
            elif code and code.startswith('51'):
                if '余额不足' in msg or 'Insufficient' in msg.lower():
                    raise OKXInsufficientBalanceError(msg, code=code)
                else:
                    raise OKXOrderError(msg, code=code)
            else:
                raise OKXError(msg, code=code)

