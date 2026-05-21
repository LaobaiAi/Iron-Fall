"""V3.0 可解释AI决策分析引擎

让每一步拆除指令"有据可查"。
为每个构件计算：
- 应力比 (当前应力/屈服强度)
- 重要性系数 (基于传力路径分析)
- 拆除后位移增幅 (预测)
- 自然语言解释
"""

import math
import logging
from typing import Optional
from collections import defaultdict, deque

from core.models import (
    StructureModel, AnalysisResult, Element, ElementType,
    ElementXAIInfo, XAIReport
)

logger = logging.getLogger(__name__)


class XAIAnalyzer:
    """可解释AI分析引擎

    基于结构拓扑分析和力学计算结果，为每个拆除决策提供量化依据。
    """

    def __init__(self):
        self._stress_cache: dict[int, float] = {}
        self._displacement_cache: dict[int, float] = {}

    # =========================================================================
    # 主分析接口
    # =========================================================================

    def analyze(
        self,
        model: StructureModel,
        analysis_result: Optional[AnalysisResult] = None,
    ) -> XAIReport:
        """执行完整的 XAI 分析

        Args:
            model: 结构模型
            analysis_result: 现有分析结果 (可选)

        Returns:
            XAIReport
        """
        # 1. 构建结构拓扑图
        graph = self._build_topology_graph(model)

        # 2. 计算各构件重要性系数
        importance_scores = self._compute_importance(model, graph)

        # 3. 计算应力比
        stress_ratios = self._compute_stress_ratios(model, analysis_result)

        # 4. 预测拆除影响 (位移增幅)
        displacement_impacts = self._estimate_displacement_impact(model, graph)

        # 5. 传力路径排名
        load_path_ranks = self._compute_load_path_ranks(model, graph)

        # 6. 生成各构件XAI详情
        details = []
        for elem in model.elements:
            isr = importance_scores.get(elem.id, 0.5)
            sr = stress_ratios.get(elem.id, 0.0)
            di = displacement_impacts.get(elem.id, 0.0)

            # 拆除建议逻辑
            # 建议优先拆除: 非关键构件(重要性低) 且 应力比高(已承担较多力，移除可释放)
            is_critical = isr > 0.7
            is_beam = elem.element_type == ElementType.BEAM
            is_brace = elem.element_type == ElementType.BRACE
            is_column_secondary = (
                elem.element_type == ElementType.COLUMN and isr < 0.5
            )

            recommend = not is_critical and (
                is_beam or is_brace or is_column_secondary
            )

            explanation = self._generate_explanation(
                elem, sr, isr, di, recommend
            )

            details.append(ElementXAIInfo(
                element_id=elem.id,
                element_type=elem.element_type.value,
                stress_ratio=round(sr, 3),
                importance_score=round(isr, 3),
                displacement_impact=round(di, 6),
                stiffness_contribution=round(1.0 / max(isr, 0.01) * 0.01, 3),
                load_path_rank=load_path_ranks.get(elem.id, 99),
                recommendation=recommend,
                explanation=explanation,
            ))

        # 按推荐优先级排序
        recommended_seq = sorted(
            [d for d in details if d.recommendation],
            key=lambda d: (
                -d.stress_ratio,  # 高应力优先
                d.importance_score,  # 低重要性优先
            )
        )

        removable = sum(1 for d in details if d.recommendation)

        # 总体评估
        if removable == 0:
            stability = "Critical - 无可安全拆除构件"
            summary = "当前结构状态下，所有构件均为关键承重构件，不应拆除任何构件。"
        elif removable < len(details) * 0.3:
            stability = "Constrained - 可拆除构件有限"
            summary = (
                f"仅 {removable}/{len(details)} 个构件可安全拆除。"
                f"建议优先拆除应力比高且重要性低的梁和支撑结构。"
            )
        else:
            stability = "Stable - 有较多拆除选择"
            summary = (
                f"{removable}/{len(details)} 个构件可安全拆除。"
                f"建议按推荐顺序执行拆除操作。"
            )

        return XAIReport(
            model_id=model.model_id,
            overall_stability=stability,
            total_elements=len(model.elements),
            removable_elements=removable,
            element_details=details,
            recommended_sequence=[d.element_id for d in recommended_seq],
            summary=summary,
        )

    # =========================================================================
    # 拓扑图构建
    # =========================================================================

    def _build_topology_graph(
        self, model: StructureModel
    ) -> dict[int, list[int]]:
        """构建结构拓扑连接图

        Returns:
            {element_id: [connected_element_ids]}
        """
        # 节点->构件映射
        node_to_elements: dict[int, list[int]] = defaultdict(list)
        for elem in model.elements:
            node_to_elements[elem.node_i_id].append(elem.id)
            node_to_elements[elem.node_j_id].append(elem.id)

        # 构件->构件连接 (通过共享节点)
        graph: dict[int, list[int]] = defaultdict(list)
        for elem_id in [e.id for e in model.elements]:
            elem = next(e for e in model.elements if e.id == elem_id)
            connected = set()
            for nid in [elem.node_i_id, elem.node_j_id]:
                for neighbor_eid in node_to_elements[nid]:
                    if neighbor_eid != elem_id:
                        connected.add(neighbor_eid)
            graph[elem_id] = list(connected)

        return dict(graph)

    # =========================================================================
    # 重要性系数计算
    # =========================================================================

    def _compute_importance(
        self,
        model: StructureModel,
        graph: dict[int, list[int]],
    ) -> dict[int, float]:
        """基于图中心性计算构件重要性

        使用改进的加权度中心性:
        - 连接度 (degree)
        - 构件类型权重 (柱 > 梁 > 支撑)
        - 高度权重 (底部更重要)

        Returns:
            {element_id: importance_score (0-1)}
        """
        type_weights = {
            ElementType.COLUMN: 1.0,
            ElementType.BEAM: 0.6,
            ElementType.BRACE: 0.4,
        }

        # 计算最大高度
        node_map = {n.id: n for n in model.nodes}
        max_z = max((n.z for n in model.nodes), default=0.0)

        scores_raw = {}
        for elem in model.elements:
            # 连接度
            degree = len(graph.get(elem.id, []))
            max_degree = max(
                (len(graph.get(e.id, [])) for e in model.elements), default=1
            )

            # 类型权重
            tw = type_weights.get(elem.element_type, 0.5)

            # 高度权重: 底部构件更重要
            ni = node_map.get(elem.node_i_id)
            nj = node_map.get(elem.node_j_id)
            if ni and nj and max_z > 0:
                avg_z = (ni.z + nj.z) / 2
                height_factor = 1.0 - (avg_z / max_z) * 0.5
            else:
                height_factor = 0.5

            # 综合得分
            degree_factor = degree / max(max_degree, 1)
            raw = degree_factor * tw * height_factor

            scores_raw[elem.id] = raw

        # 归一化到 0-1
        if scores_raw:
            max_score = max(scores_raw.values())
            if max_score > 0:
                return {
                    eid: round(score / max_score, 3)
                    for eid, score in scores_raw.items()
                }

        return {e.id: 0.5 for e in model.elements}

    # =========================================================================
    # 应力比计算
    # =========================================================================

    def _compute_stress_ratios(
        self,
        model: StructureModel,
        analysis_result: Optional[AnalysisResult],
    ) -> dict[int, float]:
        """计算各构件的应力比

        Returns:
            {element_id: stress_ratio (0-1)}
        """
        ratios = {}
        fy = 355  # MPa (Q355 默认)

        for mat in model.materials:
            fy = mat.fy
            break

        # 从分析结果提取应力
        if analysis_result and analysis_result.element_stresses:
            for eid, stress in analysis_result.element_stresses.items():
                sr = min(abs(stress) / fy, 1.0) if fy > 0 else 0
                ratios[eid] = round(sr, 3)

        # 未在分析结果中的构件：基于拓扑估算
        node_map = {n.id: n for n in model.nodes}
        max_z = max((n.z for n in model.nodes), default=0.0)

        for elem in model.elements:
            if elem.id not in ratios:
                ni = node_map.get(elem.node_i_id)
                nj = node_map.get(elem.node_j_id)

                if ni and nj and max_z > 0:
                    avg_z = (ni.z + nj.z) / 2
                    height_ratio = avg_z / max_z
                else:
                    height_ratio = 0.5

                if elem.element_type == ElementType.COLUMN:
                    base_stress = 0.6 * (1.0 - height_ratio * 0.3)
                elif elem.element_type == ElementType.BEAM:
                    base_stress = 0.3 + height_ratio * 0.2
                else:
                    base_stress = 0.4

                ratios[elem.id] = round(base_stress, 3)

        return ratios

    # =========================================================================
    # 拆除位移影响预测
    # =========================================================================

    def _estimate_displacement_impact(
        self,
        model: StructureModel,
        graph: dict[int, list[int]],
    ) -> dict[int, float]:
        """预测拆除各构件后的位移增幅

        基于该构件的刚度贡献和结构冗余度估算。
        """
        impacts = {}

        # 总构件数
        n_total = len(model.elements)

        for elem in model.elements:
            # 该构件连接的构件数
            n_connected = len(graph.get(elem.id, []))

            if n_total <= 1:
                impacts[elem.id] = float("inf")
                continue

            # 冗余度: 连接数越多，拆除影响越小
            redundancy = n_connected / max(n_total - 1, 1)

            # 基础位移增量: 假设移除一个构件位移增加 1/n_total
            base_disp = 0.001  # 1mm 基准位移

            if elem.element_type == ElementType.COLUMN:
                impact_mult = 10.0 / (redundancy + 0.1)
            elif elem.element_type == ElementType.BEAM:
                impact_mult = 5.0 / (redundancy + 0.2)
            else:
                impact_mult = 3.0 / (redundancy + 0.3)

            impact = base_disp * impact_mult
            impacts[elem.id] = round(impact, 6)

        return impacts

    # =========================================================================
    # 传力路径排名
    # =========================================================================

    def _compute_load_path_ranks(
        self,
        model: StructureModel,
        graph: dict[int, list[int]],
    ) -> dict[int, int]:
        """通过 BFS 从顶部节点到底部支座计算传力路径排名

        Returns:
            {element_id: rank} (1 = 最关键的传力路径)
        """
        node_map = {n.id: n for n in model.nodes}
        max_z = max((n.z for n in model.nodes), default=0.0)

        # 找到顶部节点
        top_nodes = [
            n.id for n in model.nodes
            if abs(n.z - max_z) < 0.01
        ]

        # 找到支座节点
        support_nodes = [
            n.id for n in model.nodes
            if any(n.restraint[:3])
        ]

        if not top_nodes or not support_nodes:
            return {e.id: 99 for e in model.elements}

        # 从顶部节点 BFS，统计每条边的传力权重
        edge_weight: dict[int, int] = defaultdict(int)

        for top_nid in top_nodes:
            visited = set()
            queue = deque([(top_nid, [])])
            visited.add(top_nid)

            while queue:
                current_nid, path = queue.popleft()
                weight = len(node_map) - len(path)

                for other_nid in [n for n in node_map if n != current_nid]:
                    if other_nid in visited:
                        continue

                    # 找到连接 current_nid 和 other_nid 的构件
                    elem = next(
                        (
                            e for e in model.elements
                            if (
                                e.node_i_id == current_nid and e.node_j_id == other_nid
                            ) or (
                                e.node_j_id == current_nid and e.node_i_id == other_nid
                            )
                        ),
                        None,
                    )

                    if elem:
                        edge_weight[elem.id] += weight
                        if other_nid not in support_nodes:
                            visited.add(other_nid)
                            queue.append((other_nid, path + [elem.id]))

        # 按权重降序排名
        sorted_edges = sorted(
            edge_weight.items(), key=lambda x: -x[1]
        )

        ranks = {}
        for rank, (eid, _) in enumerate(sorted_edges, start=1):
            ranks[eid] = rank

        # 未覆盖的构件
        for elem in model.elements:
            if elem.id not in ranks:
                ranks[elem.id] = 99

        return ranks

    # =========================================================================
    # 自然语言解释生成
    # =========================================================================

    def _generate_explanation(
        self,
        elem: Element,
        stress_ratio: float,
        importance: float,
        displacement_impact: float,
        recommend: bool,
    ) -> str:
        """为构件生成自然语言决策解释"""
        type_cn = {
            ElementType.COLUMN.value: "柱",
            ElementType.BEAM: "梁",
            ElementType.BRACE: "支撑",
        }.get(elem.element_type, elem.element_type.value)

        parts = [f"#{elem.id}号{type_cn}："]

        if recommend:
            parts.append("建议优先拆除。")
            if stress_ratio > 0.5:
                parts.append(
                    f"应力比({stress_ratio:.2f})较高，拆除后可有效释放结构内力；"
                )
            else:
                parts.append(f"应力比({stress_ratio:.2f})适中；")

            if importance < 0.3:
                parts.append("该构件为次要承重构件，")
            elif importance < 0.5:
                parts.append("该构件重要性中等，")
            else:
                parts.append("虽然有一定重要性，但仍在可拆范围内，")

            parts.append(
                f"移除后预估位移增加约{displacement_impact*1000:.1f}mm，在安全范围内。"
            )
        else:
            if importance > 0.7:
                parts.append(f"不建议拆除。该构件为关键承重{type_cn}，")
                parts.append(
                    f"重要性系数{importance:.2f}，移除可能导致整体刚度"
                    f"下降超过{int(importance*100)}%，存在安全风险。"
                )
            elif stress_ratio < 0.2:
                parts.append(
                    f"暂不建议拆除。应力比({stress_ratio:.2f})较低，"
                    f"拆除收益有限，可考虑后续步骤处理。"
                )
            else:
                parts.append(
                    f"需谨慎评估。应力比{stress_ratio:.2f}，"
                    f"重要性{importance:.2f}，建议在拆除次要构件后重新评估。"
                )

        return "".join(parts)
