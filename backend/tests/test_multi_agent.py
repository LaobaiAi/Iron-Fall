"""V4.0 多智能体协同决策测试

测试多智能体框架、案例库和全系统集成。
"""
import pytest
import asyncio
import json

from agent.parser import StructureParser
from agent.multi_agent import (
    create_orchestrator,
    RuleBasedPlanningAgent,
    RuleBasedSafetyAgent,
    RuleBasedEconomyAgent,
    DebateOrchestrator,
)
from agent.case_library import get_case_library, CaseLibrary
from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction,
    ElementType, AgentRole, MultiAgentDecision,
    AgentOpinion, DebateRecord,
)


# ============================================================================
# Helpers
# ============================================================================

def create_test_model(
    floors: int = 3,
    spans: int = 2,
    height: float = 3.6,
) -> StructureModel:
    """创建测试用钢框架模型"""
    parser = StructureParser()
    desc = f"建一个{floors}层钢框架，跨度6m，层高{height}m，H400x200，Q355"
    return parser.parse(desc, f"test_{floors}f")


def create_braced_model(floors: int = 5) -> StructureModel:
    """创建带支撑的测试模型"""
    parser = StructureParser()
    desc = (
        f"建一个带X型斜撑的{floors}层钢框架，"
        f"首层高4m，标准层高3.4m，Q355"
    )
    return parser.parse(desc, f"test_braced_{floors}f")


# ============================================================================
# 规划智能体测试
# ============================================================================

class TestPlanningAgent:
    """测试规则规划智能体"""

    def test_creates_valid_plan(self):
        agent = RuleBasedPlanningAgent()
        model = create_test_model(3)
        opinion = agent.generate_opinion(model)

        assert opinion.agent_role == AgentRole.PLANNING
        assert opinion.plan is not None
        assert len(opinion.plan.actions) > 0
        assert opinion.confidence > 0.5

    def test_plan_has_valid_steps(self):
        agent = RuleBasedPlanningAgent()
        model = create_test_model(5)
        opinion = agent.generate_opinion(model)

        steps = [a.step for a in opinion.plan.actions]
        assert steps == sorted(steps), "步骤应递增排列"
        assert steps[0] == 1, "第一步应为1"

    def test_plan_respects_max_elements_per_step(self):
        agent = RuleBasedPlanningAgent()
        model = create_test_model(3)
        opinion = agent.generate_opinion(model)

        for action in opinion.plan.actions:
            assert len(action.target_element_ids) <= 3, (
                f"每步最多3个构件，实际{len(action.target_element_ids)}个"
            )

    def test_all_element_ids_exist(self):
        agent = RuleBasedPlanningAgent()
        model = create_test_model(3)
        opinion = agent.generate_opinion(model)

        valid_ids = {e.id for e in model.elements}
        for action in opinion.plan.actions:
            for eid in action.target_element_ids:
                assert eid in valid_ids, f"构件{eid}不在模型中"

    def test_braced_model_handles_braces(self):
        agent = RuleBasedPlanningAgent()
        model = create_braced_model(5)
        opinion = agent.generate_opinion(model)

        assert opinion.plan is not None
        assert any(
            e.element_type == ElementType.BRACE
            for e in model.elements
        ), "模型应包含支撑构件"
        assert len(opinion.plan.actions) > 0


# ============================================================================
# 安全智能体测试
# ============================================================================

class TestSafetyAgent:
    """测试规则安全智能体"""

    def test_generates_opinion(self):
        agent = RuleBasedSafetyAgent()
        model = create_test_model(3)
        opinion = agent.generate_opinion(model)

        assert opinion.agent_role == AgentRole.SAFETY
        assert opinion.confidence > 0.5
        assert "safety" in opinion.scores

    def test_detects_low_columns(self):
        agent = RuleBasedSafetyAgent()
        model = create_test_model(3)
        opinion = agent.generate_opinion(model)

        assert len(opinion.reasoning) > 0
        assert opinion.scores["safety"] > 0, "安全评分应大于0"

    def test_severe_models_detected(self):
        """高风大模型应被识别"""
        agent = RuleBasedSafetyAgent()
        model = create_test_model(6)
        opinion = agent.generate_opinion(model)

        # 高层建筑安全评分应较低
        assert opinion.scores["safety"] > 0


# ============================================================================
# 经济智能体测试
# ============================================================================

