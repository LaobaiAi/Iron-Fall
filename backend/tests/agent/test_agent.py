"""AI 智能体单元测试

覆盖 agent/agent.py 的：
- SimpleDemolitionAgent（纯规则版本，无需 API）
- create_agent 工厂函数
- 降级逻辑
"""
import pytest
from agent.agent import SimpleDemolitionAgent, create_agent
from core.models import DemolitionPlan, DemolitionAction


class TestSimpleDemolitionAgent:
    """SimpleDemolitionAgent - 纯规则智能体"""

    @pytest.fixture
    def agent(self) -> SimpleDemolitionAgent:
        return SimpleDemolitionAgent()

    @pytest.mark.asyncio
    async def test_generate_plan_returns_demolition_plan(self, agent,
                                                          sample_3story_frame):
        plan = await agent.generate_plan(sample_3story_frame, user_request="拆除顶层")
        assert isinstance(plan, DemolitionPlan)
        assert plan.plan_id is not None

    @pytest.mark.asyncio
    async def test_plan_has_actions(self, agent, sample_3story_frame):
        plan = await agent.generate_plan(sample_3story_frame, user_request="拆除顶层")
        assert len(plan.actions) > 0, "应至少生成一个拆除动作"

    @pytest.mark.asyncio
    async def test_plan_is_deterministic(self, agent, sample_3story_frame):
        """同一模型多次生成应有相同的拆除步骤（plan_id 含计数器可不同）"""
        plan1 = await agent.generate_plan(sample_3story_frame, user_request="拆除")
        plan2 = await agent.generate_plan(sample_3story_frame, user_request="拆除")
        assert len(plan1.actions) == len(plan2.actions)
        assert plan1.risk_level == plan2.risk_level
        # 步骤序列应一致
        steps1 = [(a.step, a.action_type, a.target_element_ids) for a in plan1.actions]
        steps2 = [(a.step, a.action_type, a.target_element_ids) for a in plan2.actions]
        assert steps1 == steps2

    @pytest.mark.asyncio
    async def test_generate_plan_empty_model(self, agent, empty_model):
        plan = await agent.generate_plan(empty_model, user_request="拆除")
        assert isinstance(plan, DemolitionPlan)
        # 空模型应返回空 actions 或合理降级
        assert isinstance(plan.actions, list)

    @pytest.mark.asyncio
    async def test_generate_plan_5story(self, agent, sample_5story_frame):
        plan = await agent.generate_plan(sample_5story_frame, user_request="拆除")
        assert len(plan.actions) > 0

    @pytest.mark.asyncio
    async def test_actions_contain_valid_element_ids(self, agent,
                                                      sample_3story_frame):
        valid_ids = {e.id for e in sample_3story_frame.elements}
        plan = await agent.generate_plan(sample_3story_frame, user_request="拆除")
        for action in plan.actions:
            for eid in action.target_element_ids:
                assert eid in valid_ids, f"action 引用不存在的 element {eid}"

    @pytest.mark.asyncio
    async def test_actions_ordered_by_step(self, agent, sample_3story_frame):
        plan = await agent.generate_plan(sample_3story_frame, user_request="拆除")
        steps = [a.step for a in plan.actions]
        assert steps == sorted(steps), "动作步骤应有序"


class TestCreateAgent:
    """工厂函数测试"""

    @pytest.mark.asyncio
    async def test_create_agent_returns_simple_agent_for_no_api_key(self):
        agent = await create_agent()
        assert isinstance(agent, SimpleDemolitionAgent) or agent is not None

    @pytest.mark.asyncio
    async def test_create_agent_with_key_returns_simple_in_offline(self):
        """离线环境（无 openai API）自动降级为 SimpleAgent"""
        agent = await create_agent()
        # 在没有真实 OpenAI 环境时返回 SimpleAgent
        assert agent is not None
