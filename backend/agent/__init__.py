"""Iron-Fall AI 智能体模块

V4.0: 多智能体协同决策 + 案例知识库
"""
from agent.agent import DemolitionAgent, SimpleDemolitionAgent, create_agent
from agent.multi_agent import (
    DebateOrchestrator,
    RuleBasedPlanningAgent,
    RuleBasedSafetyAgent,
    RuleBasedEconomyAgent,
    create_orchestrator,
)
from agent.case_library import CaseLibrary, get_case_library
from agent.tools_v4 import (
    get_structure_topology,
    compute_dependency_graph,
    evaluate_single_removal,
    check_regulation_compliance,
    calculate_redundancy_score,
    estimate_demolition_cost,
    query_similar_case,
    merge_demolition_plans,
)

__all__ = [
    # V1-V3 单智能体
    "DemolitionAgent",
    "SimpleDemolitionAgent",
    "create_agent",
    # V4.0 多智能体
    "DebateOrchestrator",
    "RuleBasedPlanningAgent",
    "RuleBasedSafetyAgent",
    "RuleBasedEconomyAgent",
    "create_orchestrator",
    # V4.0 案例库
    "CaseLibrary",
    "get_case_library",
    # V4.0 工具
    "get_structure_topology",
    "compute_dependency_graph",
    "evaluate_single_removal",
    "check_regulation_compliance",
    "calculate_redundancy_score",
    "estimate_demolition_cost",
    "query_similar_case",
    "merge_demolition_plans",
]
