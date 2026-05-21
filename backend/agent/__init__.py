"""Iron-Fall AI 智能体模块

V4.0: 多智能体协同决策 + 案例知识库

使用懒加载 (PEP 562) 避免缺少可选依赖时阻止整个包导入。
"""
import importlib


def __getattr__(name: str):
    """懒加载子模块，按需导入。

    这允许在缺少 langgraph / langchain_openai 等可选依赖时
    仍能导入 agent 包的其余部分（如 parser, chimney_parser 等）。
    """
    _module_map = {
        # V1-V3 单智能体
        "DemolitionAgent": "agent.agent",
        "SimpleDemolitionAgent": "agent.agent",
        "create_agent": "agent.agent",
        # V4.0 多智能体
        "DebateOrchestrator": "agent.multi_agent",
        "RuleBasedPlanningAgent": "agent.multi_agent",
        "RuleBasedSafetyAgent": "agent.multi_agent",
        "RuleBasedEconomyAgent": "agent.multi_agent",
        "create_orchestrator": "agent.multi_agent",
        # V4.0 案例库
        "CaseLibrary": "agent.case_library",
        "get_case_library": "agent.case_library",
        # V4.0 工具
        "get_structure_topology": "agent.tools_v4",
        "compute_dependency_graph": "agent.tools_v4",
        "evaluate_single_removal": "agent.tools_v4",
        "check_regulation_compliance": "agent.tools_v4",
        "calculate_redundancy_score": "agent.tools_v4",
        "estimate_demolition_cost": "agent.tools_v4",
        "query_similar_case": "agent.tools_v4",
        "merge_demolition_plans": "agent.tools_v4",
    }

    if name in _module_map:
        module = importlib.import_module(_module_map[name])
        attr = getattr(module, name)
        return attr
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
