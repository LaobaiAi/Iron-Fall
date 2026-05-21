"""Iron-Fall 计算引擎模块

提供多级力学计算引擎：
- anaStruct: Python 原生快速线弹性验算（主力，100ms 级）
- Frame3DD: 3D 静力/动力求解器（降级备选，秒级）
- OpenSeesPy: 深度非线性分析（复核引擎，秒级）
- ChimneyQuickAnalyzer: V3.0 烟囱悬臂梁快速验算
- ChimneyDeepAnalyzer: V3.0 烟囱倾倒动力学深部分析
- XAIAnalyzer: V3.0 可解释AI决策分析
"""
from engine.base import BaseEngineAdapter
from engine.anastruct_adapter import AnaStructAdapter
from engine.frame3dd import Frame3DDAdapter
from engine.opensees import OpenSeesPyAdapter
from engine.chimney_analyzer import ChimneyQuickAnalyzer
from engine.chimney_opensees import ChimneyDeepAnalyzer
from engine.xai_analyzer import XAIAnalyzer

__all__ = [
    "BaseEngineAdapter",
    "AnaStructAdapter",
    "Frame3DDAdapter",
    "OpenSeesPyAdapter",
    "ChimneyQuickAnalyzer",
    "ChimneyDeepAnalyzer",
    "XAIAnalyzer",
]
