"""V4.0 工具函数测试

覆盖 agent/tools_v4.py 中 8 个 LangChain 工具的：
- 结构拓扑分析
- 依赖图计算
- 单步拆除验算
- 规范合规审查
- 冗余度计算
- 成本估算
- 案例检索
- 方案融合
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
from agent.tools_v4 import (
    get_structure_topology,
    compute_dependency_graph,
    evaluate_single_removal,
    check_regulation_compliance,
    calculate_redundancy_score,
    estimate_demolition_cost,
    merge_demolition_plans,
)
from conftest import model_to_dict


class TestTopologyTool:
    """get_structure_topology 测试"""

    def test_returns_summary(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = get_structure_topology.invoke({"model": d})

        assert result["total_nodes"] == len(sample_3story_frame.nodes)
        assert result["total_elements"] == len(sample_3story_frame.elements)
        assert result["elevation_levels"] > 0
        assert "level_map" in result
        assert "elements_by_type" in result

    def test_topology_empty_model(self, empty_model):
        d = model_to_dict(empty_model)
        result = get_structure_topology.invoke({"model": d})
        assert result["total_nodes"] == 0
        assert result["total_elements"] == 0


class TestDependencyGraphTool:
    """compute_dependency_graph 测试"""

    def test_returns_dependencies(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = compute_dependency_graph.invoke({"model": d})

        assert "dependency_graph" in result
        assert result["element_count"] > 0

    def test_empty_model(self, empty_model):
        d = model_to_dict(empty_model)
        result = compute_dependency_graph.invoke({"model": d})
        assert result["element_count"] == 0


class TestSafetyCheckTool:
    """evaluate_single_removal 测试"""

    def test_removal_safety_check(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = evaluate_single_removal.invoke({
            "model": d,
            "element_ids": [1],
        })
        assert "is_stable" in result
        assert "removed_ids" in result

    def test_removal_empty_ids(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = evaluate_single_removal.invoke({
            "model": d,
            "element_ids": [],
        })
        assert result is not None


class TestRegulationTool:
    """check_regulation_compliance 测试"""

    def test_returns_compliance_result(self, sample_3story_frame,
                                         sample_demolition_plan):
        d = model_to_dict(sample_3story_frame)
        p = sample_demolition_plan.model_dump()
        result = check_regulation_compliance.invoke({
            "model": d,
            "plan": p,
        })
        assert "compliant" in result or "passed" in result or "violations" in result


class TestRedundancyTool:
    """calculate_redundancy_score 测试"""

    def test_returns_score(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = calculate_redundancy_score.invoke({"model": d})
        assert "redundancy_score" in result or "score" in result


class TestCostTool:
    """estimate_demolition_cost 测试"""

    def test_returns_cost_estimate(self, sample_3story_frame,
                                     sample_demolition_plan):
        d = model_to_dict(sample_3story_frame)
        p = sample_demolition_plan.model_dump()
        result = estimate_demolition_cost.invoke({
            "model": d,
            "plan": p,
        })
        assert "cost_estimate_wan" in result

    def test_empty_plan(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        result = estimate_demolition_cost.invoke({
            "model": d,
            "plan": {"plan_id": "x", "actions": []},
        })
        assert result is not None


class TestMergePlansTool:
    """merge_demolition_plans 测试"""

    def test_merges_multiple_plans(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        plan1 = {
            "plan_id": "p1",
            "actions": [{"step": 1, "target_element_ids": [1]}],
        }
        plan2 = {
            "plan_id": "p2",
            "actions": [{"step": 1, "target_element_ids": [2]}],
        }
        result = merge_demolition_plans.invoke({
            "model": d,
            "plans": [plan1, plan2],
        })
        assert "plan" in result or "merged" in result
        assert "consensus_rate" in result or "merged" in result

    def test_single_plan_noop(self, sample_3story_frame):
        d = model_to_dict(sample_3story_frame)
        plan = {
            "plan_id": "only",
            "actions": [{"step": 1, "target_element_ids": [1]}],
        }
        result = merge_demolition_plans.invoke({
            "model": d,
            "plans": [plan],
        })
        assert result is not None
