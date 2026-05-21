"""拆除序列算法测试

验证基于图论的智能拆除序列生成正确性。
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import (
    StructureModel, Node, Element, Section, Material, ElementType
)
from engine.sequencer import DemolitionSequencer


class TestDemolitionSequencer:
    """拆除序列生成器测试"""

    @pytest.fixture
    def sample_model(self) -> StructureModel:
        """3层1跨钢框架"""
        section = Section(id=1, name="H400x200", A=10000,
                        Iy=2.5e8, Iz=3.3e8, J=1e7)
        material = Material(id=1, name="Q355", E=206000,
                          fy=355, density=7850)

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
                    section_id=1, material_id=1,
                    element_type=ElementType.COLUMN))
                eid += 1
            elements.append(Element(id=eid,
                node_i_id=tn, node_j_id=tn + 1,
                section_id=1, material_id=1,
                element_type=ElementType.BEAM))
            eid += 1

        return StructureModel(
            model_id="seq_test", name="3-Story Frame",
            nodes=nodes, elements=elements,
            sections=[section], materials=[material]
        )

    @pytest.fixture
    def sequencer(self) -> DemolitionSequencer:
        return DemolitionSequencer()

    def test_generate_sequence(self, sequencer, sample_model):
        """生成拆除序列"""
        plan = sequencer.generate_sequence(sample_model)

        assert plan.plan_id
        assert plan.description
        assert len(plan.actions) > 0
        assert plan.risk_level in ["Low", "Medium", "High", "Critical"]

    def test_sequence_covers_all_elements(self, sequencer, sample_model):
        """序列应覆盖所有构件"""
        plan = sequencer.generate_sequence(sample_model)

        removed = set()
        for action in plan.actions:
            removed.update(action.target_element_ids)

        expected = {e.id for e in sample_model.elements}
        assert removed == expected, f"缺少构件: {expected - removed}"

    def test_no_duplicate_removals(self, sequencer, sample_model):
        """不应重复拆除同一构件"""
        plan = sequencer.generate_sequence(sample_model)

        all_ids = []
        for action in plan.actions:
            all_ids.extend(action.target_element_ids)

        assert len(all_ids) == len(set(all_ids)), "存在重复拆除"

    def test_beam_before_column_principle(self, sequencer, sample_model):
        """梁应在同层柱之前被拆除"""
        plan = sequencer.generate_sequence(sample_model)

        # 记录每步拆了什么
        step_items = []
        for action in plan.actions:
            for eid in action.target_element_ids:
                elem = next((e for e in sample_model.elements if e.id == eid), None)
                if elem:
                    step_items.append((action.step, elem))

        # 统计：梁的平均拆除步骤应该小于柱
        beam_steps = [s for s, e in step_items if e.element_type == ElementType.BEAM]
        col_steps = [s for s, e in step_items if e.element_type == ElementType.COLUMN]

        if beam_steps and col_steps:
            avg_beam = sum(beam_steps) / len(beam_steps)
            avg_col = sum(col_steps) / len(col_steps)
            assert avg_beam < avg_col, \
                f"梁平均步骤({avg_beam})应小于柱({avg_col})"

    def test_top_down_principle(self, sequencer, sample_model):
        """上层构件应在下层之前被拆除"""
        plan = sequencer.generate_sequence(sample_model)

        # 按高度分组
        step_by_height = {}  # height_bucket -> [steps]
        for action in plan.actions:
            for eid in action.target_element_ids:
                elem = next((e for e in sample_model.elements if e.id == eid), None)
                if elem:
                    # 获取构件高度
                    nodes_z = []
                    for n in sample_model.nodes:
                        if n.id in (elem.node_i_id, elem.node_j_id):
                            nodes_z.append(n.z)
                    if nodes_z:
                        h = sum(nodes_z) / len(nodes_z)
                        bucket = int(h / 3)  # 每 3m 一个 bucket
                        if bucket not in step_by_height:
                            step_by_height[bucket] = []
                        step_by_height[bucket].append(action.step)

        # 验证：较高 bucket 的平均步骤应该小于较低 bucket
        buckets = sorted(step_by_height.keys())
        for i in range(len(buckets) - 1):
            hi_avg = sum(step_by_height[buckets[i + 1]]) / len(step_by_height[buckets[i + 1]])
            lo_avg = sum(step_by_height[buckets[i]]) / len(step_by_height[buckets[i]])
            assert hi_avg < lo_avg, \
                f"高层({buckets[i+1]})平均步骤({hi_avg})应 < 低层({buckets[i]})平均步骤({lo_avg})"

    def test_empty_model(self, sequencer):
        """空模型处理"""
        model = StructureModel(model_id="empty", name="Empty")
        plan = sequencer.generate_sequence(model)
        assert len(plan.actions) == 0

    def test_batch_size_limit(self, sequencer, sample_model):
        """每步不应超过批量限制"""
        plan = sequencer.generate_sequence(sample_model, max_elements_per_step=3)

        for action in plan.actions:
            assert len(action.target_element_ids) <= 3, \
                f"步骤 {action.step} 包含 {len(action.target_element_ids)} 个构件"

    def test_graph_build(self, sequencer, sample_model):
        """图构建"""
        sequencer._build_graph(sample_model)
        assert len(sequencer._adjacency) > 0
        assert len(sequencer._node_elements) > 0

    def test_priority_scores(self, sequencer, sample_model):
        """优先级分数计算"""
        sequencer._build_graph(sample_model)
        scores = sequencer._compute_priority_scores(sample_model)

        assert len(scores) == len(sample_model.elements)
        for v in scores.values():
            assert 0 <= v <= 1, f"分数 {v} 应在 [0, 1]"


class TestSequencerBrace:
    """含支撑的拆除序列测试"""

    @pytest.fixture
    def braced_model(self) -> StructureModel:
        """2 层带 X 撑框架"""
        section = Section(id=1, name="H300x200", A=7608,
                        Iy=1.14e8, Iz=1.94e7, J=3.42e6)
        material = Material(id=1, name="Q355", E=206000,
                          fy=355, density=7850)

        nodes = []
        nid = 1
        for z in [0, 3.6, 7.2]:
            for x in [0, 6]:
                r = [True, True, True, False, False, False] if z == 0 else [False]*6
                nodes.append(Node(id=nid, x=x, y=0, z=z, restraint=r))
                nid += 1

        elements = []
        eid = 1
        # 底层柱
        for x in range(2):
            elements.append(Element(id=eid,
                node_i_id=1 + x, node_j_id=3 + x,
                section_id=1, material_id=1,
                element_type=ElementType.COLUMN))
            eid += 1
        # 1层梁
        elements.append(Element(id=eid, node_i_id=3, node_j_id=4,
                               section_id=1, material_id=1,
                               element_type=ElementType.BEAM))
        eid += 1
        # 2层柱
        for x in range(2):
            elements.append(Element(id=eid,
                node_i_id=3 + x, node_j_id=5 + x,
                section_id=1, material_id=1,
                element_type=ElementType.COLUMN))
            eid += 1
        # 2层梁
        elements.append(Element(id=eid, node_i_id=5, node_j_id=6,
                               section_id=1, material_id=1,
                               element_type=ElementType.BEAM))
        eid += 1
        # X 撑 (底层)
        elements.append(Element(id=eid, node_i_id=1, node_j_id=4,
                               section_id=1, material_id=1,
                               element_type=ElementType.BRACE))
        eid += 1
        elements.append(Element(id=eid, node_i_id=2, node_j_id=3,
                               section_id=1, material_id=1,
                               element_type=ElementType.BRACE))
        eid += 1
        # X 撑 (2层)
        elements.append(Element(id=eid, node_i_id=3, node_j_id=6,
                               section_id=1, material_id=1,
                               element_type=ElementType.BRACE))
        eid += 1
        elements.append(Element(id=eid, node_i_id=4, node_j_id=5,
                               section_id=1, material_id=1,
                               element_type=ElementType.BRACE))

        return StructureModel(
            model_id="braced", name="Braced Frame",
            nodes=nodes, elements=elements,
            sections=[section], materials=[material]
        )

    @pytest.fixture
    def sequencer(self) -> DemolitionSequencer:
        return DemolitionSequencer()

    def test_brace_sequence(self, sequencer, braced_model):
        """含支撑框架的拆除序列"""
        plan = sequencer.generate_sequence(braced_model)
        assert len(plan.actions) > 0

        # 支撑应该在柱之前拆除
        step_types = []
        for action in plan.actions:
            for eid in action.target_element_ids:
                elem = next((e for e in braced_model.elements
                           if e.id == eid), None)
                if elem:
                    step_types.append((action.step, elem.element_type))

        # 统计
        brace_steps = [s for s, t in step_types if t == ElementType.BRACE]
        col_steps = [s for s, t in step_types if t == ElementType.COLUMN]

        if brace_steps and col_steps:
            avg_brace = sum(brace_steps) / len(brace_steps)
            avg_col = sum(col_steps) / len(col_steps)
            # 支撑优先级应该高于柱
            assert avg_brace < avg_col, \
                f"支撑平均步骤({avg_brace})应 < 柱平均步骤({avg_col})"
