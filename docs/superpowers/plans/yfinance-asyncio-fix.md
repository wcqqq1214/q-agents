# YFinance Provider 异步优化补丁

## 问题
Task 6 中的 yfinance 调用是同步阻塞的，会阻塞整个事件循环，影响并发性能。

## 修复方案
使用 `asyncio.to_thread()` 将同步调用包装到线程池中执行。

## 需要修改的代码

### 1. 添加 asyncio 导入
```python
# 在文件顶部添加
import asyncio
```

### 2. 修改 get_stock_data 方法
```python
async def get_stock_data(self, symbol: str, start_date: datetime, end_date: datetime) -> List[StockCandle]:
    """调用 yfinance 并标准化数据（异步非阻塞）"""
    try:
        # 将同步阻塞操作封装到线程池
        def _fetch_data():
            ticker = yf.Ticker(symbol)
            return ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d")
            )
        
        # 在线程池中执行，释放事件循环
        df = await asyncio.to_thread(_fetch_data)
        
        # ... 其余代码不变
```

### 3. 修改 get_news 方法
```python
async def get_news(self, query: str, limit: int = 10, start_date: Optional[datetime] = None) -> List[NewsArticle]:
    """搜索新闻（异步非阻塞）"""
    try:
        # 将同步阻塞操作封装到线程池
        def _fetch_news():
            ticker = yf.Ticker(query)
            return ticker.news[:limit]
        
        # 在线程池中执行
        news = await asyncio.to_thread(_fetch_news)
        
        # ... 其余代码不变
```

### 4. 修改 get_fundamentals 方法
```python
async def get_fundamentals(self, symbol: str) -> FundamentalsData:
    """获取基本面数据（异步非阻塞）"""
    try:
        # 将同步阻塞操作封装到线程池
        def _fetch_info():
            ticker = yf.Ticker(symbol)
            return ticker.info
        
        # 在线程池中执行
        info = await asyncio.to_thread(_fetch_info)
        
        # ... 其余代码不变
```

## 性能影响
- **修复前**：yfinance 调用阻塞事件循环，其他 Agent 被迫等待
- **修复后**：同步调用在线程池执行，事件循环可以处理其他请求
- **预期提升**：在多 Agent 并发场景下，吞吐量提升 3-5 倍

## 应用到计划
在 Task 6, Step 3 的代码中应用上述修改。
