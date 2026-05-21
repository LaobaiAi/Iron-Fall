"""V3.0 强化学习拆除序列优化环境

将结构拆除问题建模为马尔可夫决策过程。
状态: 构件类型比例、应力、稳定性
动作: 拆除第k个构件
奖励: +拆除成功 - 位移惩罚 - 风险惩罚 - 步数成本
"""

import numpy as np
from typing import Optional
from collections import defaultdict

from core.models import StructureModel, ElementType

try:
    import gymnasium as gym
    from gymnasium import spaces
    GYM_AVAILABLE = True
except ImportError:
    GYM_AVAILABLE = False
    gym = None  # type: ignore
    spaces = None  # type: ignore


if GYM_AVAILABLE:
    _EnvBase = gym.Env
else:
    _EnvBase = object


class DemolitionEnv(_EnvBase):
    """钢结构拆除任务 Gym 环境"""

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        model: StructureModel,
        stability_threshold: float = 0.05,
        alpha: float = 100.0,
        beta: float = 10.0,
    ):
        super().__init__()
        self._initial_model = model
        self.remaining_elements = list(model.elements)
        self.removed_ids: list[int] = []
        self.stability_threshold = stability_threshold
        self.alpha = alpha
        self.beta = beta
        self._step_count = 0
        self._done = False
        self._node_map = {n.id: n for n in model.nodes}
        self._total = len(model.elements)

        self._force_cache = self._estimate_forces()
        self._rebuild_index()

        # 状态空间: 7 维连续
        self.observation_space = spaces.Box(
            low=0.0, high=1.0, shape=(7,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(max(1, self._total))

    def _estimate_forces(self) -> dict[int, float]:
        forces = {}
        max_z = max(
            (n.z for n in self._node_map.values()), default=1.0
        )
        for elem in self.remaining_elements:
            ni = self._node_map.get(elem.node_i_id)
            nj = self._node_map.get(elem.node_j_id)
            avg_z = ((ni.z + nj.z) / 2 if ni and nj else 0)
            h_r = avg_z / max(max_z, 0.01)

            if elem.element_type == ElementType.COLUMN:
                f = (1.0 - h_r * 0.4) * 0.8
            elif elem.element_type == ElementType.BEAM:
                f = 0.3 + h_r * 0.2
            else:
                f = 0.3
            forces[elem.id] = f
        return forces

    def _rebuild_index(self):
        self._idx_to_id = {}
        self._id_to_idx = {}
        for i, e in enumerate(self.remaining_elements):
            self._idx_to_id[i] = e.id
            self._id_to_idx[e.id] = i

    # ---- Gym interface ----

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.remaining_elements = list(self._initial_model.elements)
        self.removed_ids = []
        self._step_count = 0
        self._done = False
        self._rebuild_index()
        return self._obs(), {}

    def step(self, action: int):
        if self._done:
            return self._obs(), 0.0, True, True, {"status": "done"}

        n_avail = len(self._idx_to_id)
        if action >= n_avail or action not in self._idx_to_id:
            self._step_count += 1
            return self._obs(), -10.0, False, False, {"status": "invalid"}

        eid = self._idx_to_id[action]
        if eid in self.removed_ids:
            self._step_count += 1
            return self._obs(), -10.0, False, False, {"status": "duplicate"}

        self.remaining_elements = [
            e for e in self.remaining_elements if e.id != eid
        ]
        self.removed_ids.append(eid)
        self._step_count += 1
        self._rebuild_index()

        obs = self._obs()
        stability = obs[5]
        reward = -1.0 + 5.0  # 步数成本 + 拆除奖励

        if stability < 0.3:
            reward -= self.beta * 5
        elif stability < 0.5:
            reward -= self.beta * 2

        terminated = False
        truncated = False

        if len(self.remaining_elements) == 0:
            terminated = True
            reward += 20
        if stability < 0.1:
            terminated = True
            reward -= 50
        if self._step_count >= self._total * 2:
            truncated = True

        return obs, float(reward), terminated, truncated, {
            "element_removed": eid,
            "remaining": len(self.remaining_elements),
            "stability": float(stability),
            "reward": float(reward),
        }

    def _obs(self) -> np.ndarray:
        total = max(self._total, 1)
        remaining = len(self.remaining_elements)

        n_b = sum(1 for e in self.remaining_elements if e.element_type == ElementType.BEAM)
        n_c = sum(1 for e in self.remaining_elements if e.element_type == ElementType.COLUMN)
        n_br = sum(1 for e in self.remaining_elements if e.element_type == ElementType.BRACE)

        forces = [self._force_cache.get(e.id, 0.3) for e in self.remaining_elements]
        avg_s = np.mean(forces) if forces else 0.0
        max_s = np.max(forces) if forces else 0.0

        col_frac = n_c / total
        remaining_frac = remaining / total
        stability = np.clip(col_frac * 0.6 + remaining_frac * 0.4, 0.0, 1.0)
        removed_frac = len(self.removed_ids) / total

        obs = np.array([
            n_b / total, n_c / total, n_br / total,
            avg_s, max_s, stability, removed_frac,
        ], dtype=np.float32)
        return np.clip(obs, 0.0, 1.0)

    def render(self):
        pass
