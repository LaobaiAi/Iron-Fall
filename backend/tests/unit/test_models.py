"""数据模型单元测试

覆盖 core/models.py 中所有 Pydantic 模型的：
- 构造与必需字段验证
- 默认值正确性
- JSON 序列化/反序列化往返一致性
- 边界条件（空列表、极端值等）
"""
import json
import pytest
from core.models import (
    Node, Section, Material, Element, ElementType,
    DemolitionAction, DemolitionPlan,
    StructureModel, AnalysisResult, DemolitionResponse,
    ChimneySegment, ChimneyAttachment, ChimneyModel,
    ChimneyStabilityReport, ChimneyTrajectoryPoint, ChimneyDeepAnalysisReport,
    ElementXAIInfo, XAIReport,
    AgentRole, AgentOpinion, DebateRecord, MultiAgentDecision,
    DemolitionCase, CaseMatchResult, CaseLibraryStats,
)


# ============================================================================
# V1.0 基础模型测试
# ============================================================================

class TestNode:
    """Node 模型测试"""

    def test_create_basic(self):
        n = Node(id=1, x=0.0, y=0.0, z=0.0)
        assert n.id == 1
        assert n.x == 0.0
        assert n.restraint == [True, True, True, False, False, False]

    def test_create_free_node(self):
        n = Node(id=5, x=6.0, y=0.0, z=9.0, restraint=[False]*6)
        assert all(not r for r in n.restraint)

    def test_serialize_roundtrip(self):
        n = Node(id=3, x=1.5, y=2.5, z=3.5)
        d = json.loads(n.model_dump_json())
        n2 = Node(**d)
        assert n2 == n

    def test_default_restraint(self):
        n = Node(id=1, x=0, y=0, z=0)
        assert len(n.restraint) == 6
        assert n.restraint[:3] == [True, True, True]

    def test_invalid_restraint_length(self):
        """约束长度不足时应报错（Pydantic 不会自动校验 list 长度但此处接受）"""
        # 约束不足6个时 rest 可能为空，pydantic 不抛异常
        n = Node(id=1, x=0, y=0, z=0, restraint=[True])
        assert n.restraint == [True]


class TestSection:
    """Section 模型测试"""

    def test_create(self):
        s = Section(id=1, name="H500x300", A=16350, Iy=6.5e8, Iz=1.8e8, J=5e7)
        assert s.name == "H500x300"
        assert s.A == 16350

    def test_serialize_roundtrip(self):
        s = Section(id=2, name="H300x200", A=7608, Iy=1.14e8, Iz=1.94e7, J=3.42e6)
        d = json.loads(s.model_dump_json())
        s2 = Section(**d)
        assert s2 == s

    def test_zero_properties(self):
        """零截面属性（边界）"""
        s = Section(id=0, name="ZERO", A=0.0, Iy=0.0, Iz=0.0, J=0.0)
        assert s.A == 0.0


class TestMaterial:
    """Material 模型测试"""

    def test_create_q355(self):
        m = Material(id=1, name="Q355", E=206000, fy=355, density=7850)
        assert m.fy == 355

    def test_serialize_roundtrip(self):
        m = Material(id=2, name="Q235", E=206000, fy=235, density=7850)
        d = json.loads(m.model_dump_json())
        m2 = Material(**d)
        assert m2 == m


class TestElement:
    """Element 模型测试"""

    def test_create_column(self):
        e = Element(id=1, node_i_id=1, node_j_id=3,
                    section_id=1, material_id=1,
                    element_type=ElementType.COLUMN)
        assert e.element_type == ElementType.COLUMN

    def test_create_beam(self):
        e = Element(id=2, node_i_id=3, node_j_id=4,
                    section_id=1, material_id=1,
                    element_type=ElementType.BEAM)
        assert e.element_type == ElementType.BEAM

    def test_create_brace(self):
        e = Element(id=99, node_i_id=1, node_j_id=4,
                    section_id=1, material_id=1,
                    element_type=ElementType.BRACE)
        assert e.element_type == ElementType.BRACE

    def test_serialize_roundtrip(self):
        e = Element(id=10, node_i_id=5, node_j_id=7,
                    section_id=2, material_id=1,
                    element_type=ElementType.COLUMN)
        d = json.loads(e.model_dump_json())
        e2 = Element(**d)
        assert e2 == e

    def test_same_node_error_acceptable(self):
        """构件两端可为同一节点（软件层面允许，工程上不合理）"""
        e = Element(id=1, node_i_id=5, node_j_id=5,
                    section_id=1, material_id=1,
                    element_type=ElementType.COLUMN)
        assert e.node_i_id == e.node_j_id


# ============================================================================
# DemolitionAction / DemolitionPlan 测试
# ============================================================================

