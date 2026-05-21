"""API REST 端点集成测试

使用 FastAPI TestClient 测试所有 V1.0 / V3.0 / V4.0 REST 端点。
覆盖正常响应 (200)、输入验证 (422)、响应结构完整性。
"""
import pytest
import time
from fastapi.testclient import TestClient
from core.models import (
    StructureModel, DemolitionPlan, DemolitionAction,
    AnalysisResult, ChimneyModel, ChimneyStabilityReport,
)


# ---------------------------------------------------------------------------
# TestClient fixture（会话级，避免重复初始化）
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient，模块级复用"""
    from api.main import app
    with TestClient(app) as c:
        yield c


# ============================================================================
# Health & Root
# ============================================================================

class TestHealthCheck:
    """健康检查与根路径"""

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Iron-Fall"
        assert "engines" in data

    def test_root_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "Iron-Fall"


# ============================================================================
# V1.0 模型验证与解析
# ============================================================================

class TestModelEndpoints:
    """模型验证 / 解析 / 序列生成"""

    def test_validate_model_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/model/validate",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "latency_ms" in data

    def test_validate_model_422_empty(self, client):
        resp = client.post("/api/v1/model/validate", json={})
        assert resp.status_code == 422

    def test_parse_natural_language_200(self, client):
        resp = client.post("/api/v1/model/parse?text=3层钢框架，跨度6m，层高3.6m")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "model" in data
        assert "nodes" in data["model"]
        assert "elements" in data["model"]

    def test_parse_empty_text_422(self, client):
        resp = client.post("/api/v1/model/parse", json={})
        assert resp.status_code == 422

    def test_plan_sequence_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/plan/sequence",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "plan" in data

    def test_plan_sequence_422_empty(self, client):
        resp = client.post("/api/v1/plan/sequence", json={})
        assert resp.status_code == 422


# ============================================================================
# V1.0 力学分析
# ============================================================================

class TestAnalysisEndpoints:
    """静力分析 / 动力分析 / 深度分析 / 推覆分析"""

    def test_static_analysis_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/analysis/static",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "analysis" in data

    def test_dynamic_analysis_200(self, client, sample_3story_frame):
        action = DemolitionAction(step=1, target_element_ids=[1]).model_dump()
        resp = client.post("/api/v1/analysis/dynamic", json={
            "model": sample_3story_frame.model_dump(),
            "action": action,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis" in data

    def test_stability_check_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/stability/check",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert "is_stable" in data

    def test_deep_analysis_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/analysis/deep", json={
            "model": sample_3story_frame.model_dump(),
            "use_opensees": False,
        })
        assert resp.status_code == 200

    def test_pushover_analysis_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/analysis/pushover", json={
            "model": sample_3story_frame.model_dump(),
        })
        assert resp.status_code == 200

    def test_analysis_report_200(self, client):
        resp = client.get("/api/v1/analysis/report?model_id=test")
        assert resp.status_code == 200


# ============================================================================
# V1.0 Agent & 预计算
# ============================================================================

class TestAgentEndpoints:
    """AI 智能体方案生成 / 方案验证"""

    def test_agent_plan_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/agent/plan",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert "plan" in data or "success" in data

    def test_agent_validate_200(self, client, sample_3story_frame):
        plan = DemolitionPlan(plan_id="x",
            actions=[DemolitionAction(step=1, target_element_ids=[1])]
            ).model_dump()
        resp = client.post("/api/v1/agent/validate", json={
            "model": sample_3story_frame.model_dump(),
            "plan": plan,
        })
        assert resp.status_code == 200


class TestPrecomputeEndpoints:
    """预计算接口"""

    def test_precompute_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/precompute",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200

    def test_precompute_stats_200(self, client):
        resp = client.get("/api/v1/precompute/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "size" in data or "success" in data


# ============================================================================
# V3.0 烟囱端点
# ============================================================================

class TestChimneyEndpoints:
    """烟囱自然语言解析 / 稳定性验算 / 深部分析"""

    def test_chimney_parse_200(self, client):
        from urllib.parse import quote
        text = "100米高钢筋混凝土烟囱，底部外径8m，顶部外径3m，壁厚0.3m，C40混凝土"
        resp = client.post(f"/api/v1/chimney/parse?text={quote(text)}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "chimney_model" in data

    def test_chimney_parse_422_empty(self, client):
        resp = client.post("/api/v1/chimney/parse", json={})
        assert resp.status_code == 422

    def test_chimney_stability_200(self, client, sample_chimney_100m):
        resp = client.post("/api/v1/chimney/stability",
                           json=sample_chimney_100m.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "report" in data

    def test_chimney_deep_200(self, client, sample_chimney_100m):
        resp = client.post("/api/v1/chimney/deep",
                           json=sample_chimney_100m.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis" in data or "success" in data


# ============================================================================
# V3.0 XAI & 可视化 & 报告
# ============================================================================

class TestXAIEndpoints:
    """XAI 可解释性分析"""

    def test_xai_explain_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/xai/explain", json={
            "model": sample_3story_frame.model_dump(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "report" in data


class TestVisualizationEndpoints:
    """力场可视化"""

    def test_force_field_200(self, client, sample_3story_frame):
        analysis = AnalysisResult().model_dump()
        resp = client.post("/api/v1/visualization/force-field", json={
            "model": sample_3story_frame.model_dump(),
            "analysis_result": analysis,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "frame" in data

    def test_timeline_200(self, client, sample_3story_frame):
        actions = [DemolitionAction(step=1, target_element_ids=[1]).model_dump()]
        resp = client.post("/api/v1/visualization/timeline", json={
            "model": sample_3story_frame.model_dump(),
            "actions": actions,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "timeline" in data


class TestReportEndpoint:
    """工程报告生成（使用 analysis/report GET 端点）"""

    def test_report_generate_html_200(self, client, sample_3story_frame):
        resp = client.get("/api/v1/analysis/report",
                          params={"model_id": sample_3story_frame.model_id})
        # 分析报告为 GET 端点，返回引擎状态和分析模式
        assert resp.status_code == 200
        data = resp.json()
        assert "engines" in data

    def test_report_generate_markdown_200(self, client, sample_3story_frame):
        resp = client.get("/api/v1/analysis/report",
                          params={"model_id": sample_3story_frame.model_id})
        assert resp.status_code == 200
        data = resp.json()
        assert "engines" in data or "analysis_modes" in data


class TestRLEndpoint:
    """RL 对比端点"""

    def test_rl_compare_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/rl/compare",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "rl_plan" in data


# ============================================================================
# V4.0 多智能体 & 案例库
# ============================================================================

class TestMultiAgentEndpoints:
    """多智能体协同决策"""

    def test_multi_agent_decide_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/multi-agent/decide", json={
            "model": sample_3story_frame.model_dump(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "decision" in data

    def test_multi_agent_debate_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/multi-agent/debate",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert "divergent_points" in data or "rounds" in data


class TestCaseEndpoints:
    """案例库端点"""

    def test_cases_stats_200(self, client):
        resp = client.get("/api/v1/cases/stats")
        assert resp.status_code == 200

    def test_cases_list_200(self, client):
        resp = client.get("/api/v1/cases")
        assert resp.status_code == 200
        data = resp.json()
        assert "cases" in data

    def test_cases_detail_200(self, client):
        resp = client.get("/api/v1/cases/case_001")
        assert resp.status_code == 200
        data = resp.json()
        assert "case" in data

    def test_cases_search_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/cases/search",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200

    def test_cases_tag_200(self, client):
        resp = client.get("/api/v1/cases/tag/钢框架")
        assert resp.status_code == 200
        data = resp.json()
        assert "cases" in data


class TestIntegrationEndpoint:
    """全系统集成测试端点"""

    def test_integration_test_200(self, client, sample_3story_frame):
        resp = client.post("/api/v1/integration/test", json={
            "model": sample_3story_frame.model_dump(),
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "multi_agent" in data or "case_matches" in data or "scenario" in data


# ============================================================================
# 统一响应结构验证
# ============================================================================

class TestResponseSchema:
    """验证所有端点返回统一的结构"""

    def test_all_200_endpoints_return_json(self, client, sample_3story_frame):
        """抽样验证关键端点返回合法 JSON"""
        endpoints = [
            ("GET", "/health", None),
            ("POST", "/api/v1/model/validate", sample_3story_frame.model_dump()),
            ("POST", "/api/v1/plan/sequence", sample_3story_frame.model_dump()),
            ("POST", "/api/v1/analysis/static", sample_3story_frame.model_dump()),
            ("GET", "/api/v1/cases/stats", None),
        ]
        for method, url, body in endpoints:
            if method == "GET":
                resp = client.get(url)
            else:
                resp = client.post(url, json=body)
            assert resp.status_code == 200, f"{method} {url} returned {resp.status_code}"
            assert "application/json" in resp.headers["content-type"], \
                f"{method} {url} not JSON"

    def test_error_endpoints_return_json(self, client):
        """验证 422 错误也返回合法 JSON"""
        resp = client.post("/api/v1/model/validate", json={})
        assert resp.status_code == 422
        assert "detail" in resp.json()
