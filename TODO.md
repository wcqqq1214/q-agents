# Redis 集成 TODO 清单

本文档记录 Redis 集成分支合并后需要改进的事项。

## 状态说明

- 🔴 高优先级
- 🟡 中等优先级  
- 🟢 低优先级
- ✅ 已完成

---

## 🟡 中等优先级

### 1. OKX 线程池变通方案重构

**文件**: `app/okx/trading_client.py:124-135`

**问题**: 
- `_run_blocking` 方法检查 `PYTEST_CURRENT_TEST` 环境变量来避免测试中使用 `asyncio.to_thread()`
- 生产代码耦合了测试环境检测，架构不够理想

**建议方案**:
- 使用 pytest fixture 来 mock OKX 客户端
- 或者在 `conftest.py` 中正确配置事件循环策略
- 将测试环境检测逻辑移到测试层而非生产代码

**影响**: 低 - 功能正确，但代码耦合度高

**相关文件**:
- `app/okx/trading_client.py`
- `tests/test_config_manager_okx.py`

---

### 2. DataFrame 序列化粒度优化

**文件**: `app/services/hot_cache.py:82-86`

**问题**:
- 当前将整个 DataFrame（最多 2880 条记录）序列化到 Redis
- 对于 1 分钟数据，这是每个键约 48 小时的数据
- 随着交易对和时间间隔增加，Redis 内存和网络开销会显著增长

**建议方案**:
1. **分块存储**: 按时间范围分桶（例如每天一个键）
2. **增量追加**: 只追加新数据，而非重写整个 DataFrame
3. **使用 Redis Streams**: 对于仅追加的工作负载更高效
4. **压缩优化**: 评估不同压缩算法的效果

**触发条件**: 当扩展到 5+ 个交易对或添加更多时间间隔时

**影响**: 当前规模（BTCUSDT、ETHUSDT）影响低

**相关文件**:
- `app/services/hot_cache.py`
- `app/services/realtime_agent.py`

---

### 3. update_daily_ohlc 任务真实验证

**文件**: `app/tasks/update_ohlc.py`

**问题**:
- ARQ worker 能成功消费任务，但任务依赖外部 MCP 服务
- 当前环境中任务返回 `success=0`，因为数据源不可用
- 缺少端到端的集成测试

**建议方案**:
1. 添加集成测试，mock MCP 依赖
2. 测试完整流程：FastAPI lifespan → APScheduler → ARQ enqueue → Worker consume
3. 添加任务执行监控和告警

**相关文件**:
- `app/tasks/update_ohlc.py`
- `tests/api/test_arq_scheduler.py`
- `mcp_servers/market_data/`


---

## 🟢 低优先级

### 4. 限流配置文档化

**文件**: `app/config/rate_limits.py`

**问题**:
- 硬编码的限流配置缺少来源说明
  - Binance: 1200 请求/分钟
  - OKX: 20 请求/秒
  - Polygon: 5 请求/分钟
- 实例数默认为 4，用于降级时的本地限流计算
- 缺少配置更新流程文档

**建议方案**:
1. 在代码注释中添加限流来源（交易所 API 文档链接）
2. 创建 `docs/rate_limits.md` 文档说明：
   - 各交易所的官方限流政策
   - 为什么选择这些数值
   - 如何更新配置
3. 考虑在生产环境中自动发现实例数（例如从 k8s API）

**相关文件**:
- `app/config/rate_limits.py`
- `app/services/rate_limiter.py`

---

### 5. 错误处理一致性

**文件**: 多个文件

**问题**:
- 大多数 Redis 错误捕获 `(redis.RedisError, asyncio.TimeoutError, OSError)`
- 某些地方还捕获 `ValueError`（例如 `hot_cache.py:160`）
- 缺少统一的错误处理策略文档

**建议方案**:
1. 在代码注释中说明为什么捕获 `ValueError`（可能来自 Parquet 反序列化）
2. 创建统一的异常处理指南
3. 考虑定义自定义异常类型以提高可读性

**相关文件**:
- `app/services/hot_cache.py`
- `app/services/rate_limiter.py`
- `app/services/redis_client.py`

---

### 6. 日志级别优化

**文件**: 多个服务文件

**问题**:
- 熔断器失败记录为 `WARNING`
- 降级操作记录为 `WARNING`
- 在生产环境中频繁出现 Redis 问题时，日志可能会很吵

**建议方案**:
1. 首次失败用 `INFO`，持续失败用 `WARNING`
2. 熔断器状态变化用 `WARNING`，单次失败用 `INFO`
3. 添加日志采样或速率限制

**相关文件**:
- `app/services/redis_client.py`
- `app/services/rate_limiter.py`
- `app/services/hot_cache.py`

---

### 7. 可观测性增强

**问题**:
- 缺少关键指标的监控和导出
- 难以诊断生产环境中的 Redis 相关问题

**建议添加的指标**:
1. **熔断器指标**:
   - 当前状态（closed/open/half_open）
   - 状态变化次数
   - 失败计数
   
2. **限流器指标**:
   - Redis vs 本地限流使用比例
   - 限流拒绝次数（按交易所分组）
   - 平均响应时间

3. **缓存指标**:
   - 缓存命中率
   - Redis vs 内存缓存使用比例
   - 缓存大小和记录数

4. **ARQ 指标**:
   - 队列深度
   - 任务成功/失败率
   - 任务执行时间

**建议方案**:
- 集成 Prometheus + Grafana
- 或使用 OpenTelemetry
- 添加健康检查端点暴露这些指标

**相关文件**:
- `app/services/redis_client.py`
- `app/services/rate_limiter.py`
- `app/services/hot_cache.py`
- `app/api/main.py`


