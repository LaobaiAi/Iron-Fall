"""Iron-Fall 测试全局配置与共享 Fixtures

提供标准化的测试模型工厂、路径配置和常用辅助函数。
所有子目录的测试自动继承此 conftest.py 中的 fixtures。
"""
import sys
import pytest
import hashlib
import json
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# 路径配置：确保 backend 目录在 sys.path 中
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ============================================================================
# 核心模型 fixtures
# ============================================================================

from core.models import (
    StructureModel, Node, Element, Section, Material, ElementType,
    DemolitionPlan, DemolitionAction, AnalysisResult,
    ChimneyModel, ChimneySegment, ChimneyAttachment,
    ChimneyStabilityReport, ChimneyDeepAnalysisReport, ChimneyTrajectoryPoint,
    XAIReport, ElementXAIInfo,
    AgentRole, AgentOpinion, DebateRecord, MultiAgentDecision,
    DemolitionCase, CaseMatchResult, CaseLibraryStats,
)


@pytest.fixture(scope="session")
def standard_section() -> Section:
    """标准 H400x200 截面"""
    return Section(
        id=1, name="H400x200",
        A=10000, Iy=2.5e8, Iz=30000000, J=10000000,
    )


@pytest.fixture(scope="session")
def standard_material_q355() -> Material:
    """标准 Q355 钢材"""
    return Material(
        id=1, name="Q355",
        E=206000, fy=355, density=7850,
    )


@pytest.fixture(scope="session")
def standard_material_q235() -> Material:
    """标准 Q235 钢材"""
    return Material(
        id=2, name="Q235",
        E=206000, fy=235, density=7850,
    )


# ---------------------------------------------------------------------------
# StructureModel fixtures
# ---------------------------------------------------------------------------


def _build_n_story_frame(stories: int, bays: int, story_height: float,
                         bay_width: float, model_id: str,
                         section: "Section | None" = None,
                         material: "Material | None" = None) -> StructureModel:
    """构建 n 层 m 跨钢框架的通用工厂函数"""
    if section is None:
        section = Section(id=1, name="H400x200",
                          A=10000, Iy=2.5e8, Iz=3.0e7, J=1.0e7)
    if material is None:
        material = Material(id=1, name="Q355",
                            E=206000, fy=355, density=7850)

    nodes: list[Node] = []
    nid = 1
    # 逐层生成节点（含基础固定层）
    for level in range(stories + 1):  # 0 = base, 1..stories = floors
        z = level * story_height
        for bx in range(bays + 1):
            x = bx * bay_width
            if level == 0:
                restraint = [True, True, True, False, False, False]
            else:
                restraint = [False] * 6
            nodes.append(Node(id=nid, x=x, y=0, z=z, restraint=restraint))
            nid += 1

    elements: list[Element] = []
    eid = 1
    cols_per_level = bays + 1

    for level in range(stories):
        base_nid = level * cols_per_level + 1
        top_nid = (level + 1) * cols_per_level + 1
        # 柱
        for xi in range(cols_per_level):
            elements.append(Element(
                id=eid, node_i_id=base_nid + xi, node_j_id=top_nid + xi,
                section_id=section.id, material_id=material.id,
                element_type=ElementType.COLUMN,
            ))
            eid += 1
        # 梁
        for xi in range(bays):
            elements.append(Element(
                id=eid, node_i_id=top_nid + xi, node_j_id=top_nid + xi + 1,
                section_id=section.id, material_id=material.id,
                element_type=ElementType.BEAM,
            ))
            eid += 1

    return StructureModel(
        model_id=model_id,
        name=f"{stories}层{bays}跨钢框架",
        nodes=nodes, elements=elements,
        sections=[section], materials=[material],
    )


@pytest.fixture(scope="session")
def sample_3story_frame() -> StructureModel:
    """3层2跨钢框架 (8节点, 9柱+6梁=15构件) - 回归测试基准模型"""
    return _build_n_story_frame(
        stories=3, bays=2, story_height=3.6, bay_width=6.0,
        model_id="baseline_v1_3story",
    )


