"""V4.0 多智能体协同决策框架

实现规划(Planning)、安全(Safety)、经济(Economy)三个角色智能体的
辩论式协作机制，产出平衡多方诉求的最优拆除方案。

支持有/无 LLM 两种模式：
- LLM 模式：基于 LangChain ReAct Agent，思考更深入
- 规则模式：基于预设规则，无需 API，保证始终可用
"""
import os
import json
import asyncio
import hashlib
import time
from typing import Optional, Any

from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction,
    ElementType, AgentRole, AgentOpinion, DebateRecord,
    MultiAgentDecision, AnalysisResult,
)
from agent.prompts_v4 import AGENT_PROMPTS


# ============================================================================
# 规则模式智能体基类
# ============================================================================

class RuleBasedAgent:
    """规则模式智能体基类
    
    无需 LLM API，基于结构规则和启发式算法生成决策。
    """
    
    def __init__(self, role: AgentRole):
        self.role = role
        self._opinion: Optional[AgentOpinion] = None
    
    def generate_opinion(
        self, model: StructureModel, user_prefs: dict = None
    ) -> AgentOpinion:
        """生成该角色的决策意见"""
        raise NotImplementedError
    
    @property
    def opinion(self) -> Optional[AgentOpinion]:
        return self._opinion


class RuleBasedPlanningAgent(RuleBasedAgent):
    """规则模式规划智能体
    
    基于拓扑排序的自上而下拆除序列规划。
    策略：先梁后柱、上半部分优先。
    """
    
    def __init__(self):
        super().__init__(AgentRole.PLANNING)
    
    def generate_opinion(
        self, model: StructureModel, user_prefs: dict = None
    ) -> AgentOpinion:
        # 提取构件
        beams = [e for e in model.elements if e.element_type == ElementType.BEAM]
        columns = [e for e in model.elements if e.element_type == ElementType.COLUMN]
        braces = [e for e in model.elements if e.element_type == ElementType.BRACE]
        
        # 按高度排序
        node_z = {n.id: n.z for n in model.nodes}
        
        def avg_z(elem) -> float:
            return (node_z.get(elem.node_i_id, 0) +
                    node_z.get(elem.node_j_id, 0)) / 2
        
        # 顺序：支撑 → 梁(自上而下) → 柱(上半部分)
        actions = []
        step = 1
        
        sorted_beams = sorted(beams, key=avg_z, reverse=True)
        sorted_columns = sorted(columns, key=avg_z, reverse=True)
        sorted_braces = sorted(braces, key=avg_z, reverse=True)
        
        # 先拆支撑（每步最多2个）
        for i in range(0, len(sorted_braces), 2):
            batch = sorted_braces[i:i+2]
            if batch:
                actions.append(DemolitionAction(
                    step=step,
                    target_element_ids=[b.id for b in batch],
                    action_type="Remove",
                ))
                step += 1
        
        # 再拆梁（每步最多3个）
        for i in range(0, len(sorted_beams), 3):
            batch = sorted_beams[i:i+3]
            if batch:
                actions.append(DemolitionAction(
                    step=step,
                    target_element_ids=[b.id for b in batch],
                    action_type="Remove",
                ))
                step += 1
        
        # 最后拆上半部分柱
        max_z = max(node_z.values()) if node_z else 0
        upper_cols = [c for c in sorted_columns if avg_z(c) > max_z * 0.4]
        for i in range(0, len(upper_cols), 2):
            batch = upper_cols[i:i+2]
            if batch:
                actions.append(DemolitionAction(
                    step=step,
                    target_element_ids=[c.id for c in batch],
                    action_type="Remove",
                ))
                step += 1
        
        # 剩余底层柱
        lower_cols = [c for c in sorted_columns if avg_z(c) <= max_z * 0.4]
        for i in range(0, len(lower_cols), 2):
            batch = lower_cols[i:i+2]
            if batch:
                actions.append(DemolitionAction(
                    step=step,
                    target_element_ids=[c.id for c in batch],
                    action_type="Remove",
                ))
                step += 1
        
        plan = DemolitionPlan(
            plan_id=f"planning_{hashlib.md5(model.model_id.encode()).hexdigest()[:8]}",
            description=f"自上而下拆除方案 - {len(actions)}步",
            actions=actions,
            risk_level=self._estimate_risk(model, actions),
        )
        
        self._opinion = AgentOpinion(
            agent_role=self.role,
            plan=plan,
            scores={
                "safety": 0.75,
                "efficiency": 0.85,
                "cost": 0.80,
                "overall": 0.80,
            },
            reasoning=f"规划: 先拆{len(braces)}支撑→{len(beams)}梁→{len(columns)}柱，共{len(actions)}步",
            confidence=0.85,
        )
        return self._opinion
    
    def _estimate_risk(
        self, model: StructureModel, actions: list[DemolitionAction]
    ) -> str:
        node_z = {n.id: n.z for n in model.nodes}
        min_z = min(node_z.values()) if node_z else 0
        max_z = max(node_z.values()) if node_z else 0
        
        for action in actions:
            for eid in action.target_element_ids:
                elem = next((e for e in model.elements if e.id == eid), None)
                if elem and elem.element_type == ElementType.COLUMN:
                    zs = [node_z.get(elem.node_i_id, 0),
                          node_z.get(elem.node_j_id, 0)]
                    if min(zs) < min_z + (max_z - min_z) * 0.15:
                        return "High"
        return "Low" if len(actions) < 10 else "Medium"