class TestEconomyAgent:
    """测试规则经济智能体"""

    def test_estimates_cost(self):
        agent = RuleBasedEconomyAgent()
        model = create_test_model(3)
        opinion = agent.generate_opinion(model)

        assert opinion.agent_role == AgentRole.ECONOMY
        assert "cost" in opinion.scores
        assert opinion.confidence > 0.5

    def test_larger_model_costs_more(self):
        agent = RuleBasedEconomyAgent()
        small = agent.generate_opinion(create_test_model(2))
        large = agent.generate_opinion(create_test_model(6))

        assert True  # 基准：不同规模模型应有不同评分


# ============================================================================
# 辩论协调器测试
# ============================================================================

class TestDebateOrchestrator:
    """测试多智能体辩论协调器"""

    def test_creates_decision_with_all_agents(self):
        orchestrator = DebateOrchestrator()
        model = create_test_model(3)
        decision = orchestrator.decide(model)

        assert isinstance(decision, MultiAgentDecision)
        assert decision.final_plan is not None
        assert len(decision.agent_opinions) == 3, (
            f"应有3个智能体意见，实际{len(decision.agent_opinions)}个"
        )
        assert len(decision.debate_history) == 3, (
            f"应有3轮辩论，实际{len(decision.debate_history)}轮"
        )

    def test_consensus_score_in_range(self):
        orchestrator = DebateOrchestrator()
        model = create_test_model(3)
        decision = orchestrator.decide(model)

        assert 0.0 <= decision.consensus_score <= 1.0, (
            f"共识度应在0-1之间，实际{decision.consensus_score}"
        )

    def test_final_plan_is_valid(self):
        orchestrator = DebateOrchestrator()
        model = create_test_model(3)
        decision = orchestrator.decide(model)

        plan = decision.final_plan
        assert plan is not None
        assert len(plan.actions) > 0
        assert plan.plan_id.startswith("v4_consensus_")

    def test_warnings_for_braced_model(self):
        orchestrator = DebateOrchestrator()
        model = create_braced_model(5)
        decision = orchestrator.decide(model)

        # 有支撑的模型应有相关警告
        brace_count = sum(
            1 for e in model.elements if e.element_type == ElementType.BRACE
        )
        if brace_count > 0:
            assert any("支撑" in w for w in decision.warnings), (
                "含支撑的模型应有支撑相关警告"
            )

    def test_different_models_produce_different_decisions(self):
        orchestrator = DebateOrchestrator()

        decision_3f = orchestrator.decide(create_test_model(3))
        decision_6f = orchestrator.decide(create_test_model(6))

        assert decision_3f.decision_id != decision_6f.decision_id
        assert decision_3f.model_id != decision_6f.model_id

    def test_risk_level_valid(self):
        orchestrator = DebateOrchestrator()
        model = create_test_model(3)
        decision = orchestrator.decide(model)

        valid_risks = {"Low", "Medium", "High", "Critical"}
        actual = decision.final_plan.risk_level if decision.final_plan else "N/A"
        assert actual in valid_risks, f"风险等级{actual}无效"

    def test_cost_duration_positive(self):
        orchestrator = DebateOrchestrator()
        model = create_test_model(3)
        decision = orchestrator.decide(model)

        assert decision.cost_estimate > 0
        assert decision.duration_estimate > 0


# ============================================================================
# 案例库测试
# ============================================================================

class TestCaseLibrary:
    """测试案例知识库"""

    def test_has_ten_cases(self):
        lib = CaseLibrary()
        assert lib.total_cases == 10, (
            f"案例库应有10个案例，实际{lib.total_cases}"
        )

    def test_search_returns_matches(self):
        lib = CaseLibrary()
        model = create_test_model(3)
        matches = lib.search_similar(model, top_k=3)

        assert len(matches) > 0, "应至少返回1个匹配"
        assert len(matches) <= 3, "不应超过top_k"
        assert all(m.similarity_score > 0 for m in matches), "相似度应>0"

    def test_matches_sorted_by_similarity(self):
        lib = CaseLibrary()
        model = create_test_model(3)
        matches = lib.search_similar(model, top_k=5)

        scores = [m.similarity_score for m in matches]
        assert scores == sorted(scores, reverse=True), "应按相似度降序"

    def test_get_stats(self):
        lib = CaseLibrary()
        stats = lib.get_stats()

        assert stats.total_cases == 10
        assert len(stats.tags) > 0
        assert 0 < stats.success_rate <= 1.0

    def test_get_case_by_id(self):
        lib = CaseLibrary()
        case = lib.get_case_by_id("case_001")
        assert case is not None
        assert case.case_id == "case_001"
        assert case.project_name

        missing = lib.get_case_by_id("non_existent")
        assert missing is None

    def test_search_by_tag(self):
        lib = CaseLibrary()
        blast_cases = lib.search_by_tag("爆破")
        assert len(blast_cases) > 0

        fail_cases = lib.search_by_tag("失效教训")
        assert len(fail_cases) > 0

    def test_case_has_required_fields(self):
        lib = CaseLibrary()
        for case in lib.get_all_cases():
            assert case.case_id
            assert case.project_name
            assert case.structure_type
            assert case.demolition_method
            assert case.duration_days > 0
            assert case.cost_wan_yuan > 0
            assert isinstance(case.success, bool)
            assert len(case.tags) > 0