@pytest.fixture(scope="session")
def sample_1story_frame() -> StructureModel:
    """单层单跨钢框架 (4节点, 2柱+1梁=3构件) - 最小可测模型"""
    return _build_n_story_frame(
        stories=1, bays=1, story_height=3.0, bay_width=5.0,
        model_id="minimal_1story",
    )


@pytest.fixture(scope="session")
def sample_5story_frame() -> StructureModel:
    """5层2跨钢框架 - 中型模型"""
    return _build_n_story_frame(
        stories=5, bays=2, story_height=3.3, bay_width=6.0,
        model_id="medium_5story",
    )


@pytest.fixture
def empty_model() -> StructureModel:
    """空模型 - 边界测试"""
    return StructureModel(
        model_id="empty",
        name="空模型",
        nodes=[], elements=[], sections=[], materials=[],
    )


@pytest.fixture
def model_hash_locked(sample_3story_frame: StructureModel) -> str:
    """对基准模型做 MD5 哈希，用于回归对比"""
    raw = sample_3story_frame.model_dump_json()
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# DemolitionPlan / DemolitionAction fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_demolition_plan(sample_3story_frame: StructureModel) -> DemolitionPlan:
    """基于基准模型的拆除方案（拆除顶层柱）"""
    top_elements = [
        e.id for e in sample_3story_frame.elements
        if e.element_type == ElementType.COLUMN
    ][-2:]  # 最顶层2根柱
    return DemolitionPlan(
        plan_id="test_plan_001",
        description="拆除顶层柱",
        actions=[
            DemolitionAction(
                step=1, target_element_ids=top_elements,
                action_type="Remove",
            )
        ],
        risk_level="Medium",
    )


# ---------------------------------------------------------------------------
# AnalysisResult fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_analysis_stable(sample_3story_frame: StructureModel) -> AnalysisResult:
    """稳定状态的分析结果"""
    disp: dict[int, list[float]] = {}
    for n in sample_3story_frame.nodes:
        disp[n.id] = [0.001, 0.0, 0.002, 0.0, 0.0, 0.0]
    return AnalysisResult(
        success=True,
        node_displacements=disp,
        max_displacement=0.005,
        stability_status="Stable",
        is_safe=True,
        engine_info="MockEngine",
    )


@pytest.fixture
def sample_analysis_unstable() -> AnalysisResult:
    """失稳状态的分析结果"""
    return AnalysisResult(
        success=True,
        max_displacement=0.5,
        stability_status="Unstable",
        is_safe=False,
        warnings=["位移超限"],
        engine_info="MockEngine",
    )


# ---------------------------------------------------------------------------
# ChimneyModel fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_chimney_100m() -> ChimneyModel:
    """100m 钢筋混凝土烟囱 - 单段等截面（回归基准）"""
    segment = ChimneySegment(
        id=1,
        bottom_elevation=0, top_elevation=100,
        outer_diameter_bottom=8.0, outer_diameter_top=8.0,
        wall_thickness=0.4,
        material="C40",
    )
    return ChimneyModel(
        model_id="chimney_baseline_100m",
        name="100m等截面烟囱",
        total_height=100,
        segments=[segment],
        base_diameter=8.0, top_diameter=8.0,
        notch_height=2.0, notch_angle=220,
    )


