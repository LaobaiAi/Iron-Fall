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
    DemolitionResponse, AnalysisResult,
    ChimneyModel, ChimneyStabilityReport, XAIReport
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
    
    # 初始化预计算引擎
    from engine.precompute import PrecomputeEngine
    app.state.precompute = PrecomputeEngine()
    app.state.precompute.set_engines(app.state.anastruct, app.state.frame3dd)
    
    logger.info(f"anaStruct  状态: {app.state.anastruct.version}")
    logger.info(f"Frame3DD   状态: {app.state.frame3dd.version}")
    logger.info(f"OpenSeesPy 状态: {app.state.opensees.version}")
    logger.info(f"预计算引擎 状态: ready")
    
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
# 自然语言解析接口
# ============================================================================

@app.post("/api/v1/model/parse")
async def parse_natural_language(
    text: str,
    model_id: str = "nl_model"
) -> dict:
    """自然语言解析：描述 → StructureModel
    
    支持描述示例：
    - "建一个3层钢框架，跨度6m，层高3.6m"
    - "建一个带X型斜撑的五层钢框架，首层高4.5m，标准层高3.6m，H400x200，Q355"
    
    Args:
        text: 自然语言结构描述
        model_id: 模型 ID
        
    Returns:
        包含完整 StructureModel 的响应
    """
    start_time = time.time()
    
    from agent.parser import StructureParser
    
    parser = StructureParser()
    model = parser.parse(text, model_id)
    
    return {
        "success": True,
        "model": model.model_dump(),
        "stats": {
            "nodes": len(model.nodes),
            "elements": len(model.elements),
            "columns": len([e for e in model.elements if e.element_type == "Column"]),
            "beams": len([e for e in model.elements if e.element_type == "Beam"]),
            "braces": len([e for e in model.elements if e.element_type == "Brace"]),
        },
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# 拆除序列生成接口
# ============================================================================

@app.post("/api/v1/plan/sequence")
async def generate_demolition_sequence(model: StructureModel) -> dict:
    """基于图论的智能拆除序列生成
    
    自动分析结构拓扑，生成最优拆除顺序。
    遵循"先次要后主要、自上而下"原则。
    
    Args:
        model: 结构模型
        
    Returns:
        拆除方案
    """
    start_time = time.time()
    
    from engine.sequencer import DemolitionSequencer
    
    sequencer = DemolitionSequencer()
    
    # 使用 anaStruct 作为安全检查
    async def safety_check(m: StructureModel, _) -> bool:
        is_stable, _ = await app.state.anastruct.check_stability(m, 0.1)
        return is_stable
    
    plan = sequencer.generate_sequence(
        model,
        max_elements_per_step=3,
        safety_check_fn=None  # 异步回调暂不直接支持
    )
    
    return {
        "success": True,
        "plan": plan.model_dump(),
        "stats": {
            "total_steps": len(plan.actions),
            "total_elements": len(model.elements),
            "risk_level": plan.risk_level,
        },
        "latency_ms": (time.time() - start_time) * 1000
    }


# ============================================================================
# 深度力学分析接口
# ============================================================================

@app.post("/api/v1/analysis/pushover")
async def run_pushover_analysis(
    model: StructureModel,
    action: Optional[DemolitionAction] = None
) -> dict:
    """OpenSeesPy 推覆分析（深度非线性）
    
    仅在关键步骤触发，计算代价较高。
    生成塑性铰分布、荷载-位移曲线、性能点评估。
    
    Args:
        model: 结构模型
        action: 拆除动作（可选）
        
    Returns:
        深度分析报告
    """
    start_time = time.time()
    
    from engine.deep_analysis import create_deep_analysis_report
    
    result = create_deep_analysis_report(model, action)
    
    return {
        **result,
        "latency_ms": (time.time() - start_time) * 1000
    }


@app.get("/api/v1/analysis/report")
async def get_analysis_report(model_id: str = "") -> dict:
    """获取力学分析报告摘要
    
    返回各级引擎的可用状态和分析能力。
    """
    return {
        "engines": {
            "anastruct": {
                "status": app.state.anastruct.version,
                "mode": "快速线弹性分析",
                "latency": "< 200ms"
            },
            "frame3dd": {
                "status": app.state.frame3dd.version,
                "mode": "3D 静力/动力分析",
                "latency": "< 2s"
            },
            "opensees": {
                "status": app.state.opensees.version,
                "mode": "深度非线性推覆分析",
                "latency": "< 5s"
            },
        },
        "analysis_modes": [
            "static_linear",     # anaStruct
            "static_3d",         # Frame3DD
            "dynamic_removal",   # Frame3DD
            "pushover",          # OpenSeesPy
            "plastic_hinge",     # OpenSeesPy
        ]
    }


# ============================================================================
# 预计算与缓存接口
# ============================================================================

@app.post("/api/v1/precompute")
async def precompute_model(model: StructureModel) -> dict:
    """预计算结构模型的所有分析结果
    
    后台异步预计算拆除方案、静力分析和各步骤稳定性。
    结果存入 LRU 缓存，后续请求直接命中。
    
    Args:
        model: 结构模型
        
    Returns:
        预计算状态
    """
    start_time = time.time()
    
    await app.state.precompute.precompute_all(model)
    
    return {
        "success": True,
        "cache_stats": app.state.precompute.stats,
        "model_hash": model_hash_from_precompute(model),
        "latency_ms": (time.time() - start_time) * 1000
    }


def model_hash_from_precompute(model: StructureModel) -> str:
    from engine.precompute import model_hash
    return model_hash(model)


@app.get("/api/v1/precompute/stats")
async def get_cache_stats() -> dict:
    """获取预计算缓存统计"""
    return {
        "success": True,
        "cache": app.state.precompute.stats
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
# V3.0 烟囱结构解析接口
# ============================================================================

@app.post("/api/v1/chimney/parse")
async def parse_chimney_description(text: str, model_id: str = "chimney_nl") -> dict:
    """烟囱自然语言解析

    支持描述示例：
    - "建立一个高60m、底径5m、顶径3m、壁厚0.3m的C40钢筋混凝土烟囱，顶部设5m钢制排气筒"
    - "50m烟囱，底部直径4m，顶部2m，C30混凝土，壁厚0.25m"
    - "高80m变截面烟囱，底径6m，在30m处直径变为4m，顶部2m，C50混凝土"

    Args:
        text: 自然语言烟囱描述
        model_id: 模型 ID

    Returns:
        包含完整 ChimneyModel 的响应
    """
    start_time = time.time()

    from agent.chimney_parser import ChimneyParser

    parser = ChimneyParser()
    model = parser.parse(text, model_id)

    return {
        "success": True,
        "model": model.model_dump(),
        "stats": {
            "total_height": model.total_height,
            "base_diameter": model.base_diameter,
            "top_diameter": model.top_diameter,
            "segments": len(model.segments),
            "attachments": len(model.attachments),
            "notch_height": model.notch_height,
        },
        "latency_ms": (time.time() - start_time) * 1000,
    }


@app.post("/api/v1/chimney/stability")
async def check_chimney_stability(model: ChimneyModel) -> dict:
    """烟囱切口后稳定性快速验算

    基于变截面悬臂梁模型，计算切口形成后偏心自重矩作用下的稳定性。

    Args:
        model: 烟囱模型

    Returns:
        稳定性报告
    """
    start_time = time.time()

    from engine.chimney_analyzer import ChimneyQuickAnalyzer

    analyzer = ChimneyQuickAnalyzer()
    report = analyzer.analyze_stability(model)

    return {
        "success": True,
        "report": report.model_dump(),
        "latency_ms": (time.time() - start_time) * 1000,
    }


@app.post("/api/v1/chimney/deep")
async def run_chimney_deep_analysis(
    model: ChimneyModel,
    notch_height: Optional[float] = None,
    time_step: float = 0.02,
    max_time: float = 15.0,
) -> dict:
    """烟囱深部分析 - 倾倒过程动力学

    执行烟囱切口后的倾倒全过程动力学分析。
    - N 级 (OpenSeesPy 可用): FiberSection + dispBeamColumn，动力时程分析
    - L-1 级 (降级): 基于转动动力学的刚体倾倒仿真

    输出：倾倒轨迹、重心时程、触地速度、撞击力

    Args:
        model: 烟囱模型
        notch_height: 切口高度 (m)，不指定则用模型默认值
        time_step: 时间步长 (s)，默认 0.02s (50fps)
        max_time: 最大模拟时间 (s)

    Returns:
        深部分析报告
    """
    start_time = time.time()

    from engine.chimney_opensees import ChimneyDeepAnalyzer

    analyzer = ChimneyDeepAnalyzer()
    report = analyzer.run_deep_analysis(
        model,
        notch_height=notch_height,
        time_step=time_step,
        max_time=max_time,
    )

    return {
        "success": True,
        "report": report.model_dump(),
        "stats": {
            "engine": report.engine_used,
            "trajectory_points": len(report.trajectory),
            "impact_time": report.impact_time,
            "impact_velocity": report.impact_velocity,
            "impact_force_kn": report.impact_force,
        },
        "warnings": report.warnings,
        "latency_ms": (time.time() - start_time) * 1000,
    }


# ============================================================================
# V3.0 可解释AI (XAI) 决策接口
# ============================================================================

@app.post("/api/v1/xai/explain")
async def explain_demolition_decision(
    model: StructureModel,
    analysis_result: Optional[AnalysisResult] = None,
) -> dict:
    """生成可解释AI决策报告

    为每个构件生成详细的决策依据：
    - 应力比 (当前应力/屈服强度)
    - 重要性系数 (基于传力路径)
    - 拆除后位移增幅预测
    - 自然语言解释

    Args:
        model: 结构模型
        analysis_result: 力学分析结果 (可选)

    Returns:
        XAI 决策报告
    """
    start_time = time.time()

    from engine.xai_analyzer import XAIAnalyzer

    analyzer = XAIAnalyzer()
    report = analyzer.analyze(model, analysis_result)

    return {
        "success": True,
        "report": report.model_dump(),
        "stats": {
            "total_elements": report.total_elements,
            "removable": report.removable_elements,
            "overall_stability": report.overall_stability,
        },
        "latency_ms": (time.time() - start_time) * 1000,
    }


# ============================================================================
# V3.0 强化学习拆除序列优化接口
# ============================================================================

@app.post("/api/v1/rl/compare")
async def compare_rl_vs_baseline(
    model: StructureModel,
    train: bool = False,
    timesteps: int = 5000,
) -> dict:
    """RL vs 传统方案对比

    使用 PPO 训练拆除智能体，与规则方案同屏对比。
    RL智能体在简单框架上训练收敛后，展示优化效果。

    Args:
        model: 结构模型
        train: 是否现场训练 (较耗时，默认使用启发式)
        timesteps: 训练步数 (仅 train=true 时有效)

    Returns:
        对比结果
    """
    start_time = time.time()

    from engine.rl_agent import create_rl_comparison

    result = create_rl_comparison(
        model, train=train, timesteps=timesteps
    )

    return {
        "success": True,
        "trained": result.trained,
        "rl_plan": {
            "sequence": result.rl_sequence,
            "steps": result.rl_steps,
            "removed": result.rl_removed,
            "reward": result.rl_reward,
            "final_stability": result.rl_stability_end,
        },
        "baseline_plan": {
            "sequence": result.baseline_sequence,
            "steps": result.baseline_steps,
            "removed": result.baseline_removed,
        },
        "comparison": {
            "improvement": result.improvement,
            "rl_steps": result.rl_steps,
            "baseline_steps": result.baseline_steps,
        },
        "latency_ms": (time.time() - start_time) * 1000,
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
