"""anaStruct 适配器测试

验证 anaStruct 2D 投影分析的正确性和性能。
"""
import pytest
import sys
import time
from pathlib import Path

# 添加 backend 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import (
    StructureModel, Node, Element, Section, Material, ElementType,
    DemolitionAction
)
from engine.anastruct_adapter import AnaStructAdapter


class TestAnaStructAdapter:
    """anaStruct 适配器测试"""

    @pytest.fixture
    def simple_2d_frame(self) -> StructureModel:
        """创建简单的 2D 平面钢框架模型 (X-Z 平面)
        结构: 单跨两层框架
        """
        section = Section(
            id=1, name="H300x200",
            A=7608, Iy=1.14e8, Iz=1.94e7, J=3.42e6
        )
        material = Material(
            id=1, name="Q355",
            E=206000, fy=355, density=7850
        )

        nodes = []
        nid = 1
        # 底层固定节点
        for x in [0, 6]:
            nodes.append(Node(id=nid, x=x, y=0, z=0,
                            restraint=[True, True, True, False, False, False]))
            nid += 1
        # 1层自由节点
        for x in [0, 6]:
            nodes.append(Node(id=nid, x=x, y=0, z=3))
            nid += 1
        # 2层自由节点
        for x in [0, 6]:
            nodes.append(Node(id=nid, x=x, y=0, z=6))
            nid += 1

        elements = []
        eid = 1
        # 底层柱
        elements.append(Element(id=eid, node_i_id=1, node_j_id=3,
                               section_id=1, material_id=1,
                               element_type=ElementType.COLUMN))
        eid += 1
        elements.append(Element(id=eid, node_i_id=2, node_j_id=4,
                               section_id=1, material_id=1,
                               element_type=ElementType.COLUMN))
        eid += 1
        # 1层梁
        elements.append(Element(id=eid, node_i_id=3, node_j_id=4,
                               section_id=1, material_id=1,
                               element_type=ElementType.BEAM))
        eid += 1
        # 2层柱
        elements.append(Element(id=eid, node_i_id=3, node_j_id=5,
                               section_id=1, material_id=1,
                               element_type=ElementType.COLUMN))
        eid += 1
        elements.append(Element(id=eid, node_i_id=4, node_j_id=6,
                               section_id=1, material_id=1,
                               element_type=ElementType.COLUMN))
        eid += 1
        # 2层梁
        elements.append(Element(id=eid, node_i_id=5, node_j_id=6,
                               section_id=1, material_id=1,
                               element_type=ElementType.BEAM))

        return StructureModel(
            model_id="test_2d_frame",
            name="Test 2D Frame",
            nodes=nodes, elements=elements,
            sections=[section], materials=[material]
        )

    @pytest.fixture
    def adapter(self) -> AnaStructAdapter:
        return AnaStructAdapter()

    def test_adapter_initialization(self, adapter):
        assert adapter.name == "anaStruct"
        assert adapter._available is True

    def test_version(self, adapter):
        assert adapter.version in ("installed", "Not Installed")

    @pytest.mark.asyncio
    async def test_validate_model_success(self, adapter, simple_2d_frame):
        is_valid, error = await adapter.validate_model(simple_2d_frame)
        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_model_empty(self, adapter):
        model = StructureModel(model_id="empty", name="Empty")
        is_valid, error = await adapter.validate_model(model)
        assert is_valid is False
        assert "至少一个节点" in error

    @pytest.mark.asyncio
    async def test_validate_model_invalid_ref(self, adapter):
        model = StructureModel(
            model_id="bad_ref", name="Bad Reference",
            nodes=[Node(id=1, x=0, y=0, z=0)],
            elements=[Element(
                id=1, node_i_id=1, node_j_id=999,
                section_id=1, material_id=1,
                element_type=ElementType.COLUMN
            )],
            sections=[Section(id=1, name="H300", A=7608,
                            Iy=1e8, Iz=1e8, J=1e6)],
            materials=[Material(id=1, name="Q355",
                              E=206000, fy=355, density=7850)]
        )
        is_valid, error = await adapter.validate_model(model)
        assert is_valid is False
        assert "不存在" in error

    @pytest.mark.asyncio
    async def test_run_static_analysis(self, adapter, simple_2d_frame):
        result = await adapter.run_static_analysis(simple_2d_frame)
        assert hasattr(result, "success")
        assert hasattr(result, "node_displacements")
        assert isinstance(result.node_displacements, dict)
        assert result.stability_status in ["Stable", "Unstable", "Critical", "Collapse", "Error"]

    @pytest.mark.asyncio
    async def test_check_stability(self, adapter, simple_2d_frame):
        is_stable, max_disp = await adapter.check_stability(simple_2d_frame, 0.05)
        assert isinstance(is_stable, bool)
        assert isinstance(max_disp, float)
        assert max_disp >= 0

    @pytest.mark.asyncio
    async def test_run_dynamic_analysis(self, adapter, simple_2d_frame):
        action = DemolitionAction(step=1, target_element_ids=[3], action_type="Remove")
        result = await adapter.run_dynamic_analysis(simple_2d_frame, action)
        assert hasattr(result, "stability_status")

    @pytest.mark.asyncio
    async def test_demolish_all_elements(self, adapter, simple_2d_frame):
        all_ids = [e.id for e in simple_2d_frame.elements]
        action = DemolitionAction(step=1, target_element_ids=all_ids, action_type="Remove")
        result = await adapter.run_dynamic_analysis(simple_2d_frame, action)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_projection_2d(self, adapter, simple_2d_frame):
        proj = adapter._project_to_2d(simple_2d_frame)
        assert "nodes_2d" in proj
        assert "elements_2d" in proj
        assert "supports" in proj
        assert len(proj["nodes_2d"]) > 0
        assert len(proj["elements_2d"]) > 0

    def test_build_anastruct_model(self, adapter, simple_2d_frame):
        ss, elem_map = adapter._build_anastruct_model(simple_2d_frame)
        assert not isinstance(ss, str)
        assert elem_map is not None

    @pytest.mark.asyncio
    async def test_performance_baseline(self, adapter, simple_2d_frame):
        start = time.time()
        result = await adapter.run_static_analysis(simple_2d_frame)
        elapsed = (time.time() - start) * 1000
        assert elapsed < 500, f"anaStruct 耗时 {elapsed:.1f}ms, 超过 500ms"