@pytest.fixture(scope="session")
def sample_chimney_150m_varied() -> ChimneyModel:
    """150m 变截面烟囱（3段）"""
    seg1 = ChimneySegment(
        id=1, bottom_elevation=100, top_elevation=150,
        outer_diameter_bottom=4.0, outer_diameter_top=2.5,
        wall_thickness=0.25, material="C35",
    )
    seg2 = ChimneySegment(
        id=2, bottom_elevation=40, top_elevation=100,
        outer_diameter_bottom=7.0, outer_diameter_top=4.0,
        wall_thickness=0.35, material="C40",
    )
    seg3 = ChimneySegment(
        id=3, bottom_elevation=0, top_elevation=40,
        outer_diameter_bottom=9.0, outer_diameter_top=7.0,
        wall_thickness=0.5, material="C45",
    )
    return ChimneyModel(
        model_id="chimney_150m_varied",
        name="150m变截面烟囱",
        total_height=150,
        segments=[seg1, seg2, seg3],
        base_diameter=9.0, top_diameter=2.5,
        notch_height=3.0, notch_angle=240,
        attachments=[
            ChimneyAttachment(
                name="避雷针", height=3.0, diameter=0.15, material="Q235",
            )
        ],
    )


# ---------------------------------------------------------------------------
# V4.0 Multi-Agent fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_agent_opinion_planning(sample_demolition_plan: DemolitionPlan) -> AgentOpinion:
    return AgentOpinion(
        agent_role=AgentRole.PLANNING,
        plan=sample_demolition_plan,
        scores={"safety": 0.85, "efficiency": 0.90, "cost": 0.75, "overall": 0.85},
        reasoning="自上而下拆除，力学路径最短",
        confidence=0.88,
    )


@pytest.fixture
def sample_agent_opinion_safety() -> AgentOpinion:
    return AgentOpinion(
        agent_role=AgentRole.SAFETY,
        scores={"safety": 0.95, "efficiency": 0.70, "cost": 0.65, "overall": 0.80},
        reasoning="建议增加临时支撑确保安全冗余",
        confidence=0.92,
    )


@pytest.fixture
def sample_multi_agent_decision(
    sample_demolition_plan: DemolitionPlan,
    sample_agent_opinion_planning: AgentOpinion,
    sample_agent_opinion_safety: AgentOpinion,
) -> MultiAgentDecision:
    return MultiAgentDecision(
        decision_id="test_decision_001",
        model_id="baseline_v1_3story",
        final_plan=sample_demolition_plan,
        agent_opinions=[sample_agent_opinion_planning, sample_agent_opinion_safety],
        debate_history=[],
        consensus_score=0.85,
        risk_assessment="中低风险 - 建议增加监测点",
        cost_estimate=15.0,
        duration_estimate=7,
    )


# ---------------------------------------------------------------------------
# DemolitionCase fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_case() -> DemolitionCase:
    return DemolitionCase(
        case_id="case_001",
        project_name="测试项目A",
        location="上海",
        year=2024,
        structure_type="钢框架",
        height=15.0,
        floors=5,
        material="Q355",
        demolition_method="逐层机械拆除",
        duration_days=15,
        cost_wan_yuan=50.0,
        success=True,
        key_lessons=["自上而下拆除", "监测关键节点应力"],
        tags=["钢框架", "5层", "上海"],
        description="标准5层钢框架拆除工程",
    )


# ============================================================================
# 辅助工具
# ============================================================================

def model_to_dict(model: StructureModel) -> dict:
    """将 StructureModel 转为 dict (模拟 LangChain tool 输入)"""
    return json.loads(model.model_dump_json())


def validate_model_integrity(model: StructureModel) -> list[str]:
    """验证模型完整性，返回错误列表"""
    errors: list[str] = []
    node_ids = {n.id for n in model.nodes}
    section_ids = {s.id for s in model.sections}
    material_ids = {m.id for m in model.materials}

    for e in model.elements:
        if e.node_i_id not in node_ids:
            errors.append(f"Element {e.id}: node_i_id {e.node_i_id} 不存在")
        if e.node_j_id not in node_ids:
            errors.append(f"Element {e.id}: node_j_id {e.node_j_id} 不存在")
        if e.section_id not in section_ids:
            errors.append(f"Element {e.id}: section_id {e.section_id} 不存在")
        if e.material_id not in material_ids:
            errors.append(f"Element {e.id}: material_id {e.material_id} 不存在")

    return errors
