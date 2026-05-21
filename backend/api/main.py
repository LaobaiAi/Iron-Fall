"""FastAPI 主入口和 WebSocket 接口

Iron-Fall 后端服务入口。
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import time
import logging
from typing import Optional

from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction,
    DemolitionResponse, AnalysisResult
)
from engine.anastruct_adapter import AnaStructAdapter
from engine.frame3dd import Frame3DDAdapter
from engine.opensees import OpenSeesPyAdapter
from agent.agent import DemolitionAgent, SimpleDemolitionAgent

# 日志配置
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# 应用生命周期
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("Iron-Fall 后端服务启动中...")
    
    # 初始化计算引擎（三级体系）
    app.state.anastruct = AnaStructAdapter()      # 主力：Python 原生快速验算
    app.state.frame3dd = Frame3DDAdapter()         # 备选：3D 静力/动力分析
    app.state.opensees = OpenSeesPyAdapter()       # 深度：非线性复核
    
    logger.info(f"anaStruct  状态: {app.state.anastruct.version}")
    logger.info(f"Frame3DD   状态: {app.state.frame3dd.version}")
    logger.info(f"OpenSeesPy 状态: {app.state.opensees.version}")
    
    yield
    
    logger.info("Iron-Fall 后端服务关闭")


# ============================================================================
# FastAPI 应用
# ============================================================================

app = FastAPI(
    title="Iron-Fall API",
    description="智能钢结构拆除决策系统 API",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# 健康检查
# ============================================================================

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "Iron-Fall",
        "engines": {
            "anastruct": app.state.anastruct.version,
            "frame3dd": app.state.frame3dd.version,
            "opensees": app.state.opensees.version
        }
    }


# ============================================================================
# 模型验证接口
# ============================================================================

@app.post("/api/v1/model/validate")
async def validate_model(model: StructureModel) -> dict:
    """验证结构模型
    
    Args:
        model: 待验证的结构模型
        
    Returns:
        验证结果
    """
    start_time = time.time()
    
    is_valid, error = await app.state.anastruct.validate_model(model)
    
    return {
        "success": is_valid,
        "error": error,
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# 级联分析辅助函数：anaStruct → Frame3DD → 降级
# ============================================================================

async def cascading_analysis(
    model: StructureModel,
    action: DemolitionAction = None,
    method: str = "static"
) -> tuple[AnalysisResult, str]:
    """级联分析：优先 anaStruct，失败则 Frame3DD 兜底
    
    Args:
        model: 结构模型
        action: 拆除动作（可选，用于动力分析）
        method: 分析类型 ("static" | "dynamic")
    
    Returns:
        (result, engine_used)
    """
    # 第一级：anaStruct 快速验算
    try:
        if method == "dynamic" and action:
            result = await app.state.anastruct.run_dynamic_analysis(model, action)
        else:
            result = await app.state.anastruct.run_static_analysis(model)
        if result.success:
            return result, "anaStruct"
    except Exception as e:
        logger.warning(f"anaStruct 分析失败，降级到 Frame3DD: {e}")
    
    # 第二级：Frame3DD 降级备选
    try:
        if method == "dynamic" and action:
            result = await app.state.frame3dd.run_dynamic_analysis(model, action)
        else:
            result = await app.state.frame3dd.run_static_analysis(model)
        return result, "Frame3DD"
    except Exception as e:
        logger.warning(f"Frame3DD 分析失败，使用模拟数据: {e}")
    
    # 第三级：完全降级（mock 数据）
    return AnalysisResult(
        success=False,
        is_safe=False,
        stability_status="Error",
        warnings=["所有计算引擎不可用"]
    ), "None"


# ============================================================================
# 静力分析接口
# ============================================================================

@app.post("/api/v1/analysis/static")
async def run_static_analysis(model: StructureModel) -> dict:
    """执行静力分析
    
    Args:
        model: 结构模型
        
    Returns:
        分析结果
    """
    start_time = time.time()
    
    result, engine = await cascading_analysis(model, method="static")
    
    return {
        "success": result.is_safe,
        "analysis": result.model_dump(),
        "engine": engine,
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# 动力分析接口 (拆除模拟)
# ============================================================================

@app.post("/api/v1/analysis/dynamic")
async def run_dynamic_analysis(
    model: StructureModel,
    action: DemolitionAction
) -> dict:
    """执行动力分析（拆除模拟）
    
    Args:
        model: 结构模型
        action: 拆除动作
        
    Returns:
        分析结果
    """
    start_time = time.time()
    
    result, engine = await cascading_analysis(model, action, method="dynamic")
    
    return {
        "success": result.is_safe,
        "analysis": result.model_dump(),
        "engine": engine,
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# 深度分析接口 (OpenSeesPy)
# ============================================================================

@app.post("/api/v1/analysis/deep")
async def run_deep_analysis(
    model: StructureModel,
    action: Optional[DemolitionAction] = None,
    use_opensees: bool = True
) -> dict:
    """执行深度非线性分析
    
    仅在高危场景下使用，计算代价较高。
    
    Args:
        model: 结构模型
        action: 拆除动作（可选）
        use_opensees: 是否使用 OpenSeesPy
        
    Returns:
        分析结果
    """
    start_time = time.time()
    
    if use_opensees:
        if action:
            result = await app.state.opensees.run_dynamic_analysis(model, action)
        else:
            result = await app.state.opensees.run_static_analysis(model)
    else:
        if action:
            result = await app.state.frame3dd.run_dynamic_analysis(model, action)
        else:
            result = await app.state.frame3dd.run_static_analysis(model)
    
    return {
        "success": result.is_safe,
        "analysis": result.model_dump(),
        "engine": "OpenSeesPy" if use_opensees else "Frame3DD",
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# 稳定性检查接口
# ============================================================================

@app.post("/api/v1/stability/check")
async def check_stability(
    model: StructureModel,
    threshold: float = 0.05
) -> dict:
    """检查结构稳定性
    
    Args:
        model: 结构模型
        threshold: 位移阈值（米）
        
    Returns:
        稳定性检查结果
    """
    start_time = time.time()
    
    is_stable, max_disp = await app.state.anastruct.check_stability(
        model, threshold
    )
    
    return {
        "is_stable": is_stable,
        "max_displacement": max_disp,
        "threshold": threshold,
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# AI 决策接口
# ============================================================================

@app.post("/api/v1/agent/plan")
async def generate_demolition_plan(
    model: StructureModel,
    user_request: str = "请生成安全的拆除方案"
) -> dict:
    """AI 智能体生成拆除方案
    
    基于 ReAct 范式的 AI 决策引擎，自动分析结构并生成拆除方案。
    
    Args:
        model: 结构模型
        user_request: 用户请求描述
        
    Returns:
        拆除方案
    """
    start_time = time.time()
    
    try:
        agent = DemolitionAgent(model_name="gpt-4", temperature=0.1)
        plan = await agent.generate_plan(model, user_request)
    except ValueError:
        agent = SimpleDemolitionAgent()
        plan = await agent.generate_plan(model, user_request)
    
    return {
        "success": True,
        "plan": plan.model_dump(),
        "latency_ms": (time.time() - start_time) * 1000
    }


@app.post("/api/v1/agent/validate")
async def validate_demolition_plan(
    model: StructureModel,
    plan: DemolitionPlan
) -> dict:
    """验证拆除方案的安全性
    
    对方案中的每个步骤进行稳定性校验。
    
    Args:
        model: 结构模型
        plan: 拆除方案
        
    Returns:
        验证结果
    """
    start_time = time.time()
    
    results = []
    cumulative_model = StructureModel(
        model_id=model.model_id,
        name=model.name,
        nodes=model.nodes,
        elements=model.elements.copy(),
        sections=model.sections,
        materials=model.materials
    )
    
    for action in plan.actions:
        is_valid, error = await app.state.anastruct.validate_model(cumulative_model)
        
        if not is_valid:
            results.append({
                "step": action.step,
                "valid": False,
                "error": error
            })
            continue
        
        is_stable, max_disp = await app.state.anastruct.check_stability(
            cumulative_model
        )
        
        results.append({
            "step": action.step,
            "valid": is_stable,
            "max_displacement": max_disp,
            "elements_removed": action.target_element_ids
        })
        
        remaining = [
            e for e in cumulative_model.elements
            if e.id not in action.target_element_ids
        ]
        cumulative_model.elements = remaining
    
    all_valid = all(r.get("valid", False) for r in results)
    
    return {
        "success": all_valid,
        "results": results,
        "plan_risk_level": plan.risk_level,
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# WebSocket 实时接口
# ============================================================================

class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def send_json(self, websocket: WebSocket, data: dict):
        await websocket.send_json(data)


manager = ConnectionManager()


@app.websocket("/ws/demolition")
async def websocket_demolition(websocket: WebSocket):
    """实时拆除推演 WebSocket 接口
    
    协议:
    1. 客户端发送: {"type": "demolish", "model": {...}, "action": {...}}
    2. 服务端返回: {"type": "result", "success": bool, "analysis": {...}}
    """
    await manager.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif msg_type == "demolish":
                start_time = time.time()
                
                try:
                    model = StructureModel(**data.get("model", {}))
                    action = DemolitionAction(**data.get("action", {}))
                    
                    # 级联分析：anaStruct → Frame3DD
                    result, engine = await cascading_analysis(
                        model, action, method="dynamic"
                    )
                    
                    response = {
                        "type": "result",
                        "success": result.is_safe,
                        "analysis": result.model_dump(),
                        "engine": engine,
                        "latency_ms": (time.time() - start_time) * 1000
                    }
                    
                    await websocket.send_json(response)
                    
                except Exception as e:
                    logger.error(f"Demolish 处理错误: {e}")
                    await websocket.send_json({
                        "type": "result",
                        "success": False,
                        "analysis": {
                            "stability_status": "Error",
                            "is_safe": False,
                            "warnings": [f"处理错误: {str(e)}"]
                        },
                        "latency_ms": (time.time() - start_time) * 1000
                    })
            
            elif msg_type == "validate":
                try:
                    model = StructureModel(**data.get("model", {}))
                    is_valid, error = await app.state.anastruct.validate_model(model)
                    
                    await websocket.send_json({
                        "type": "validation_result",
                        "is_valid": is_valid,
                        "error": error
                    })
                except Exception as e:
                    logger.error(f"Validate 处理错误: {e}")
                    await websocket.send_json({
                        "type": "validation_result",
                        "is_valid": False,
                        "error": str(e)
                    })
            
            elif msg_type == "analyze_static":
                start_time = time.time()
                try:
                    model = StructureModel(**data.get("model", {}))
                    result, engine = await cascading_analysis(model, method="static")
                    
                    await websocket.send_json({
                        "type": "analysis_result",
                        "success": result.is_safe,
                        "analysis": result.model_dump(),
                        "engine": engine,
                        "latency_ms": (time.time() - start_time) * 1000
                    })
                except Exception as e:
                    logger.error(f"Analyze 处理错误: {e}")
                    await websocket.send_json({
                        "type": "analysis_result",
                        "success": False,
                        "error": str(e)
                    })
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}"
                })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("WebSocket 连接断开")
    
    except Exception as e:
        logger.error(f"WebSocket 错误: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e) or "Unknown error"
            })
        except:
            pass


# ============================================================================
# 根路径
# ============================================================================

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Iron-Fall",
        "version": "0.1.0",
        "description": "智能钢结构拆除决策系统",
        "docs": "/docs"
    }
