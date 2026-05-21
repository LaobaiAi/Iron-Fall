"""V3.0 力学状态实时可视化引擎

将构件内力映射为颜色热力图数据。
蓝→绿→黄→红 对应低应力到高应力。
支持拆除过程中内力重分布的时序动画数据生成。
"""

import math
import logging
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict

from core.models import (
    StructureModel, AnalysisResult, DemolitionAction, ElementType
)

logger = logging.getLogger(__name__)


@dataclass
class ElementForceColor:
    """单个构件内力→颜色映射"""
    element_id: int
    element_type: str
    stress_ratio: float  # 0-1
    axial_force: float
    bending_moment: float
    color_hex: str  # "#0000FF" → "#FF0000"
    alpha: float = 1.0  # 透明度


@dataclass
class ForceVisualFrame:
    """力场可视化帧"""
    frame_index: int
    action_step: int
    description: str
    elements: list[ElementForceColor]
    max_stress_ratio: float
    avg_stress_ratio: float
    stable: bool


@dataclass
class ForceVisualTimeline:
    """力场可视化时间线"""
    model_id: str
    model_name: str
    total_frames: int
    frames: list[ForceVisualFrame] = field(default_factory=list)
    legend: dict = field(default_factory=lambda: {
        "levels": [
            {"label": "安全 (0-20%)", "color": "#2196F3", "range": [0, 0.2]},
            {"label": "低应力 (20-40%)", "color": "#4CAF50", "range": [0.2, 0.4]},
            {"label": "中等 (40-60%)", "color": "#FFEB3B", "range": [0.4, 0.6]},
            {"label": "高应力 (60-80%)", "color": "#FF9800", "range": [0.6, 0.8]},
            {"label": "危险 (80-100%)", "color": "#F44336", "range": [0.8, 1.0]},
        ]
    })


