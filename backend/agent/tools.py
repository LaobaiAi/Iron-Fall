"""AI 智能体工具集

定义 LangChain 工具，用于结构分析和拆除决策。
"""
from typing import Any
from langchain_core.tools import tool
from core.models import StructureModel, AnalysisResult


# ============================================================================
# 计算工具
# ============================================================================

@tool
def check_structure_stability(model: dict) -> dict:
    """检查结构稳定性

    使用 Frame3DD 进行快速静力分析，判断结构是否稳定。
    
    Args:
        model: StructureModel 的字典表示
        
    Returns:
        {
            "is_stable": bool,
            "max_displacement": float,
            "warnings": list[str]
        }
    """
    from engine.frame3dd import Frame3DDAdapter
    
    adapter = Frame3DDAdapter()
    structure_model = StructureModel(**model)
    
    import asyncio
    result = asyncio.run(adapter.run_static_analysis(structure_model))
    
    return {
        "is_stable": result.is_safe,
        "max_displacement": result.max_displacement,
        "stability_status": result.stability_status,
        "warnings": result.warnings
    }


@tool
def analyze_demolition_action(model: dict, action: dict) -> dict:
    """分析拆除动作的影响

    执行动力分析，评估移除构件后的结构响应。
    
    Args:
        model: StructureModel 的字典表示
        action: DemolitionAction 的字典表示
        
    Returns:
        {
            "is_safe": bool,
            "max_displacement": float,
            "warnings": list[str]
        }
    """
    from engine.frame3dd import Frame3DDAdapter
    from core.models import DemolitionAction
    
    adapter = Frame3DDAdapter()
    structure_model = StructureModel(**model)
    demolition_action = DemolitionAction(**action)
    
    import asyncio
    result = asyncio.run(
        adapter.run_dynamic_analysis(structure_model, demolition_action)
    )
    
    return {
        "is_safe": result.is_safe,
        "max_displacement": result.max_displacement,
        "stability_status": result.stability_status,
        "warnings": result.warnings
    }


@tool
def validate_structure_model(model: dict) -> dict:
    """验证结构模型的有效性

    检查节点、构件、材料、截面的完整性和一致性。
    
    Args:
        model: StructureModel 的字典表示
        
    Returns:
        {
            "is_valid": bool,
            "error_message": str | None
        }
    """
    from engine.frame3dd import Frame3DDAdapter
    
    adapter = Frame3DDAdapter()
    structure_model = StructureModel(**model)
    
    import asyncio
    is_valid, error = asyncio.run(adapter.validate_model(structure_model))
    
    return {
        "is_valid": is_valid,
        "error_message": error
    }


# ============================================================================
# 知识查询工具
# ============================================================================

@tool
def query_demolition_regulations(query: str) -> str:
    """查询钢结构拆除规范

    从知识库中检索相关的规范条文和安全要求。
    
    Args:
        query: 查询关键词
        
    Returns:
        相关规范条文的文本内容
    """
    # TODO: 实现 RAG 知识库检索
    # 临时返回基础规范摘要
    regulations = {
        "底层柱": "严禁拆除底层主要承重柱，如需拆除必须先设置支撑替换",
        "拆除顺序": "应遵循先次要构件、后主要构件的原则",
        "支撑系统": "必须保留足够的侧向支撑，确保结构整体稳定性",
        "监测要求": "拆除过程中应进行变形监测，发现异常立即停止作业"
    }
    
    for key, value in regulations.items():
        if key in query:
            return f"{key}: {value}"
    
    return "未找到相关规范条文，请咨询专业工程师"


@tool
def get_risk_assessment(element_ids: list[int], model: dict) -> str:
    """评估拆除风险等级

    根据目标构件类型和位置，评估拆除风险。
    
    Args:
        element_ids: 目标构件 ID 列表
        model: StructureModel 的字典表示
        
    Returns:
        风险评估报告
    """
    structure_model = StructureModel(**model)
    
    # 找出目标构件
    target_elements = [
        e for e in structure_model.elements if e.id in element_ids
    ]
    
    # 找出这些构件连接的节点
    target_nodes = {
        e.node_i_id for e in target_elements
    } | {
        e.node_j_id for e in target_elements
    }
    
    # 计算节点平均高度
    related_nodes = [n for n in structure_model.nodes if n.id in target_nodes]
    if related_nodes:
        avg_height = sum(n.z for n in related_nodes) / len(related_nodes)
    else:
        avg_height = 0
    
    # 风险评估
    element_types = {e.element_type.value for e in target_elements}
    
    if "Column" in element_types and avg_height < 1.0:
        return "HIGH: 涉及底层柱拆除，必须进行详细验算并设置临时支撑"
    elif "Column" in element_types:
        return "MEDIUM: 涉及柱构件拆除，建议复核稳定性"
    elif "Brace" in element_types:
        return "MEDIUM: 涉及支撑拆除，可能影响整体稳定性"
    else:
        return "LOW: 仅涉及梁等次要构件，风险可控"
