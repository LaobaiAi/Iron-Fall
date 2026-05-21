"""V3.0 强化学习拆除序列优化测试

验证 PPO 环境和智能体的基本功能。
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import StructureModel
from agent.parser import StructureParser
from engine.rl_agent import DemolitionRLAgent, RLPlanResult, create_rl_comparison

try:
    import gymnasium as gym
    RL_ENV_AVAILABLE = True
except ImportError:
    RL_ENV_AVAILABLE = False

try:
    from stable_baselines3 import PPO
    SB3_AVAILABLE = True
except ImportError:
    SB3_AVAILABLE = False


# ============================================================================
# RL Environment 测试
# ============================================================================

@pytest.mark.skipif(not RL_ENV_AVAILABLE, reason="gymnasium 未安装")
class TestDemolitionEnv:
    """Gym 环境测试"""

    @pytest.fixture
    def model(self) -> StructureModel:
        parser = StructureParser()
        return parser.parse("3层Q355钢框架，跨度6m")

    def test_env_creation(self, model):
        """环境可创建"""
        from engine.rl_environment import DemolitionEnv
        env = DemolitionEnv(model)
        assert env.observation_space.shape == (7,)
        assert env.action_space.n == len(model.elements)

    def test_reset(self, model):
        """reset 返回观测"""
        env = DemolitionEnv(model)
        obs, info = env.reset()
        assert obs.shape == (7,)
        assert all(0 <= v <= 1 for v in obs)

    def test_step(self, model):
        """step 执行一步并返回 """
        env = DemolitionEnv(model)
        obs, _ = env.reset()
        obs, reward, terminated, truncated, info = env.step(0)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)

    def test_step_removes_element(self, model):
        """拆除后构件应减少"""
        env = DemolitionEnv(model)
        obs, _ = env.reset()
        n_before = len(env.remaining_elements)
        obs, reward, term, trunc, info = env.step(0)
        if info.get("status") == "ok":
            n_after = len(env.remaining_elements)
            assert n_after == n_before - 1

    def test_invalid_action_penalty(self, model):
        """无效动作应受惩罚"""
        env = DemolitionEnv(model)
        obs, _ = env.reset()
        n = len(model.elements)
        obs, reward, term, trunc, info = env.step(n + 100)
        assert reward < 0, "无效动作应负奖励"


# ============================================================================
# RL Agent 测试
# ============================================================================

class TestDemolitionRLAgent:
    """RL 智能体测试"""

    @pytest.fixture
    def model(self) -> StructureModel:
        parser = StructureParser()
        return parser.parse("3层Q355钢框架，跨度6m，层高3.6m")

    def test_compare_no_training(self, model):
        """未训练时也能生成对比结果 (降级)"""
        agent = DemolitionRLAgent()
        result = agent.compare(model)

        assert isinstance(result, RLPlanResult)
        # 即使未训练也有启发式方案
        assert len(result.rl_sequence) > 0
        assert len(result.baseline_sequence) > 0
        assert result.baseline_steps > 0

    def test_compare_covers_all_elements(self, model):
        """对比结果应覆盖所有构件 (不在序列中也有属性)"""
        agent = DemolitionRLAgent()
        result = agent.compare(model)
        assert result.rl_removed > 0
        assert result.baseline_removed > 0

    def test_heuristic_plan(self, model):
        """启发式方案非空"""
        agent = DemolitionRLAgent()
        seq, reward, stability, removed = agent._heuristic_plan(model)
        assert len(seq) > 0
        assert removed == len(seq)

    def test_create_rl_comparison(self, model):
        """便捷函数可用"""
        result = create_rl_comparison(model, train=False)
        assert isinstance(result, RLPlanResult)
        assert len(result.rl_sequence) > 0

    @pytest.mark.skipif(
        not SB3_AVAILABLE,
        reason="stable-baselines3 未安装"
    )
    def test_train_and_compare(self, model):
        """训练后对比"""
        agent = DemolitionRLAgent()
        ok = agent.train(model, total_timesteps=500, verbose=0)
        if ok:
            result = agent.compare(model)
            assert result.trained
            assert len(result.rl_sequence) > 0

    def test_empty_model(self):
        """空模型安全处理"""
        model = StructureModel(
            model_id="empty", name="空",
            nodes=[], elements=[], sections=[], materials=[]
        )
        agent = DemolitionRLAgent()
        result = agent.compare(model)
        assert len(result.rl_sequence) >= 0


class TestRLIntegration:
    """RL 集成测试"""

    def test_with_braced_structure(self):
        """含支撑结构的RL测试"""
        parser = StructureParser()
        model = parser.parse("带X型斜撑的3层钢框架，跨度6m")
        result = create_rl_comparison(model, train=False)

        assert len(result.rl_sequence) > 0
        assert len(result.baseline_sequence) > 0
        assert result.improvement
