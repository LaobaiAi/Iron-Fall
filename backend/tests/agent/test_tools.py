"""V1.0 工具函数测试

覆盖 agent/tools.py 中 5 个 LangChain 工具的：
- 结构稳定性检查
- 拆除动作分析
- 模型验证
- 规范查询
- 风险评估
"""
import sys
from pathlib import Path
# 确保 backend 和 tests 都在 sys.path 中
_backend_dir = str(Path(__file__).resolve().parent.parent.parent)
_tests_dir = str(Path(__file__).resolve().parent.parent)
for d in (_backend_dir, _tests_dir):
    if d not in sys.path:
        sys.path.insert(0, d)

import pytest
from agent.tools import (
    check_structure_stability,
    analyze_demolition_action,
    validate_structure_model,
    query_demolition_regulations,
    get_risk_assessment,
)
from conftest import model_to_dict


class TestStabilityTool:
    """check_structure_stability 测试"""

    def test_returns_result(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = check_structure_stability.invoke({"model": d})
        assert "is_stable" in result
        assert "max_displacement" in result


class TestAnalyzeActionTool:
    """analyze_demolition_action 测试"""

    def test_returns_analysis(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        action = {"step": 1, "target_element_ids": [1], "action_type": "Remove"}
        result = analyze_demolition_action.invoke({
            "model": d,
            "action": action,
        })
        assert "is_safe" in result or "warnings" in result

class TestValidateModelTool:
    """validate_structure_model 测试"""

    def test_valid_model(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = validate_structure_model.invoke({"model": d})
        assert "is_valid" in result

    def test_empty_model(self, empty_model):
        d = model_to_dict(empty_model)
        result = validate_structure_model.invoke({"model": d})
        assert "is_valid" in result or "error_message" in result


class TestRegulationTool:
    """query_demolition_regulations 测试"""

    def test_returns_regulations(self):
        result = query_demolition_regulations.invoke({
            "query": "钢结构拆除安全规范"
        })
        assert len(result) > 0
        assert isinstance(result, str)

    def test_query_keyword(self):
        result = query_demolition_regulations.invoke({"query": "拆除顺序"})
        assert len(result) > 0


class TestRiskAssessmentTool:
    """get_risk_assessment 测试"""

    def test_returns_risk_data(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = get_risk_assessment.invoke({
            "model": d,
            "element_ids": [1, 2, 3],
        })
        # 返回风险评级字符串，如 "MEDIUM: ..."
        assert any(level in result for level in ("HIGH", "MEDIUM", "LOW"))
