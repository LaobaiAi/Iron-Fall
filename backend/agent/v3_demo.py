"""V3.0 完整演示脚本

整合所有 V3.0 模块的竞赛级演示流程。
包含：
- 烟囱模型解析与力学分析
- XAI 可解释决策
- RL 优化对比
- 力场可视化
- 工程报告生成
"""

import sys
import json
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import DemolitionAction, StructureModel
from agent.parser import StructureParser
from agent.chimney_parser import ChimneyParser
from engine.chimney_analyzer import ChimneyQuickAnalyzer
from engine.chimney_opensees import ChimneyDeepAnalyzer
from engine.xai_analyzer import XAIAnalyzer
from engine.rl_agent import DemolitionRLAgent
from engine.force_visualizer import ForceVisualizer
from engine.report_generator import ReportGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# 演示阶段
# ============================================================================

def demo_v3_full(output_dir: str = "demo_output"):
    """运行完整 V3.0 演示流程"""
    output = Path(output_dir)
    output.mkdir(exist_ok=True)

    results = {}

    # ------------------------------------------------------------------
    # Phase 1: 烟囱结构 AI 解析 + 快速力学分析
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Phase 1: 烟囱结构 AI 解析 + 快速力学验算")
    print("=" * 60)

    chimney_parser = ChimneyParser()
    chimney_model = chimney_parser.parse(
        "建立一个高60m、底径5m、顶径3m、壁厚0.3m的"
        "C40钢筋混凝土烟囱，顶部设5m钢制排气筒",
        model_id="demo_chimney"
    )

    print(f"  模型: {chimney_model.name}")
    print(f"  段数: {len(chimney_model.segments)}")
    print(f"  附属结构: {len(chimney_model.attachments)} 个")

    chimney_analyzer = ChimneyQuickAnalyzer()
    chimney_stability = chimney_analyzer.analyze_stability(
        chimney_model, notch_height=8.0
    )

    print(f"  稳定系数: {chimney_stability.stability_ratio:.3f}")
    print(f"  稳定性: {'稳定' if chimney_stability.is_stable else '危险'}")
    print(f"  倾覆力矩: {chimney_stability.overturning_moment:.1f} kN·m")

    results["chimney"] = {
        "model": chimney_model.model_dump(),
        "stability": chimney_stability.model_dump(),
    }

    # ------------------------------------------------------------------
    # Phase 2: 烟囱深部分析
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Phase 2: 烟囱深部动力学分析 (L-1 刚体转动仿真)")
    print("=" * 60)

    chimney_deep = ChimneyDeepAnalyzer()
    deep_report = chimney_deep.run_deep_analysis(
        chimney_model, notch_height=8.0, max_time=10.0
    )

    print(f"  引擎: {deep_report.engine_used}")
    print(f"  轨迹点数: {len(deep_report.trajectory)}")
    print(f"  触地时间: {deep_report.impact_time:.2f} s")
    print(f"  触地速度: {deep_report.impact_velocity:.1f} m/s")
    print(f"  撞击力: {deep_report.impact_force:.1f} kN")

    results["chimney_deep"] = deep_report.model_dump()

    # ------------------------------------------------------------------
    # Phase 3: 钢框架 XAI 决策面板
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Phase 3: 可解释 AI 决策面板")
    print("=" * 60)

    frame_parser = StructureParser()
    frame_model = frame_parser.parse(
        "带X型斜撑的五层钢框架，首层高4.5m，标准层高3.6m，H400x200，Q355"
    )

    print(f"  模型: {frame_model.name}")
    print(f"  构件: {len(frame_model.elements)} 个")

    xai_analyzer = XAIAnalyzer()
    xai_report = xai_analyzer.analyze(frame_model)

    print(f"  可拆除: {xai_report.removable_elements}/{xai_report.total_elements}")
    print(f"  稳定性: {xai_report.overall_stability}")
    print(f"  推荐顺序: {xai_report.recommended_sequence[:5]}...")

    # 展示前3个推荐拆除构件的解释
    for detail in xai_report.element_details[:5]:
        if detail.recommendation:
            print(f"  {detail.explanation[:80]}...")

    results["xai"] = xai_report.model_dump()

    # ------------------------------------------------------------------
    # Phase 4: RL 拆除序列对比
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Phase 4: RL vs 传统方案对比")
    print("=" * 60)

    rl_agent = DemolitionRLAgent()
    rl_result = rl_agent.compare(frame_model)

    print(f"  RL方案步数: {rl_result.rl_steps}")
    print(f"  传统方案步数: {rl_result.baseline_steps}")
    print(f"  {rl_result.improvement}")

    results["rl_comparison"] = {
        "rl_steps": rl_result.rl_steps,
        "baseline_steps": rl_result.baseline_steps,
        "improvement": rl_result.improvement,
        "trained": rl_result.trained,
    }

    # ------------------------------------------------------------------
    # Phase 5: 力场可视化
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Phase 5: 力学状态实时可视化 (力场热力图)")
    print("=" * 60)

    force_viz = ForceVisualizer()
    force_frame = force_viz.visualize(frame_model)

    print(f"  最大应力比: {force_frame.max_stress_ratio:.3f}")
    print(f"  平均应力比: {force_frame.avg_stress_ratio:.3f}")
    print(f"  稳定性: {'稳定' if force_frame.stable else '需要关注'}")

    results["force_field"] = {
        "max_stress_ratio": force_frame.max_stress_ratio,
        "avg_stress_ratio": force_frame.avg_stress_ratio,
        "total_elements": len(force_frame.elements),
    }

    # ------------------------------------------------------------------
    # Phase 6: 工程报告生成
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Phase 6: 工程报告自动生成")
    print("=" * 60)

    report_gen = ReportGenerator()

    # 钢框架报告
    frame_html = report_gen.generate_html(frame_model)
    frame_md = report_gen.generate_markdown(frame_model)

    with open(output / "钢框架拆除工程报告.html", "w", encoding="utf-8") as f:
        f.write(frame_html)
    print(f"  钢框架 HTML 报告: {output}/钢框架拆除工程报告.html")

    with open(output / "钢框架拆除工程报告.md", "w", encoding="utf-8") as f:
        f.write(frame_md)
    print(f"  钢框架 MD 报告: {output}/钢框架拆除工程报告.md")

    # 烟囱报告
    chimney_html = report_gen.generate_html(
        StructureModel(
            model_id="dummy", name="临时",
            nodes=[], elements=[], sections=[], materials=[]
        ),
        chimney_model=chimney_model,
        chimney_report=chimney_stability,
    )
    with open(output / "烟囱拆除工程报告.html", "w", encoding="utf-8") as f:
        f.write(chimney_html)
    print(f"  烟囱 HTML 报告: {output}/烟囱拆除工程报告.html")

    results["reports"] = {
        "frame_html": str(output / "钢框架拆除工程报告.html"),
        "frame_md": str(output / "钢框架拆除工程报告.md"),
        "chimney_html": str(output / "烟囱拆除工程报告.html"),
    }

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("V3.0 完整演示完成!")
    print("=" * 60)

    summary = {
        "chimney_stability": chimney_stability.stability_ratio,
        "chimney_engine": deep_report.engine_used,
        "xai_removable": xai_report.removable_elements,
        "rl_improvement": rl_result.improvement,
        "force_max_stress": force_frame.max_stress_ratio,
    }

    results["summary"] = summary

    # 保存汇总 JSON
    with open(output / "demo_summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n  汇总数据: {output}/demo_summary.json")
    print(f"  所有输出文件位于: {output}/")

    return results


# ============================================================================
# CLI 入口
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Iron-Fall V3.0 完整演示"
    )
    parser.add_argument(
        "--output", "-o",
        default="demo_output",
        help="输出目录 (默认: demo_output)"
    )
    args = parser.parse_args()

    try:
        demo_v3_full(output_dir=args.output)
    except Exception as e:
        logger.error(f"演示执行失败: {e}", exc_info=True)
        sys.exit(1)
