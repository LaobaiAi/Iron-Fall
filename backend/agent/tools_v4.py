"""V4.0 多智能体专用工具集

为 Planning(规划)、Safety(安全)、Economy(经济) 智能体
提供专用的 LangChain 工具函数。
"""
from typing import Any
from langchain_core.tools import tool
from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction,
    AnalysisResult, ElementType, DemolitionCase
)


# ============================================================================
# 规划智能体工具
# ============================================================================

@tool
def get_structure_topology(model: dict) -> dict:
    """获取结构拓扑信息

    返回结构的层级关系、构件分组、传力路径摘要，
    供规划智能体决策拆除顺序。

    Args:
        model: StructureModel 的字典表示

    Returns:
        拓扑分析摘要
    """
    structure = StructureModel(**model)

    nodes_by_z = {}
    for n in structure.nodes:
        z_key = round(n.z, 1)
        nodes_by_z.setdefault(z_key, []).append(n.id)

    sorted_zs = sorted(nodes_by_z.keys())

    elements_by_type = {"Column": [], "Beam": [], "Brace": []}
    for e in structure.elements:
        elements_by_type[e.element_type.value].append(e.id)

    return {
        "total_nodes": len(structure.nodes),
        "total_elements": len(structure.elements),
        "elevation_levels": len(nodes_by_z),
        "level_map": {f"L{i}": nodes_by_z[z]
                       for i, z in enumerate(sorted_zs)},
        "elements_by_type": elements_by_type,
        "columns": len(elements_by_type["Column"]),
        "beams": len(elements_by_type["Beam"]),
        "braces": len(elements_by_type["Brace"]),
    }


@tool
def compute_dependency_graph(model: dict) -> dict:
    """计算构件依赖图

    分析哪些构件在拆除时需要其他构件提供支撑，
    用于规划拆除顺序。

    Args:
        model: StructureModel 的字典表示

    Returns:
        依赖关系摘要
    """
    structure = StructureModel(**model)

    node_to_elements = {}
    for e in structure.elements:
        node_to_elements.setdefault(e.node_i_id, []).append(e.id)
        node_to_elements.setdefault(e.node_j_id, []).append(e.id)

    dep_graph = {}
    for e in structure.elements:
        connected_i = set(node_to_elements.get(e.node_i_id, [])) - {e.id}
        connected_j = set(node_to_elements.get(e.node_j_id, [])) - {e.id}
        dep_graph[e.id] = list(connected_i | connected_j)

    return {
        "dependency_graph": dep_graph,
        "element_count": len(structure.elements),
    }


# ============================================================================
# 安全智能体工具
# ============================================================================

@tool
def evaluate_single_removal(
    model: dict, element_ids: list[int]
) -> dict:
    """评估移除指定构件后的结构安全

    使用 anaStruct 快速验算移除后结构的位移和稳定性。

    Args:
        model: StructureModel 的字典表示
        element_ids: 要移除的构件 ID 列表

    Returns:
        安全评估结果
    """
    from engine.anastruct_adapter import AnaStructAdapter

    structure = StructureModel(**model)

    # 创建移除后的临时模型
    remaining = [
        e for e in structure.elements if e.id not in element_ids
    ]
    temp_model = StructureModel(
        model_id=f"{structure.model_id}_temp",
        name=structure.name,
        nodes=structure.nodes,
        elements=remaining,
        sections=structure.sections,
        materials=structure.materials,
    )

    adapter = AnaStructAdapter()

    import asyncio
    try:
        is_stable, max_disp = asyncio.run(
            adapter.check_stability(temp_model, threshold=0.1)
        )
    except Exception:
        is_stable = False
        max_disp = 999.0

    return {
        "removed_ids": element_ids,
        "is_stable": is_stable,
        "max_displacement_m": round(max_disp, 4),
        "remaining_elements": len(remaining),
        "critical": max_disp > 0.1 or not is_stable,
    }


@tool
def check_regulation_compliance(model: dict, plan: dict) -> dict:
    """检查方案是否符合安全规范

    对照《钢结构拆除施工安全技术规范》逐条审查。

    Args:
        model: StructureModel 的字典表示
        plan: DemolitionPlan 的字典表示

    Returns:
        合规审查结果
    """
    structure = StructureModel(**model)
    demolish_plan = DemolitionPlan(**plan)

    max_z = max(n.z for n in structure.nodes)
    min_z = min(n.z for n in structure.nodes)

    violations = []
    required = []

    for action in demolish_plan.actions:
        for eid in action.target_element_ids:
            elem = next((e for e in structure.elements if e.id == eid), None)
            if not elem:
                continue

            if elem.element_type == ElementType.COLUMN:
                node_zs = [
                    n.z for n in structure.nodes
                    if n.id in (elem.node_i_id, elem.node_j_id)
                ]
                if node_zs and min(node_zs) < (min_z + (max_z - min_z) * 0.1):
                    violations.append(
                        f"步骤{action.step}: 构件{eid}为底层柱，"
                        "拆除前必须设置临时支撑"
                    )

            if elem.element_type == ElementType.BRACE:
                violations.append(
                    f"步骤{action.step}: 拆除支撑构件{eid}前"
                    "需进行侧向稳定性验算"
                )

    return {
        "plan_id": demolish_plan.plan_id,
        "violations": violations,
        "required_measures": required,
        "is_compliant": len(violations) == 0,
        "violation_count": len(violations),
    }


