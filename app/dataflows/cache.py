# app/dataflows/cache.py
import hashlib
import json
from datetime import timedelta
from typing import List, Optional

import redis.asyncio as redis
from pydantic import BaseModel


class CacheConfig:
    """缓存配置"""

    STOCK_DATA_TTL = timedelta(days=7)
    INDICATORS_TTL = timedelta(days=1)
    NEWS_TTL = timedelta(hours=1)
    FUNDAMENTALS_TTL = timedelta(days=1)


class DataCache:
    """异步 Redis 缓存层"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = redis.from_url(redis_url, decode_responses=True)

    def _make_key(self, prefix: str, **kwargs) -> str:
        """生成缓存键"""
        params_str = json.dumps(kwargs, sort_keys=True, default=str)
        hash_suffix = hashlib.md5(params_str.encode()).hexdigest()[:8]
        return f"dataflow:{prefix}:{hash_suffix}"

    async def get(self, prefix: str, **kwargs) -> Optional[List[dict]]:
        """
        从缓存获取数据

        Returns:
            List[dict]: 返回 dict 列表（非 Pydantic 模型）
                       调用方需要手动重建模型
        """
        key = self._make_key(prefix, **kwargs)
        data = await self.redis.get(key)
        if data:
            return json.loads(data)
        return None

    async def set(self, prefix: str, data: List[BaseModel], ttl: timedelta, **kwargs):
        """写入缓存（Pydantic V2）"""
        key = self._make_key(prefix, **kwargs)
        json_data = json.dumps([item.model_dump() for item in data], default=str)
        await self.redis.setex(key, int(ttl.total_seconds()), json_data)

    async def invalidate(self, prefix: str, **kwargs):
        """清除缓存"""
        key = self._make_key(prefix, **kwargs)
        await self.redis.delete(key)
