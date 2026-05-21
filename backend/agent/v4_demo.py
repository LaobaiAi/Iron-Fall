"""V4.0 完整演示脚本 - 多智能体进化与系统集成

演示流程：
Phase 1: 多智能体协同决策 → 规划/安全/经济三智能体辩论
Phase 2: 案例库检索 → 匹配历史经验
Phase 3: 全系统集成 → 端到端测试
"""
import asyncio
import time
import json

from agent.parser import StructureParser
from agent.multi_agent import create_orchestrator, RuleBasedPlanningAgent
from agent.case_library import get_case_library
from core.models import StructureModel, DemolitionPlan


def print_separator(title: str, char: str = "="):
    print(f"\n{char * 60}")
    print(f"  {title}")
    print(f"{char * 60}\n")


def print_agent_opinion(opinion):
    print(f"  [{opinion.agent_role.value.upper():12s}] "
          f"置信度: {opinion.confidence:.0%} | "
          f"评分: {opinion.scores}")
    print(f"      理由: {opinion.reasoning[:100]}")


def print_case_match(match):
    print(f"  [{match.similarity_score:.0%}] {match.case.project_name}")
    print(f"      类型: {match.case.structure_type} | "
          f"方法: {match.case.demolition_method}")
    print(f"      成本: {match.case.cost_wan_yuan}万 | "
          f"工期: {match.case.duration_days}天")


# ============================================================================
# Phase 1: 多智能体协同决策
# ============================================================================

def phase1_multi_agent():
    """Phase 1: 多智能体决策框架演示"""
    print_separator("Phase 1: 多智能体协同决策")

    # 创建测试模型
    parser = StructureParser()
    model = parser.parse(
        "建一个3层钢框架，跨度6m，层高3.6m，H400x200，Q355",
        "v4_phase1_model",
    )

    print(f"模型: {model.name}")
    print(f"  节点: {len(model.nodes)} | 构件: {len(model.elements)}")
    print(f"  柱: {sum(1 for e in model.elements if e.element_type == 'Column')} | "
          f"梁: {sum(1 for e in model.elements if e.element_type == 'Beam')}")
    print()

    # 创建协调器
    orchestrator = create_orchestrator(use_llm=False)
    decision = orchestrator.decide(model)

    print(f"决策ID: {decision.decision_id}")
    print(f"共识度: {decision.consensus_score:.0%}\n")

    # 展示各智能体意见
    print("各智能体独立意见:")
    for opinion in decision.agent_opinions:
        print_agent_opinion(opinion)
        if opinion.plan:
            print(f"      方案: {len(opinion.plan.actions)}步, "
                  f"风险: {opinion.plan.risk_level}")

    # 展示辩论过程
    print("\n辩论过程:")
    for record in decision.debate_history:
        print(f"  Round {record.round}: {record.topic}")
        print(f"    参与智能体: {len(record.opinions)}个")
        print(f"    达成共识: {'是' if record.consensus_reached else '否'}")

    # 展示最终方案
    print(f"\n最终共识方案:")
    if decision.final_plan and decision.final_plan.actions:
        plan = decision.final_plan
        print(f"  方案ID: {plan.plan_id}")
        print(f"  描述: {plan.description}")
        print(f"  风险等级: {plan.risk_level}")
        print(f"  总步数: {len(plan.actions)}")
        print(f"  成本估算: {decision.cost_estimate}万元")
        print(f"  工期估算: {decision.duration_estimate}天")
        print(f"\n  拆除步骤:")
        for action in plan.actions[:10]:
            types = []
            for eid in action.target_element_ids:
                elem = next(
                    (e for e in model.elements if e.id == eid), None
                )
                types.append(elem.element_type.value[:2] if elem else "??")
            print(f"    步骤{action.step}: 拆除 {action.target_element_ids} "
                  f"({', '.join(types)})")
        if len(plan.actions) > 10:
            print(f"    ... (共{len(plan.actions)}步)")

    # 展示警告和分歧
    if decision.warnings:
        print("\nConsistent warnings:")
        for w in decision.warnings:
            print(f"  ! {w}")

    if decision.divergent_points:
        print("\nDivergent points:")
        for d in decision.divergent_points:
            print(f"  ? {d}")

    return decision


# ============================================================================
# Phase 2: 案例库检索
# ============================================================================

