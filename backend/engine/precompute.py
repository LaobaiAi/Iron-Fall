"""预计算与缓存系统

异步预计算多种拆除方案，用户交互时直接调用缓存结果。
从点击"执行"到动画开始 < 500ms 的保证。
"""
import asyncio
import time
import hashlib
import json
import logging
from typing import Optional, Callable
from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction,
    AnalysisResult
)

logger = logging.getLogger(__name__)


class PrecomputeCache:
    """预计算结果缓存
    
    使用 LRU 策略管理内存，键为模型哈希。
    """
    
    def __init__(self, max_size: int = 50, ttl_seconds: float = 300):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: dict[str, dict] = {}
        self._access_times: dict[str, float] = {}
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}
    
    def get(self, key: str) -> Optional[dict]:
        """获取缓存条目"""
        if key in self._cache:
            entry = self._cache[key]
            if self._is_expired(entry):
                self._evict(key)
                self._stats["misses"] += 1
                return None
            self._access_times[key] = time.time()
            self._stats["hits"] += 1
            return entry["data"]
        self._stats["misses"] += 1
        return None
    
    def set(self, key: str, data: dict):
        """设置缓存条目"""
        if len(self._cache) >= self._max_size:
            self._evict_lru()
        
        self._cache[key] = {
            "data": data,
            "timestamp": time.time()
        }
        self._access_times[key] = time.time()
    
    def _is_expired(self, entry: dict) -> bool:
        return time.time() - entry["timestamp"] > self._ttl
    
    def _evict(self, key: str):
        self._cache.pop(key, None)
        self._access_times.pop(key, None)
        self._stats["evictions"] += 1
    
    def _evict_lru(self):
        """驱逐最久未使用的条目"""
        if self._access_times:
            lru_key = min(self._access_times, key=self._access_times.get)
            self._evict(lru_key)
    
    @property
    def stats(self) -> dict:
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / max(1, total)
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{hit_rate:.1%}",
            "evictions": self._stats["evictions"],
        }


def model_hash(model: StructureModel) -> str:
    """生成结构模型的哈希键"""
    data = json.dumps({
        "nodes": [(n.id, n.x, n.y, n.z) for n in sorted(model.nodes, key=lambda n: n.id)],
        "elements": [(e.id, e.node_i_id, e.node_j_id, e.element_type.value)
                     for e in sorted(model.elements, key=lambda e: e.id)],
        "sections": [(s.id, s.name) for s in sorted(model.sections, key=lambda s: s.id)],
        "materials": [(m.id, m.name) for m in sorted(model.materials, key=lambda m: m.id)],
    }, sort_keys=True)
    return hashlib.md5(data.encode()).hexdigest()[:16]


class PrecomputeEngine:
    """预计算引擎
    
    特性：
    - 异步预计算多种拆除方案
    - LRU 缓存，TTL 5 分钟
    - 后台任务，不阻塞主线程
    """
    
    def __init__(self):
        self._cache = PrecomputeCache(max_size=50, ttl_seconds=300)
        self._tasks: dict[str, asyncio.Task] = {}
        self._sequencer = None
        self._anastruct = None
        self._frame3dd = None
    
    def set_engines(self, anastruct, frame3dd):
        """设置计算引擎引用"""
        self._anastruct = anastruct
        self._frame3dd = frame3dd
    
    async def get_demolition_plan(
        self,
        model: StructureModel,
        force_recompute: bool = False
    ) -> DemolitionPlan:
        """获取拆除方案（缓存优先）"""
        key = f"plan_{model_hash(model)}"
        
        if not force_recompute:
            cached = self._cache.get(key)
            if cached:
                plan_data = cached.get("plan")
                if plan_data:
                    return DemolitionPlan(**plan_data)
        
        # 生成新方案
        from engine.sequencer import DemolitionSequencer
        sequencer = DemolitionSequencer()
        plan = sequencer.generate_sequence(model)
        
        self._cache.set(key, {
            "plan": plan.model_dump(),
            "generated_at": time.time()
        })
        
        return plan
    
    async def get_static_analysis(
        self,
        model: StructureModel,
        force_recompute: bool = False
    ) -> AnalysisResult:
        """获取静力分析结果（缓存优先）"""
        key = f"static_{model_hash(model)}"
        
        if not force_recompute:
            cached = self._cache.get(key)
            if cached:
                result_data = cached.get("result")
                if result_data:
                    return AnalysisResult(**result_data)
        
        # 执行分析
        if self._anastruct:
            result = await self._anastruct.run_static_analysis(model)
        else:
            from engine.frame3dd import Frame3DDAdapter
            adapter = Frame3DDAdapter()
            result = await adapter.run_static_analysis(model)
        
        self._cache.set(key, {
            "result": result.model_dump(),
            "generated_at": time.time()
        })
        
        return result
    
    async def precompute_all(self, model: StructureModel):
        """异步预计算所有分析结果
        
        在后台预计算：
        1. 拆除方案
        2. 静力分析
        3. 拆除后各步的稳定性
        """
        tasks = []
        
        # 预计算拆除方案
        tasks.append(self.get_demolition_plan(model))
        
        # 预计算静力分析
        tasks.append(self.get_static_analysis(model))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        plan = None
        for r in results:
            if isinstance(r, DemolitionPlan):
                plan = r
        
        # 预计算各步拆除后的稳定性
        if plan and self._anastruct:
            for action in plan.actions[:5]:  # 只预计算前 5 步
                remaining = [e for e in model.elements
                           if e.id not in action.target_element_ids]
                modified = StructureModel(
                    model_id=model.model_id,
                    name=model.name,
                    nodes=model.nodes,
                    elements=remaining,
                    sections=model.sections,
                    materials=model.materials
                )
                step_key = f"step_{action.step}_{model_hash(modified)}"
                try:
                    result = await self._anastruct.run_static_analysis(modified)
                    self._cache.set(step_key, {
                        "result": result.model_dump(),
                        "step": action.step,
                        "removed": action.target_element_ids,
                    })
                except Exception as e:
                    logger.warning(f"预计算步骤 {action.step} 失败: {e}")
        
        logger.info(f"预计算完成: {len(tasks)} 个任务, 缓存 {self._cache.stats['size']} 项")
    
    @property
    def stats(self) -> dict:
        return self._cache.stats