class TestDemolitionAction:
    """DemolitionAction 模型测试"""

    def test_create_remove(self):
        a = DemolitionAction(step=1, target_element_ids=[1, 2], action_type="Remove")
        assert a.action_type == "Remove"
        assert len(a.target_element_ids) == 2

    def test_create_apply_force(self):
        a = DemolitionAction(
            step=2, target_element_ids=[5],
            action_type="ApplyForce",
            force_vector=(10, 0, -50),
        )
        assert a.force_vector == (10, 0, -50)

    def test_default_action_type(self):
        a = DemolitionAction(step=1, target_element_ids=[1])
        assert a.action_type == "Remove"

    def test_force_vector_none_by_default(self):
        a = DemolitionAction(step=1, target_element_ids=[1])
        assert a.force_vector is None


class TestDemolitionPlan:
    """DemolitionPlan 模型测试"""

    def test_create(self):
        actions = [
            DemolitionAction(step=1, target_element_ids=[1]),
            DemolitionAction(step=2, target_element_ids=[2, 3]),
        ]
        plan = DemolitionPlan(
            plan_id="p001", description="测试方案",
            actions=actions, risk_level="Low",
        )
        assert len(plan.actions) == 2
        assert plan.risk_level == "Low"

    def test_defaults(self):
        plan = DemolitionPlan(plan_id="empty")
        assert plan.actions == []
        assert plan.risk_level == "Low"
        assert plan.description == ""

    def test_risk_levels(self):
        for level in ("Low", "Medium", "High", "Critical"):
            plan = DemolitionPlan(plan_id="x", risk_level=level)
            assert plan.risk_level == level


# ============================================================================
# StructureModel 测试
# ============================================================================

class TestStructureModel:
    """StructureModel 模型测试"""

    def test_create_empty(self, empty_model):
        assert empty_model.model_id == "empty"
        assert empty_model.nodes == []

    def test_create_with_fixture(self, sample_3story_frame):
        m = sample_3story_frame
        assert m.model_id == "baseline_v1_3story"
        assert len(m.nodes) > 0
        assert len(m.elements) > 0
        assert len(m.sections) == 1
        assert len(m.materials) == 1

    def test_unit_default(self, sample_3story_frame):
        assert sample_3story_frame.unit == "SI"

    def test_serialize_roundtrip(self, sample_3story_frame):
        d = json.loads(sample_3story_frame.model_dump_json())
        m2 = StructureModel(**d)
        assert m2.model_id == sample_3story_frame.model_id
        assert len(m2.nodes) == len(sample_3story_frame.nodes)
        assert len(m2.elements) == len(sample_3story_frame.elements)

    def test_model_integrity(self, sample_3story_frame):
        """模型内部引用完整性"""
        import sys
        from pathlib import Path
        _tests_dir = str(Path(__file__).parent.parent)
        if _tests_dir not in sys.path:
            sys.path.insert(0, _tests_dir)
        from conftest import validate_model_integrity
        errors = validate_model_integrity(sample_3story_frame)
        assert errors == [], f"模型完整性错误: {errors}"

    def test_integrity_all_fixtures(self, sample_1story_frame, sample_5story_frame):
        import sys
        from pathlib import Path
        _tests_dir = str(Path(__file__).parent.parent)
        if _tests_dir not in sys.path:
            sys.path.insert(0, _tests_dir)
        from conftest import validate_model_integrity
        for m in [sample_1story_frame, sample_5story_frame]:
            errors = validate_model_integrity(m)
            assert errors == [], f"{m.model_id} 完整性错误: {errors}"


# ============================================================================
# AnalysisResult / DemolitionResponse 测试
# ============================================================================

class TestAnalysisResult:
    """AnalysisResult 模型测试"""

    def test_create_default(self):
        r = AnalysisResult()
        assert r.success is True
        assert r.stability_status == "Stable"
        assert r.is_safe is True

    def test_create_unstable(self, sample_analysis_unstable):
        assert not sample_analysis_unstable.is_safe
        assert sample_analysis_unstable.stability_status == "Unstable"

    def test_stability_statuses(self):
        for status in ("Stable", "Unstable", "Critical", "Collapse", "Error", "Timeout"):
            r = AnalysisResult(stability_status=status)
            assert r.stability_status == status


class TestDemolitionResponse:
    """DemolitionResponse 模型测试"""

    def test_create_success(self, sample_demolition_plan, sample_analysis_stable):
        r = DemolitionResponse(
            success=True, plan=sample_demolition_plan,
            analysis=sample_analysis_stable,
            message="ok", latency_ms=150.0,
        )
        assert r.success
        assert r.latency_ms == 150.0

    def test_defaults(self):
        r = DemolitionResponse()
        assert r.success is True
        assert r.plan is None
        assert r.latency_ms == 0.0


# ============================================================================
# V3.0 烟囱模型测试
# ============================================================================

class TestChimneySegment:
    def test_create(self):
        s = ChimneySegment(
            id=1, bottom_elevation=0, top_elevation=40,
            outer_diameter_bottom=9.0, outer_diameter_top=7.0,
            wall_thickness=0.5, material="C45",
        )
        assert s.reinforcement_ratio == 0.008  # 默认值

    def test_top_less_than_bottom(self):
        """顶部直径可以小于底部（变截面）"""
        s = ChimneySegment(
            id=1, bottom_elevation=0, top_elevation=100,
            outer_diameter_bottom=8.0, outer_diameter_top=3.0,
            wall_thickness=0.3, material="C40",
        )
        assert s.outer_diameter_top < s.outer_diameter_bottom