def phase2_case_library():
    """Phase 2: 案例库检索演示"""
    print_separator("Phase 2: 案例知识库检索")

    lib = get_case_library()

    # 案例库统计
    stats = lib.get_stats()
    print(f"案例库概况:")
    print(f"  总案例数: {stats.total_cases}")
    print(f"  成功率: {stats.success_rate:.0%}")
    print(f"  标签分布: {len(stats.tags)}种标签")

    print(f"\n全部案例一览:")
    for case in lib.get_all_cases():
        status = "OK" if case.success else "FAIL"
        print(f"  [{status}] {case.case_id}: {case.project_name}")
        print(f"      类型: {case.structure_type} | "
              f"层数: {case.floors}F | 方法: {case.demolition_method}")

    # 基于模型的相似案例检索
    print(f"\n基于3层钢框架的相似案例检索:")

    parser = StructureParser()
    model = parser.parse(
        "建一个3层钢框架，跨度6m，层高3.6m",
        "v4_search_model",
    )

    matches = lib.search_similar(model, top_k=5)
    for m in matches:
        print_case_match(m)

    # 按标签搜索
    print(f"\n按标签[爆破]搜索:")
    blast_cases = lib.search_by_tag("爆破")
    for case in blast_cases:
        print(f"  - {case.project_name} ({case.demolition_method})")

    print(f"\n按标签[失效教训]搜索:")
    fail_cases = lib.search_by_tag("失效教训")
    for case in fail_cases:
        print(f"  - {case.project_name}")
        for lesson in case.key_lessons:
            print(f"    ! {lesson}")

    return matches


# ============================================================================
# Phase 3: 全系统集成测试
# ============================================================================

def phase3_integration():
    """Phase 3: 全系统端到端集成测试"""
    print_separator("Phase 3: 全系统集成测试")

    parser = StructureParser()
    orchestrator = create_orchestrator()
    lib = get_case_library()

    test_scenarios = [
        ("标准3层钢框架", "建一个3层钢框架，跨度6m，层高3.6m，H400x200，Q355"),
        ("带支撑5层框架", "建一个带X型斜撑的五层钢框架，首层高4m，标准层高3.4m"),
        ("6层钢框架", "建一个6层钢框架，跨度8m，层高3.5m，H500x250，Q355"),
    ]

    results = []

    for name, desc in test_scenarios:
        print(f"\n--- 场景: {name} ---")

        t0 = time.time()

        # Step 1: 建模
        model = parser.parse(desc, f"test_{name.replace(' ', '_')}")
        t1 = time.time()

        # Step 2: 多智能体决策
        decision = orchestrator.decide(model)
        t2 = time.time()

        # Step 3: 案例匹配
        matches = lib.search_similar(model, top_k=3)
        t3 = time.time()

        print(f"  建模: {len(model.nodes)}节点, {len(model.elements)}构件 "
              f"({(t1-t0)*1000:.0f}ms)")
        print(f"  决策: 共识度={decision.consensus_score:.0%}, "
              f"{len(decision.final_plan.actions) if decision.final_plan else 0}步 "
              f"({(t2-t1)*1000:.0f}ms)")
        print(f"  案例: {len(matches)}个匹配, "
              f"最佳={matches[0].case.project_name if matches else 'N/A'} "
              f"({(t3-t2)*1000:.0f}ms)")
        print(f"  总耗时: {(t3-t0)*1000:.0f}ms")

        results.append({
            "scenario": name,
            "model_size": f"{len(model.nodes)}N/{len(model.elements)}E",
            "consensus": decision.consensus_score,
            "plan_steps": len(decision.final_plan.actions) if decision.final_plan else 0,
            "risk": decision.final_plan.risk_level if decision.final_plan else "N/A",
            "cost": decision.cost_estimate,
            "duration": decision.duration_estimate,
            "total_ms": round((t3 - t0) * 1000),
        })

    # 汇总
    print(f"\n{'='*60}")
    print(f"  集成测试汇总")
    print(f"{'='*60}")
    print(f"  {'场景':20s} {'规模':10s} {'共识':>6s} {'步数':>5s} "
          f"{'风险':>7s} {'耗时':>6s}")
    print(f"  {'-'*56}")
    for r in results:
        print(f"  {r['scenario']:20s} {r['model_size']:10s} "
              f"{r['consensus']:>5.0%} {r['plan_steps']:>5d} "
              f"{r['risk']:>7s} {r['total_ms']:>5d}ms")

    # 验收检查
    print(f"\nV4.0 验收清单:")
    checks = [
        ("多智能体框架运行", all(
            r["plan_steps"] > 0 for r in results
        )),
        ("案例库有10个案例", lib.total_cases >= 10),
        ("案例匹配可用", len(matches) > 0),
        ("端到端耗时<3s", all(r["total_ms"] < 3000 for r in results)),
        ("方案安全审查", all(
            r["risk"] != "Critical" for r in results
        )),
    ]
    all_pass = True
    for name, passed in checks:
        status = "PASS" if passed else "FAIL"
        all_pass = all_pass and passed
        print(f"  [{status}] {name}")

    print(f"\n  {'All checks passed!' if all_pass else 'Some checks failed!'}")
    return results


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 60)
    print("  Iron-Fall V4.0: 智能体进化与系统集成演示")
    print("=" * 60)

    # Phase 1
    decision = phase1_multi_agent()

    # Phase 2
    phase2_case_library()

    # Phase 3
    phase3_integration()

    print(f"\n{'='*60}")
    print(f"  V4.0 演示完成!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
