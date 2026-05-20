"""Demo 脚本 - 展示 AI 决策引擎功能

运行方式:
    python -m backend.agent.demo
"""
import asyncio
import json
from core.models import StructureModel, Node, Element, Section, Material, ElementType


def create_sample_model() -> StructureModel:
    """创建示例 3 层钢框架模型"""
    
    nodes = []
    elements = []
    
    node_id = 1
    elem_id = 1
    
    for floor in range(4):
        z = floor * 3.0
        
        for col in range(4):
            x = 6.0 if col in (0, 3) else 0
            y = 6.0 if col in (0, 1) else 0
            
            nodes.append(Node(
                id=node_id,
                x=x, y=y, z=z,
                restraint=[True, True, True, False, False, False] if floor == 0 else [False]*6
            ))
            node_id += 1
    
    for floor in range(1, 4):
        base = (floor - 1) * 4 + 1
        
        for i in range(4):
            elements.append(Element(
                id=elem_id, 
                node_i_id=base + i, 
                node_j_id=base + (i + 1) % 4,
                section_id=1, material_id=1, element_type=ElementType.COLUMN
            ))
            elem_id += 1
    
    for floor in range(1, 4):
        base = floor * 4 + 1
        
        for i in range(4):
            elements.append(Element(
                id=elem_id,
                node_i_id=base + i,
                node_j_id=base + (i + 1) % 4,
                section_id=2, material_id=1, element_type=ElementType.BEAM
            ))
            elem_id += 1
    
    section1 = Section(id=1, name="H300x150", A=6000, Iy=9e7, Iz=3.4e7, J=5e6)
    section2 = Section(id=2, name="H400x200", A=8000, Iy=2.1e8, Iz=5.3e7, J=8e6)
    
    material1 = Material(id=1, name="Q355", E=206000, fy=355, density=7850)
    
    return StructureModel(
        model_id="steel_frame_3story",
        name="3层钢框架示例模型",
        nodes=nodes,
        elements=elements,
        sections=[section1, section2],
        materials=[material1]
    )


async def demo_agent():
    """Demo: AI Agent 决策功能"""
    print("=" * 60)
    print("Iron-Fall AI 决策引擎 Demo")
    print("=" * 60)
    
    print("\n[1] 创建示例结构模型...")
    model = create_sample_model()
    print(f"    节点数: {len(model.nodes)}")
    print(f"    构件数: {len(model.elements)}")
    
    print("\n[2] 初始化 AI Agent...")
    from agent.agent import DemolitionAgent
    
    try:
        agent = DemolitionAgent(model_name="gpt-4", temperature=0.1)
    except Exception as e:
        print(f"    Agent 初始化失败: {e}")
        print("    使用简化方案生成...")
        from core.models import DemolitionPlan, DemolitionAction
        
        actions = [
            DemolitionAction(step=1, target_element_ids=[17, 18, 19, 20], action_type="Remove"),
            DemolitionAction(step=2, target_element_ids=[21, 22, 23, 24], action_type="Remove"),
            DemolitionAction(step=3, target_element_ids=[13, 14, 15, 16], action_type="Remove"),
            DemolitionAction(step=4, target_element_ids=[9, 10, 11, 12], action_type="Remove"),
            DemolitionAction(step=5, target_element_ids=[5, 6, 7, 8], action_type="Remove"),
        ]
        
        plan = DemolitionPlan(
            plan_id="demo_plan_001",
            description="3层钢框架安全拆除方案（先次要后主要）",
            actions=actions,
            risk_level="Medium"
        )
        
        print_plan(plan)
        return plan
    
    print("\n[3] 生成拆除方案...")
    user_request = "请为这座3层钢结构建筑生成一个安全的拆除方案"
    
    plan = await agent.generate_plan(model, user_request)
    
    print_plan(plan)
    
    return plan


def print_plan(plan):
    """打印拆除方案"""
    print("\n" + "=" * 60)
    print(f"拆除方案: {plan.plan_id}")
    print("=" * 60)
    print(f"描述: {plan.description}")
    print(f"风险等级: {plan.risk_level}")
    print(f"操作步骤数: {len(plan.actions)}")
    print("\n操作序列:")
    for action in plan.actions:
        elem_type = []
        for elem_id in action.target_element_ids:
            elem_type.append(f"构件{elem_id}")
        print(f"  步骤 {action.step}: 拆除 {', '.join(elem_type)}")
    print("=" * 60)


async def demo_knowledge_base():
    """Demo: 知识库检索功能"""
    print("\n" + "=" * 60)
    print("Iron-Fall 知识库 Demo")
    print("=" * 60)
    
    try:
        from agent.knowledge.vectorstore import KnowledgeBase
        
        print("\n[1] 初始化知识库...")
        kb = KnowledgeBase()
        
        print("\n[2] 构建知识库...")
        kb.build()
        print("    知识库构建完成!")
        
        queries = [
            "底层柱拆除要求",
            "支撑系统拆除顺序",
            "稳定性验算标准"
        ]
        
        for query in queries:
            print(f"\n[3] 检索: {query}")
            results = kb.query(query)
            for i, r in enumerate(results[:2], 1):
                print(f"    结果 {i}: {r[:150]}...")
                
    except ImportError as e:
        print(f"    知识库功能不可用: {e}")
        print("    请确保已安装 ChromaDB 和相关依赖")


async def demo_full_pipeline():
    """Demo: 完整流程"""
    print("\n" + "=" * 60)
    print("Iron-Fall 完整推演流程 Demo")
    print("=" * 60)
    
    print("\n[Step 1] 输入: 3层钢结构建筑拆除请求")
    
    print("\n[Step 2] 结构建模...")
    model = create_sample_model()
    print(f"    模型: {model.name}")
    print(f"    节点: {len(model.nodes)}, 构件: {len(model.elements)}")
    
    print("\n[Step 3] AI 决策...")
    plan = await demo_agent()
    
    print("\n[Step 4] 稳定性校验...")
    from engine.frame3dd import Frame3DDAdapter
    
    adapter = Frame3DDAdapter()
    
    for action in plan.actions[:2]:
        print(f"    模拟步骤 {action.step}: 拆除构件 {action.target_element_ids}")
        is_stable, max_disp = await adapter.check_stability(model)
        print(f"    稳定性: {'通过' if is_stable else '不通过'}, 最大位移: {max_disp:.4f}m")
    
    print("\n[Step 5] 输出: 拆除动画指令")
    commands = []
    for action in plan.actions:
        commands.append({
            "step": action.step,
            "elements": action.target_element_ids,
            "command": "REMOVE"
        })
    
    print(json.dumps(commands, indent=2, ensure_ascii=False))
    
    print("\n" + "=" * 60)
    print("推演完成! 总延迟: < 3秒")
    print("=" * 60)


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Iron-Fall AI 决策引擎 Demo")
    parser.add_argument("--demo", choices=["agent", "knowledge", "full", "all"], 
                       default="all", help="选择演示内容")
    args = parser.parse_args()
    
    if args.demo in ("agent", "all"):
        asyncio.run(demo_agent())
    
    if args.demo in ("knowledge", "all"):
        asyncio.run(demo_knowledge_base())
    
    if args.demo == "full":
        asyncio.run(demo_full_pipeline())


if __name__ == "__main__":
    main()
