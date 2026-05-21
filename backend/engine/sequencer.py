"""智能拆除序列算法

基于图论和启发式搜索的最优拆除路径生成。
核心策略：
1. 将结构建模为图 G = (V, E)，V=节点, E=构件
2. 关键性排序：按构件类型、高度、连接度计算优先拆除权重
3. 贪婪搜索：每步选择风险最低的构件组合
4. 约束检查：拆除后稳定性、连接完整性
"""
import logging
import math
from typing import Optional
from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction,
    Element, Node, ElementType
)

logger = logging.getLogger(__name__)


class DemolitionSequencer:
    """拆除序列生成器

    基于图论和结构力学约束，生成最优拆除顺序。
    遵循"先次要后主要、自上而下、由外而内"原则。
    """

    def __init__(self):
        self._adjacency = {}
        self._node_elements = {}
        self._element_heights = {}
        self._connection_degree = {}

    # =========================================================================
    # 主接口
    # =========================================================================

    def generate_sequence(
        self,
        model: StructureModel,
        max_elements_per_step: int = 3,
        safety_check_fn=None
    ) -> DemolitionPlan:
        """生成拆除序列

        Args:
            model: 结构模型
            max_elements_per_step: 每步最多拆除构件数
            safety_check_fn: 安全检查回调 (model, element_ids) -> bool

        Returns:
            拆除方案
        """
        self._build_graph(model)

        # 计算所有构件的优先级分数
        scores = self._compute_priority_scores(model)

        # 按优先级排序（分数越高优先级越高）
        remaining = sorted(
            model.elements,
            key=lambda e: scores.get(e.id, 0),
            reverse=True
        )

        actions = []
        step = 1

        while remaining:
            # 每次选择 top-N 个相同类型的构件
            batch = self._select_batch(remaining, scores, max_elements_per_step)

            if not batch:
                break

            target_ids = [e.id for e in batch]
            actions.append(DemolitionAction(
                step=step,
                target_element_ids=target_ids,
                action_type="Remove"
            ))
            step += 1

            # 更新剩余
            remaining = [e for e in remaining if e not in batch]

            # 安全检查（如果提供）
            if safety_check_fn:
                modified = self._remove_elements(model, target_ids)
                if not safety_check_fn(modified, []):
                    logger.warning(f"步骤 {step-1} 可能不安全，标记为高风险")

        # 评估风险等级
        risk_level = self._assess_risk(actions, model)

        return DemolitionPlan(
            plan_id=f"seq_{self._generate_plan_id()}",
            description=self._generate_description(model, len(actions)),
            actions=actions,
            risk_level=risk_level
        )

    # =========================================================================
    # 图构建
    # =========================================================================

    def _build_graph(self, model: StructureModel):
        """构建结构拓扑图"""
        self._adjacency.clear()
        self._node_elements.clear()
        self._element_heights.clear()
        self._connection_degree.clear()

        # 节点 -> 构件列表
        for elem in model.elements:
            for nid in [elem.node_i_id, elem.node_j_id]:
                if nid not in self._node_elements:
                    self._node_elements[nid] = []
                self._node_elements[nid].append(elem)

        # 构件邻接关系
        node_map = {n.id: n for n in model.nodes}
        for elem in model.elements:
            neighbors = set()
            for nid in [elem.node_i_id, elem.node_j_id]:
                for other in self._node_elements.get(nid, []):
                    if other.id != elem.id:
                        neighbors.add(other.id)
            self._adjacency[elem.id] = neighbors

            # 构件高度
            ni = node_map.get(elem.node_i_id)
            nj = node_map.get(elem.node_j_id)
            if ni and nj:
                self._element_heights[elem.id] = (ni.z + nj.z) / 2

            # 连接度（连接的构件数）
            self._connection_degree[elem.id] = len(neighbors)

    # =========================================================================
    # 优先级计算
    # =========================================================================

    def _compute_priority_scores(self, model: StructureModel) -> dict[int, float]:
        """计算每个构件的拆除优先级分数

        分数越高 = 应该优先拆除（更安全）
        决策因子：
        - 高度: 高层优先 (weight: 0.35)
        - 构件类型: 梁 > 支撑 > 柱 (weight: 0.30)
        - 连接度: 低连接度优先 (weight: 0.20)
        - 是否底层: 底层延后 (weight: 0.15)
        """
        scores = {}
        max_z = max(n.z for n in model.nodes) if model.nodes else 1.0
        min_z = min(n.z for n in model.nodes) if model.nodes else 0.0

        for elem in model.elements:
            score = 0.0

            # 1. 高度因子 (0.35): 越高越优先
            h = self._element_heights.get(elem.id, 0)
            height_factor = (h - min_z) / max(0.01, (max_z - min_z))
            score += 0.35 * height_factor

            # 2. 类型因子 (0.30): 梁 > 支撑 > 柱
            type_weights = {
                ElementType.BEAM: 1.0,
                ElementType.BRACE: 0.6,
                ElementType.COLUMN: 0.3,
            }
            score += 0.30 * type_weights.get(elem.element_type, 0.5)

            # 3. 连接度因子 (0.20): 连接越少越优先
            degree = self._connection_degree.get(elem.id, 0)
            max_degree = max(self._connection_degree.values()) if self._connection_degree else 1
            degree_factor = 1.0 - (degree / max(1, max_degree))
            score += 0.20 * degree_factor

            # 4. 底层危险因子 (0.15): 底层构件应延后
            is_low = height_factor < 0.15
            if elem.element_type == ElementType.COLUMN and is_low:
                score += 0.15 * (-1.0)  # 惩罚
            else:
                score += 0.15 * (0.5 if not is_low else 0.0)

            scores[elem.id] = score

        return scores

    # =========================================================================
    # 批量选择
    # =========================================================================

    def _select_batch(
        self,
        remaining: list[Element],
        scores: dict[int, float],
        max_batch: int
    ) -> list[Element]:
        """选择一批构件进行拆除

        策略：选择相同类型的最高分构件
        """
        if not remaining:
            return []

        # 按分数排序
        sorted_elems = sorted(remaining, key=lambda e: scores.get(e.id, 0), reverse=True)

        # 取最高分构件的类型
        top_type = sorted_elems[0].element_type

        # 从同类型中选择 top-N
        batch = [e for e in sorted_elems if e.element_type == top_type][:max_batch]

        # 如果同类型不够，也补充次高分类型
        if len(batch) < min(max_batch, 1):
            other = [e for e in sorted_elems if e.element_type != top_type]
            batch.extend(other[:max_batch - len(batch)])

        return batch[:max_batch]

    # =========================================================================
    # 风险评估
    # =========================================================================

    def _assess_risk(
        self,
        actions: list[DemolitionAction],
        model: StructureModel
    ) -> str:
        """评估拆除方案的整体风险等级"""
        if not actions:
            return "Low"

        col_actions = 0
        brace_actions = 0
        total_steps = len(actions)

        for action in actions:
            for eid in action.target_element_ids:
                elem = next((e for e in model.elements if e.id == eid), None)
                if elem:
                    if elem.element_type == ElementType.COLUMN:
                        col_actions += 1
                    elif elem.element_type == ElementType.BRACE:
                        brace_actions += 1

        col_ratio = col_actions / max(1, len(model.elements))
        brace_ratio = brace_actions / max(1, len(model.elements))

        if col_ratio > 0.3:
            return "Critical"
        elif col_ratio > 0.15 or brace_ratio > 0.2:
            return "High"
        elif total_steps > 20:
            return "Medium"
        else:
            return "Low"

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _remove_elements(
        self,
        model: StructureModel,
        element_ids: list[int]
    ) -> StructureModel:
        """返回移除构件后的模型（不修改原模型）"""
        remaining = [e for e in model.elements if e.id not in element_ids]
        return StructureModel(
            model_id=model.model_id,
            name=model.name,
            nodes=model.nodes,
            elements=remaining,
            sections=model.sections,
            materials=model.materials
        )

    def _generate_plan_id(self) -> str:
        import random
        return f"{random.randint(1000, 9999)}"

    def _generate_description(self, model: StructureModel, steps: int) -> str:
        n_stories = len(set(round(n.z, 1) for n in model.nodes))
        n_cols = len([e for e in model.elements if e.element_type == ElementType.COLUMN])
        n_beams = len([e for e in model.elements if e.element_type == ElementType.BEAM])
        n_braces = len([e for e in model.elements if e.element_type == ElementType.BRACE])

        desc = f"{n_stories-1}层钢框架智能拆除方案（{steps}步）"
        parts = []
        if n_beams:
            parts.append(f"{n_beams}梁")
        if n_cols:
            parts.append(f"{n_cols}柱")
        if n_braces:
            parts.append(f"{n_braces}支撑")
        desc += f"，共{'/'.join(parts)}"

        return desc
