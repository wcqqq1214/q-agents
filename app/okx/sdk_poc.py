"""OKX SDK概念验证代码"""
import os
from dotenv import load_dotenv

load_dotenv()

# 测试导入python-okx包
try:
    import okx
    print(f"✓ python-okx version: {okx.__version__}")
except ImportError as e:
    print(f"✗ Failed to import python-okx: {e}")
    exit(1)

# 测试初始化客户端
api_key = os.getenv("OKX_DEMO_API_KEY")
secret_key = os.getenv("OKX_DEMO_SECRET_KEY")
passphrase = os.getenv("OKX_DEMO_PASSPHRASE")

print(f"\nTesting with demo credentials:")
print(f"API Key: {api_key[:10]}..." if api_key else "API Key: Not found")

# 根据实际SDK API调整以下代码
# flag="1" 表示模拟盘
try:
    from okx.Account import AccountAPI
    from okx.MarketData import MarketAPI
    from okx.Trade import TradeAPI

    # 初始化客户端 (flag="1" for demo trading)
    account_client = AccountAPI(
        api_key=api_key,
        api_secret_key=secret_key,
        passphrase=passphrase,
        flag="1",  # 1=demo, 0=live
        debug=False
    )

    market_client = MarketAPI(
        api_key=api_key,
        api_secret_key=secret_key,
        passphrase=passphrase,
        flag="1",
        debug=False
    )

    trade_client = TradeAPI(
        api_key=api_key,
        api_secret_key=secret_key,
        passphrase=passphrase,
        flag="1",
        debug=False
    )

    print("✓ SDK clients initialized successfully")

    # 测试账户API - 获取余额
    print("\n--- Testing Account API ---")
    balance_result = account_client.get_account_balance()
    print(f"Balance API response code: {balance_result.get('code', 'N/A')}")
    print(f"Balance API response msg: {balance_result.get('msg', 'N/A')}")
    if balance_result.get('code') == '0':
        print("✓ Account API working")
    else:
        print(f"✗ Account API error: {balance_result}")

    # 测试行情API - 获取ticker
    print("\n--- Testing Market Data API ---")
    ticker_result = market_client.get_ticker(instId="BTC-USDT")
    print(f"Ticker API response code: {ticker_result.get('code', 'N/A')}")
    print(f"Ticker API response msg: {ticker_result.get('msg', 'N/A')}")
    if ticker_result.get('code') == '0' and ticker_result.get('data'):
        ticker_data = ticker_result['data'][0]
        print(f"✓ Market Data API working - BTC-USDT last price: {ticker_data.get('last', 'N/A')}")
    else:
        print(f"✗ Market Data API error: {ticker_result}")

    # 测试交易API - 查询订单历史
    print("\n--- Testing Trade API ---")
    orders_result = trade_client.get_orders_history(instType="SPOT")
    print(f"Orders API response code: {orders_result.get('code', 'N/A')}")
    print(f"Orders API response msg: {orders_result.get('msg', 'N/A')}")
    if orders_result.get('code') == '0':
        print(f"✓ Trade API working - Found {len(orders_result.get('data', []))} historical orders")
    else:
        print(f"✗ Trade API error: {orders_result}")

except Exception as e:
    print(f"✗ SDK initialization or API call failed: {e}")
    import traceback
    traceback.print_exc()

print("\n=== SDK Verification Complete ===")
print("Next: Update trading_client.py with verified SDK API")