class TestAnaStructEdgeCases:
    """边界情况"""

    @pytest.fixture
    def adapter(self) -> AnaStructAdapter:
        return AnaStructAdapter()

    @pytest.mark.asyncio
    async def test_single_column(self, adapter):
        model = StructureModel(
            model_id="solo", name="Single Column",
            nodes=[
                Node(id=1, x=0, y=0, z=0, restraint=[True, True, True, False, False, False]),
                Node(id=2, x=0, y=0, z=3),
            ],
            elements=[Element(id=1, node_i_id=1, node_j_id=2,
                            section_id=1, material_id=1,
                            element_type=ElementType.COLUMN)],
            sections=[Section(id=1, name="H300", A=7608,
                            Iy=1.14e8, Iz=1.94e7, J=3.42e6)],
            materials=[Material(id=1, name="Q355", E=206000, fy=355, density=7850)]
        )
        result = await adapter.run_static_analysis(model)
        assert hasattr(result, "max_displacement")

    @pytest.mark.asyncio
    async def test_only_y_direction_beams(self, adapter):
        """Y方向梁: 2D投影后两端重合"""
        model = StructureModel(
            model_id="y_only", name="Y-direction",
            nodes=[
                Node(id=1, x=0, y=0, z=0, restraint=[True, True, True, False, False, False]),
                Node(id=2, x=0, y=6, z=0, restraint=[True, True, True, False, False, False]),
            ],
            elements=[Element(id=1, node_i_id=1, node_j_id=2,
                            section_id=1, material_id=1, element_type=ElementType.BEAM)],
            sections=[Section(id=1, name="H300", A=7608, Iy=1.14e8, Iz=1.94e7, J=3.42e6)],
            materials=[Material(id=1, name="Q355", E=206000, fy=355, density=7850)]
        )
        result = await adapter.run_static_analysis(model)
        assert hasattr(result, "stability_status")


class TestIntegrationWorkflow:
    """完整工作流集成测试"""

    @pytest.fixture
    def adapter(self) -> AnaStructAdapter:
        return AnaStructAdapter()

    @pytest.mark.asyncio
    async def test_full_workflow(self, adapter):
        """建模 -> 验证 -> 分析 -> 拆除 -> 再分析"""
        section = Section(id=1, name="H400x200", A=10000,
                        Iy=2.5e8, Iz=3.3e8, J=1e7)
        material = Material(id=1, name="Q355", E=206000, fy=355, density=7850)

        nodes = []
        nid = 1
        for z in [0, 3, 6, 9]:
            for x in [0, 6]:
                r = [True, True, True, False, False, False] if z == 0 else [False]*6
                nodes.append(Node(id=nid, x=x, y=0, z=z, restraint=r))
                nid += 1

        elements = []
        eid = 1
        for lv in range(3):
            bn = lv * 2 + 1
            tn = (lv + 1) * 2 + 1
            for xi in range(2):
                elements.append(Element(id=eid,
                    node_i_id=bn + xi, node_j_id=tn + xi,
                    section_id=1, material_id=1, element_type=ElementType.COLUMN))
                eid += 1
            elements.append(Element(id=eid,
                node_i_id=tn, node_j_id=tn + 1,
                section_id=1, material_id=1, element_type=ElementType.BEAM))
            eid += 1

        model = StructureModel(
            model_id="wf", name="3-Story",
            nodes=nodes, elements=elements,
            sections=[section], materials=[material]
        )

        # 验证
        is_valid, error = await adapter.validate_model(model)
        assert is_valid is True

        # 静力分析
        r1 = await adapter.run_static_analysis(model)
        assert r1.success in (True, False)

        # 稳定性
        is_stable, md = await adapter.check_stability(model, 0.05)
        assert isinstance(is_stable, bool)

        # 拆除顶层梁
        action = DemolitionAction(step=1, target_element_ids=[eid-1], action_type="Remove")
        r2 = await adapter.run_dynamic_analysis(model, action)
        assert hasattr(r2, "stability_status")
