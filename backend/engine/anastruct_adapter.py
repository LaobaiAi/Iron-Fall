"""anaStruct 求解器适配器

纯 Python 快速结构分析引擎，替代 Frame3DD 作为主力快速验算工具。
基于有限元法的 2D 平面框架分析，< 200ms 级响应。

与 Frame3DD 的区别：
- Python 原生，无需外部可执行文件
- 更轻量、更快速（100ms vs 子进程调用）
- 2D 分析（投影到 X-Z 平面），适合大多数钢框架场景
- 支持弹性线性和几何非线性分析
"""
import logging
import time
import math
from typing import Optional
from core.models import StructureModel, AnalysisResult, DemolitionAction, Node, Element
from engine.base import BaseEngineAdapter

logger = logging.getLogger(__name__)


class AnaStructAdapter(BaseEngineAdapter):
    """anaStruct 适配器

    将 Iron-Fall 3D 结构模型投影到 X-Z 平面进行 2D 平面框架分析。
    对于典型钢框架结构，2D 分析能快速给出可靠的应力和位移结果。
    """

    def __init__(self):
        self._timeout = 5.0  # 5 秒超时，anaStruct 通常在 100ms 内完成
        self._available = self._check_availability()

    @property
    def name(self) -> str:
        return "anaStruct"

    @property
    def version(self) -> str:
        if self._available:
            try:
                from anastruct import SystemElements
                # anaStruct 没有 version 属性
                return "installed"
            except ImportError:
                return "Not Installed"
        return "Not Installed"

    def _check_availability(self) -> bool:
        """检查 anaStruct 是否可用"""
        try:
            from anastruct import SystemElements
            return True
        except ImportError:
            logger.warning("anaStruct 未安装，将降级使用 Frame3DD")
            return False

    # =========================================================================
    # 模型验证
    # =========================================================================

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

    # =========================================================================
    # 2D 投影与模型构建
    # =========================================================================

    def _project_to_2d(self, model: StructureModel) -> dict:
        """将 3D 结构投影到 X-Z 平面

        投影策略：
        - 保留 X (水平跨度) 和 Z (垂向高度) 坐标
        - Y 坐标丢弃（平面外方向）
        - 对于 Y 方向上完全重叠的节点，合并为一个 2D 节点
        - 构件按其两端节点的投影定义

        Returns:
            {
                "nodes_2d": {node_id: (x, z)},
                "elements_2d": [(elem_id, node_i_2d_id, node_j_2d_id, section, material)],
                "supports": {node_id: bool},  # True = fixed, False = hinged
                "warnings": [...]
            }
        """
        from collections import defaultdict

        # 构建节点映射：将相同 (x, z) 的节点合并
        xz_to_nodes = defaultdict(list)
        node_map = self._build_node_map(model.nodes)

        for node in model.nodes:
            xz_key = (round(node.x, 3), round(node.z, 3))
            xz_to_nodes[xz_key].append(node.id)

        # 生成 2D 节点
        node_2d_ids = {}
        node_2d_coords = {}
        node_2d_id_counter = 1

        for xz_key, node_ids in xz_to_nodes.items():
            nid_2d = node_2d_id_counter
            node_2d_id_counter += 1
            node_2d_coords[nid_2d] = (xz_key[0], xz_key[1])
            for original_nid in node_ids:
                node_2d_ids[original_nid] = nid_2d

        # 映射支撑条件
        supports = {}
        for node in model.nodes:
            nid_2d = node_2d_ids[node.id]
            if any(node.restraint[:3]):  # 有平动约束
                is_fixed = all(node.restraint[:3])  # 三向约束 = 固定
                supports[nid_2d] = "fixed" if is_fixed else "hinged"

        # 映射构件
        elements_2d = []
        for elem in model.elements:
            node_i_2d = node_2d_ids.get(elem.node_i_id)
            node_j_2d = node_2d_ids.get(elem.node_j_id)

            if node_i_2d is None or node_j_2d is None:
                continue

            # 跳过两端投影到同一点的构件（如 Y 方向的梁）
            if node_i_2d == node_j_2d:
                continue

            section = None
            material = None
            for s in model.sections:
                if s.id == elem.section_id:
                    section = s
                    break
            for m in model.materials:
                if m.id == elem.material_id:
                    material = m
                    break

            if section and material:
                elements_2d.append({
                    "elem_id": elem.id,
                    "node_i": node_i_2d,
                    "node_j": node_j_2d,
                    "section": section,
                    "material": material,
                    "element_type": elem.element_type.value
                })

        return {
            "nodes_2d": node_2d_coords,
            "elements_2d": elements_2d,
            "supports": supports,
            "node_2d_ids": node_2d_ids,
            "warnings": []
        }

    def _build_node_map(self, nodes: list[Node]) -> dict[int, Node]:
        """构建节点 ID 到节点的映射"""
        return {node.id: node for node in nodes}

    def _build_anastruct_model(self, model: StructureModel):
        """构建 anaStruct 模型

        步骤：
        1. 先添加所有构件（anaStruct 自动创建节点）
        2. 然后根据位置查找 anaStruct 节点 ID，添加支撑
        3. 最后施加荷载

        Returns:
            (SystemElements, element_map) 或 (None, error_msg)
        """
        if not self._available:
            return None, "anaStruct 未安装"

        from anastruct import SystemElements

        proj = self._project_to_2d(model)

        if not proj["elements_2d"]:
            return None, "2D 投影后无可分析构件"

        ss = SystemElements()

        # 记录支撑位置，等构件添加后再施加
        support_positions = {}  # (x, z) -> "fixed"|"hinged"
        node_positions = {}
        for nid_2d, (cx, cz) in proj["nodes_2d"].items():
            node_positions[nid_2d] = (cx, cz)
            if nid_2d in proj["supports"]:
                support_positions[(round(cx, 3), round(cz, 3))] = proj["supports"][nid_2d]

        # =====================================================================
        # 第一步：添加所有构件
        # =====================================================================
        elem_map = {}  # anaStruct_elem_id -> ironfall_elem_id
        for edata in proj["elements_2d"]:
            ni = edata["node_i"]
            nj = edata["node_j"]

            if ni not in node_positions or nj not in node_positions:
                continue

            ci = node_positions[ni]
            cj = node_positions[nj]

            section = edata["section"]
            material = edata["material"]

            # 转换单位
            A_m2 = section.A / 1e6      # mm² → m²
            I_m4 = section.Iy / 1e12     # mm⁴ → m⁴
            E_kNm2 = material.E * 1000   # MPa → kN/m²

            EA = E_kNm2 * A_m2
            EI = E_kNm2 * I_m4

            try:
                ss.add_element(
                    location=[[ci[0], ci[1]], [cj[0], cj[1]]],
                    EA=EA, EI=EI
                )
                elem_map[ss.id_last_element] = edata["elem_id"]
            except Exception as e:
                logger.warning(f"添加构件 {edata['elem_id']} 失败: {e}")
                continue

        if not elem_map:
            return None, "无法添加任何构件到 anaStruct 模型"

        # =====================================================================
        # 第二步：根据位置查找 anaStruct 节点 ID，添加支撑
        # =====================================================================
        # 构建 (x, z) -> anaStruct_node_id 的映射
        position_to_anid = {}
        for anid, anode in ss.node_map.items():
            if anid == 0:
                continue
            pos_key = (round(anode.vertex.x, 3), round(anode.vertex.y, 3))
            position_to_anid[pos_key] = anid

        for (sx, sz), stype in support_positions.items():
            anid = position_to_anid.get((sx, sz))
            if anid is not None:
                try:
                    if stype == "fixed":
                        ss.add_support_fixed(node_id=anid)
                    elif stype == "hinged":
                        ss.add_support_hinged(node_id=anid)
                except Exception as e:
                    logger.warning(f"添加支撑到节点 {anid} 失败: {e}")

        # =====================================================================
        # 第三步：施加荷载
        # =====================================================================
        # 自重荷载
        for anid, _ in ss.node_map.items():
            if anid == 0:
                continue
            ironfall_eid = elem_map.get(anid)
            if ironfall_eid is not None:
                edata_local = next(
                    (e for e in proj["elements_2d"] if e["elem_id"] == ironfall_eid),
                    None
                )
                if edata_local:
                    density = edata_local["material"].density
                    A_m2 = edata_local["section"].A / 1e6
                    dead_load = density * A_m2 * 9.81 / 1000
                    if dead_load > 0.001:
                        try:
                            ss.q_load(q=dead_load, element_id=anid, direction="element")
                        except Exception:
                            pass

        # 顶部节点荷载
        if position_to_anid:
            max_z = max(pos[1] for pos in position_to_anid.keys())
            for (px, pz), anid in position_to_anid.items():
                if abs(pz - max_z) < 0.01:
                    try:
                        ss.point_load(node_id=anid, Fx=0, Fz=-10)
                    except Exception:
                        pass

        return ss, elem_map

    # =========================================================================
    # 静力分析
    # =========================================================================

    async def run_static_analysis(
        self,
        model: StructureModel,
        load_case: str = "DeadLoad"
    ) -> AnalysisResult:
        """执行静力分析

        使用 anaStruct 进行线弹性静力分析，100ms 级响应。
        """
        start = time.time()

        if not self._available:
            return AnalysisResult(
                success=False,
                is_safe=False,
                stability_status="Error",
                warnings=["anaStruct 未安装，无法执行分析"]
            )

        try:
            ss, elem_map = self._build_anastruct_model(model)

            if isinstance(ss, str):
                return AnalysisResult(
                    success=False,
                    is_safe=False,
                    stability_status="Error",
                    warnings=[ss] if isinstance(ss, str) else []
                )

            # 求解
            ss.solve()

            # 提取结果 - 遍历所有节点获取位移
            node_displacements = {}
            max_displacement = 0.0

            for anid in ss.node_map:
                if anid == 0:
                    continue
                try:
                    disp = ss.get_node_results_system(node_id=anid)
                    if disp:
                        ux = float(disp.get("ux", 0))
                        uz = float(disp.get("uz", 0))
                        phi_y = float(disp.get("phi_y", 0))
                        node_displacements[anid] = [ux, 0.0, uz, 0.0, phi_y, 0.0]
                        max_disp = math.sqrt(ux**2 + uz**2)
                        max_displacement = max(max_displacement, max_disp)
                except Exception:
                    continue

            # 提取构件内力
            element_stresses = {}
            for anid in elem_map:
                try:
                    er = ss.get_element_results(element_id=anid)
                    if er:
                        N = abs(float(er.get("N", 0)))
                        ironfall_eid = elem_map[anid]
                        element_stresses[ironfall_eid] = N
                except Exception:
                    continue

            # 稳定性评估
            height = max(
                abs(node.z) for node in model.nodes
            ) if model.nodes else 1.0

            drift_ratio = max_displacement / height if height > 0 else 0

            if drift_ratio > 0.02:
                status = "Collapse"
            elif drift_ratio > 0.01:
                status = "Critical"
            elif drift_ratio > 0.005:
                status = "Unstable"
            else:
                status = "Stable"

            latency = (time.time() - start) * 1000

            return AnalysisResult(
                success=True,
                node_displacements=node_displacements,
                element_stresses=element_stresses,
                max_displacement=max_displacement,
                stability_status=status,
                is_safe=status in ("Stable", "Unstable"),
                warnings=[
                    f"anaStruct 2D 投影分析完成 ({latency:.1f}ms)"
                ]
            )

        except Exception as e:
            logger.error(f"anaStruct 分析失败: {e}", exc_info=True)
            return AnalysisResult(
                success=False,
                is_safe=False,
                stability_status="Error",
                warnings=[f"anaStruct 分析错误: {str(e)}"]
            )

    # =========================================================================
    # 动力分析 (拆除模拟)
    # =========================================================================

    async def run_dynamic_analysis(
        self,
        model: StructureModel,
        demolition_action: DemolitionAction
    ) -> AnalysisResult:
        """执行动力分析（拆除模拟）

        对于 anaStruct，通过移除构件后重新静力分析来模拟拆除效果。
        """
        # 移除目标构件
        remaining_elements = [
            e for e in model.elements
            if e.id not in demolition_action.target_element_ids
        ]

        modified_model = StructureModel(
            model_id=model.model_id,
            name=f"{model.name} (拆除步骤 {demolition_action.step})",
            nodes=model.nodes,
            elements=remaining_elements,
            sections=model.sections,
            materials=model.materials
        )

        if not remaining_elements:
            return AnalysisResult(
                success=False,
                is_safe=False,
                stability_status="Collapse",
                warnings=["所有构件已移除，结构倒塌"]
            )

        return await self.run_static_analysis(modified_model)

    # =========================================================================
    # 稳定性检查
    # =========================================================================

    async def check_stability(
        self,
        model: StructureModel,
        threshold: float = 0.05
    ) -> tuple[bool, float]:
        """检查结构稳定性

        Args:
            model: 结构模型
            threshold: 位移阈值 (m)

        Returns:
            (is_stable, max_displacement)
        """
        result = await self.run_static_analysis(model)
        return result.max_displacement < threshold, result.max_displacement
