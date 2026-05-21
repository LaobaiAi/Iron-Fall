"""枚举类型单元测试

覆盖 core/enums.py 中所有枚举定义的正确性。
"""
import pytest
from core.enums import (
    ElementType, ActionType, CalculationEngine,
    StabilityStatus, NodeRestraintType, MaterialGrade,
)


class TestElementType:
    """构件类型枚举"""

    def test_all_values_present(self):
        assert ElementType.COLUMN == "Column"
        assert ElementType.BEAM == "Beam"
        assert ElementType.BRACE == "Brace"

    def test_values_are_unique(self):
        vals = [e.value for e in ElementType]
        assert len(vals) == len(set(vals)), "ElementType 值应唯一"

    def test_str_roundtrip(self):
        for e in ElementType:
            assert ElementType(e.value) == e


class TestActionType:
    """拆除动作类型枚举"""

    def test_remove_and_apply_force(self):
        assert ActionType.REMOVE == "Remove"
        assert ActionType.APPLY_FORCE == "ApplyForce"

    def test_mutual_exclusive(self):
        assert ActionType.REMOVE != ActionType.APPLY_FORCE


class TestCalculationEngine:
    """计算引擎枚举"""

    def test_three_engines(self):
        assert CalculationEngine.ANASTRUCT == "anaStruct"
        assert CalculationEngine.FRAME3DD == "Frame3DD"
        assert CalculationEngine.OPENSEES == "OpenSeesPy"

    def test_engines_are_ranked(self):
        engines = list(CalculationEngine)
        assert engines[0] == CalculationEngine.ANASTRUCT  # 主力
        assert engines[2] == CalculationEngine.OPENSEES   # 核威慑


class TestStabilityStatus:
    """稳定性状态枚举"""

    def test_all_states_present(self):
        assert StabilityStatus.STABLE == "Stable"
        assert StabilityStatus.UNSTABLE == "Unstable"
        assert StabilityStatus.CRITICAL == "Critical"
        assert StabilityStatus.COLLAPSE == "Collapse"

    def test_values_unique(self):
        vals = [s.value for s in StabilityStatus]
        assert len(vals) == len(set(vals))


class TestNodeRestraintType:
    """节点约束类型枚举"""

    def test_all_types_present(self):
        assert NodeRestraintType.FIXED == "Fixed"
        assert NodeRestraintType.PINNED == "Pinned"
        assert NodeRestraintType.ROLLER == "Roller"
        assert NodeRestraintType.FREE == "Free"


class TestMaterialGrade:
    """钢材牌号枚举"""

    def test_common_grades(self):
        assert MaterialGrade.Q235 == "Q235"
        assert MaterialGrade.Q355 == "Q355"
        assert MaterialGrade.Q390 == "Q390"

    def test_fy_values_match(self):
        """确认牌号与屈服强度对应"""
        # Q235 fy=235, Q355 fy=355, Q390 fy=390
        grade_to_fy = {
            MaterialGrade.Q235: 235,
            MaterialGrade.Q355: 355,
            MaterialGrade.Q390: 390,
        }
        for grade, expected_fy in grade_to_fy.items():
            assert int(grade.value[1:]) == expected_fy