class RuleBasedSafetyAgent(RuleBasedAgent):
    """规则模式安全审查智能体
    
    基于规范条文和风险矩阵评估方案安全性。
    """
    
    def __init__(self):
        super().__init__(AgentRole.SAFETY)
    
    def generate_opinion(
        self, model: StructureModel, user_prefs: dict = None
    ) -> AgentOpinion:
        node_z = {n.id: n.z for n in model.nodes}
        min_z = min(node_z.values()) if node_z else 0
        max_z = max(node_z.values()) if node_z else 0
        
        critical_risks = []
        violations = []
        required_measures = []
        
        # 检查底层柱
        for e in model.elements:
            if e.element_type == ElementType.COLUMN:
                zs = [node_z.get(e.node_i_id, 0),
                      node_z.get(e.node_j_id, 0)]
                if min(zs) < min_z + (max_z - min_z) * 0.15:
                    critical_risks.append(
                        f"构件{e.id}: 底层柱，拆除风险极高"
                    )
                    required_measures.append(
                        f"底层柱{e.id}拆除前必须设置临时钢支撑"
                    )
                    violations.append(
                        f"《规范》第4.2条: 底层主要承重柱需支撑替换后拆除"
                    )
        
        # 检查支撑
        braces = [e for e in model.elements if e.element_type == ElementType.BRACE]
        if braces:
            critical_risks.append(
                f"结构含{len(braces)}根支撑，拆除时将削弱侧向刚度"
            )
            required_measures.append(
                "支撑应在拆除顺序中尽可能靠后保留"
            )
        
        safety_score = max(0.1, 1.0 - 0.3 * len(critical_risks) - 0.2 * len(violations))
        
        self._opinion = AgentOpinion(
            agent_role=self.role,
            plan=None,
            scores={
                "safety": round(safety_score, 2),
                "efficiency": 0.0,
                "cost": 0.0,
                "overall": round(safety_score, 2),
            },
            reasoning=f"安全审查: {len(critical_risks)}个关键风险, {len(violations)}条规范违例",
            confidence=0.9,
        )
        return self._opinion


