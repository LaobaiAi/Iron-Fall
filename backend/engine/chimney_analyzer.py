"""V3.0 烟囱快速力学验算引擎

基于变截面悬臂梁模型，在 100ms 内完成切口后稳定性快速分析。
核心逻辑：
1. 将烟囱离散为多段等截面梁单元
2. 模拟切口：在指定高度移除单元，形成偏心
3. 计算偏心自重矩作用的倾覆/抗倾覆力矩比

参考标准：GB 50051-2013 烟囱设计规范
"""

import math
import logging
from typing import Optional
from core.models import ChimneyModel, ChimneyStabilityReport, ChimneySegment

logger = logging.getLogger(__name__)

GRAVITY = 9.81  # m/s²

# 混凝土密度映射 (kg/m³)
DENSITY_MAP = {
    "C30": 2400, "C35": 2400, "C40": 2450,
    "C45": 2450, "C50": 2500,
}

# 混凝土抗压强度 (MPa)
FC_MAP = {
    "C30": 20.1, "C35": 23.4, "C40": 26.8,
    "C45": 29.6, "C50": 32.4,
}


class ChimneyQuickAnalyzer:
    """烟囱快速力学分析器

    基于变截面悬臂梁模型，快速计算切口形成后的：
    - 倾覆力矩
    - 抗倾覆力矩
    - 稳定系数
    - 切口处最大应力
    """

    def __init__(self, discretization_steps: int = 20):
        """
        Args:
            discretization_steps: 高度方向离散步数
        """
        self._steps = discretization_steps

    # =========================================================================
    # 主分析接口
    # =========================================================================

    def analyze_stability(
        self,
        model: ChimneyModel,
        notch_height: Optional[float] = None,
    ) -> ChimneyStabilityReport:
        """分析切口后的稳定性

        Args:
            model: 烟囱模型
            notch_height: 切口高度 (m)，如不指定则使用模型默认值

        Returns:
            稳定性报告
        """
        nh = notch_height if notch_height is not None else model.notch_height
        if nh <= 0:
            nh = model.total_height * 0.1  # 默认 10% 高度处

        # 确保切口高度合理
        nh = max(0.5, min(nh, model.total_height * 0.4))

        warnings = []

        # 1. 计算上部结构 (切口以上) 的重量和重心
        top_mass, top_arm, top_error = self._calc_top_section(
            model, nh
        )
        if top_error:
            warnings.append(top_error)

        if top_mass <= 0:
            return ChimneyStabilityReport(
                model_id=model.model_id,
                notch_height=nh,
                overturning_moment=0,
                resisting_moment=0,
                stability_ratio=1.0,
                is_stable=False,
                max_stress=0,
                warnings=["切口以上结构无质量，无法分析"] + warnings,
            )

        # 2. 计算下部结构 (切口以下) 的重量和重心
        bottom_mass, bottom_arm, bottom_error = self._calc_bottom_section(
            model, nh
        )
        if bottom_error:
            warnings.append(bottom_error)

        # 3. 计算截面特性
        notch_od = self._get_diameter_at_height(model, nh)
        if notch_od <= 0:
            notch_od = model.base_diameter

        wall_t = self._get_wall_thickness_at_height(model, nh)
        if wall_t <= 0:
            wall_t = 0.3

        # 4. 计算偏心距
        eccentricity = notch_od * 0.3  # 切口导致重心偏心

        # 5. 倾覆力矩: 上部结构重量 × 偏心距
        # 转换为 kN·m
        top_weight_kn = top_mass * GRAVITY / 1000
        overturning_moment = top_weight_kn * eccentricity

        # 6. 抗倾覆力矩: 下部结构自重稳定
        # 下部结构重量 × 底部半径 (悬臂梁根部抗倾覆)
        bottom_weight_kn = bottom_mass * GRAVITY / 1000
        root_radius = notch_od / 2  # 切口处半径
        resisting_moment = bottom_weight_kn * root_radius

        # 7. 稳定系数
        if overturning_moment < 0.01:
            stability_ratio = 999.0
        else:
            stability_ratio = resisting_moment / overturning_moment

        is_stable = stability_ratio >= 1.0

        # 8. 切口处应力计算
        max_stress = self._calc_notch_stress(
            top_weight_kn, notch_od, wall_t, stability_ratio
        )

        # 9. 初始倾斜角度
        if notch_od > 0:
            tipping_angle = math.degrees(eccentricity / notch_od)
        else:
            tipping_angle = 0.0

        if not is_stable:
            warnings.append(
                f"稳定系数 {stability_ratio:.2f} < 1.0，结构可能失稳"
            )
        if stability_ratio < 1.5:
            warnings.append(
                f"稳定系数 {stability_ratio:.2f} < 1.5，建议增加安全储备"
            )

        return ChimneyStabilityReport(
            model_id=model.model_id,
            notch_height=nh,
            overturning_moment=round(overturning_moment, 2),
            resisting_moment=round(resisting_moment, 2),
            stability_ratio=round(stability_ratio, 3),
            is_stable=is_stable,
            max_stress=round(max_stress, 2),
            tipping_angle=round(tipping_angle, 3),
            warnings=warnings,
        )

    # =========================================================================
    # 分段计算
    # =========================================================================

    def _calc_top_section(
        self, model: ChimneyModel, notch_height: float
    ) -> tuple[float, float, str]:
        """计算切口以上结构的总质量(kg)和重心距切口的高度(m)

        Returns:
            (mass_kg, arm_m, error_msg)
        """
        total_mass = 0.0
        total_moment = 0.0  # 相对于切口高度

        for seg in model.segments:
            if seg.bottom_elevation >= model.total_height - 0.01:
                continue
            if seg.top_elevation <= notch_height + 0.01:
                continue

            # 计算该段在切口以上的部分
            effective_bottom = max(seg.bottom_elevation, notch_height)
            effective_top = min(seg.top_elevation, model.total_height)

            if effective_top <= effective_bottom:
                continue

            seg_height = effective_top - effective_bottom

            # 该段在有效范围的平均直径
            avg_od_bottom = self._interp_diameter(seg, effective_bottom)
            avg_od_top = self._interp_diameter(seg, effective_top)
            avg_od = (avg_od_bottom + avg_od_top) / 2

            wt = seg.wall_thickness
            inner_od = avg_od - 2 * wt

            if inner_od <= 0:
                inner_od = avg_od * 0.7

            # 环形截面积
            area = math.pi / 4 * (avg_od**2 - inner_od**2)

            density = DENSITY_MAP.get(seg.material, 2450)

            seg_mass = area * seg_height * density  # kg

            # 重心距切口的高度 (中部)
            centroid_from_notch = (effective_bottom + effective_top) / 2 - notch_height

            total_mass += seg_mass
            total_moment += seg_mass * centroid_from_notch

        # 加入顶部附属结构质量
        for att in model.attachments:
            att_top = model.total_height
            att_bottom = att_top - att.height

            if att_bottom >= notch_height:
                att_area = math.pi / 4 * att.diameter**2
                steel_density = 7850
                att_mass = att_area * att.height * steel_density
                att_centroid = (att_bottom + att_top) / 2 - notch_height
                total_mass += att_mass
                total_moment += att_mass * att_centroid

        arm = total_moment / total_mass if total_mass > 0 else 0

        error = ""
        if total_mass <= 0:
            error = f"在高度 {notch_height}m 切口以上无有效结构"
        elif arm < 0.01:
            error = "上部结构重心距切口过近"

        return total_mass, arm, error

    def _calc_bottom_section(
        self, model: ChimneyModel, notch_height: float
    ) -> tuple[float, float, str]:
        """计算切口以下结构的总质量(kg)和重心距底部高度(m)

        Returns:
            (mass_kg, arm_m, error_msg)
        """
        total_mass = 0.0
        total_moment = 0.0

        for seg in model.segments:
            if seg.bottom_elevation >= notch_height:
                continue

            effective_top = min(seg.top_elevation, notch_height)
            effective_bottom = seg.bottom_elevation

            if effective_top <= effective_bottom:
                continue

            seg_height = effective_top - effective_bottom
            avg_od_bottom = self._interp_diameter(seg, effective_bottom)
            avg_od_top = self._interp_diameter(seg, effective_top)
            avg_od = (avg_od_bottom + avg_od_top) / 2

            wt = seg.wall_thickness
            inner_od = avg_od - 2 * wt
            if inner_od <= 0:
                inner_od = avg_od * 0.7

            area = math.pi / 4 * (avg_od**2 - inner_od**2)
            density = DENSITY_MAP.get(seg.material, 2450)
            seg_mass = area * seg_height * density

            centroid = (effective_bottom + effective_top) / 2
            total_mass += seg_mass
            total_moment += seg_mass * centroid

        arm = total_moment / total_mass if total_mass > 0 else 0

        error = ""
        if total_mass <= 0:
            error = f"在高度 {notch_height}m 切口以下无有效结构"

        return total_mass, arm, error

    # =========================================================================
    # 几何插值
    # =========================================================================

    def _interp_diameter(self, seg: ChimneySegment, elevation: float) -> float:
        """计算变截面段在指定标高的外径"""
        if seg.top_elevation <= seg.bottom_elevation:
            return seg.outer_diameter_bottom

        t = (elevation - seg.bottom_elevation) / (
            seg.top_elevation - seg.bottom_elevation
        )
        t = max(0.0, min(1.0, t))
        return (
            seg.outer_diameter_bottom
            + t * (seg.outer_diameter_top - seg.outer_diameter_bottom)
        )

    def _get_diameter_at_height(self, model: ChimneyModel, height: float) -> float:
        """获取指定高度的外径"""
        for seg in model.segments:
            if seg.bottom_elevation <= height <= seg.top_elevation:
                return self._interp_diameter(seg, height)

        # 超出范围
        if height < 0:
            return model.base_diameter
        return model.top_diameter

    def _get_wall_thickness_at_height(
        self, model: ChimneyModel, height: float
    ) -> float:
        """获取指定高度的壁厚"""
        for seg in model.segments:
            if seg.bottom_elevation <= height <= seg.top_elevation:
                return seg.wall_thickness

        if model.segments:
            return model.segments[0].wall_thickness
        return 0.3

    # =========================================================================
    # 应力计算
    # =========================================================================

    def _calc_notch_stress(
        self,
        top_weight_kn: float,
        diameter_m: float,
        wall_thickness_m: float,
        stability_ratio: float,
    ) -> float:
        """计算切口处由偏心自重引起的最大压应力 (MPa)"""
        if diameter_m <= 0 or wall_thickness_m <= 0:
            return 0.0

        # 截面面积 (环形)
        inner_d = diameter_m - 2 * wall_thickness_m
        if inner_d < 0:
            inner_d = 0
        area = math.pi / 4 * (diameter_m**2 - inner_d**2)

        if area <= 1e-6:
            return 0.0

        # 轴压应力
        axial_stress = top_weight_kn / area * 1000  # kN/m² → kPa

        # 弯曲应力 (由偏心矩引起)
        # 截面惯性矩
        outer_r = diameter_m / 2
        inner_r = inner_d / 2
        I = math.pi / 64 * (diameter_m**4 - inner_d**4)

        if I <= 1e-12:
            return axial_stress / 1000  # kPa → MPa

        eccentricity = diameter_m * 0.3
        moment = top_weight_kn * eccentricity  # kN·m
        bending_stress = moment * outer_r / I * 1000  # kN·m / m⁴ → kPa

        max_stress_kpa = abs(axial_stress) + abs(bending_stress)
        max_stress_mpa = max_stress_kpa / 1000  # kPa → MPa

        return max_stress_mpa
