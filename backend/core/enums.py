"""Iron-Fall 枚举定义

定义项目中使用的所有枚举类型。
"""
from enum import Enum


class ElementType(str, Enum):
    """构件类型枚举"""
    COLUMN = "Column"      # 柱
    BEAM = "Beam"          # 梁
    BRACE = "Brace"        # 支撑


class ActionType(str, Enum):
    """拆除动作类型"""
    REMOVE = "Remove"           # 移除构件
    APPLY_FORCE = "ApplyForce"  # 施加外力


class CalculationEngine(str, Enum):
    """计算引擎类型"""
    FRAME3DD = "Frame3DD"       # 快速静力/动力求解器
    OPENSEES = "OpenSeesPy"     # 深度非线性分析


class StabilityStatus(str, Enum):
    """结构稳定性状态"""
    STABLE = "Stable"           # 稳定
    UNSTABLE = "Unstable"       # 失稳
    CRITICAL = "Critical"       # 临界状态
    COLLAPSE = "Collapse"       # 倒塌


class NodeRestraintType(str, Enum):
    """节点约束类型"""
    FIXED = "Fixed"             # 固定端
    PINNED = "Pinned"           # 铰接
    ROLLER = "Roller"           # 滚支
    FREE = "Free"               # 自由


class MaterialGrade(str, Enum):
    """钢材牌号"""
    Q235 = "Q235"               # Q235 钢
    Q355 = "Q355"               # Q355 钢
    Q390 = "Q390"               # Q390 钢
