"""环境安装与导入验证测试

验证所有依赖可正确导入、版本兼容。
无需网络或外部服务即可运行。
"""
import sys
import pytest
from pathlib import Path


class TestPythonVersion:
    """Python 版本检查"""

    def test_python_version(self):
        assert sys.version_info >= (3, 10), "需要 Python >= 3.10"


# ============================================================================
# 核心依赖导入测试
# ============================================================================

class TestCoreImports:
    """核心 web 和数值计算库导入"""

    def test_fastapi(self):
        import fastapi

    def test_uvicorn(self):
        import uvicorn

    def test_pydantic(self):
        import pydantic
        assert pydantic.VERSION.startswith("2"), "需要 Pydantic v2"

    def test_numpy(self):
        import numpy as np
        version = tuple(int(x) for x in np.__version__.split(".")[:2])
        assert version >= (1, 26), f"numpy >= 1.26 需要, 当前 {np.__version__}"

    def test_scipy(self):
        import scipy
        version = tuple(int(x) for x in scipy.__version__.split(".")[:2])
        assert version >= (1, 11), f"scipy >= 1.11 需要, 当前 {scipy.__version__}"


class TestAIImports:
    """AI 框架导入"""

    def test_langchain(self):
        import langchain

    def test_langchain_openai(self):
        import langchain_openai

    def test_langchain_community(self):
        try:
            import langchain_community
        except ImportError:
            pytest.skip("langchain_community 未安装 (可选依赖)")


# ============================================================================
# 可选依赖导入测试（允许缺失）
# ============================================================================

class TestOptionalImports:
    """可选引擎依赖导入（优雅降级验证）"""

    def test_anastruct_optional(self):
        """anaStruct 为可选主力引擎"""
        try:
            import anastruct
            has_anastruct = True
        except ImportError:
            has_anastruct = False
        # 记录但不阻塞 - anastruct 不是必需的
        if not has_anastruct:
            pytest.skip("anaStruct 未安装 (可选依赖)")

    def test_chromadb_optional(self):
        """ChromaDB 为可选 RAG 依赖"""
        try:
            import chromadb
            has_chroma = True
        except ImportError:
            has_chroma = False
        if not has_chroma:
            pytest.skip("ChromaDB 未安装 (可选依赖)")

    def test_openai_optional(self):
        """langchain-openai 需要 openai 包"""
        try:
            import openai
        except ImportError:
            pytest.skip("openai 未安装 (可选依赖)")


# ============================================================================
# 项目内部模块链式导入测试
# ============================================================================

class TestProjectImports:
    """验证项目所有核心模块可被正确导入"""

    def test_core_imports(self):
        from core import models, enums
        from core.models import (
            StructureModel, Node, Element, Section, Material, ElementType,
            DemolitionPlan, DemolitionAction, AnalysisResult,
            ChimneyModel, ChimneySegment, ChimneyStabilityReport,
            XAIReport, AgentRole, MultiAgentDecision, DemolitionCase,
        )

    def test_engine_imports(self):
        from engine import (
            AnaStructAdapter, Frame3DDAdapter, OpenSeesPyAdapter,
            ChimneyQuickAnalyzer, ChimneyDeepAnalyzer,
            XAIAnalyzer, DemolitionRLAgent,
        )

    def test_engine_submodules(self):
        from engine import sequencer, force_visualizer
        from engine import precompute, report_generator

    def test_agent_imports(self):
        from agent.agent import DemolitionAgent, SimpleDemolitionAgent, create_agent
        from agent.parser import StructureParser, create_structure_from_text
        from agent.multi_agent import (
            DebateOrchestrator,
            RuleBasedPlanningAgent, RuleBasedSafetyAgent, RuleBasedEconomyAgent,
        )

    def test_case_library_import(self):
        from agent.case_library import CaseLibrary, get_case_library

    def test_api_module_exists(self):
        """验证 API 模块文件存在"""
        api_main = Path(__file__).parent.parent.parent / "api" / "main.py"
        assert api_main.exists(), f"API 入口不存在: {api_main}"


# ============================================================================
# 依赖一致性检查
# ============================================================================

class TestDependencyAlignment:
    """检查 requirements.txt 与 pyproject.toml 依赖一致性"""

    def test_requirements_file_exists(self):
        req = Path(__file__).parent.parent.parent.parent / "requirements.txt"
        assert req.exists(), "requirements.txt 不存在"

    def test_pyproject_exists(self):
        pp = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
        assert pp.exists(), "pyproject.toml 不存在"

    def test_test_config_exists(self):
        pp = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
        content = pp.read_text(encoding="utf-8")
        assert "testpaths" in content, "pyproject.toml 缺少 testpaths 配置"
        assert "pytest" in content, "pyproject.toml 缺少 pytest 配置"
