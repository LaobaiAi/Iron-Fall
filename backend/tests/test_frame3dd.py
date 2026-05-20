"""Frame3DD 输出解析测试"""
import pytest
import sys
from pathlib import Path

# 添加 backend 目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import StructureModel, Node, Element, Section, Material, ElementType
from engine.frame3dd import Frame3DDAdapter


class TestFrame3DDAdapter:
    """Frame3DD 适配器测试类"""

    @pytest.fixture
    def simple_model(self) -> StructureModel:
        """创建一个简单的3层钢框架模型"""
        # 截面
        section = Section(
            id=1,
            name="H400x200",
            A=10000,  # mm²
            Iy=2.5e8,  # mm⁴
            Iz=3.3e8,  # mm⁴
            J=1.0e7   # mm⁴
        )
        
        # 材料
        material = Material(
            id=1,
            name="Q355",
            E=206000,  # MPa
            fy=355,    # MPa
            density=7850  # kg/m³
        )
        
        # 节点 (3x3x3 框架)
        nodes = []
        node_id = 1
        
        for z in [0, 3, 6]:  # 3层
            for y in [0, 5]:  # 2跨
                for x in [0, 6]:  # 2开间
                    restraint = [True, True, True, False, False, False] if z == 0 else [False]*6
                    nodes.append(Node(
                        id=node_id,
                        x=x, y=y, z=z,
                        restraint=restraint
                    ))
                    node_id += 1
        
        # 构件
        elements = []
        elem_id = 1
        
        # 底层柱 (z=0 to z=3)
        for y in [0, 5]:
            for x in [0, 6]:
                elements.append(Element(
                    id=elem_id,
                    node_i_id=1 + (y//5)*2,
                    node_j_id=1 + (y//5)*2 + 4,
                    section_id=1,
                    material_id=1,
                    element_type=ElementType.COLUMN
                ))
                elem_id += 1
        
        return StructureModel(
            model_id="test_3x3_frame",
            name="Test 3x3 Steel Frame",
            nodes=nodes,
            elements=elements,
            sections=[section],
            materials=[material]
        )

    @pytest.fixture
    def adapter(self) -> Frame3DDAdapter:
        """创建 Frame3DD 适配器实例"""
        return Frame3DDAdapter()

    def test_adapter_initialization(self, adapter):
        """测试适配器初始化"""
        assert adapter.name == "Frame3DD"
        assert adapter._timeout == 2.0

    @pytest.mark.asyncio
    async def test_validate_model_success(self, adapter, simple_model):
        """测试模型验证成功"""
        is_valid, error = await adapter.validate_model(simple_model)
        assert is_valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_model_empty_nodes(self, adapter):
        """测试空节点模型验证失败"""
        model = StructureModel(model_id="empty", name="Empty Model")
        is_valid, error = await adapter.validate_model(model)
        assert is_valid is False
        assert "至少一个节点" in error

    @pytest.mark.asyncio
    async def test_validate_model_empty_elements(self, adapter):
        """测试空构件模型验证失败"""
        model = StructureModel(
            model_id="no_elements",
            name="No Elements",
            nodes=[Node(id=1, x=0, y=0, z=0)]
        )
        is_valid, error = await adapter.validate_model(model)
        assert is_valid is False
        assert "至少一个构件" in error

    @pytest.mark.asyncio
    async def test_validate_model_invalid_node_reference(self, adapter):
        """测试无效节点引用"""
        model = StructureModel(
            model_id="invalid_ref",
            name="Invalid Node Reference",
            nodes=[Node(id=1, x=0, y=0, z=0)],
            elements=[Element(
                id=1,
                node_i_id=1,
                node_j_id=999,  # 不存在的节点
                section_id=1,
                material_id=1,
                element_type=ElementType.COLUMN
            )],
            sections=[Section(id=1, name="H400", A=10000, Iy=1e8, Iz=1e8, J=1e6)],
            materials=[Material(id=1, name="Q355", E=206000, fy=355, density=7850)]
        )
        is_valid, error = await adapter.validate_model(model)
        assert is_valid is False
        assert "不存在" in error

    @pytest.mark.asyncio
    async def test_run_static_analysis(self, adapter, simple_model):
        """测试静力分析"""
        result = await adapter.run_static_analysis(simple_model)
        
        # 验证返回结构
        assert hasattr(result, "node_displacements")
        assert hasattr(result, "max_displacement")
        assert hasattr(result, "stability_status")
        assert hasattr(result, "is_safe")
        
        # 验证位移数据
        assert isinstance(result.node_displacements, dict)
        
        # 验证状态
        assert result.stability_status in ["Stable", "Unstable", "Critical", "Collapse"]

    @pytest.mark.asyncio
    async def test_check_stability(self, adapter, simple_model):
        """测试稳定性检查"""
        is_stable, max_disp = await adapter.check_stability(simple_model)
        
        assert isinstance(is_stable, bool)
        assert isinstance(max_disp, float)
        assert max_disp >= 0

    def test_generate_input_file(self, adapter, simple_model):
        """测试输入文件生成"""
        content = adapter._generate_input_file(simple_model)
        
        # 验证基本结构
        assert "Iron-Fall Analysis" in content
        assert str(len(simple_model.nodes)) in content
        assert str(len(simple_model.elements)) in content
        
        # 验证节点数据
        assert "0.000000" in content  # 坐标精度
        
        # 验证构件数据
        assert "645.16" in content  # 单位转换


class TestModels:
    """数据模型测试类"""

    def test_node_creation(self):
        """测试节点创建"""
        node = Node(id=1, x=0.0, y=0.0, z=0.0)
        assert node.id == 1
        assert node.x == 0.0
        assert len(node.restraint) == 6

    def test_node_default_restraint(self):
        """测试节点默认约束"""
        node = Node(id=1, x=0, y=0, z=0)
        # 默认: 底部固定
        assert node.restraint[:3] == [True, True, True]
        assert node.restraint[3:] == [False, False, False]

    def test_element_creation(self):
        """测试构件创建"""
        elem = Element(
            id=1,
            node_i_id=1,
            node_j_id=2,
            section_id=1,
            material_id=1,
            element_type=ElementType.COLUMN
        )
        assert elem.element_type == ElementType.COLUMN

    def test_structure_model(self):
        """测试结构模型"""
        model = StructureModel(
            model_id="test",
            name="Test Model",
            nodes=[Node(id=1, x=0, y=0, z=0)],
            elements=[Element(
                id=1, node_i_id=1, node_j_id=2,
                section_id=1, material_id=1,
                element_type=ElementType.BEAM
            )]
        )
        assert len(model.nodes) == 1
        assert len(model.elements) == 1
