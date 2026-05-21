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
        success: 分析是否成功完成
        node_displacements: 节点位移字典 {node_id: [Ux, Uy, Uz, Rx, Ry, Rz]}
        element_stresses: 构件应力字典 {element_id: stress_value}
        max_displacement: 最大位移值
        stability_status: 稳定性状态
        is_safe: 是否安全可执行
        warnings: 警告信息列表
        engine_info: 使用的计算引擎信息
    """
    success: bool = Field(default=True, description="分析是否成功完成")
    node_displacements: dict[int, list[float]] = Field(
        default_factory=dict,
        description="节点位移 {node_id: [Ux, Uy, Uz, Rx, Ry, Rz]}"
    )
    element_stresses: dict[int, float] = Field(
        default_factory=dict,
        description="构件应力 {element_id: stress_MPa}"
    )
    max_displacement: float = Field(default=0.0, description="最大位移 (m)")
    stability_status: Literal["Stable", "Unstable", "Critical", "Collapse", "Error", "Timeout"] = "Stable"
    is_safe: bool = Field(default=True, description="是否安全可执行")
    warnings: list[str] = Field(default_factory=list, description="警告信息")
    engine_info: str = Field(default="", description="使用的计算引擎信息")


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


# =============================================================================
# V3.0 特种结构模型 - 烟囱
# =============================================================================

class ChimneySegment(BaseModel):
    """烟囱变截面段

    Attributes:
        id: 段唯一标识符
        bottom_elevation: 段底标高 (m)
        top_elevation: 段顶标高 (m)
        outer_diameter_bottom: 段底外径 (m)
        outer_diameter_top: 段顶外径 (m)
        wall_thickness: 壁厚 (m)
        material: 材料名称，如 "C40"
        reinforcement_ratio: 配筋率 (纵向钢筋)
    """
    id: int
    bottom_elevation: float = Field(description="段底标高 (m)")
    top_elevation: float = Field(description="段顶标高 (m)")
    outer_diameter_bottom: float = Field(description="段底外径 (m)")
    outer_diameter_top: float = Field(description="段顶外径 (m)")
    wall_thickness: float = Field(description="壁厚 (m)")
    material: str = Field(description="混凝土材料等级，如 C40")
    reinforcement_ratio: float = Field(
        default=0.008, description="纵向配筋率 (默认0.8%)"
    )


class ChimneyAttachment(BaseModel):
    """烟囱顶部附属结构

    Attributes:
        name: 附属结构名称
        height: 高度 (m)
        diameter: 直径 (m)
        material: 材料名称，如 "Q235"
    """
    name: str = Field(description="附属结构名称")
    height: float = Field(description="高度 (m)")
    diameter: float = Field(description="直径 (m)")
    material: str = Field(description="材料")


class ChimneyModel(BaseModel):
    """烟囱结构模型 - V3.0 特种结构

    支持变截面钢筋混凝土烟囱的参数化描述与力学分析。

    Attributes:
        model_id: 模型唯一标识符
        name: 模型名称
        total_height: 总高度 (m)
        segments: 变截面段列表 (自上而下)
        attachments: 顶部附属结构列表
        base_diameter: 底部外径 (m)
        top_diameter: 顶部外径 (m)
        notch_height: 切口设计高度 (m)
        notch_angle: 切口角度 (度)
        notion_direction: 定向倾倒方向 (角度)
    """
    model_id: str = Field(description="模型唯一标识符")
    name: str = Field(default="钢筋混凝土烟囱", description="模型名称")
    total_height: float = Field(description="总高度 (m)")
    segments: list[ChimneySegment] = Field(
        default_factory=list, description="变截面段"
    )
    attachments: list[ChimneyAttachment] = Field(
        default_factory=list, description="顶部附属结构"
    )
    base_diameter: float = Field(description="底部外径 (m)")
    top_diameter: float = Field(description="顶部外径 (m)")
    notch_height: float = Field(default=0.0, description="切口设计高度 (m)")
    notch_angle: float = Field(default=0.0, description="切口角度 (度)")
    notion_direction: float = Field(
        default=0.0, description="定向倾倒方向 (度, 0=正X)"
    )


class ChimneyStabilityReport(BaseModel):
    """烟囱切口后稳定性报告

    Attributes:
        model_id: 模型 ID
        notch_height: 切口高度 (m)
        overturning_moment: 倾覆力矩 (kN·m)
        resisting_moment: 抗倾覆力矩 (kN·m)
        stability_ratio: 稳定系数
        is_stable: 是否稳定 (ratio > 1.0)
        max_stress: 切口处最大应力 (MPa)
        tipping_angle: 初始倾斜角度 (度)
    """
    model_id: str
    notch_height: float
    overturning_moment: float = Field(description="倾覆力矩 (kN·m)")
    resisting_moment: float = Field(description="抗倾覆力矩 (kN·m)")
    stability_ratio: float = Field(
        default=1.0, description="稳定系数 (抗倾覆/倾覆)"
    )
    is_stable: bool = Field(default=True)
    max_stress: float = Field(default=0.0, description="最大应力 (MPa)")
    tipping_angle: float = Field(
        default=0.0, description="初始倾斜角 (度)"
    )
    warnings: list[str] = Field(default_factory=list)


class ChimneyTrajectoryPoint(BaseModel):
    """烟囱倾倒轨迹点

    Attributes:
        time: 时间 (s)
        angle: 倾斜角 (度)
        angular_velocity: 角速度 (rad/s)
        com_x: 重心 X 坐标 (m)
        com_z: 重心 Z 坐标 (m)
        kinetic_energy: 动能 (J)
    """
    time: float
    angle: float = Field(description="倾斜角 (度)")
    angular_velocity: float = Field(description="角速度 (rad/s)")
    com_x: float = Field(description="重心 X (m)")
    com_z: float = Field(description="重心 Z (m)")
    kinetic_energy: float = Field(default=0.0, description="动能 (J)")


class ChimneyDeepAnalysisReport(BaseModel):
    """烟囱深部分析报告 - 倾倒过程动力学分析

    Attributes:
        model_id: 模型 ID
        notch_height: 切口高度 (m)
        stability_report: 快速稳定性分析结果
        trajectory: 倾倒轨迹点序列
        impact_time: 触地时间 (s)
        impact_velocity: 触地时顶点速度 (m/s)
        impact_force: 估计撞击力 (kN)
        fall_direction: 倾倒方向 (度)
        engine_used: 使用的计算引擎
    """
    model_id: str
    notch_height: float
    stability_report: Optional[ChimneyStabilityReport] = None
    trajectory: list[ChimneyTrajectoryPoint] = Field(default_factory=list)
    impact_time: float = Field(default=0.0, description="触地时间 (s)")
    impact_velocity: float = Field(default=0.0, description="顶点触地速度 (m/s)")
    impact_force: float = Field(default=0.0, description="撞击力 (kN)")
    fall_direction: float = Field(default=0.0, description="倾倒方向 (度)")
    engine_used: str = Field(default="ChimneyDeepAnalyzer", description="引擎名称")
    warnings: list[str] = Field(default_factory=list)


# =============================================================================
# V3.0 可解释AI (XAI) 模型
# =============================================================================

class ElementXAIInfo(BaseModel):
    """单个构件的XAI解释信息

    Attributes:
        element_id: 构件 ID
        element_type: 构件类型
        stress_ratio: 当前应力比 (应力/屈服强度)
        importance_score: 重要性系数 (基于传力路径, 0-1)
        displacement_impact: 拆除后最大位移增幅 (预测, m)
        stiffness_contribution: 刚度贡献比例
        load_path_rank: 传力路径排名 (1=最关键)
        recommendation: 是否建议优先拆除
        explanation: 自然语言解释
    """
    element_id: int
    element_type: str = Field(description="构件类型")
    stress_ratio: float = Field(default=0.0, description="应力比 (0-1)")
    importance_score: float = Field(
        default=0.5, description="重要性系数 (0-1, 越小越安全可拆)"
    )
    displacement_impact: float = Field(
        default=0.0, description="拆除后位移增幅 (m)"
    )
    stiffness_contribution: float = Field(
        default=0.0, description="刚度贡献比例"
    )
    load_path_rank: int = Field(default=99, description="传力路径排名")
    recommendation: bool = Field(
        default=False, description="是否建议优先拆除"
    )
    explanation: str = Field(default="", description="自然语言解释")


class XAIReport(BaseModel):
    """可解释AI决策报告

    Attributes:
        model_id: 模型 ID
        overall_stability: 整体稳定性评估
        total_elements: 总构件数
        removable_elements: 可安全拆除的构件数
        element_details: 各构件XAI详情
        recommended_sequence: 推荐拆除顺序 (element_id列表)
        summary: 总体决策摘要
    """
    model_id: str
    overall_stability: str = Field(default="Stable", description="整体稳定性")
    total_elements: int = Field(default=0)
    removable_elements: int = Field(default=0)
    element_details: list[ElementXAIInfo] = Field(default_factory=list)
    recommended_sequence: list[int] = Field(default_factory=list)
    summary: str = Field(default="", description="决策摘要")
