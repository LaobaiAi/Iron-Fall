"""AI 智能体 - ReAct 逻辑实现

基于 LangChain 的 ReAct Agent，用于智能拆除决策。
"""
import os
import json
import asyncio
from typing import Optional, Literal
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.tools import tool

from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction, 
    AnalysisResult, ElementType
)
from agent.prompt import SYSTEM_PROMPT


class DemolitionAgent:
    """智能拆除决策 Agent
    
    基于 ReAct (Reasoning + Acting) 范式，
    实现"思考-行动-观察"的循环推理。
    """
    
    def __init__(
        self,
        model_name: str = "gpt-4",
        temperature: float = 0.1,
        max_iterations: int = 10
    ):
        """初始化 Agent
        
        Args:
            model_name: OpenAI 模型名称
            temperature: 温度参数 (0-1)
            max_iterations: 最大迭代次数
        """
        self._model_name = model_name
        self._temperature = temperature
        self._max_iterations = max_iterations
        self._llm: Optional[ChatOpenAI] = None
        self._agent_executor: Optional[AgentExecutor] = None
        self._current_model: Optional[StructureModel] = None
        self._tools = self._create_tools()
        
    def _create_tools(self) -> list:
        """创建 Agent 工具集"""
        from agent.tools import (
            check_structure_stability,
            analyze_demolition_action,
            validate_structure_model,
            query_demolition_regulations,
            get_risk_assessment
        )
        
        return [
            check_structure_stability,
            analyze_demolition_action,
            validate_structure_model,
            query_demolition_regulations,
            get_risk_assessment
        ]
    
    def _initialize_llm(self) -> ChatOpenAI:
        """初始化 LLM"""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("未设置 OPENAI_API_KEY 环境变量")
        
        return ChatOpenAI(
            model=self._model_name,
            temperature=self._temperature,
            api_key=api_key
        )
    
    def _create_prompt(self) -> ChatPromptTemplate:
        """创建 ReAct Agent 的提示词模板"""
        
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            HumanMessage(content="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        return prompt
    
    def initialize(self) -> None:
        """初始化 Agent (延迟加载)"""
        if self._agent_executor is None:
            self._llm = self._initialize_llm()
            
            base_agent = create_react_agent(
                llm=self._llm,
                tools=self._tools,
                prompt=self._create_prompt()
            )
            
            self._agent_executor = AgentExecutor(
                agent=base_agent,
                tools=self._tools,
                max_iterations=self._max_iterations,
                verbose=True,
                handle_parsing_errors=True
            )
    
    async def generate_plan(
        self,
        model: StructureModel,
        user_request: str
    ) -> DemolitionPlan:
        """生成拆除方案
        
        Args:
            model: 结构模型
            user_request: 用户请求描述
            
        Returns:
            拆除方案
        """
        self._current_model = model
        
        model_json = model.model_dump_json(indent=2)
        
        input_text = f"""请为以下钢结构建筑生成拆除方案：

用户请求: {user_request}

结构模型信息:
{model_json}

请按照以下步骤思考并生成方案：
1. 首先理解结构模型，识别柱、梁、支撑等构件
2. 检查模型的有效性
3. 分析拆除风险，确定拆除顺序
4. 生成包含多个步骤的拆除方案

输出格式为 JSON，包含 plan_id, description, actions 和 risk_level 字段。
"""
        
        try:
            self.initialize()
            
            if asyncio.get_event_loop().is_running():
                result = await asyncio.to_thread(
                    self._agent_executor.invoke,
                    {"input": input_text}
                )
            else:
                result = self._agent_executor.invoke({"input": input_text})
            
            output = result.get("output", "")
            
            return self._parse_agent_output(output, model)
            
        except Exception as e:
            return self._generate_fallback_plan(model, str(e))
    
    def _parse_agent_output(self, output: str, model: StructureModel) -> DemolitionPlan:
        """解析 Agent 输出为 DemolitionPlan"""
        
        try:
            if "```json" in output:
                json_str = output.split("```json")[1].split("```")[0].strip()
            elif "```" in output:
                json_str = output.split("```")[1].split("```")[0].strip()
            else:
                json_str = output
            
            data = json.loads(json_str)
            
            actions = [
                DemolitionAction(**action) 
                for action in data.get("actions", [])
            ]
            
            return DemolitionPlan(
                plan_id=data.get("plan_id", "unknown"),
                description=data.get("description", ""),
                actions=actions,
                risk_level=data.get("risk_level", "Medium")
            )
            
        except json.JSONDecodeError:
            return self._generate_fallback_plan(model, "JSON解析失败")
    
    def _generate_fallback_plan(
        self, 
        model: StructureModel, 
        reason: str
    ) -> DemolitionPlan:
        """生成备用方案 (Agent 不可用时)"""
        
        beams = [e for e in model.elements if e.element_type == ElementType.BEAM]
        columns = [e for e in model.elements if e.element_type == ElementType.COLUMN]
        braces = [e for e in model.elements if e.element_type == ElementType.BRACE]
        
        max_z = max(n.z for n in model.nodes)
        min_z = min(n.z for n in model.nodes)
        height = max_z - min_z
        
        actions = []
        step = 1
        
        for beam in beams:
            actions.append(DemolitionAction(
                step=step,
                target_element_ids=[beam.id],
                action_type="Remove"
            ))
            step += 1
        
        for col in columns:
            node_z_values = [
                n.z for n in model.nodes 
                if n.id in (col.node_i_id, col.node_j_id)
            ]
            if node_z_values and max(node_z_values) <= height * 0.6:
                actions.append(DemolitionAction(
                    step=step,
                    target_element_ids=[col.id],
                    action_type="Remove"
                ))
                step += 1
        
        risk_level = "High" if any(
            self._check_low_column(col, model) for col in columns
            if col not in [a.target_element_ids[0] for a in actions if len(a.target_element_ids) == 1]
        ) else "Medium"
        
        return DemolitionPlan(
            plan_id="fallback_plan",
            description=f"自动生成方案 (原因: {reason})",
            actions=actions,
            risk_level=risk_level
        )
    
    def _check_low_column(self, col, model: StructureModel) -> bool:
        """检查是否为底层柱"""
        node_z_values = [
            n.z for n in model.nodes 
            if n.id in (col.node_i_id, col.node_j_id)
        ]
        min_z = min(node_z_values) if node_z_values else 0
        max_height = max(n.z for n in model.nodes)
        return min_z < max_height * 0.2


class SimpleDemolitionAgent:
    """简化版 Agent (无需 OpenAI API)"""
    
    def __init__(self):
        self._plan_counter = 0
    
    async def generate_plan(
        self,
        model: StructureModel,
        user_request: str
    ) -> DemolitionPlan:
        """基于规则的方案生成"""
        
        self._plan_counter += 1
        
        beams = [e for e in model.elements if e.element_type == ElementType.BEAM]
        columns = [e for e in model.elements if e.element_type == ElementType.COLUMN]
        
        actions = []
        step = 1
        
        node_heights = {}
        for node in model.nodes:
            node_heights[node.id] = node.z
        
        def get_element_height(elem) -> float:
            i_z = node_heights.get(elem.node_i_id, 0)
            j_z = node_heights.get(elem.node_j_id, 0)
            return (i_z + j_z) / 2
        
        sorted_beams = sorted(beams, key=get_element_height, reverse=True)
        
        for beam in sorted_beams[:8]:
            actions.append(DemolitionAction(
                step=step,
                target_element_ids=[beam.id],
                action_type="Remove"
            ))
            step += 1
        
        max_z = max(n.z for n in model.nodes)
        upper_columns = [
            c for c in columns 
            if get_element_height(c) > max_z * 0.5
        ]
        
        for col in upper_columns[:4]:
            actions.append(DemolitionAction(
                step=step,
                target_element_ids=[col.id],
                action_type="Remove"
            ))
            step += 1
        
        risk = "Low"
        if any(get_element_height(c) < 1.0 for c in columns):
            risk = "High"
        elif actions:
            risk = "Medium"
        
        return DemolitionPlan(
            plan_id=f"simple_plan_{self._plan_counter:03d}",
            description="基于规则的简化拆除方案",
            actions=actions,
            risk_level=risk
        )


async def create_agent() -> DemolitionAgent:
    """工厂函数：创建 Agent"""
    try:
        return DemolitionAgent()
    except ValueError:
        return SimpleDemolitionAgent()
