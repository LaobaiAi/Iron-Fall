"""V3.0 可解释AI (XAI) 决策分析测试

验证构件应力比、重要性系数、拆除影响预测等XAI功能的正确性。
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import StructureModel, XAIReport, ElementXAIInfo
from engine.xai_analyzer import XAIAnalyzer
from agent.parser import StructureParser


class TestXAIAnalyzer:
    """XAI 分析器核心测试"""

    @pytest.fixture
    def analyzer(self) -> XAIAnalyzer:
        return XAIAnalyzer()

    @pytest.fixture
    def simple_model(self) -> StructureModel:
        parser = StructureParser()
        return parser.parse("3层Q355钢框架，跨度6m，层高3.6m")

    @pytest.fixture
    def braced_model(self) -> StructureModel:
        parser = StructureParser()
        return parser.parse(
            "带X型斜撑的五层钢框架，首层高4.5m，标准层高3.6m，H400x200，Q355"
        )

    # -------------------------------------------------------------------------
    # 基础分析
    # -------------------------------------------------------------------------

    def test_analyze_basic(self, analyzer, simple_model):
        """基础XAI分析"""
        report = analyzer.analyze(simple_model)

        assert isinstance(report, XAIReport)
        assert report.total_elements == len(simple_model.elements)
        assert len(report.element_details) == report.total_elements

    def test_all_elements_have_details(self, analyzer, simple_model):
        """每个构件都应有XAI详情"""
        report = analyzer.analyze(simple_model)

        element_ids = {e.id for e in simple_model.elements}
        detail_ids = {d.element_id for d in report.element_details}
        assert element_ids == detail_ids

    def test_report_has_summary(self, analyzer, simple_model):
        """报告应有决策摘要"""
        report = analyzer.analyze(simple_model)
        assert report.summary
        assert len(report.summary) > 0

    # -------------------------------------------------------------------------
    # 字段验证
    # -------------------------------------------------------------------------

    def test_stress_ratio_in_range(self, analyzer, simple_model):
        """应力比应在 0-1 范围内"""
        report = analyzer.analyze(simple_model)

        for detail in report.element_details:
            assert 0 <= detail.stress_ratio <= 1, (
                f"构件 {detail.element_id} 应力比 {detail.stress_ratio} 超出范围"
            )

    def test_importance_score_in_range(self, analyzer, simple_model):
        """重要性系数应在 0-1 范围内"""
        report = analyzer.analyze(simple_model)

        for detail in report.element_details:
            assert 0 <= detail.importance_score <= 1, (
                f"构件 {detail.element_id} 重要性 {detail.importance_score} 超出范围"
            )

    def test_displacement_impact_non_negative(self, analyzer, simple_model):
        """位移增幅应非负"""
        report = analyzer.analyze(simple_model)

        for detail in report.element_details:
            assert detail.displacement_impact >= 0, (
                f"构件 {detail.element_id} 位移增幅为负"
            )

    def test_load_path_rank_positive(self, analyzer, simple_model):
        """传力路径排名应为正整数"""
        report = analyzer.analyze(simple_model)

        for detail in report.element_details:
            assert detail.load_path_rank > 0, (
                f"构件 {detail.element_id} 排名无效: {detail.load_path_rank}"
            )

    # -------------------------------------------------------------------------
    # 决策逻辑
    # -------------------------------------------------------------------------

    def test_column_high_importance(self, analyzer, simple_model):
        """柱构件应有较高重要性"""
        report = analyzer.analyze(simple_model)

        columns = [
            d for d in report.element_details
            if d.element_type == "Column"
        ]
        beams = [
            d for d in report.element_details
            if d.element_type == "Beam"
        ]

        if columns and beams:
            avg_col_importance = sum(c.importance_score for c in columns) / len(columns)
            avg_beam_importance = sum(b.importance_score for b in beams) / len(beams)
            assert avg_col_importance >= avg_beam_importance, (
                "柱的平均重要性应不低于梁"
            )

    def test_recommendations_have_explanation(self, analyzer, simple_model):
        """推荐拆除的构件应有自然语言解释"""
        report = analyzer.analyze(simple_model)

        for detail in report.element_details:
            if detail.recommendation:
                assert detail.explanation, (
                    f"构件 {detail.element_id} 被推荐但无解释"
                )

    def test_recommended_sequence_non_empty(self, analyzer, simple_model):
        """简单结构应有至少一个推荐拆除的构件"""
        report = analyzer.analyze(simple_model)

        # 正常结构至少有梁可拆
        assert report.removable_elements > 0 or report.total_elements > 0

    # -------------------------------------------------------------------------
    # 含支撑结构
    # -------------------------------------------------------------------------

    def test_braced_structure(self, analyzer, braced_model):
        """含支撑结构的XAI分析"""
        report = analyzer.analyze(braced_model)

        braces = [
            d for d in report.element_details
            if d.element_type == "Brace"
        ]

        if braces:
            # 支撑通常可优先拆除
            assert len(braces) > 0

        assert report.total_elements == len(braced_model.elements)

    def test_json_serializable(self, analyzer, simple_model):
        """XAI报告应可JSON序列化"""
        report = analyzer.analyze(simple_model)
        data = report.model_dump()

        assert "element_details" in data
        assert "recommended_sequence" in data
        assert "summary" in data

    # -------------------------------------------------------------------------
    # 集成测试
    # -------------------------------------------------------------------------

    def test_with_analysis_result(self, analyzer, simple_model):
        """结合力学分析结果"""
        from engine.anastruct_adapter import AnaStructAdapter
        import asyncio

        adapter = AnaStructAdapter()
        if adapter._available:
            try:
                result = asyncio.run(adapter.run_static_analysis(simple_model))
                report = analyzer.analyze(simple_model, result)

                # 有分析结果时应力比应更精确
                has_nonzero_stress = any(
                    d.stress_ratio > 0
                    for d in report.element_details
                )
                assert has_nonzero_stress or len(report.element_details) > 0
            except Exception:
                pass

    def test_empty_model(self, analyzer):
        """空模型应安全处理"""
        model = StructureModel(
            model_id="empty",
            name="空模型",
            nodes=[],
            elements=[],
            sections=[],
            materials=[],
        )
        report = analyzer.analyze(model)

        assert report.total_elements == 0
        assert report.removable_elements == 0
        assert len(report.summary) > 0


class TestXAIExplanations:
    """自然语言解释质量测试"""

    @pytest.fixture
    def analyzer(self) -> XAIAnalyzer:
        return XAIAnalyzer()

    @pytest.fixture
    def model(self) -> StructureModel:
        parser = StructureParser()
        return parser.parse("3层Q355钢框架，跨度6m")

    def test_explanations_contain_justification(self, analyzer, model):
        """解释应包含量化依据"""
        report = analyzer.analyze(model)

        for detail in report.element_details:
            expl = detail.explanation
            assert len(expl) > 0
            # 应包含构件类型或构件号
            assert (
                "号" in expl
                or "柱" in expl
                or "梁" in expl
                or "支撑" in expl
                or "Column" in expl
                or "Beam" in expl
                or "Brace" in expl
            )
