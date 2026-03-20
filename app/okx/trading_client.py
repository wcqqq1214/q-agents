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

    async def get_positions(self, inst_type: Optional[str] = None) -> List[Dict]:
        """获取持仓信息（异步）

        Args:
            inst_type: 产品类型，如SPOT/MARGIN/SWAP/FUTURES/OPTION
                      不传则返回所有类型

        Returns:
            持仓列表，格式：
            [
                {
                    "inst_id": "BTC-USDT-SWAP",
                    "position_side": "long",
                    "position": "10",
                    "available_position": "10",
                    "average_price": "50000",
                    "unrealized_pnl": "500",
                    "leverage": "10"
                }
            ]

        Raises:
            OKXAuthError: 认证错误
            OKXError: 其他API错误
        """
        return await asyncio.to_thread(self._get_positions_sync, inst_type)

    def _get_positions_sync(self, inst_type: Optional[str] = None) -> List[Dict]:
        """获取持仓的同步实现"""
        # 构建请求参数
        params = {}
        if inst_type:
            params['instType'] = inst_type

        # 调用SDK
        response = self.account_api.get_positions(**params)

        # 验证响应
        self._validate_response(response)

        # 解析持仓数据
        positions = []
        for pos in response.get('data', []):
            positions.append({
                'inst_id': pos.get('instId'),
                'position_side': pos.get('posSide'),
                'position': pos.get('pos'),
                'available_position': pos.get('availPos'),
                'average_price': pos.get('avgPx'),
                'unrealized_pnl': pos.get('upl'),
                'leverage': pos.get('lever')
            })

        return positions

    async def place_order(
        self,
        inst_id: str,
        side: str,
        order_type: str,
        size: str,
        price: Optional[str] = None,
        client_order_id: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """下单（异步）

        Args:
            inst_id: 产品ID，如 BTC-USDT
            side: 订单方向 buy/sell
            order_type: 订单类型 market/limit/post_only/fok/ioc
            size: 委托数量
            price: 委托价格（限价单必填）
            client_order_id: 客户端订单ID（可选）
            **kwargs: 其他参数（如reduce_only等）

        Returns:
            订单信息，格式：
            {
                "order_id": "123456",
                "client_order_id": "my-order-1",
                "status_code": "0"
            }

        Raises:
            OKXAuthError: 认证错误
            OKXInsufficientBalanceError: 余额不足
            OKXOrderError: 订单错误
            OKXError: 其他错误
        """
        return await asyncio.to_thread(
            self._place_order_sync, inst_id, side, order_type, size, price, client_order_id, **kwargs
        )

    def _place_order_sync(
        self,
        inst_id: str,
        side: str,
        order_type: str,
        size: str,
        price: Optional[str] = None,
        client_order_id: Optional[str] = None,
        **kwargs
    ) -> Dict:
        """下单的同步实现"""
        # 构建请求参数
        params = {
            'instId': inst_id,
            'tdMode': 'cash',  # 现货交易模式
            'side': side,
            'ordType': order_type,
            'sz': size
        }

        # 限价单需要价格
        if price:
            params['px'] = price

        # 客户端订单ID
        if client_order_id:
            params['clOrdId'] = client_order_id

        # 其他参数
        params.update(kwargs)

        # 调用SDK
        response = self.trade_api.place_order(**params)

        # 验证响应
        self._validate_response(response)

        # 解析订单数据
        data = response.get('data', [{}])[0]
        return {
            'order_id': data.get('ordId'),
            'client_order_id': data.get('clOrdId', ''),
            'status_code': data.get('sCode', '0')
        }

    async def cancel_order(
        self,
        inst_id: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict:
        """撤单（异步）

        Args:
            inst_id: 产品ID
            order_id: 订单ID（与client_order_id二选一）
            client_order_id: 客户端订单ID（与order_id二选一）

        Returns:
            撤单结果，格式：
            {
                "order_id": "123456",
                "client_order_id": "my-order-1",
                "status_code": "0"
            }

        Raises:
            ValueError: 如果order_id和client_order_id都未提供
            OKXOrderError: 订单不存在或撤单失败
            OKXError: 其他错误
        """
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided")

        return await asyncio.to_thread(
            self._cancel_order_sync, inst_id, order_id, client_order_id
        )

    def _cancel_order_sync(
        self,
        inst_id: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict:
        """撤单的同步实现"""
        # 构建请求参数
        params = {'instId': inst_id}

        if order_id:
            params['ordId'] = order_id
        if client_order_id:
            params['clOrdId'] = client_order_id

        # 调用SDK
        response = self.trade_api.cancel_order(**params)

        # 验证响应
        self._validate_response(response)

        # 解析结果
        data = response.get('data', [{}])[0]
        return {
            'order_id': data.get('ordId'),
            'client_order_id': data.get('clOrdId', ''),
            'status_code': data.get('sCode', '0')
        }

    async def get_order_details(
        self,
        inst_id: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict:
        """查询订单详情（异步）

        Args:
            inst_id: 产品ID
            order_id: 订单ID（与client_order_id二选一）
            client_order_id: 客户端订单ID（与order_id二选一）

        Returns:
            订单详情，格式：
            {
                "order_id": "123456",
                "client_order_id": "my-order-1",
                "inst_id": "BTC-USDT",
                "status": "filled",
                "side": "buy",
                "order_type": "limit",
                "size": "0.01",
                "filled_size": "0.01",
                "price": "50000",
                "average_price": "50000",
                "timestamp": "1710000000000"
            }

        Raises:
            ValueError: 如果order_id和client_order_id都未提供
            OKXOrderError: 订单不存在
            OKXError: 其他错误
        """
        if not order_id and not client_order_id:
            raise ValueError("Either order_id or client_order_id must be provided")

        return await asyncio.to_thread(
            self._get_order_details_sync, inst_id, order_id, client_order_id
        )

    def _get_order_details_sync(
        self,
        inst_id: str,
        order_id: Optional[str] = None,
        client_order_id: Optional[str] = None
    ) -> Dict:
        """查询订单详情的同步实现"""
        # 构建请求参数
        params = {'instId': inst_id}

        if order_id:
            params['ordId'] = order_id
        if client_order_id:
            params['clOrdId'] = client_order_id

        # 调用SDK
        response = self.trade_api.get_order(**params)

        # 验证响应
        self._validate_response(response)

        # 解析订单数据
        data = response.get('data', [{}])[0]
        return {
            'order_id': data.get('ordId'),
            'client_order_id': data.get('clOrdId', ''),
            'inst_id': data.get('instId'),
            'status': data.get('state'),
            'side': data.get('side'),
            'order_type': data.get('ordType'),
            'size': data.get('sz'),
            'filled_size': data.get('fillSz'),
            'price': data.get('px') or None,
            'average_price': data.get('avgPx') or None,
            'timestamp': data.get('cTime')
        }

    async def get_order_history(
        self,
        inst_type: str = 'SPOT',
        inst_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """查询历史订单（异步）

        Args:
            inst_type: 产品类型，如SPOT/MARGIN/SWAP/FUTURES
            inst_id: 产品ID（可选，不传则返回该类型所有产品）
            limit: 返回数量限制，默认100

        Returns:
            历史订单列表，格式同get_order_details

        Raises:
            OKXError: API错误
        """
        return await asyncio.to_thread(
            self._get_order_history_sync, inst_type, inst_id, limit
        )

    def _get_order_history_sync(
        self,
        inst_type: str = 'SPOT',
        inst_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """查询历史订单的同步实现"""
        # 构建请求参数
        params = {
            'instType': inst_type,
            'limit': str(limit)
        }

        if inst_id:
            params['instId'] = inst_id

        # 调用SDK
        response = self.trade_api.get_orders_history(**params)

        # 验证响应
        self._validate_response(response)

        # 解析订单列表
        orders = []
        for order in response.get('data', []):
            orders.append({
                'order_id': order.get('ordId'),
                'client_order_id': order.get('clOrdId', ''),
                'inst_id': order.get('instId'),
                'status': order.get('state'),
                'side': order.get('side'),
                'order_type': order.get('ordType'),
                'size': order.get('sz'),
                'filled_size': order.get('fillSz'),
                'price': order.get('px') or None,
                'average_price': order.get('avgPx') or None,
                'timestamp': order.get('cTime')
            })

        return orders

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
            # 余额不足错误（特定错误码或消息包含关键词）
            elif code == '51008' or '余额不足' in msg or 'insufficient' in msg.lower():
                raise OKXInsufficientBalanceError(msg, code=code)
            # 其他业务错误
            elif code and code.startswith('51'):
                raise OKXOrderError(msg, code=code)
            else:
                raise OKXError(msg, code=code)

