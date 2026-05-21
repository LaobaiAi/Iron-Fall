"""OpenSeesPy 深度非线性分析

提供推覆分析 (Pushover)、塑性铰监控和详细报告生成。
作为"核威慑"级复核引擎，仅在关键步骤触发。
"""
import logging
import time
import math
from typing import Optional
from core.models import StructureModel, AnalysisResult, DemolitionAction

logger = logging.getLogger(__name__)

# ============================================================================
# 深度分析结果
# ============================================================================

class DeepAnalysisReport:
    """深度分析报告"""
    
    def __init__(self):
        self.timestamp = time.time()
        self.pushover_curve: list[tuple[float, float]] = []  # (displacement, base_shear)
        self.plastic_hinges: list[dict] = []
        self.max_drift_ratio: float = 0.0
        self.performance_point: Optional[tuple[float, float]] = None
        self.yield_sequence: list[int] = []  # element IDs in yield order
        self.collapse_displacement: float = float('inf')
        self.stability_assessment: str = ""
        self.warnings: list[str] = []
        
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "pushover_curve": self.pushover_curve[-10:],  # 只返回关键点
            "pushover_summary": {
                "initial_stiffness": self._calc_initial_stiffness(),
                "max_base_shear": max((s for _, s in self.pushover_curve), default=0),
                "max_displacement": max((d for d, _ in self.pushover_curve), default=0),
            },
            "plastic_hinges_count": len(self.plastic_hinges),
            "plastic_hinges": self.plastic_hinges[:10],
            "max_drift_ratio": self.max_drift_ratio,
            "performance_point": self.performance_point,
            "yield_sequence": self.yield_sequence[:20],
            "stability_assessment": self.stability_assessment,
            "warnings": self.warnings,
        }
    
    def _calc_initial_stiffness(self) -> float:
        if len(self.pushover_curve) < 2:
            return 0
        d1, s1 = self.pushover_curve[0]
        d2, s2 = self.pushover_curve[1]
        if abs(d2 - d1) < 1e-10:
            return 0
        return (s2 - s1) / (d2 - d1)


