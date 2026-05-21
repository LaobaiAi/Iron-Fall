"""V3.0 烟囱深部分析引擎 - 倾倒过程动力学

双层引擎：
1. OpenSeesPy 纤维模型 (N - 精细): FiberSection + dispBeamColumn，动力时程分析
2. 物理仿真降级 (L-1): 基于转动动力学的刚体倾倒模拟（无需 OpenSeesPy）

输出：倾倒轨迹、重心时程、触地速度、撞击力
"""

import math
import logging
from typing import Optional
from core.models import (
    ChimneyModel, ChimneyStabilityReport,
    ChimneyTrajectoryPoint, ChimneyDeepAnalysisReport
)
from engine.chimney_analyzer import ChimneyQuickAnalyzer

logger = logging.getLogger(__name__)

GRAVITY = 9.81  # m/s²


class ChimneyDeepAnalyzer:
    """烟囱深部分析引擎

    分析切口形成后烟囱的倾倒动力学全过程。
    优先使用 OpenSeesPy 精细模型，不可用时降级为刚体转动仿真。
    """

    def __init__(self):
        self._opensees_available = self._check_opensees()
        self._quick_analyzer = ChimneyQuickAnalyzer()

    @property
    def engine_name(self) -> str:
        return "OpenSeesPy-Fiber" if self._opensees_available else "RigidBody-Physics"

    def _check_opensees(self) -> bool:
        try:
            import openseespy.opensees as ops
            return True
        except ImportError:
            logger.warning("OpenSeesPy 未安装，使用刚体转动仿真")
            return False

    # =========================================================================
    # 主分析接口
    # =========================================================================

    def run_deep_analysis(
        self,
        model: ChimneyModel,
        notch_height: Optional[float] = None,
        time_step: float = 0.02,
        max_time: float = 15.0,
    ) -> ChimneyDeepAnalysisReport:
        """执行深部分析

        Args:
            model: 烟囱模型
            notch_height: 切口高度 (m)
            time_step: 时间步长 (s)，默认 50fps
            max_time: 最大模拟时间 (s)

        Returns:
            ChimneyDeepAnalysisReport
        """
        nh = notch_height if notch_height is not None else model.notch_height
        if nh <= 0:
            nh = model.total_height * 0.1

        nh = max(0.5, min(nh, model.total_height * 0.4))

        warnings = []

        # 1. 快速稳定性分析
        stability = self._quick_analyzer.analyze_stability(model, nh)

        # 2. 如果 OpenSeesPy 可用，使用纤维模型
        if self._opensees_available:
            report = self._run_opensees_analysis(
                model, nh, time_step, max_time, stability
            )
        else:
            # 3. 降级：刚体转动仿真
            report = self._run_rigid_body_simulation(
                model, nh, time_step, max_time, stability
            )
            warnings.append("OpenSeesPy 不可用，使用物理仿真降级分析")
            warnings.append(
                "建议安装 OpenSeesPy 以获得精细非线性结果: pip install openseespy"
            )

        report.warnings = warnings + stability.warnings
        return report

    # =========================================================================
    # OpenSeesPy 纤维模型分析 (N 级)
    # =========================================================================

    def _run_opensees_analysis(
        self,
        model: ChimneyModel,
        notch_height: float,
        time_step: float,
        max_time: float,
        stability: ChimneyStabilityReport,
    ) -> ChimneyDeepAnalysisReport:
        """OpenSeesPy 纤维模型动力时程分析"""
        try:
            import openseespy.opensees as ops

            ops.wipe()
            ops.model("basic", "-ndm", 3, "-ndf", 6)

            total_h = model.total_height
            n_elements = 20  # 离散为 20 个梁单元

            # 材料：混凝土纤维
            mat_concrete = 1
            mat_steel = 2
            fc = -26.8e6  # C40 抗压强度 (Pa)，负值表示受压
            eps_c0 = -0.002
            ops.uniaxialMaterial("Concrete01", mat_concrete, fc, eps_c0, -0.0035)

            fy_steel = 400e6
            E_steel = 200e9
            ops.uniaxialMaterial("Steel01", mat_steel, fy_steel, E_steel, 0.01)

            # 构建节点（沿高度离散）
            dh = total_h / n_elements
            nodes = []
            for i in range(n_elements + 1):
                z = i * dh
                node_id = i + 1
                ops.node(node_id, 0.0, 0.0, z)
                nodes.append(node_id)
                if i == 0:
                    ops.fix(node_id, 1, 1, 1, 1, 1, 1)

            # 构建纤维截面
            for i in range(n_elements):
                z_mid = (i + 0.5) * dh
                od = self._interp_diameter(model, z_mid)
                wt = self._interp_wall_thickness(model, z_mid)

                sec_tag = 100 + i
                self._build_fiber_section(ops, sec_tag, od, wt, mat_concrete, mat_steel)

                # 构件
                coord_tag = 200 + i
                ops.geomTransf("Linear", coord_tag, 1, 0, 0)

                ops.element(
                    "dispBeamColumn",
                    300 + i,
                    i + 1, i + 2,
                    coord_tag,
                    sec_tag,
                    5,  # 积分点
                    "-mass",
                )

            # 重力荷载
            ops.timeSeries("Linear", 1)
            ops.pattern("Plain", 1, 1)

            for i in range(1, len(nodes)):
                ops.load(nodes[i], 0, 0, -10000, 0, 0, 0)

            # 静力求解初始状态
            ops.system("BandGeneral")
            ops.numberer("RCM")
            ops.constraints("Transformation")
            ops.integrator("LoadControl", 1.0)
            ops.algorithm("Newton")
            ops.test("NormDispIncr", 1e-6, 10)
            ops.analysis("Static")

            ok = ops.analyze(1)
            if ok < 0:
                logger.warning("OpenSees 静力分析不收敛，降级仿真")
                ops.wipe()
                return self._run_rigid_body_simulation(
                    model, notch_height, time_step, max_time, stability
                )

            ops.loadConst("-time", 0.0)

            # 动力分析：释放切口处约束
            ops.wipeAnalysis()
            ops.constraints("Transformation")
            ops.numberer("RCM")
            ops.system("BandGeneral")
            ops.test("NormDispIncr", 1e-5, 20)
            ops.algorithm("Newton")
            ops.integrator("Newmark", 0.5, 0.25)
            ops.analysis("Transient")

            n_steps = int(max_time / time_step)
            trajectory = []
            impact_time = max_time
            impact_velocity = 0.0
            impact_force = 0.0

            for step in range(n_steps):
                t = (step + 1) * time_step
                ok = ops.analyze(1, time_step)

                top_node = nodes[-1]
                top_disp_x = ops.nodeDisp(top_node, 1)
                top_disp_z = ops.nodeDisp(top_node, 3)

                angle = math.degrees(math.atan2(abs(top_disp_x), top_disp_z)) if top_disp_z > 0.01 else 0

                vel_x = ops.nodeVel(top_node, 1)
                vel_z = ops.nodeVel(top_node, 3)
                ang_vel = abs(vel_x) / total_h if total_h > 0 else 0

                ke = 0.5 * 50000 * (vel_x**2 + vel_z**2)

                trajectory.append(ChimneyTrajectoryPoint(
                    time=round(t, 3),
                    angle=round(angle, 3),
                    angular_velocity=round(ang_vel, 3),
                    com_x=round(abs(top_disp_x * 0.5), 3),
                    com_z=round(top_disp_z * 0.5, 3),
                    kinetic_energy=round(ke, 2),
                ))

                if top_disp_z <= 0.01 or ok < 0:
                    impact_time = t
                    impact_velocity = math.sqrt(vel_x**2 + vel_z**2)
                    impact_force = 50000 * impact_velocity / 0.1 / 1000
                    break

            ops.wipe()

            return ChimneyDeepAnalysisReport(
                model_id=model.model_id,
                notch_height=notch_height,
                stability_report=stability,
                trajectory=trajectory,
                impact_time=round(impact_time, 3),
                impact_velocity=round(impact_velocity, 2),
                impact_force=round(impact_force, 2),
                fall_direction=model.notion_direction,
                engine_used="OpenSeesPy-Fiber",
            )

        except Exception as e:
            logger.warning(f"OpenSeesPy 分析异常: {e}，降级到物理仿真")
            try:
                import openseespy.opensees as ops
                ops.wipe()
            except Exception:
                pass
            return self._run_rigid_body_simulation(
                model, notch_height, time_step, max_time, stability
            )

    # =========================================================================
    # 刚体转动仿真 (L-1 降级)
    # =========================================================================

    def _run_rigid_body_simulation(
        self,
        model: ChimneyModel,
        notch_height: float,
        time_step: float,
        max_time: float,
        stability: ChimneyStabilityReport,
    ) -> ChimneyDeepAnalysisReport:
        """基于转动动力学的烟囱倾倒仿真

        简化假设：
        - 烟囱为刚体，绕切口下缘铰链旋转
        - 初始微倾角由偏心距导数
        - 重力提供倾覆力矩
        """
        total_h = model.total_height
        top_h = total_h - notch_height

        if top_h <= 0 or stability.overturning_moment < 0.01:
            return ChimneyDeepAnalysisReport(
                model_id=model.model_id,
                notch_height=notch_height,
                stability_report=stability,
                trajectory=[],
                impact_time=0,
                impact_velocity=0,
                impact_force=0,
                fall_direction=model.notion_direction,
                engine_used="RigidBody-Physics",
                warnings=["上部结构高度无效或倾覆力矩过小"],
            )

        # 上部结构质量
        top_mass_kg = (stability.overturning_moment * 1000) / (GRAVITY * 0.3 * (model.base_diameter))

        if top_mass_kg < 100:
            top_mass_kg = 5000

        # 上部结构重心距切口高度
        upper_cg = top_h * 0.55

        # 初始倾斜角 (来自稳定性分析)
        theta0 = math.radians(stability.tipping_angle) if stability.tipping_angle > 0.01 else 0.02

        # 模拟常量
        hinge_radius = notch_height

        trajectory = []
        impact_time = max_time
        impact_velocity = 0.0

        theta = theta0
        omega = 0.0
        dt = time_step

        n_steps = int(max_time / dt)
        for step in range(n_steps):
            t = step * dt

            # 重力倾覆力矩
            overturning_torque = top_mass_kg * GRAVITY * upper_cg * math.sin(theta)

            # 惯性矩 (近似为细杆绕端部)
            I = (1.0 / 3.0) * top_mass_kg * top_h**2

            # 角加速度
            alpha = overturning_torque / I if I > 0 else 0

            # 数值积分 (半隐式欧拉)
            omega += alpha * dt
            theta += omega * dt

            ang_vel = omega
            angle_deg = math.degrees(theta)

            # 重心位置
            com_x = hinge_radius + upper_cg * math.sin(theta)
            com_z = upper_cg * math.cos(theta)

            # 动能
            ke = 0.5 * I * omega**2

            trajectory.append(ChimneyTrajectoryPoint(
                time=round(t, 3),
                angle=round(angle_deg, 2),
                angular_velocity=round(ang_vel, 3),
                com_x=round(com_x, 3),
                com_z=round(com_z, 3),
                kinetic_energy=round(ke, 2),
            ))

            # 触地条件
            if theta >= math.pi / 2 or com_z <= 0:
                impact_time = t
                impact_velocity = omega * total_h
                break

        # 撞击力估计
        if impact_time > 0:
            contact_duration = 0.1
            impact_force_kn = top_mass_kg * impact_velocity / contact_duration / 1000
        else:
            impact_force_kn = 0

        return ChimneyDeepAnalysisReport(
            model_id=model.model_id,
            notch_height=notch_height,
            stability_report=stability,
            trajectory=trajectory,
            impact_time=round(impact_time, 3),
            impact_velocity=round(impact_velocity, 2),
            impact_force=round(impact_force_kn, 2),
            fall_direction=model.notion_direction,
            engine_used="RigidBody-Physics",
        )

    # =========================================================================
    # 辅助方法
    # =========================================================================

    def _build_fiber_section(
        self, ops, sec_tag: int, diameter: float, wall_thickness: float,
        mat_concrete: int, mat_steel: int
    ):
        """构建环形纤维截面"""
        outer_r = diameter / 2
        inner_r = max(0, outer_r - wall_thickness)

        ops.section("Fiber", sec_tag)

        # 混凝土环
        n_circum = 32
        n_radial = 4

        for ri in range(n_radial):
            r = inner_r + (ri + 0.5) * (outer_r - inner_r) / n_radial
            dr = (outer_r - inner_r) / n_radial
            ring_area = 2 * math.pi * r * dr / n_circum

            for ci in range(n_circum):
                angle = 2 * math.pi * ci / n_circum
                y = r * math.cos(angle)
                z = r * math.sin(angle)
                ops.fiber(y, z, ring_area, mat_concrete)

        # 纵向钢筋
        rebar_area = 0.001  # 每根钢筋
        n_rebars = 16
        r_rebar = outer_r * 0.85

        for i in range(n_rebars):
            angle = 2 * math.pi * i / n_rebars
            y = r_rebar * math.cos(angle)
            z = r_rebar * math.sin(angle)
            ops.fiber(y, z, rebar_area, mat_steel)

    def _interp_diameter(self, model: ChimneyModel, height: float) -> float:
        """插值获取直径"""
        for seg in model.segments:
            if seg.bottom_elevation <= height <= seg.top_elevation:
                t = (height - seg.bottom_elevation) / (seg.top_elevation - seg.bottom_elevation) if seg.top_elevation > seg.bottom_elevation else 0
                t = max(0, min(1, t))
                return seg.outer_diameter_bottom + t * (seg.outer_diameter_top - seg.outer_diameter_bottom)
        return model.top_diameter

    def _interp_wall_thickness(self, model: ChimneyModel, height: float) -> float:
        """插值获取壁厚"""
        for seg in model.segments:
            if seg.bottom_elevation <= height <= seg.top_elevation:
                return seg.wall_thickness
        if model.segments:
            return model.segments[0].wall_thickness
        return 0.3
