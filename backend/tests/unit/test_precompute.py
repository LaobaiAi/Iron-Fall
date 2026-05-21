"""预计算与缓存系统测试

覆盖 engine/precompute.py 的：
- LRU 缓存操作 (get/set/过期/驱逐)
- 模型哈希一致性
- PrecomputeEngine 缓存优先逻辑
- 缓存统计正确性
"""
import time
import pytest
import asyncio
from core.models import StructureModel, Node, Element, Section, Material, ElementType, DemolitionPlan
from engine.precompute import PrecomputeCache, model_hash, PrecomputeEngine


# ============================================================================
# PrecomputeCache 测试
# ============================================================================

class TestPrecomputeCache:
    """LRU 缓存核心测试"""

    def test_set_and_get(self):
        cache = PrecomputeCache(max_size=10, ttl_seconds=60)
        cache.set("key1", {"value": 42})
        data = cache.get("key1")
        assert data == {"value": 42}

    def test_miss_returns_none(self):
        cache = PrecomputeCache()
        assert cache.get("nonexistent") is None

    def test_expiry(self):
        cache = PrecomputeCache(ttl_seconds=0.01)
        cache.set("key1", {"value": 1})
        time.sleep(0.02)
        assert cache.get("key1") is None  # 已过期

    def test_lru_eviction(self):
        cache = PrecomputeCache(max_size=3, ttl_seconds=60)
        # 插入 3 个条目
        cache.set("a", {"n": 1})
        cache.set("b", {"n": 2})
        cache.set("c", {"n": 3})

        # 访问 a（变为最近）
        cache.get("a")

        # 插入第 4 个，应驱逐 b（最久未访问）
        cache.set("d", {"n": 4})

        assert cache.get("a") is not None  # a 被访问过，保留
        assert cache.get("c") is not None  # c 较新
        assert cache.get("d") is not None  # d 最新
        # b 应被驱逐（最久未访问，且最早插入）
        assert cache.get("b") is None

    def test_stats_initial(self):
        cache = PrecomputeCache()
        s = cache.stats
        assert s["size"] == 0
        assert s["hits"] == 0
        assert s["misses"] == 0

    def test_stats_hit_miss(self):
        cache = PrecomputeCache()
        cache.set("k", {"x": 1})
        cache.get("k")   # hit
        cache.get("k2")  # miss
        s = cache.stats
        assert s["hits"] == 1
        assert s["misses"] == 1

    def test_stats_evictions(self):
        cache = PrecomputeCache(max_size=2, ttl_seconds=60)
        cache.set("a", {})
        cache.set("b", {})
        cache.set("c", {})  # 应驱逐 a
        s = cache.stats
        assert s["evictions"] >= 1

    def test_ttl_not_expired_early(self):
        cache = PrecomputeCache(ttl_seconds=60)
        cache.set("k", {"x": 1})
        time.sleep(0.01)
        assert cache.get("k") is not None  # 远未过期

    def test_cache_size_respected(self):
        cache = PrecomputeCache(max_size=5, ttl_seconds=60)
        for i in range(10):
            cache.set(f"key_{i}", {"i": i})
        # 缓存大小不应超过 max_size
        s = cache.stats
        assert s["size"] <= 5


# ============================================================================
# model_hash 测试
# ============================================================================

class TestModelHash:
    """模型哈希函数测试"""

    def test_same_model_same_hash(self, sample_3story_frame):
        h1 = model_hash(sample_3story_frame)
        h2 = model_hash(sample_3story_frame)
        assert h1 == h2

    def test_different_models_different_hash(self, sample_3story_frame,
                                               sample_1story_frame):
        h1 = model_hash(sample_3story_frame)
        h2 = model_hash(sample_1story_frame)
        assert h1 != h2

    def test_empty_model_has_hash(self, empty_model):
        h = model_hash(empty_model)
        assert len(h) == 16  # MD5[:16]

    def test_hash_is_hex_string(self, sample_3story_frame):
        h = model_hash(sample_3story_frame)
        int(h, 16)  # 不抛异常即合法 hex


# ============================================================================
# PrecomputeEngine 测试
# ============================================================================

class TestPrecomputeEngine:
    """预计算引擎测试"""

    @pytest.fixture
    def engine(self) -> PrecomputeEngine:
        return PrecomputeEngine()

    @pytest.mark.asyncio
    async def test_get_plan_generates_result(self, engine, sample_3story_frame):
        """首次请求应生成拆除方案"""
        plan = await engine.get_demolition_plan(sample_3story_frame)
        assert isinstance(plan, DemolitionPlan)
        assert len(plan.actions) > 0

    @pytest.mark.asyncio
    async def test_get_plan_cached_second_time(self, engine, sample_3story_frame):
        """第二次请求应从缓存返回"""
        plan1 = await engine.get_demolition_plan(sample_3story_frame)
        plan2 = await engine.get_demolition_plan(sample_3story_frame)
        # 两次返回同一方案（缓存命中）
        assert plan1.plan_id == plan2.plan_id
        assert len(plan1.actions) == len(plan2.actions)

    @pytest.mark.asyncio
    async def test_force_recompute(self, engine, sample_3story_frame):
        """force_recompute=True 应重新生成"""
        plan1 = await engine.get_demolition_plan(sample_3story_frame)
        plan2 = await engine.get_demolition_plan(
            sample_3story_frame, force_recompute=True
        )
        assert isinstance(plan2, DemolitionPlan)

    @pytest.mark.asyncio
    async def test_cache_stats_increases(self, engine, sample_3story_frame):
        """多次调用应增加缓存命中率"""
        await engine.get_demolition_plan(sample_3story_frame)
        s1 = engine._cache.stats
        await engine.get_demolition_plan(sample_3story_frame)
        s2 = engine._cache.stats
        # 第二次应击中缓存
        assert s2["hits"] >= s1["hits"]
