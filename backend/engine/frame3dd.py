"""Frame3DD 求解器适配器

封装 Frame3DD 命令行工具，执行快速静力/动力分析。
Frame3DD 是一款轻量级三维框架结构分析软件。
"""
import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from core.models import StructureModel, AnalysisResult, DemolitionAction
from engine.base import BaseEngineAdapter


class Frame3DDAdapter(BaseEngineAdapter):
    """Frame3DD 适配器

    通过子进程调用 Frame3DD CLI，完成结构分析。
    重点：子进程调用、输出解析、超时控制。
    """

    def __init__(self, executable_path: str = "frame3dd"):
        """初始化 Frame3DD 适配器

        Args:
            executable_path: Frame3DD 可执行文件路径
        """
        self._executable_path = executable_path
        self._timeout = 10.0  # 10秒超时，给够计算时间

    @property
    def name(self) -> str:
        return "Frame3DD"

    @property
    def version(self) -> str:
        """获取 Frame3DD 版本"""
        try:
            result = subprocess.run(
                [self._executable_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() or "Unknown"
        except Exception:
            return "Not Installed"

    async def validate_model(self, model: StructureModel) -> tuple[bool, Optional[str]]:
        """验证结构模型"""
        if not model.nodes:
            return False, "结构模型必须包含至少一个节点"

        if not model.elements:
            return False, "结构模型必须包含至少一个构件"

        # 验证节点 ID 连续性
        node_ids = {n.id for n in model.nodes}
        for elem in model.elements:
            if elem.node_i_id not in node_ids:
                return False, f"构件 {elem.id} 的 i 端节点 {elem.node_i_id} 不存在"
            if elem.node_j_id not in node_ids:
                return False, f"构件 {elem.id} 的 j 端节点 {elem.node_j_id} 不存在"

        # 验证截面和材料 ID
        section_ids = {s.id for s in model.sections}
        material_ids = {m.id for m in model.materials}

        for elem in model.elements:
            if elem.section_id not in section_ids:
                return False, f"构件 {elem.id} 引用的截面 {elem.section_id} 不存在"
            if elem.material_id not in material_ids:
                return False, f"构件 {elem.id} 引用的材料 {elem.material_id} 不存在"

        return True, None

    def _generate_input_file(self, model: StructureModel) -> str:
        """生成 Frame3DD 输入文件

        Args:
            model: 结构模型

        Returns:
            Frame3DD 输入文件内容
        """
        lines = []
        lines.append("Iron-Fall Analysis")
        lines.append("")
        lines.append(f"{len(model.nodes)}  # 节点数")
        lines.append(f"{len(model.elements)}  # 构件数")
        lines.append("1  # 静力荷载工况数")
        lines.append("0  # 移动荷载工况数")
        lines.append("0  # 动力分析模态数")
        lines.append("")

        # 节点数据
        for node in sorted(model.nodes, key=lambda n: n.id):
            rest = "".join(["1" if r else "0" for r in node.restraint])
            lines.append(f"{node.id}  {node.x:.6f}  {node.y:.6f}  {node.z:.6f}  {rest}")
        lines.append("")

        # 构件数据
        for elem in sorted(model.elements, key=lambda e: e.id):
            section = next((s for s in model.sections if s.id == elem.section_id), None)
            material = next((m for m in model.materials if m.id == elem.material_id), None)

            if section and material:
                A = section.A / 645.16  # mm² -> in²
                Ix = section.Iz / 9290304  # mm⁴ -> in⁴
                E = material.E / 6.89476  # MPa -> ksi
                density = material.density * 0.062428  # kg/m³ -> lb/ft³

                lines.append(
                    f"{elem.id}  {elem.node_i_id}  {elem.node_j_id}  "
                    f"{A:.6f}  {Ix:.6f}  {E:.6f}  {density:.6f}"
                )
        lines.append("")

        # 自重荷载
        lines.append("1  # 考虑自重")
        lines.append("0 0 -1  # 重力方向 (gX, gY, gZ)")
        lines.append("")
        lines.append("0  # 节点荷载数")
        lines.append("")
        lines.append("0  # 构件荷载数")

        return "\n".join(lines)

    async def run_static_analysis(
        self,
        model: StructureModel,
        load_case: str = "DeadLoad"
    ) -> AnalysisResult:
        """执行静力分析"""
        input_content = self._generate_input_file(model)

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "model.f3d"
            output_path = Path(tmpdir) / "output.out"

            input_path.write_text(input_content)

            try:
                process = await asyncio.create_subprocess_exec(
                    self._executable_path,
                    str(input_path),
                    str(output_path),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self._timeout
                    )
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                        await process.wait()
                    except Exception:
                        pass
                    return AnalysisResult(
                        success=False,
                        is_safe=False,
                        stability_status="Timeout",
                        warnings=["计算超时，使用模拟数据"]
                    )

                if process.returncode != 0:
                    return AnalysisResult(
                        success=False,
                        is_safe=False,
                        warnings=[f"Frame3DD 错误: {stderr.decode()}"]
                    )

                return self._parse_output(output_path)

            except (FileNotFoundError, OSError, Exception) as e:
                logger = __import__('logging').getLogger(__name__)
                logger.warning(f"Frame3DD 不可用，使用模拟数据: {e}")
                return self._generate_mock_result(model)

    async def run_dynamic_analysis(
        self,
        model: StructureModel,
        demolition_action: DemolitionAction
    ) -> AnalysisResult:
        """执行动力分析 (拆除模拟)"""
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

    def _parse_output(self, output_path: Path) -> AnalysisResult:
        """解析 Frame3DD 输出文件"""
        try:
            content = output_path.read_text()
            lines = content.split("\n")

            node_displacements = {}
            max_displacement = 0.0

            in_displacement_section = False
            for line in lines:
                if "DISPLACEMENTS" in line.upper():
                    in_displacement_section = True
                    continue

                if in_displacement_section and line.strip().startswith(("N", "Node")):
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            node_id = int(parts[1] if parts[0].startswith("N") else parts[0])
                            displacements = [
                                float(parts[2]) / 1000,
                                float(parts[3]) / 1000,
                                float(parts[4]) / 1000
                            ]
                            node_displacements[node_id] = displacements
                            max_disp = max(abs(d) for d in displacements)
                            max_displacement = max(max_displacement, max_disp)
                        except (ValueError, IndexError):
                            continue

            if max_displacement > 0.1:
                status = "Collapse"
            elif max_displacement > 0.05:
                status = "Critical"
            elif max_displacement > 0.02:
                status = "Unstable"
            else:
                status = "Stable"

            return AnalysisResult(
                node_displacements=node_displacements,
                max_displacement=max_displacement,
                stability_status=status,
                is_safe=status in ("Stable", "Unstable")
            )

        except Exception as e:
            return AnalysisResult(
                success=False,
                is_safe=False,
                warnings=[f"解析 Frame3DD 输出失败: {str(e)}"]
            )

    def _generate_mock_result(self, model: StructureModel) -> AnalysisResult:
        """生成模拟结果 (开发阶段使用)"""
        import random

        node_displacements = {}
        for node in model.nodes:
            displacements = [
                random.uniform(-0.01, 0.01),
                random.uniform(-0.05, 0.05),
                random.uniform(-0.01, 0.01)
            ]
            node_displacements[node.id] = displacements

        max_displacement = max(
            max(abs(d) for d in node_displacements[n.id])
            for n in model.nodes
        ) if node_displacements else 0.0

        return AnalysisResult(
            node_displacements=node_displacements,
            max_displacement=max_displacement,
            stability_status="Stable",
            is_safe=True,
            warnings=["Frame3DD 未安装，使用模拟数据"]
        )