class ForceVisualizer:
    """力场可视化生成器

    将力学分析结果转换为前端可渲染的颜色映射数据。
    支持单帧和多帧时序动画数据生成。
    """

    def __init__(self, fy: float = 355.0):
        """
        Args:
            fy: 屈服强度参考值 (MPa)
        """
        self.fy = fy

    # =========================================================================
    # 主接口
    # =========================================================================

    def visualize(
        self,
        model: StructureModel,
        analysis_result: Optional[AnalysisResult] = None,
    ) -> ForceVisualFrame:
        """生成单帧力场可视化数据

        基于静力分析结果或拓扑估算，为每个构件生成颜色映射。

        Args:
            model: 结构模型
            analysis_result: 力学分析结果

        Returns:
            ForceVisualFrame
        """
        elements = []
        forces = self._extract_forces(model, analysis_result)

        max_sr = 0.0
        sum_sr = 0.0

        for elem in model.elements:
            force_data = forces.get(elem.id, {"axial": 0, "moment": 0, "ratio": 0})
            sr = force_data["ratio"]
            color = self._stress_to_color(sr)
            alpha = 0.7 + 0.3 * sr  # 高应力更不透明

            elements.append(ElementForceColor(
                element_id=elem.id,
                element_type=elem.element_type.value,
                stress_ratio=round(sr, 3),
                axial_force=round(force_data["axial"], 2),
                bending_moment=round(force_data["moment"], 2),
                color_hex=color,
                alpha=round(alpha, 2),
            ))

            max_sr = max(max_sr, sr)
            sum_sr += sr

        avg_sr = sum_sr / max(len(elements), 1)
        stable = max_sr < 0.8 and avg_sr < 0.5

        return ForceVisualFrame(
            frame_index=0,
            action_step=0,
            description="初始状态力场分布",
            elements=elements,
            max_stress_ratio=round(max_sr, 3),
            avg_stress_ratio=round(avg_sr, 3),
            stable=stable,
        )

    def visualize_timeline(
        self,
        model: StructureModel,
        demo_actions: list[DemolitionAction],
    ) -> ForceVisualTimeline:
        """生成拆除过程的力场变化时间线

        模拟逐步拆除过程中内力重分布的动画数据。

        Args:
            model: 初始结构模型
            demo_actions: 拆除动作序列

        Returns:
            ForceVisualTimeline
        """
        timeline = ForceVisualTimeline(
            model_id=model.model_id,
            model_name=model.name,
            total_frames=len(demo_actions) + 1,
        )

        # 帧 0: 初始状态
        frame0 = self.visualize(model)
        frame0.frame_index = 0
        frame0.action_step = 0
        timeline.frames.append(frame0)

        current_elements = list(model.elements)

        for i, action in enumerate(demo_actions, start=1):
            # 移除指定构件
            current_elements = [
                e for e in current_elements
                if e.id not in action.target_element_ids
            ]

            # 创建修改后的模型
            modified = StructureModel(
                model_id=model.model_id,
                name=f"{model.name} (拆除步骤 {action.step})",
                nodes=model.nodes,
                elements=current_elements,
                sections=model.sections,
                materials=model.materials,
            )

            # 模拟内力重分布
            elements = []
            redist_forces = self._simulate_redistribution(
                model, current_elements, action
            )

            max_sr = 0.0
            sum_sr = 0.0

            for elem in current_elements:
                force_data = redist_forces.get(
                    elem.id, {"axial": 0, "moment": 0, "ratio": 0}
                )
                sr = force_data["ratio"]
                color = self._stress_to_color(sr)
                alpha = 0.7 + 0.3 * sr

                elements.append(ElementForceColor(
                    element_id=elem.id,
                    element_type=elem.element_type.value,
                    stress_ratio=round(sr, 3),
                    axial_force=round(force_data["axial"], 2),
                    bending_moment=round(force_data["moment"], 2),
                    color_hex=color,
                    alpha=round(alpha, 2),
                ))

                max_sr = max(max_sr, sr)
                sum_sr += sr

                # 被拆除的构件标记为红色
                for removed_id in action.target_element_ids:
                    elements.append(ElementForceColor(
                        element_id=removed_id,
                        element_type="Removed",
                        stress_ratio=0,
                        axial_force=0,
                        bending_moment=0,
                        color_hex="#9E9E9E",  # 灰色表示已拆除
                        alpha=0.3,
                    ))

            avg_sr = sum_sr / max(len(current_elements), 1)
            stable = max_sr < 0.8 and avg_sr < 0.5

            timeline.frames.append(ForceVisualFrame(
                frame_index=i,
                action_step=action.step,
                description=f"步骤 {action.step}: 拆除构件 {action.target_element_ids}",
                elements=elements,
                max_stress_ratio=round(max_sr, 3),
                avg_stress_ratio=round(avg_sr, 3),
                stable=stable,
            ))

        return timeline

    # =========================================================================
    # 内力提取
    # =========================================================================

    def _extract_forces(
        self,
        model: StructureModel,
        analysis_result: Optional[AnalysisResult],
    ) -> dict[int, dict]:
        """提取/估算各构件内力

        Returns:
            {element_id: {axial, moment, ratio}}
        """
        forces = {}
        node_map = {n.id: n for n in model.nodes}
        max_z = max((n.z for n in model.nodes), default=1.0)

        if analysis_result and analysis_result.element_stresses:
            for eid, stress_val in analysis_result.element_stresses.items():
                sr = min(abs(stress_val) / self.fy, 1.0) if self.fy > 0 else 0
                forces[eid] = {
                    "axial": stress_val,
                    "moment": stress_val * 0.2,
                    "ratio": round(sr, 3),
                }

        for elem in model.elements:
            if elem.id in forces:
                continue

            ni = node_map.get(elem.node_i_id)
            nj = node_map.get(elem.node_j_id)
            avg_z = ((ni.z + nj.z) / 2 if ni and nj else 0)
            h_r = avg_z / max_z if max_z > 0 else 0.5

            if elem.element_type == ElementType.COLUMN:
                axial = self.fy * 0.5 * (1.0 - h_r * 0.3)
                moment = axial * 0.1
            elif elem.element_type == ElementType.BEAM:
                axial = self.fy * 0.15
                moment = self.fy * 0.2 * (0.5 + h_r * 0.3)
            else:
                axial = self.fy * 0.1
                moment = self.fy * 0.05

            total = math.sqrt(axial**2 + (moment * 10)**2)
            sr = min(total / self.fy, 1.0)

            forces[elem.id] = {
                "axial": round(axial, 2),
                "moment": round(moment, 2),
                "ratio": round(sr, 3),
            }

        return forces

    def _simulate_redistribution(
        self,
        original_model: StructureModel,
        remaining: list,
        action: DemolitionAction,
    ) -> dict[int, dict]:
        """模拟拆除后内力重分布

        简化逻辑: 拆除构件后，相邻构件分担额外内力
        """
        forces = self._extract_forces(original_model, None)

        # 找出与拆除构件相邻的构件
        removed_ids = set(action.target_element_ids)
        affected_ids = set()

        # 建立节点->构件索引
        node_to_elems = defaultdict(list)
        for elem in original_model.elements:
            node_to_elems[elem.node_i_id].append(elem.id)
            node_to_elems[elem.node_j_id].append(elem.id)

        for rid in removed_ids:
            removed_elem = next(
                (e for e in original_model.elements if e.id == rid),
                None
            )
            if removed_elem:
                for nid in [removed_elem.node_i_id, removed_elem.node_j_id]:
                    affected_ids.update(
                        eid for eid in node_to_elems[nid]
                        if eid not in removed_ids
                    )

        # 剩余构件分担额外荷载
        if affected_ids:
            extra_load = len(removed_ids) / max(len(affected_ids), 1)
            for eid in affected_ids:
                if eid in forces:
                    forces[eid]["axial"] *= (1.0 + extra_load * 0.3)
                    forces[eid]["moment"] *= (1.0 + extra_load * 0.3)
                    total = math.sqrt(
                        forces[eid]["axial"]**2 + (forces[eid]["moment"] * 10)**2
                    )
                    forces[eid]["ratio"] = round(
                        min(total / self.fy, 1.0), 3
                    )

        return forces

    # =========================================================================
    # 颜色映射
    # =========================================================================

    def _stress_to_color(self, ratio: float) -> str:
        """应力比 → 渐变色 (蓝→绿→黄→红)

        0.0 → #2196F3 (蓝)
        0.25 → #4CAF50 (绿)
        0.5 → #FFEB3B (黄)
        0.75 → #FF9800 (橙)
        1.0 → #F44336 (红)
        """
        ratio = max(0, min(1, ratio))

        stops = [
            (0.0, (0x21, 0x96, 0xF3)),   # 蓝
            (0.25, (0x4C, 0xAF, 0x50)),   # 绿
            (0.5, (0xFF, 0xEB, 0x3B)),    # 黄
            (0.75, (0xFF, 0x98, 0x00)),   # 橙
            (1.0, (0xF4, 0x43, 0x36)),    # 红
        ]

        # 线性插值
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= ratio <= t1:
                f = (ratio - t0) / (t1 - t0) if t1 > t0 else 0
                r = int(c0[0] + f * (c1[0] - c0[0]))
                g = int(c0[1] + f * (c1[1] - c0[1]))
                b = int(c0[2] + f * (c1[2] - c0[2]))
                return f"#{r:02X}{g:02X}{b:02X}"

        return "#F44336"  # 默认红色