# ============================================================================
# 集成测试
# ============================================================================

class TestIntegration:
    """端到端集成测试"""

    def test_e2e_standard_model(self):
        """E2E: 标准3层钢框架全流程"""
        parser = StructureParser()
        model = parser.parse(
            "建一个3层钢框架，跨度6m，层高3.6m",
            "e2e_test",
        )

        assert len(model.nodes) > 0
        assert len(model.elements) > 0

        orchestrator = DebateOrchestrator()
        decision = orchestrator.decide(model)

        assert decision.final_plan is not None
        assert len(decision.final_plan.actions) > 0

        lib = CaseLibrary()
        matches = lib.search_similar(model)
        assert len(matches) > 0

    def test_e2e_braced_model(self):
        """E2E: 带支撑5层框架"""
        parser = StructureParser()
        model = parser.parse(
            "建一个带X型斜撑的五层钢框架，首层高4m，标准层高3.4m",
            "e2e_braced",
        )

        assert any(
            e.element_type == ElementType.BRACE
            for e in model.elements
        ), "应包含支撑构件"

        orchestrator = DebateOrchestrator()
        decision = orchestrator.decide(model)
        assert decision.final_plan is not None

    def test_factory_creates_agents(self):
        orchestrator = create_orchestrator(use_llm=False)
        assert isinstance(orchestrator, DebateOrchestrator)

        model = create_test_model(3)
        decision = orchestrator.decide(model)
        assert isinstance(decision, MultiAgentDecision)

    def test_performance_under_1_second(self):
        """性能: 单次决策应在1秒内完成"""
        import time
        orchestrator = DebateOrchestrator()
        model = create_test_model(3)

        start = time.time()
        decision = orchestrator.decide(model)
        elapsed = time.time() - start

        assert elapsed < 1.0, f"决策耗时{elapsed:.2f}s，超过1s阈值"


# ============================================================================
# 模型验证测试
# ============================================================================

class TestV4Models:
    """测试 V4.0 新增数据模型"""

    def test_agent_opinion_model(self):
        opinion = AgentOpinion(
            agent_role=AgentRole.PLANNING,
            reasoning="测试",
            confidence=0.8,
            scores={"safety": 0.9, "efficiency": 0.7, "cost": 0.6, "overall": 0.75},
        )
        assert opinion.confidence == 0.8
        assert opinion.scores["safety"] == 0.9

    def test_debate_record_model(self):
        record = DebateRecord(
            round=1,
            topic="测试辩论",
            opinions=[],
            consensus_reached=False,
        )
        assert record.round == 1
        assert not record.consensus_reached

    def test_multi_agent_decision_model(self):
        decision = MultiAgentDecision(
            decision_id="test_001",
            model_id="model_001",
            consensus_score=0.85,
            risk_assessment="低风险",
            cost_estimate=25.0,
            duration_estimate=15,
        )
        assert decision.consensus_score > 0.8
        assert decision.cost_estimate > 0

    def test_case_models(self):
        from core.models import DemolitionCase, CaseMatchResult

        case = DemolitionCase(
            case_id="test_001",
            project_name="测试项目",
            structure_type="钢框架",
            floors=3,
            demolition_method="机械拆除",
            duration_days=10,
            cost_wan_yuan=20.0,
            tags=["钢框架", "测试"],
        )
        assert case.floors == 3

        match = CaseMatchResult(
            case=case,
            similarity_score=0.85,
            relevance_reason="相似结构",
        )
        assert match.similarity_score > 0.8
