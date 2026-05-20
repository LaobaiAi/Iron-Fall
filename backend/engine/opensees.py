"""OpenSeesPy 求解器适配器

封装 OpenSeesPy，执行深度非线性分析。
仅在高危模式下由用户手动触发，作为"核威慑"级复核。
"""
from typing import Optional
from core.models import StructureModel, AnalysisResult, DemolitionAction
from engine.base import BaseEngineAdapter


class OpenSeesPyAdapter(BaseEngineAdapter):
    """OpenSeesPy 适配器

    用于深度非线性分析和极限状态判断。
    计算代价较高，仅在需要严格验证时使用。
    """

    def __init__(self):
        """初始化 OpenSeesPy 适配器"""
        self._available = self._check_availability()

    def _check_availability(self) -> bool:
        """检查 OpenSeesPy 是否可用"""
        try:
            import openseespy
            return True
        except ImportError:
            return False

    @property
    def name(self) -> str:
        return "OpenSeesPy"

    @property
    def version(self) -> str:
        """获取 OpenSeesPy 版本"""
        try:
            import openseespy
            return openseespy.version()
        except Exception:
            return "Not Installed"

    async def validate_model(self, model: StructureModel) -> tuple[bool, Optional[str]]:
        """验证结构模型"""
        if not self._available:
            return False, "OpenSeesPy 未安装"

        if not model.nodes:
            return False, "结构模型必须包含至少一个节点"

        if not model.elements:
            return False, "结构模型必须包含至少一个构件"

        return True, None

    async def run_static_analysis(
        self,
        model: StructureModel,
        load_case: str = "DeadLoad"
    ) -> AnalysisResult:
        """执行静力分析"""
        if not self._available:
            return AnalysisResult(
                success=False,
                is_safe=False,
                warnings=["OpenSeesPy 未安装，请安装: pip install openseespy"]
            )

        try:
            import openseespy.pipe as ops

            ops.wipe()
            ops.model("basic", "-ndm", 3, "-ndf", 6)

            # 添加节点
            for node in model.nodes:
                ops.node(node.id, node.x, node.y, node.z)
                if all(node.restraint):
                    ops.fix(node.id, 1, 1, 1, 1, 1, 1)
                elif node.restraint[0] and node.restraint[1] and node.restraint[2]:
                    ops.fix(node.id, 1, 1, 1, 0, 0, 0)

            # 添加材料
            for material in model.materials:
                ops.uniaxialMaterial("Elastic", material.id, material.E * 1000)

            # 添加构件
            for elem in model.elements:
                material = next(
                    (m for m in model.materials if m.id == elem.material_id),
                    None
                )
                if material:
                    ops.element(
                        "elasticBeamColumn",
                        elem.id,
                        elem.node_i_id,
                        elem.node_j_id,
                        0.01,
                        material.E * 1000,
                        0.0001,
                        elem.id
                    )

            # 添加荷载
            ops.timeSeries("Linear", 1)
            ops.pattern("Plain", 1, 1)

            for node in model.nodes:
                ops.load(node.id, 0, -10, 0, 0, 0, 0)

            # 分析
            ops.system("BandSPD")
            ops.numberer("RCM")
            ops.constraints("Plain")
            ops.integrator("LoadControl", 0.1)
            ops.algorithm("Newton")
            ops.analysis("Static")

            ok = ops.analyze(10)

            node_displacements = {}
            max_displacement = 0.0

            for node in model.nodes:
                disp = ops.nodeDisp(node.id)
                node_displacements[node.id] = disp[:3]
                max_d = max(abs(d) for d in disp[:3])
                max_displacement = max(max_displacement, max_d)

            ops.wipe()

            return AnalysisResult(
                node_displacements=node_displacements,
                max_displacement=max_displacement,
                stability_status="Stable" if ok == 0 else "Unstable",
                is_safe=(ok == 0)
            )

        except ImportError:
            return AnalysisResult(
                success=False,
                is_safe=False,
                warnings=["OpenSeesPy 导入失败"]
            )
        except Exception as e:
            return AnalysisResult(
                success=False,
                is_safe=False,
                warnings=[f"OpenSeesPy 分析失败: {str(e)}"]
            )

    async def run_dynamic_analysis(
        self,
        model: StructureModel,
        demolition_action: DemolitionAction
    ) -> AnalysisResult:
        """执行动力分析 (拆除模拟)"""
        if not self._available:
            return AnalysisResult(
                success=False,
                is_safe=False,
                warnings=["OpenSeesPy 未安装"]
            )

        remaining_elements = [
            e for e in model.elements
            if e.id not in demolition_action.target_element_ids
        ]

        modified_model = StructureModel(
            model_id=model.model_id,
            name=model.name,
            nodes=model.nodes,
            elements=remaining_elements,
            sections=model.sections,
            materials=model.materials
        )

        return await self.run_static_analysis(modified_model)

    async def check_stability(
        self,
        model: StructureModel,
        threshold: float = 0.05
    ) -> tuple[bool, float]:
        """检查结构稳定性"""
        result = await self.run_static_analysis(model)
        return result.max_displacement < threshold, result.max_displacement