@tool
def calculate_redundancy_score(model: dict) -> dict:
    """计算结构冗余度

    评估结构在构件失效后的安全性储备。

    Args:
        model: StructureModel 的字典表示

    Returns:
        冗余度分析
    """
    structure = StructureModel(**model)

    columns = [e for e in structure.elements
               if e.element_type == ElementType.COLUMN]
    beams = [e for e in structure.elements
             if e.element_type == ElementType.BEAM]
    braces = [e for e in structure.elements
              if e.element_type == ElementType.BRACE]

    redundancy_score = min(
        1.0,
        len(columns) * 0.25 + len(beams) * 0.05 + len(braces) * 0.15
    )

    return {
        "redundancy_score": round(redundancy_score, 2),
        "level": (
            "High" if redundancy_score > 0.7
            else "Medium" if redundancy_score > 0.4
            else "Low"
        ),
        "critical_path_columns": len(columns),
        "redundant_beams": len(beams),
    }


# ============================================================================
# 经济智能体工具
# ============================================================================

@tool
def estimate_demolition_cost(
    model: dict, plan: dict
) -> dict:
    """估算拆除成本

    基于构件数量、类型和拆除步骤估算机械台班和人工费用。

    Args:
        model: StructureModel 的字典表示
        plan: DemolitionPlan 的字典表示

    Returns:
        成本估算
    """
    structure = StructureModel(**model)
    demolish_plan = DemolitionPlan(**plan)

    total_elements = len(demolish_plan.actions)
    columns = sum(
        1 for action in demolish_plan.actions
        for eid in action.target_element_ids
        if any(e.id == eid and e.element_type == ElementType.COLUMN
               for e in structure.elements)
    )
    beams = sum(
        1 for action in demolish_plan.actions
        for eid in action.target_element_ids
        if any(e.id == eid and e.element_type == ElementType.BEAM
               for e in structure.elements)
    )

    # 成本基准 (万元)
    mechanical_cost = total_elements * 0.8  # 机械台班
    labor_cost = total_elements * 0.5        # 人工
    material_cost = total_elements * 0.2     # 材料与耗材
    support_cost = columns * 0.3             # 临时支撑

    total = round(mechanical_cost + labor_cost + material_cost + support_cost, 1)

    return {
        "cost_estimate_wan": total,
        "breakdown": {
            "mechanical": round(mechanical_cost, 1),
            "labor": round(labor_cost, 1),
            "materials": round(material_cost, 1),
            "temporary_support": round(support_cost, 1),
        },
        "total_elements": total_elements,
        "columns_to_remove": columns,
        "duration_estimate_days": max(7, total_elements // 3 + 3),
    }


@tool
def query_similar_case(model: dict) -> dict:
    """查询相似历史拆除案例

    检索与当前结构相似的已完工拆除项目，获取成本和工期基准。

    Args:
        model: StructureModel 的字典表示

    Returns:
        相似案例摘要
    """
    from agent.case_library import CaseLibrary

    structure = StructureModel(**model)
    lib = CaseLibrary()
    matches = lib.search_similar(structure, top_k=3)

    return {
        "matches": [
            {
                "case_id": m.case.case_id,
                "project_name": m.case.project_name,
                "similarity": round(m.similarity_score, 2),
                "cost_wan": m.case.cost_wan_yuan,
                "duration_days": m.case.duration_days,
                "method": m.case.demolition_method,
                "lessons": m.case.key_lessons[:2],
            }
            for m in matches
        ],
        "avg_cost_wan": round(
            sum(m.case.cost_wan_yuan for m in matches) / max(len(matches), 1), 1
        ),
        "avg_duration_days": sum(
            m.case.duration_days for m in matches
        ) // max(len(matches), 1),
    }


# ============================================================================
# 通用工具
# ============================================================================

@tool
def merge_demolition_plans(plans: list[dict]) -> dict:
    """融合多个拆除方案

    当规划/安全/经济智能体各自生成方案后，
    通过投票/优先级融合为统一方案。

    Args:
        plans: 多个 DemolitionPlan 字典列表

    Returns:
        融合后的方案
    """
    if not plans:
        return {"plan": None, "merged": False}

    # 投票选出最常用的步骤
    step_votes = {}
    for p in plans:
        plan_obj = DemolitionPlan(**p.get("plan", p))
        for action in plan_obj.actions:
            key = (action.step, tuple(sorted(action.target_element_ids)))
            step_votes[key] = step_votes.get(key, 0) + 1

    # 多数通过的步骤
    threshold = len(plans) // 2 + 1
    merged_actions = []
    for (step, element_ids), votes in sorted(step_votes.items()):
        if votes >= threshold:
            merged_actions.append(DemolitionAction(
                step=step,
                target_element_ids=list(element_ids),
                action_type="Remove",
            ))

    if not merged_actions and plans:
        merged_plan = DemolitionPlan(**plans[0].get("plan", plans[0]))
        merged_actions = merged_plan.actions

    merged_plan = DemolitionPlan(
        plan_id="merged_plan",
        description=f"多智能体融合方案 (来自{len(plans)}个智能体)",
        actions=merged_actions,
        risk_level="Medium",
    )

    return {
        "plan": merged_plan.model_dump(),
        "merged": True,
        "consensus_rate": round(
            len(merged_actions) / max(len(plans), 1), 2
        ),
    }