---

## 🟢 测试缺口

### 8. 集成测试

**问题**:
- 缺少端到端的集成测试
- 单元测试覆盖良好，但缺少真实场景验证

**建议添加的测试**:

1. **完整 ARQ 工作流测试**:
   ```python
   # FastAPI lifespan → APScheduler → ARQ enqueue → Worker consume
   async def test_full_arq_workflow():
       # 启动 FastAPI app
       # 触发调度任务
       # 验证 ARQ 队列中有任务
       # 启动 worker 消费
       # 验证任务执行结果
   ```

2. **Redis 故障转移测试**:
   ```python
   # 测试 Redis 重启场景
   async def test_redis_restart_recovery():
       # Redis 正常运行
       # 写入缓存
       # 停止 Redis
       # 验证降级到内存
       # 重启 Redis
       # 验证恢复到 Redis
       # 验证内存缓存被清空
   ```

3. **并发限流测试**:
   ```python
   # 测试多线程/多协程并发访问限流器
   async def test_concurrent_rate_limiting():
       # 并发发起 N 个请求
       # 验证只有 M 个通过（M < N）
       # 验证无竞态条件
   ```

**相关文件**:
- `tests/integration/` (新建目录)

---

### 9. 熔断器恢复测试

**问题**:
- 缺少负载下 half-open → closed 转换的测试
- 缺少熔断器在高并发下的行为测试

**建议测试**:
```python
async def test_circuit_breaker_under_load():
    # 模拟高并发请求
    # 触发熔断器打开
    # 等待恢复超时
    # 验证 half-open 状态下的限流
    # 验证成功后转为 closed
```

**相关文件**:
- `tests/services/test_redis_client.py`

---

### 10. 性能基准测试

**问题**:
- 缺少性能基准测试
- 不清楚各组件的性能瓶颈

**建议添加**:
1. Redis vs 内存缓存读写性能对比
2. Lua 脚本执行时间
3. DataFrame 序列化/反序列化开销
4. 限流器吞吐量测试

**工具建议**:
- pytest-benchmark
- locust (负载测试)

**相关文件**:
- `tests/benchmarks/` (新建目录)


---

## 🟢 架构改进建议

### 11. Redis 连接池监控

**文件**: `app/services/redis_client.py`

**当前状态**:
- 使用 `ConnectionPool.from_url()` 配置连接池
- 连接池全局共享（单例模式）
- 配置了最大连接数、超时等参数

**建议改进**:
1. 添加连接池使用率监控
2. 暴露连接池统计信息（活跃连接数、空闲连接数）
3. 添加连接泄漏检测
4. 考虑连接池预热策略

**相关文件**:
- `app/services/redis_client.py`
- `app/config_manager.py`

---

### 12. 配置热更新

**问题**:
- 限流配置、Redis 配置等需要重启才能生效
- 缺少动态配置更新机制

**建议方案**:
1. 使用配置中心（如 etcd、Consul）
2. 实现配置文件监听和热重载
3. 添加配置变更的审计日志

**优先级**: 低 - 当前规模不需要

---

### 13. 分布式追踪

**问题**:
- 缺少跨服务的请求追踪
- 难以诊断复杂的调用链问题

**建议方案**:
1. 集成 OpenTelemetry
2. 添加 trace_id 到所有日志
3. 追踪关键路径：
   - API 请求 → 限流检查 → 缓存查询 → 外部 API 调用
   - 调度任务 → ARQ 入队 → Worker 消费 → 任务执行

**优先级**: 低 - 适合生产环境规模化后

---

## ✅ 已完成

### ✓ 测试隔离 Bug 修复

**文件**: `tests/services/test_hot_cache_redis.py:54-76`

**问题**: 
- `test_append_to_hot_cache_falls_back_to_memory_on_redis_error` 测试失败
- mock 作用域问题导致 `get_hot_cache` 尝试访问真实 Redis

**解决方案**:
- 扩展 mock 上下文覆盖 `get_hot_cache` 调用
- 确保读写操作都在同一个 mock 环境中

**提交**: 2026-03-26

---

### ✓ OKX 线程池变通方案文档化

**文件**: `app/okx/trading_client.py:124-135`

**改进**:
- 为 `_run_blocking` 方法添加详细的 docstring
- 说明为什么需要这个变通方案
- 记录如何通过环境变量禁用

**提交**: 2026-03-26

---

## 实施优先级建议

### 立即执行（合并前）
- ✅ 修复测试隔离 bug
- ✅ 添加 OKX 变通方案文档

### 短期（1-2 周）
- 🟡 添加可观测性指标（#7）
- 🟡 完善 update_daily_ohlc 集成测试（#3）

### 中期（1-2 月）
- 🟡 优化 DataFrame 序列化粒度（#2）- 当扩展到更多交易对时
- 🟢 添加集成测试套件（#8）
- 🟢 限流配置文档化（#4）

### 长期（按需）
- 🟡 重构 OKX 线程池变通方案（#1）- 如果成为维护负担
- 🟢 添加分布式追踪（#13）- 生产环境规模化后
- 🟢 实现配置热更新（#12）- 运维需求驱动

---

## 相关文档

- [Redis 集成实现计划](docs/superpowers/plans/2026-03-26-redis-integration.md)
- [Redis 集成设计规范](docs/superpowers/specs/2026-03-25-redis-integration-design.md)
- [代码审查报告](本次 code review 输出)

---

## 更新日志

- **2026-03-26**: 初始版本，基于 Redis 集成分支代码审查
- **2026-03-26**: 修复测试 bug，添加 OKX 文档