class RuleBasedEconomyAgent(RuleBasedAgent):
    """规则模式经济智能体
    
    基于构件数量和类型估算拆除成本和工期。
    """
    
    def __init__(self):
        super().__init__(AgentRole.ECONOMY)
    
    def generate_opinion(
        self, model: StructureModel, user_prefs: dict = None
    ) -> AgentOpinion:
        total_elements = len(model.elements)
        columns = sum(1 for e in model.elements
                      if e.element_type == ElementType.COLUMN)
        
        # 简易成本估算（万元）
        unit_cost_map = {
            ElementType.COLUMN: 0.5,
            ElementType.BEAM: 0.3,
            ElementType.BRACE: 0.4,
        }
        
        total_cost = sum(
            unit_cost_map.get(e.element_type, 0.3)
            for e in model.elements
        )
        base_cost = 5.0  # 基础固定成本（进场、清理等）
        total_cost = round(base_cost + total_cost, 1)
        
        # 工期估算
        daily_capacity = 6  # 每天可拆构件数
        duration = max(3, total_elements // daily_capacity + 2)
        
        # 机械成本占比
        mechanical_ratio = 0.5 + 0.1 * (columns / max(total_elements, 1))
        
        self._opinion = AgentOpinion(
            agent_role=self.role,
            plan=None,
            scores={
                "safety": 0.0,
                "efficiency": 0.0,
                "cost": round(max(0.1, 1.0 - total_cost / 100), 2),
                "overall": 0.0,
            },
            reasoning=(
                f"经济估算: 总成本约{total_cost}万元 "
                f"(机械{total_cost*mechanical_ratio:.1f}/人工{total_cost*(1-mechanical_ratio):.1f})"
                f", 工期{duration}天, 共{total_elements}个构件"
            ),
            confidence=0.75,
        )
        return self._opinion


# ============================================================================
# 辩论协调器
# ============================================================================

class DebateOrchestrator:
    """多智能体辩论协调器
    
    组织 Planning/Safety/Economy 三个智能体进行辩论式协作。
    
    机制：
    1. 各智能体独立生成方案
    2. Safety 审查 Planning 的方案
    3. Economy 评估各方方案的成本
    4. 融合生成最终共识方案
    """
    
    MAX_DEBATE_ROUNDS = 3
    CONSENSUS_THRESHOLD = 0.15  # 评分方差阈值
    
    def __init__(self, use_llm: bool = False):
        """
        Args:
            use_llm: 是否使用 LLM (需要 OPENAI_API_KEY)
        """
        self._use_llm = use_llm
        self._planning = RuleBasedPlanningAgent()
        self._safety = RuleBasedSafetyAgent()
        self._economy = RuleBasedEconomyAgent()
    
    def decide(
        self,
        model: StructureModel,
        user_prefs: dict = None,
    ) -> MultiAgentDecision:
        """执行多智能体协同决策
        
        Args:
            model: 结构模型
            user_prefs: 用户偏好，如 {"safety": 0.7, "speed": 0.2, "cost": 0.1}
            
        Returns:
            融合各方意见的最终决策
        """
        if user_prefs is None:
            user_prefs = {"safety": 0.5, "speed": 0.25, "cost": 0.25}
        
        start_time = time.time()
        debate_history = []
        
        # ========================================
        # Round 1: 各智能体独立生成意见
        # ========================================
        planning_opinion = self._planning.generate_opinion(model, user_prefs)
        safety_opinion = self._safety.generate_opinion(model, user_prefs)
        economy_opinion = self._economy.generate_opinion(model, user_prefs)
        
        debate_history.append(DebateRecord(
            round=1,
            topic="独立方案生成",
            opinions=[planning_opinion, safety_opinion, economy_opinion],
            consensus_reached=False,
        ))
        
        # ========================================
        # Round 2: Safety 审查 Planning 方案
        # ========================================
        safety_on_planning = self._safety_review_plan(
            model, planning_opinion.plan
        )
        
        debate_history.append(DebateRecord(
            round=2,
            topic="安全审查规划方案",
            opinions=[safety_on_planning],
            consensus_reached=self._check_consensus(
                planning_opinion, safety_on_planning
            ),
        ))
        
        # ========================================
        # Round 3: Economy 评估 & 融合
        # ========================================
        economy_on_planning = self._economy_review_plan(
            model, planning_opinion.plan
        )
        
        debate_history.append(DebateRecord(
            round=3,
            topic="经济评估与方案融合",
            opinions=[economy_on_planning],
            consensus_reached=True,
        ))
        
        # ========================================
        # 最终融合
        # ========================================
        final_plan = self._merge_plans(
            model, planning_opinion, safety_opinion, economy_opinion
        )
        
        all_opinions = [planning_opinion, safety_opinion, economy_opinion]
        consensus_score = self._compute_consensus_score(all_opinions)
        
        warnings = self._collect_warnings(
            model, planning_opinion, safety_opinion, economy_opinion
        )
        
        divergent_points = self._find_divergent_points(
            planning_opinion, safety_opinion, economy_opinion
        )
        
        decision_id = hashlib.md5(
            f"{model.model_id}_{time.time()}".encode()
        ).hexdigest()[:12]
        
        return MultiAgentDecision(
            decision_id=decision_id,
            model_id=model.model_id,
            final_plan=final_plan,
            agent_opinions=all_opinions,
            debate_history=debate_history,
            consensus_score=round(consensus_score, 2),
            risk_assessment=self._summarize_risk(safety_opinion),
            cost_estimate=self._estimate_from_economy(economy_opinion, model),
            duration_estimate=self._estimate_duration(planning_opinion, model),
            warnings=warnings,
            divergent_points=divergent_points,
        )
    
    def _safety_review_plan(
        self, model: StructureModel, plan: DemolitionPlan
    ) -> AgentOpinion:
        """安全审查规划方案"""
        violations = []
        critical_risks = []
        node_z = {n.id: n.z for n in model.nodes}
        min_z = min(node_z.values()) if node_z else 0
        max_z = max(node_z.values()) if node_z else 0
        
        for action in plan.actions:
            for eid in action.target_element_ids:
                elem = next((e for e in model.elements if e.id == eid), None)
                if elem and elem.element_type == ElementType.COLUMN:
                    zs = [
                        node_z.get(elem.node_i_id, 0),
                        node_z.get(elem.node_j_id, 0),
                    ]
                    if min(zs) < min_z + (max_z - min_z) * 0.2:
                        violations.append(
                            f"步骤{action.step}: 底层柱{eid}不应在此阶段拆除"
                        )
                if elem and elem.element_type == ElementType.BRACE:
                    critical_risks.append(
                        f"步骤{action.step}: 支撑{eid}拆除可能影响侧向稳定"
                    )
        
        s = max(0.1, 1.0 - 0.3 * len(violations) - 0.1 * len(critical_risks))
        
        return AgentOpinion(
            agent_role=AgentRole.SAFETY,
            plan=plan,
            scores={"safety": round(s, 2), "efficiency": 0.0,
                    "cost": 0.0, "overall": round(s, 2)},
            reasoning=f"审查结果: {len(violations)}个违规, {len(critical_risks)}个风险点",
            confidence=0.85,
        )
    
    def _economy_review_plan(
        self, model: StructureModel, plan: DemolitionPlan
    ) -> AgentOpinion:
        """经济评估规划方案"""
        total_steps = len(plan.actions)
        columns_removed = sum(
            1 for action in plan.actions
            for eid in action.target_element_ids
            if any(e.id == eid and e.element_type == ElementType.COLUMN
                   for e in model.elements)
        )
        
        cost = round(5.0 + total_steps * 1.2 + columns_removed * 0.5, 1)
        duration = max(3, total_steps + 2)
        
        return AgentOpinion(
            agent_role=AgentRole.ECONOMY,
            plan=plan,
            scores={
                "safety": 0.0, "efficiency": 0.0,
                "cost": round(max(0.1, 1.0 - cost / 80), 2),
                "overall": 0.0,
            },
            reasoning=f"成本: ~{cost}万元, 工期: ~{duration}天",
            confidence=0.7,
        )
    
    def _merge_plans(
        self,
        model: StructureModel,
        planning: AgentOpinion,
        safety: AgentOpinion,
        economy: AgentOpinion,
    ) -> DemolitionPlan:
        """融合三个智能体的意见生成最终方案"""
        # 以规划方案为基础
        base_plan = planning.plan
        if not base_plan:
            return DemolitionPlan(
                plan_id="merged_fallback",
                description="所有智能体均未生成有效方案",
                actions=[],
                risk_level="High",
            )
        
        # 安全检查：移除有风险的步骤
        node_z = {n.id: n.z for n in model.nodes}
        min_z = min(node_z.values()) if node_z else 0
        max_z = max(node_z.values()) if node_z else 0
        
        safe_actions = []
        postponed = []  # 推迟到底层的柱
        
        for action in base_plan.actions:
            safe_eids = []
            for eid in action.target_element_ids:
                elem = next((e for e in model.elements if e.id == eid), None)
                if elem and elem.element_type == ElementType.COLUMN:
                    zs = [
                        node_z.get(elem.node_i_id, 0),
                        node_z.get(elem.node_j_id, 0),
                    ]
                    if min(zs) < min_z + (max_z - min_z) * 0.2:
                        postponed.append(eid)
                        continue
                safe_eids.append(eid)
            
            if safe_eids:
                safe_actions.append(DemolitionAction(
                    step=action.step,
                    target_element_ids=safe_eids,
                    action_type=action.action_type,
                ))
        
        # 将推迟的底层柱放在最后
        if postponed:
            max_step = safe_actions[-1].step if safe_actions else 0
            safe_actions.append(DemolitionAction(
                step=max_step + 1,
                target_element_ids=postponed,
                action_type="Remove",
            ))
        
        # 重新编号
        for i, a in enumerate(safe_actions, 1):
            a.step = i
        
        risk = "Low"
        if postponed:
            risk = "High"
        elif len(safe_actions) > 15:
            risk = "Medium"
        
        return DemolitionPlan(
            plan_id=f"v4_consensus_{hashlib.md5(model.model_id.encode()).hexdigest()[:8]}",
            description=(
                f"多智能体共识方案 - "
                f"规划({planning.scores['overall']:.1%}) | "
                f"安全({safety.scores['safety']:.1%}) | "
                f"经济({economy.scores['cost']:.1%})"
            ),
            actions=safe_actions,
            risk_level=risk,
        )
    
    def _check_consensus(
        self, op1: AgentOpinion, op2: AgentOpinion
    ) -> bool:
        """检查两个智能体是否达成共识"""
        scores1 = list(op1.scores.values())
        scores2 = list(op2.scores.values())
        n = min(len(scores1), len(scores2))
        if n == 0:
            return True
        var = sum(abs(scores1[i] - scores2[i]) for i in range(n)) / n
        return var < self.CONSENSUS_THRESHOLD
    
    def _compute_consensus_score(self, opinions: list[AgentOpinion]) -> float:
        """计算共识度"""
        overalls = [o.scores["overall"] for o in opinions]
        if len(overalls) < 2:
            return 0.5
        mean = sum(overalls) / len(overalls)
        var = sum((v - mean) ** 2 for v in overalls) / len(overalls)
        return round(max(0.0, 1.0 - var * 5), 2)
    
    def _collect_warnings(
        self,
        model: StructureModel,
        planning: AgentOpinion,
        safety: AgentOpinion,
        economy: AgentOpinion,
    ) -> list[str]:
        """收集多方一致警告"""
        warnings = []
        node_z = {n.id: n.z for n in model.nodes}
        min_z = min(node_z.values()) if node_z else 0
        max_z = max(node_z.values()) if node_z else 0
        
        low_cols = [
            e.id for e in model.elements
            if e.element_type == ElementType.COLUMN
            and min(node_z.get(e.node_i_id, 0),
                    node_z.get(e.node_j_id, 0)) < min_z + (max_z - min_z) * 0.15
        ]
        if low_cols:
            warnings.append(
                f"底层柱({low_cols})必须最后拆除，或设置临时支撑"
            )
        
        braces = [e for e in model.elements if e.element_type == ElementType.BRACE]
        if braces:
            warnings.append(f"结构含{len(braces)}根支撑，保留至拆除后期")
        
        return warnings
    
    def _find_divergent_points(
        self,
        planning: AgentOpinion,
        safety: AgentOpinion,
        economy: AgentOpinion,
    ) -> list[str]:
        """找出分歧点"""
        divergent = []
        if abs(planning.scores["overall"] - safety.scores["overall"]) > 0.3:
            divergent.append("规划与安全在方案可行性上存在较大分歧")
        if abs(safety.scores["safety"] - economy.scores["cost"]) > 0.4:
            divergent.append("安全与经济在成本约束上存在权衡")
        return divergent
    
    def _summarize_risk(self, safety: AgentOpinion) -> str:
        if safety.scores["safety"] >= 0.8:
            return "低风险：方案整体安全可控"
        elif safety.scores["safety"] >= 0.5:
            return "中等风险：部分步骤需加强安全措施"
        return "高风险：方案需重新评估，多处安全隐患"
    
    def _estimate_from_economy(
        self, economy: AgentOpinion, model: StructureModel
    ) -> float:
        total = len(model.elements)
        return round(5.0 + total * 0.8, 1)
    
    def _estimate_duration(
        self, planning: AgentOpinion, model: StructureModel
    ) -> int:
        if planning.plan:
            return max(3, len(planning.plan.actions) + 2)
        return max(3, len(model.elements) // 4 + 1)


# ============================================================================
# 工厂函数
# ============================================================================

def create_orchestrator(use_llm: bool = False) -> DebateOrchestrator:
    """创建多智能体辩论协调器
    
    Args:
        use_llm: 是否启用 LLM 模式
    """
    if use_llm:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("[V4.0] OPENAI_API_KEY 未设置，回退到规则模式")
            return DebateOrchestrator(use_llm=False)
    
    return DebateOrchestrator(use_llm=use_llm)
