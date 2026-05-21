"""AI 结构解析器测试

验证自然语言到 StructureModel 的解析精度。
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import StructureModel, ElementType
from agent.parser import StructureParser, create_structure_from_text


class TestStructureParser:
    """结构解析器核心测试"""

    @pytest.fixture
    def parser(self) -> StructureParser:
        return StructureParser()

    # -------------------------------------------------------------------------
    # 基础解析测试
    # -------------------------------------------------------------------------

    def test_parse_basic_3story(self, parser):
        """解析基础 3 层钢框架"""
        text = "建一个3层钢框架，跨度6m，层高3.6m"
        model = parser.parse(text)

        assert isinstance(model, StructureModel)
        assert model.nodes
        assert model.elements
        assert len(model.sections) > 0
        assert len(model.materials) > 0

    def test_parse_with_material(self, parser):
        """解析指定材料"""
        text = "Q355钢框架，3层，跨度6m"
        model = parser.parse(text)

        assert model.materials[0].name == "Q355"
        assert model.materials[0].fy == 355

    def test_parse_with_section(self, parser):
        """解析指定截面"""
        text = "H500x300钢框架，3层，跨度6m"
        model = parser.parse(text)

        assert model.sections[0].name == "H500x300"
        assert model.sections[0].A == 16350

    def test_parse_stories_number(self, parser):
        """解析层数"""
        assert parser.parse("5层框架").nodes  # 应有 6 层节点（含基础）
        assert parser.parse("10层钢框架").nodes

    # -------------------------------------------------------------------------
    # 复杂描述测试
    # -------------------------------------------------------------------------

    def test_parse_complex_description(self, parser):
        """解析复杂描述：层高+支撑+截面+材料"""
        text = ("建一个带X型斜撑的五层钢框架，首层高4.5m，"
                "标准层高3.6m，H400x200，Q355")
        model = parser.parse(text)

        assert len(model.nodes) > 0
        assert len(model.elements) > 0

        # 应有支撑构件
        braces = [e for e in model.elements if e.element_type == ElementType.BRACE]
        assert len(braces) > 0, "应包含 X 型斜撑"

        # 应包含柱和梁
        columns = [e for e in model.elements if e.element_type == ElementType.COLUMN]
        beams = [e for e in model.elements if e.element_type == ElementType.BEAM]
        assert len(columns) > 0
        assert len(beams) > 0

    def test_parse_multi_bay(self, parser):
        """解析多跨框架"""
        text = "3层2跨钢框架"
        model = parser.parse(text)

        # 2 跨 = 每层 3 列节点
        nodes_per_level = sum(
            1 for n in model.nodes if abs(n.z - 3.6) < 0.01
        )  # First floor nodes

        # 根据 Y 方向跨度
        assert len(model.nodes) > 0

    def test_parse_height_parameters(self, parser):
        """解析自定义层高"""
        text = "首层高5.0m，标准层高4.2m的三层钢框架"
        model = parser.parse(text)

        # 验证节点高度
        z_values = sorted(set(round(n.z, 1) for n in model.nodes))
        assert 0.0 in z_values, "应有基础节点 (z=0)"
        assert 5.0 in z_values, "首层高度应为 5.0m"

    # -------------------------------------------------------------------------
    # 参数提取测试
    # -------------------------------------------------------------------------

    def test_extract_stories(self, parser):
        params = parser._extract_parameters("5层钢框架")
        assert params["num_stories"] == 5

    def test_extract_defaults(self, parser):
        """未指定时使用默认值"""
        params = parser._extract_parameters("一个钢框架")
        assert params["num_stories"] == 3
        assert params["material_name"] == "Q355"
        assert params["section_name"] == "H400x200"

    def test_extract_brace_type(self, parser):
        """识别支撑类型"""
        params_x = parser._extract_parameters("带X型斜撑的框架")
        assert params_x["brace_type"] == "X"

        params_v = parser._extract_parameters("带V型支撑的框架")
        assert params_v["brace_type"] == "V"

    def test_extract_material_grade(self, parser):
        """识别材料等级"""
        for grade in ["Q235", "Q355", "Q390", "Q420"]:
            params = parser._extract_parameters(f"{grade}钢框架")
            assert params["material_name"] == grade

    # -------------------------------------------------------------------------
    # 模型构建测试
    # -------------------------------------------------------------------------

    def test_build_model_node_count(self, parser):
        """验证节点数量"""
        # 3 层 1 跨 = (3+1) * (1+1) * (1+1) = 4*2*2 = 16 节点
        params = {
            "num_stories": 3, "ground_height": 4.5,
            "typical_height": 3.6, "span_x": 6.0, "span_y": 6.0,
            "num_bays_x": 1, "num_bays_y": 1,
            "brace_type": None, "section_name": "H400x200",
            "material_name": "Q355"
        }
        model = parser._build_model(params, "test")
        expected = (3 + 1) * (1 + 1) * (1 + 1)  # 16
        assert len(model.nodes) == expected, \
            f"期望 {expected} 节点，实际 {len(model.nodes)}"

    def test_build_model_element_count(self, parser):
        """验证构件数量"""
        # 3 层 1 跨：每层 4 柱 + 2 梁 (X) + 2 梁 (Y) = 8
        # 总计: 3 * 8 = 24
        params = {
            "num_stories": 3, "ground_height": 4.5,
            "typical_height": 3.6, "span_x": 6.0, "span_y": 6.0,
            "num_bays_x": 1, "num_bays_y": 1,
            "brace_type": None, "section_name": "H400x200",
            "material_name": "Q355"
        }
        model = parser._build_model(params, "test")

        columns = len([e for e in model.elements if e.element_type == ElementType.COLUMN])
        beams = len([e for e in model.elements if e.element_type == ElementType.BEAM])

        # 每层: 4 柱 + 4 梁 = 8，3 层 = 24
        assert columns == 12, f"期望 12 柱，实际 {columns}"
        assert beams == 12, f"期望 12 梁，实际 {beams}"

    def test_build_model_with_brace(self, parser):
        """验证含支撑的模型"""
        params = {
            "num_stories": 3, "ground_height": 4.5,
            "typical_height": 3.6, "span_x": 6.0, "span_y": 6.0,
            "num_bays_x": 1, "num_bays_y": 1,
            "brace_type": "X", "section_name": "H400x200",
            "material_name": "Q355"
        }
        model = parser._build_model(params, "test")

        braces = [e for e in model.elements if e.element_type == ElementType.BRACE]
        assert len(braces) > 0, "X 型斜撑应生成支撑构件"


class TestCreateFromText:
    """便捷函数测试"""

    def test_create_basic(self):
        model = create_structure_from_text("3层钢框架，Q355")
        assert isinstance(model, StructureModel)
        assert model.materials[0].name == "Q355"


class TestIntegrationWithModel:
    """与数据模型的集成测试"""

    @pytest.fixture
    def parser(self) -> StructureParser:
        return StructureParser()

    def test_parsed_model_is_valid(self, parser):
        """解析的模型应通过基本验证"""
        model = parser.parse("5层Q355钢框架，跨度8m，H500x300")

        # 基本结构验证
        assert model.model_id == "nl_model"
        assert model.name
        assert len(model.nodes) > 0
        assert len(model.elements) > 0

        # 节点 ID 唯一性
        node_ids = [n.id for n in model.nodes]
        assert len(set(node_ids)) == len(node_ids), "节点 ID 应唯一"

        # 构件引用验证
        for elem in model.elements:
            assert elem.node_i_id in node_ids, \
                f"构件 {elem.id} 引用的节点 {elem.node_i_id} 不存在"
            assert elem.node_j_id in node_ids, \
                f"构件 {elem.id} 引用的节点 {elem.node_j_id} 不存在"

    def test_multiple_descriptions(self, parser):
        """测试多种描述变体"""
        descriptions = [
            "建一个3层Q355钢框架",
            "三层钢框架，首层高4.5米，标准层高3.6米",
            "5层2跨钢框架，带X型斜撑",
            "H400x200的Q355钢框架，跨度6米",
            "一个带斜撑的三层钢框架",
        ]

        for desc in descriptions:
            model = parser.parse(desc)
            assert isinstance(model, StructureModel), f"解析失败: {desc}"
            assert len(model.nodes) > 0, f"无节点: {desc}"
            assert len(model.elements) > 0, f"无构件: {desc}"
