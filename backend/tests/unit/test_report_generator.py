"""工程报告生成器测试

覆盖 engine/report_generator.py 的：
- HTML 报告生成
- Markdown 报告生成
- 数据完整性（所有关键字段）
- 边界条件（空模型、缺失数据）
"""
import pytest
import re
from core.models import (
    StructureModel, AnalysisResult, DemolitionPlan, DemolitionAction,
    ChimneyModel, ChimneyStabilityReport,
)
from engine.report_generator import ReportGenerator, ReportData


class TestReportGenerator:
    """报告生成器核心测试"""

    @pytest.fixture
    def generator(self) -> ReportGenerator:
        return ReportGenerator()

    # -------------------------------------------------------------------------
    # HTML 报告生成
    # -------------------------------------------------------------------------

    def test_generate_html_basic(self, generator, sample_3story_frame,
                                  sample_analysis_stable, sample_demolition_plan):
        """基础 HTML 报告生成，验证关键字段在场"""
        html = generator.generate_html(
            model=sample_3story_frame,
            analysis_result=sample_analysis_stable,
            plan=sample_demolition_plan,
        )

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert sample_3story_frame.name in html
        assert "Iron-Fall" in html
        # 验证关键章节
        assert "工程概况" in html or "一、" in html
        assert "力学分析" in html or "二、" in html
        assert "拆除方案" in html or "三、" in html

    def test_generate_html_empty_plan(self, generator, sample_3story_frame,
                                       sample_analysis_stable):
        """无拆除方案时应正常生成（无拆除表）"""
        html = generator.generate_html(
            model=sample_3story_frame,
            analysis_result=sample_analysis_stable,
            plan=None,
        )
        assert "<!DOCTYPE html>" in html
        assert sample_3story_frame.name in html

    def test_generate_html_unstable(self, generator, sample_3story_frame,
                                      sample_analysis_unstable):
        """失稳状态应在报告中体现"""
        html = generator.generate_html(
            model=sample_3story_frame,
            analysis_result=sample_analysis_unstable,
            plan=None,
        )
        assert "Unstable" in html or "危险" in html

    def test_generate_html_with_chimney(self, generator, sample_chimney_100m):
        """含烟囱数据的报告"""
        stability = ChimneyStabilityReport(
            model_id=sample_chimney_100m.model_id,
            notch_height=2.0,
            overturning_moment=500,
            resisting_moment=800,
            is_stable=True,
        )
        html = generator.generate_html(
            model=None,
            analysis_result=None,
            plan=None,
            chimney_model=sample_chimney_100m,
            chimney_report=stability,
        )
        # 烟囱特有字段应出现
        assert "烟囱" in html or "chimney" in html.lower()
        assert "稳定系数" in html or "100.0" in html

    # -------------------------------------------------------------------------
    # Markdown 报告生成
    # -------------------------------------------------------------------------

    def test_generate_markdown_basic(self, generator, sample_3story_frame,
                                       sample_analysis_stable, sample_demolition_plan):
        """基础 Markdown 报告生成"""
        md = generator.generate_markdown(
            model=sample_3story_frame,
            analysis_result=sample_analysis_stable,
            plan=sample_demolition_plan,
        )
        assert sample_3story_frame.name in md
        assert "# " in md  # 至少有一个标题
        assert "稳定" in md or "Stable" in md

    def test_generate_markdown_structure(self, generator, sample_3story_frame,
                                          sample_analysis_stable, sample_demolition_plan):
        """Markdown 应有合理的层级结构"""
        md = generator.generate_markdown(
            model=sample_3story_frame,
            analysis_result=sample_analysis_stable,
            plan=sample_demolition_plan,
        )
        # 至少有 ## 二级标题
        assert "## " in md

    def test_generate_markdown_empty(self, generator):
        """完全空输入时不应崩溃"""
        md = generator.generate_markdown(
            model=None, analysis_result=None, plan=None,
            chimney_model=None, chimney_report=None,
        )
        assert isinstance(md, str)

    # -------------------------------------------------------------------------
    # 数据完整性
    # -------------------------------------------------------------------------

    def test_html_contains_timestamp(self, generator, sample_3story_frame):
        """HTML 报告应包含时间戳"""
        html = generator.generate_html(sample_3story_frame)
        # 年份至少应在报告中（在 footer）
        assert "2026" in html or "2025" in html or "2024" in html

    def test_html_contains_model_stats(self, generator, sample_3story_frame):
        """HTML 报告应包含构件数和节点数"""
        html = generator.generate_html(sample_3story_frame)
        n_elements = str(len(sample_3story_frame.elements))
        n_nodes = str(len(sample_3story_frame.nodes))
        assert n_elements in html
        assert n_nodes in html

    def test_output_is_utf8_safe(self, generator, sample_3story_frame):
        """输出应为合法 UTF-8 字符串"""
        html = generator.generate_html(sample_3story_frame)
        html.encode("utf-8")  # 不抛异常
        md = generator.generate_markdown(sample_3story_frame)
        md.encode("utf-8")

    # -------------------------------------------------------------------------
    # ReportData dataclass
    # -------------------------------------------------------------------------

    def test_report_data_defaults(self):
        rd = ReportData()
        assert rd.title == "结构拆除工程计算书"
        assert rd.total_elements == 0
        assert rd.is_safe is True
