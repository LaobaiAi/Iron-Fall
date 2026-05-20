"""Iron-Fall 核心数据结构 (IFCS) - Iron-Fall Core Schema

基于 Pydantic 的钢结构拆除分析数据模型。
严格遵循计划书第四章的 IFCS 规范。
"""
from enum import Enum
from typing import Optional, Literal
from pydantic import BaseModel, Field


class ElementType(str, Enum):
    """构件类型枚举"""
    COLUMN = "Column"
    BEAM = "Beam"
    BRACE = "Brace"


class Node(BaseModel):
    """节点模型 - 结构中的连接点

    Attributes:
        id: 节点唯一标识符
        x, y, z: 节点三维坐标 (单位: 米)
        restraint: 约束条件列表 [Ux, Uy, Uz, Rx, Ry, Rz]
                   True 表示该方向被约束
    """
    id: int
    x: float
    y: float
    z: float
    restraint: list[bool] = Field(
        default_factory=lambda: [True, True, True, False, False, False],
        description="节点约束条件 [Ux, Uy, Uz, Rx, Ry, Rz]"
    )


class Section(BaseModel):
    """截面模型 - 构件的几何特性

    Attributes:
        id: 截面唯一标识符
        name: 截面名称，如 "H400x200"
        A: 截面积 (单位: mm²)
        Iy: 绕 y 轴惯性矩 (单位: mm⁴)
        Iz: 绕 z 轴惯性矩 (单位: mm⁴)
        J: 扭转常数 (单位: mm⁴)
    """
    id: int
    name: str = Field(description="截面名称，如 H400x200")
    A: float = Field(description="截面积 (mm²)")
    Iy: float = Field(description="绕 y 轴惯性矩 (mm⁴)")
    Iz: float = Field(description="绕 z 轴惯性矩 (mm⁴)")
    J: float = Field(description="扭转常数 (mm⁴)")


class Material(BaseModel):
    """材料模型 - 钢材的力学特性

    Attributes:
        id: 材料唯一标识符
        name: 材料牌号，如 "Q355"
        E: 弹性模量 (单位: MPa)
        fy: 屈服强度 (单位: MPa)
        density: 密度 (单位: kg/m³)
    """
    id: int
    name: str = Field(description="材料牌号，如 Q355")
    E: float = Field(description="弹性模量 (MPa)")
    fy: float = Field(description="屈服强度 (MPa)")
    density: float = Field(description="密度 (kg/m³)")


class Element(BaseModel):
    """构件模型 - 结构中的梁、柱、支撑

    Attributes:
        id: 构件唯一标识符
        node_i_id: 构件 i 端节点 ID
        node_j_id: 构件 j 端节点 ID
        section_id: 截面 ID
        material_id: 材料 ID
        element_type: 构件类型 (柱/梁/支撑)
    """
    id: int
    node_i_id: int
    node_j_id: int
    section_id: int
    material_id: int
    element_type: ElementType


class DemolitionAction(BaseModel):
    """拆除动作模型 - 单个拆除操作

    Attributes:
        step: 操作步骤序号
        target_element_ids: 目标构件 ID 列表
        action_type: 动作类型 (Remove/ApplyForce)
        force_vector: 外力向量 (x, y, z)，单位: kN
    """
    step: int
    target_element_ids: list[int]
    action_type: Literal["Remove", "ApplyForce"] = "Remove"
    force_vector: Optional[tuple[float, float, float]] = None


class DemolitionPlan(BaseModel):
    """拆除方案模型 - 完整的拆除计划

    Attributes:
        plan_id: 方案唯一标识符
        description: 方案描述
        actions: 拆除动作序列
        risk_level: 风险等级 (Low/Medium/High/Critical)
    """
    plan_id: str
    description: str = ""
    actions: list[DemolitionAction] = Field(default_factory=list)
    risk_level: Literal["Low", "Medium", "High", "Critical"] = "Low"


class StructureModel(BaseModel):
    """结构模型 - 完整的钢结构模型

    Attributes:
        model_id: 模型唯一标识符
        name: 模型名称
        nodes: 节点列表
        elements: 构件列表
        sections: 截面列表
        materials: 材料列表
        unit: 单位系统 (默认: SI, m-kN-s)
    """
    model_id: str
    name: str = "Steel Structure"
    nodes: list[Node] = Field(default_factory=list)
    elements: list[Element] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    materials: list[Material] = Field(default_factory=list)
    unit: str = Field(default="SI", description="单位系统 (SI: m-kn-s)")


class AnalysisResult(BaseModel):
    """分析结果模型 - 力学计算结果

    Attributes:
        node_displacements: 节点位移字典 {node_id: [Ux, Uy, Uz, Rx, Ry, Rz]}
        element_stresses: 构件应力字典 {element_id: stress_value}
        max_displacement: 最大位移值
        stability_status: 稳定性状态
        is_safe: 是否安全可执行
    """
    node_displacements: dict[int, list[float]] = Field(
        default_factory=dict,
        description="节点位移 {node_id: [Ux, Uy, Uz, Rx, Ry, Rz]}"
    )
    element_stresses: dict[int, float] = Field(
        default_factory=dict,
        description="构件应力 {element_id: stress_MPa}"
    )
    max_displacement: float = Field(default=0.0, description="最大位移 (m)")
    stability_status: Literal["Stable", "Unstable", "Critical", "Collapse"] = "Stable"
    is_safe: bool = Field(default=True, description="是否安全可执行")
    warnings: list[str] = Field(default_factory=list, description="警告信息")


class DemolitionResponse(BaseModel):
    """拆除响应模型 - API 响应数据结构

    Attributes:
        success: 是否成功
        plan: 拆除方案 (如果有)
        analysis: 分析结果 (如果有)
        message: 响应消息
        latency_ms: 处理延迟 (毫秒)
    """
    success: bool = True
    plan: Optional[DemolitionPlan] = None
    analysis: Optional[AnalysisResult] = None
    message: str = ""
    latency_ms: float = 0.0
