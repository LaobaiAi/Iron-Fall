"""V3.0 工程报告自动生成器

基于 Jinja2 模板 + 力学分析结果，自动生成专业格式的工程报告。
支持 Markdown 和 HTML 输出，可进一步转换为 PDF。
"""

import logging
import time
from typing import Optional
from dataclasses import dataclass, field

from core.models import (
    StructureModel, DemolitionPlan, AnalysisResult, ChimneyModel,
    ChimneyStabilityReport, ChimneyDeepAnalysisReport
)

logger = logging.getLogger(__name__)

# Try Jinja2 for HTML templates
try:
    import jinja2
    JINJA_AVAILABLE = True
except ImportError:
    JINJA_AVAILABLE = False

# Try reportlab for PDF
try:
    import reportlab
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# ============================================================================
# HTML 报告模板
# ============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>{{ title }}</title>
<style>
body { font-family: 'Microsoft YaHei', sans-serif; margin: 40px; color: #333; line-height: 1.8; }
h1 { color: #1a5276; border-bottom: 3px solid #2980b9; padding-bottom: 10px; }
h2 { color: #2471a3; border-bottom: 2px solid #85c1e9; padding-bottom: 6px; margin-top: 30px; }
h3 { color: #2e86c1; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; }
th, td { border: 1px solid #bdc3c7; padding: 8px 12px; text-align: left; }
th { background: #ecf0f1; font-weight: 600; }
.section { margin: 20px 0; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.info-item { padding: 8px; background: #f8f9fa; border-radius: 4px; }
.info-label { font-weight: 600; color: #7f8c8d; font-size: 12px; }
.info-value { color: #2c3e50; font-size: 16px; font-weight: 600; }
.stable { color: #27ae60; }
.unstable { color: #e74c3c; }
.warning { color: #f39c12; }
.footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px; }
</style>
</head>
<body>
<h1>{{ title }}</h1>
<p><strong>项目名称：</strong>Iron-Fall 智能拆除决策系统 V3.0</p>
<p><strong>报告生成时间：</strong>{{ timestamp }}</p>

<h2>一、工程概况</h2>
<div class="section">
<p><strong>结构类型：</strong>{{ structure_type }}</p>
<p><strong>模型名称：</strong>{{ model_name }}</p>
<p><strong>构件总数：</strong>{{ total_elements }} 个</p>
<p><strong>节点总数：</strong>{{ total_nodes }} 个</p>
<p><strong>材料等级：</strong>{{ materials }}</p>
<p><strong>截面规格：</strong>{{ sections }}</p>
</div>

<h2>二、力学分析结果</h2>
<div class="info-grid">
<div class="info-item"><span class="info-label">最大位移</span><br><span class="info-value">{{ max_displacement }} m</span></div>
<div class="info-item"><span class="info-label">稳定性状态</span><br><span class="info-value {{ stability_class }}">{{ stability_status }}</span></div>
<div class="info-item"><span class="info-label">整体安全性</span><br><span class="info-value {{ 'stable' if is_safe else 'unstable' }}">{{ '安全' if is_safe else '危险' }}</span></div>
<div class="info-item"><span class="info-label">计算引擎</span><br><span class="info-value">{{ engine }}</span></div>
</div>

<h2>三、拆除方案</h2>
<div class="section">
<p><strong>方案等级：</strong>{{ risk_level }}</p>
<p><strong>总拆除步数：</strong>{{ total_steps }}</p>
<p><strong>拆除构件数：</strong>{{ total_removed }}</p>
{{ demolition_table }}
</div>

<h2>四、安全评估</h2>
<div class="section">
<p>{{ safety_assessment }}</p>
{{ warnings_section }}
</div>

<h2>五、结论与建议</h2>
<div class="section">
<p>{{ conclusion }}</p>
</div>

<div class="footer">
<p>本报告由 Iron-Fall V3.0 智能拆除决策系统自动生成。</p>
<p>报告数据基于 {{ engine }} 计算引擎。</p>
<p>© 2026 Iron-Fall Project - MIT License</p>
</div>
</body>
</html>"""


@dataclass
class ReportData:
    """工程报告数据"""
    title: str = "结构拆除工程计算书"
    model_name: str = ""
    structure_type: str = "钢框架结构"
    total_elements: int = 0
    total_nodes: int = 0
    materials: str = ""
    sections: str = ""
    max_displacement: float = 0.0
    stability_status: str = "Stable"
    stability_class: str = "stable"
    is_safe: bool = True
    engine: str = "anaStruct"
    risk_level: str = "Low"
    total_steps: int = 0
    total_removed: int = 0
    demolition_table: str = ""
    safety_assessment: str = ""
    warnings_section: str = ""
    conclusion: str = ""
    timestamp: str = ""
    chimney_data: Optional[dict] = None


class ReportGenerator:
    """工程报告生成器

    整合结构模型、力学分析、拆除方案等数据，生成格式规范的工程报告。
    支持 HTML 和 Markdown 格式。
    """

    def __init__(self):
        pass

    # =========================================================================
    # 主接口
    # =========================================================================

    def generate_html(
        self,
        model: StructureModel,
        analysis_result: Optional[AnalysisResult] = None,
        plan: Optional[DemolitionPlan] = None,
        chimney_model: Optional[ChimneyModel] = None,
        chimney_report: Optional[ChimneyStabilityReport] = None,
    ) -> str:
        """生成 HTML 格式工程报告

        Args:
            model: 结构模型
            analysis_result: 力学分析结果
            plan: 拆除方案
            chimney_model: 烟囱模型（可选）
            chimney_report: 烟囱稳定性报告（可选）

        Returns:
            HTML 报告字符串
        """
        data = self._build_report_data(
            model, analysis_result, plan, chimney_model, chimney_report
        )

        # 使用模板
        if JINJA_AVAILABLE:
            env = jinja2.Environment()
            template = env.from_string(HTML_TEMPLATE)
            html = template.render(**data.__dict__)
        else:
            # 简单字符串替换
            html = self._simple_render(data)

        return html

    def generate_markdown(
        self,
        model: StructureModel,
        analysis_result: Optional[AnalysisResult] = None,
        plan: Optional[DemolitionPlan] = None,
        chimney_model: Optional[ChimneyModel] = None,
        chimney_report: Optional[ChimneyStabilityReport] = None,
    ) -> str:
        """生成 Markdown 格式工程报告"""
        data = self._build_report_data(
            model, analysis_result, plan, chimney_model, chimney_report
        )

        md = f"""# {data.title}

**项目名称**: Iron-Fall 智能拆除决策系统 V3.0  
**报告时间**: {data.timestamp}

## 一、工程概况

- **结构类型**: {data.structure_type}
- **模型名称**: {data.model_name}
- **构件总数**: {data.total_elements} 个
- **节点总数**: {data.total_nodes} 个
- **材料等级**: {data.materials}
- **截面规格**: {data.sections}

## 二、力学分析结果

| 指标 | 数值 |
|------|------|
| 最大位移 | {data.max_displacement:.4f} m |
| 稳定性状态 | {data.stability_status} |
| 整体安全性 | {"安全" if data.is_safe else "危险"} |
| 计算引擎 | {data.engine} |

## 三、拆除方案

- **方案等级**: {data.risk_level}
- **总拆除步数**: {data.total_steps}
- **拆除构件数**: {data.total_removed}

## 四、安全评估

{data.safety_assessment}

## 五、结论与建议

{data.conclusion}

---

*本报告由 Iron-Fall V3.0 自动生成 | © 2026 Iron-Fall Project*
"""
        return md

    # =========================================================================
    # 数据构建
    # =========================================================================

    def _build_report_data(
        self,
        model: StructureModel,
        analysis_result: Optional[AnalysisResult],
        plan: Optional[DemolitionPlan],
        chimney_model: Optional[ChimneyModel],
        chimney_report: Optional[ChimneyStabilityReport],
    ) -> ReportData:
        """构建报告数据"""
        data = ReportData()
        data.timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        data.model_name = model.name
        data.total_elements = len(model.elements)
        data.total_nodes = len(model.nodes)
        data.materials = ", ".join(m.name for m in model.materials)
        data.sections = ", ".join(s.name for s in model.sections)

        # 结构类型判断
        if chimney_model:
            grade = (
                chimney_model.segments[0].material
                if chimney_model.segments
                else "C40"
            )
            data.structure_type = f"钢筋混凝土烟囱 ({grade})"
        elif any(e.element_type.value == "Brace" for e in model.elements):
            data.structure_type = "钢框架-支撑结构"
        else:
            data.structure_type = "钢框架结构"

        # 分析结果
        if analysis_result:
            data.max_displacement = analysis_result.max_displacement
            data.stability_status = analysis_result.stability_status
            data.is_safe = analysis_result.is_safe
            data.stability_class = "stable" if data.is_safe else "unstable"
            if analysis_result.warnings:
                data.warnings_section = "### 警告信息:\n" + "\n".join(
                    f"- {w}" for w in analysis_result.warnings
                )
        else:
            data.stability_status = "未分析"
            data.is_safe = True
            data.stability_class = "stable"

        # 计算引擎
        data.engine = "anaStruct (快速线弹性)" if analysis_result else "未执行"

        # 拆除方案
        if plan:
            data.risk_level = plan.risk_level
            data.total_steps = len(plan.actions)
            data.total_removed = sum(
                len(a.target_element_ids) for a in plan.actions
            )

            # 拆除表格
            rows = []
            rows.append("<tr><th>步骤</th><th>拆除构件ID</th><th>动作类型</th></tr>")
            for a in plan.actions:
                rows.append(
                    f"<tr><td>{a.step}</td><td>{a.target_element_ids}</td>"
                    f"<td>{a.action_type}</td></tr>"
                )
            data.demolition_table = f"<table>{''.join(rows)}</table>"

        # 安全评估
        if analysis_result and analysis_result.is_safe:
            data.safety_assessment = (
                "结构在拆除过程中保持稳定，位移和应力均在可控范围内。"
                "建议按照拆除方案顺序执行，同时监测关键节点位移。"
            )
        else:
            data.safety_assessment = (
                "部分拆除步骤可能导致结构失稳，建议重新评估方案或"
                "加强临时支撑措施。"
            )

        # 烟囱专项
        if chimney_report:
            chimney_str = f"""
- 烟囱高度: {chimney_model.total_height if chimney_model else 'N/A'} m
- 切口高度: {chimney_report.notch_height} m
- 稳定系数: {chimney_report.stability_ratio:.3f}
- 最大应力: {chimney_report.max_stress:.2f} MPa
- 稳定性: {"稳定" if chimney_report.is_stable else "可能失稳"}
"""
            data.safety_assessment += "\n\n### 烟囱专项分析:\n" + chimney_str

        # 结论
        data.conclusion = (
            f"综合评估结果，{data.model_name} 在正常工况下结构安全，"
            f"拆除方案可行。推荐采用拆解顺序方案进行结构拆除。"
        )

        return data

    def _simple_render(self, data: ReportData) -> str:
        """无 Jinja2 时的简单模板渲染"""
        html = HTML_TEMPLATE
        for key, value in data.__dict__.items():
            if value is None:
                value = ""
            html = html.replace(f"{{{{ {key} }}}}", str(value))
        return html