class OpenSeesDeepAnalyzer:
    """OpenSeesPy 深度分析器
    
    功能：
    - 推覆分析 (Pushover Analysis)
    - 塑性铰检测与跟踪
    - 荷载-位移曲线生成
    - 性能点评估
    """
    
    def __init__(self):
        self._available = self._check_opensees()
    
    @property
    def available(self) -> bool:
        return self._available
    
    def _check_opensees(self) -> bool:
        try:
            import openseespy.opensees as ops
            return True
        except ImportError:
            logger.warning("OpenSeesPy 未安装，深度分析不可用")
            return False
    
    # =========================================================================
    # 推覆分析
    # =========================================================================
    
    def run_pushover(
        self,
        model: StructureModel,
        max_drift: float = 0.04,  # 4% 层间位移角上限
        n_steps: int = 50
    ) -> DeepAnalysisReport:
        """执行推覆分析
        
        Args:
            model: 结构模型
            max_drift: 最大层间位移角
            n_steps: 分析步数
            
        Returns:
            DeepAnalysisReport
        """
        report = DeepAnalysisReport()
        
        if not self._available:
            report.warnings.append("OpenSeesPy 未安装，无法执行推覆分析")
            report.stability_assessment = "N/A - OpenSeesPy 不可用"
            return report
        
        try:
            import openseespy.opensees as ops
            
            # 清理模型
            ops.wipe()
            ops.model('basic', '-ndm', 3, '-ndf', 6)
            
            height = self._build_opensees_model(model, ops)
            if height == 0:
                report.stability_assessment = "无法构建 OpenSees 模型"
                return report
            
            # 推覆荷载模式: 倒三角分布
            self._apply_pushover_loads(model, ops)
            
            # 记录
            target_disp = max_drift * height
            step_disp = target_disp / n_steps
            
            for i in range(n_steps):
                disp = (i + 1) * step_disp
                
                try:
                    ok = ops.analyze(1)
                    if ok < 0:
                        report.warnings.append(f"推覆分析在第 {i+1} 步发散")
                        break
                except Exception:
                    report.warnings.append(f"推覆分析在第 {i+1} 步异常")
                    break
                
                # 提取结果
                current_disp = self._get_top_displacement(ops, model)
                base_shear = self._get_base_shear(ops, model)
                
                report.pushover_curve.append((current_disp, base_shear))
                
                # 检测塑性铰
                hinges = self._detect_plastic_hinges(ops, model)
                for h in hinges:
                    if h not in report.plastic_hinges:
                        report.plastic_hinges.append(h)
                        report.yield_sequence.append(h.get("element_id", 0))
            
            # 计算关键指标
            if report.pushover_curve:
                max_disp = max(d[0] for d in report.pushover_curve)
                report.max_drift_ratio = max_disp / height if height > 0 else 0
            
            report.stability_assessment = self._assess_stability(report)
            
            ops.wipe()
            
        except Exception as e:
            logger.error(f"推覆分析失败: {e}", exc_info=True)
            report.warnings.append(f"推覆分析错误: {str(e)}")
            report.stability_assessment = f"Error: {str(e)}"
        
        return report
    
    def _build_opensees_model(self, model: StructureModel, ops) -> float:
        """构建 OpenSees 模型，返回结构高度"""
        # 材料定义
        mat_id = 1
        E = 206e9  # Pa
        fy = 355e6  # Pa
        ops.uniaxialMaterial('Steel01', mat_id, fy, E, 0.02)
        
        # 截面定义 (纤维截面简化)
        sec_id = 1
        sec = model.sections[0] if model.sections else None
        if sec:
            A = sec.A / 1e6  # mm2 -> m2
            Iy = sec.Iy / 1e12  # mm4 -> m4
        else:
            A = 0.01
            Iy = 1e-4
        
        # 转换单位: m, N
        G = E / (2 * (1 + 0.3))
        J = (sec.J / 1e12) if sec else 1e-5
        
        ops.section('Elastic', sec_id, E, A, Iy, Iy, G, J)
        
        # 节点
        node_map = {}
        for node in model.nodes:
            ops.node(node.id, node.x, node.y, node.z)
            node_map[node.id] = node
        
        # 约束
        for node in model.nodes:
            if any(node.restraint[:3]):
                ops.fix(node.id, *[int(r) for r in node.restraint])
        
        # 构件
        coord_transf_id = 1
        ops.geomTransf('Linear', coord_transf_id, 0, 0, 1)
        
        for elem in model.elements:
            ops.element(
                'elasticBeamColumn', elem.id,
                elem.node_i_id, elem.node_j_id,
                A, E, G, J, Iy, Iy,
                coord_transf_id
            )
        
        # 质量 (用于地震分析)
        mass = 0
        for node in model.nodes:
            if node.z > 0.01:
                m = 5000  # kg per node (approx)
                ops.mass(node.id, m, m, m, 0, 0, 0)
                mass += m
        
        height = max(n.z for n in model.nodes) if model.nodes else 0
        return height
    
    def _apply_pushover_loads(self, model: StructureModel, ops):
        """施加推覆荷载"""
        max_z = max(n.z for n in model.nodes)
        total_height = max_z
        
        time_series_id = 1
        pattern_id = 1
        ops.timeSeries('Linear', time_series_id)
        ops.pattern('Plain', pattern_id, time_series_id)
        
        for node in model.nodes:
            if node.z > 0.01:
                # 倒三角分布
                factor = node.z / total_height if total_height > 0 else 1.0
                force = factor * 10000  # N
                ops.load(node.id, force, 0, 0, 0, 0, 0)
        
        # 分析设置
        ops.constraints('Transformation')
        ops.numberer('RCM')
        ops.system('BandGeneral')
        ops.test('NormDispIncr', 1.0e-6, 20, 0)
        ops.algorithm('Newton')
        ops.integrator('DisplacementControl', self._get_control_node(model), 1, 0.001)
        ops.analysis('Static')
    
    def _get_control_node(self, model: StructureModel) -> int:
        """获取控制节点（顶层角节点）"""
        max_z = max(n.z for n in model.nodes)
        top_nodes = [n for n in model.nodes if abs(n.z - max_z) < 0.01]
        if top_nodes:
            return min(top_nodes, key=lambda n: n.x + n.y).id
        return model.nodes[-1].id if model.nodes else 1
    
    def _get_top_displacement(self, ops, model: StructureModel) -> float:
        """获取顶层位移"""
        max_z = max(n.z for n in model.nodes)
        top_nodes = [n for n in model.nodes if abs(n.z - max_z) < 0.01]
        if top_nodes:
            disp = ops.nodeDisp(top_nodes[0].id, 1)  # X 方向
            return abs(disp)
        return 0.0
    
    def _get_base_shear(self, ops, model: StructureModel) -> float:
        """获取基底剪力"""
        base_reaction_x = 0.0
        for node in model.nodes:
            if node.z < 0.01:
                try:
                    rx = ops.nodeReaction(node.id, 1)
                    base_reaction_x += abs(rx)
                except Exception:
                    pass
        
        if base_reaction_x < 1e-10:
            return 1000.0  # 默认值
        return base_reaction_x
    
    def _detect_plastic_hinges(self, ops, model: StructureModel) -> list[dict]:
        """检测塑性铰"""
        hinges = []
        fy = 355e6  # Pa
        
        for elem in model.elements:
            try:
                forces = ops.eleForce(elem.id)
                if forces:
                    Fx = abs(forces[0])  # 轴力
                    My = abs(forces[5])  # 弯矩
                    
                    sec = model.sections[0] if model.sections else None
                    if sec:
                        A = sec.A / 1e6
                        W = sec.Iy / 1e12 / (0.2)  # 粗略截面模量
                    else:
                        A, W = 0.01, 1e-4
                    
                    axial_stress = Fx / A if A > 0 else 0
                    bending_stress = My / W if W > 0 else 0
                    total_stress = axial_stress + bending_stress
                    
                    if total_stress > fy * 0.8:  # 80% 屈服应力
                        hinges.append({
                            "element_id": elem.id,
                            "element_type": elem.element_type.value,
                            "axial_stress_MPa": axial_stress / 1e6,
                            "bending_stress_MPa": bending_stress / 1e6,
                            "utilization": total_stress / fy,
                            "status": "Yield" if total_stress > fy else "Approaching_Yield"
                        })
            except Exception:
                continue
        
        return hinges
    
    def _assess_stability(self, report: DeepAnalysisReport) -> str:
        """综合稳定性评估"""
        if not report.pushover_curve:
            return "无法评估"
        
        dr = report.max_drift_ratio
        n_hinges = len(report.plastic_hinges)
        
        if dr > 0.04 or n_hinges > 10:
            return "Critical - 结构接近倒塌"
        elif dr > 0.02 or n_hinges > 5:
            return "Damaged - 显著损伤"
        elif dr > 0.01 or n_hinges > 0:
            return "Minor_Damage - 轻微损伤"
        else:
            return "Elastic - 弹性阶段"


# ============================================================================
# 便捷函数
# ============================================================================

def create_deep_analysis_report(
    model: StructureModel,
    action: Optional[DemolitionAction] = None
) -> dict:
    """执行深度分析并生成报告（便捷函数）"""
    analyzer = OpenSeesDeepAnalyzer()
    
    if not analyzer.available:
        return {
            "success": False,
            "message": "OpenSeesPy 未安装",
            "report": None
        }
    
    if action:
        # 拆除后的模型
        modified = StructureModel(
            model_id=model.model_id,
            name=model.name,
            nodes=model.nodes,
            elements=[e for e in model.elements if e.id not in action.target_element_ids],
            sections=model.sections,
            materials=model.materials
        )
        target = modified
    else:
        target = model
    
    report = analyzer.run_pushover(target, max_drift=0.04, n_steps=50)
    
    return {
        "success": True,
        "report": report.to_dict(),
        "summary": report.stability_assessment
    }