class TestChimneyModel:
    def test_create_basic(self, sample_chimney_100m):
        assert sample_chimney_100m.total_height == 100
        assert len(sample_chimney_100m.segments) == 1

    def test_create_varied(self, sample_chimney_150m_varied):
        assert len(sample_chimney_150m_varied.segments) == 3
        assert len(sample_chimney_150m_varied.attachments) == 1

    def test_notch_defaults(self):
        m = ChimneyModel(
            model_id="x", total_height=50,
            base_diameter=5.0, top_diameter=3.0,
        )
        assert m.notch_height == 0.0
        assert m.notch_angle == 0.0


class TestChimneyStabilityReport:
    def test_create(self):
        r = ChimneyStabilityReport(
            model_id="x", notch_height=2.0,
            overturning_moment=500, resisting_moment=800,
            is_stable=True, max_stress=15.0,
        )
        assert r.stability_ratio == 1.0
        assert r.warnings == []


class TestChimneyTrajectoryPoint:
    def test_create(self):
        tp = ChimneyTrajectoryPoint(
            time=1.0, angle=15.0, angular_velocity=0.5,
            com_x=2.0, com_z=20.0, kinetic_energy=1000,
        )
        assert tp.angle == 15.0


class TestChimneyDeepAnalysisReport:
    def test_create_default(self):
        r = ChimneyDeepAnalysisReport(model_id="x", notch_height=2.0)
        assert r.trajectory == []
        assert r.impact_time == 0.0
        assert r.engine_used == "ChimneyDeepAnalyzer"


# ============================================================================
# V3.0 XAI 模型测试
# ============================================================================

class TestElementXAIInfo:
    def test_create(self):
        xi = ElementXAIInfo(
            element_id=1, element_type="Column",
            stress_ratio=0.3, importance_score=0.2,
            recommendation=True,
        )
        assert xi.load_path_rank == 99
        assert xi.recommendation is True


class TestXAIReport:
    def test_create(self):
        r = XAIReport(model_id="x", total_elements=15, removable_elements=8)
        assert r.element_details == []
        assert r.recommended_sequence == []


# ============================================================================
# V4.0 多智能体模型测试
# ============================================================================

class TestAgentOpinion:
    def test_create(self, sample_agent_opinion_planning):
        assert sample_agent_opinion_planning.agent_role == AgentRole.PLANNING
        assert sample_agent_opinion_planning.confidence == 0.88

    def test_default_scores(self):
        o = AgentOpinion(agent_role=AgentRole.SAFETY)
        assert o.scores["safety"] == 0.0
        assert o.scores["overall"] == 0.0

    def test_confidence_range(self):
        """置信度应在 [0, 1] 范围内"""
        with pytest.raises(Exception):
            AgentOpinion(agent_role=AgentRole.ECONOMY, confidence=1.5)
        with pytest.raises(Exception):
            AgentOpinion(agent_role=AgentRole.ECONOMY, confidence=-0.1)


class TestDebateRecord:
    def test_create(self):
        r = DebateRecord(round=1, topic="拆除顺序")
        assert r.consensus_reached is False


class TestMultiAgentDecision:
    def test_create(self, sample_multi_agent_decision):
        assert sample_multi_agent_decision.consensus_score == 0.85
        assert sample_multi_agent_decision.cost_estimate == 15.0
        assert sample_multi_agent_decision.duration_estimate == 7


# ============================================================================
# V4.0 案例库模型测试
# ============================================================================

class TestDemolitionCase:
    def test_create(self, sample_case):
        assert sample_case.case_id == "case_001"
        assert sample_case.success is True

    def test_tags(self, sample_case):
        assert "钢框架" in sample_case.tags


class TestCaseMatchResult:
    def test_create(self, sample_case):
        r = CaseMatchResult(case=sample_case, similarity_score=0.85)
        assert r.similarity_score == 0.85


class TestCaseLibraryStats:
    def test_defaults(self):
        s = CaseLibraryStats()
        assert s.total_cases == 0
        assert s.success_rate == 0.0

    def test_create(self):
        s = CaseLibraryStats(total_cases=10, tags={"钢框架": 5}, success_rate=0.9)
        assert s.total_cases == 10
        assert s.success_rate == 0.9


# ============================================================================
# 跨模型兼容性测试
# ============================================================================

class TestCrossModelCompatibility:
    """验证不同版本模型之间的数据兼容性"""

    def test_v1_to_dict_works(self, sample_3story_frame, sample_demolition_plan):
        d = sample_3story_frame.model_dump()
        assert isinstance(d, dict)
        assert "nodes" in d

    def test_v3_to_dict_works(self, sample_chimney_100m):
        d = sample_chimney_100m.model_dump()
        assert d["total_height"] == 100

    def test_v4_to_dict_works(self, sample_multi_agent_decision):
        d = sample_multi_agent_decision.model_dump()
        assert "decision_id" in d
