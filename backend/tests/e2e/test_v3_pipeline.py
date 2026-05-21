"""V3.0 端到端回归测试

烟囱 NL 解析 → 稳定性验算 → 深部分析(轨迹) → XAI 报告 → 力场可视化 → 工程报告
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


class TestV3Pipeline:
    """V3.0 全流程回归测试"""

    def test_chimney_full_pipeline(self, client):
        """烟囱完整分析流程"""
        text = "100米高钢筋混凝土烟囱，底部外径8米，顶部外径3米，壁厚0.3米，C40混凝土"

        # 1. 烟囱解析
        from urllib.parse import quote
        resp = client.post(f"/api/v1/chimney/parse?text={quote(text)}")
        assert resp.status_code == 200
        chimney_data = resp.json()
        assert chimney_data["success"] is True
        chimney_model = chimney_data["chimney_model"]
        assert chimney_model["total_height"] == 100

        # 2. 稳定性验算
        resp = client.post("/api/v1/chimney/stability", json=chimney_model)
        assert resp.status_code == 200
        stability = resp.json()
        assert stability["success"] is True
        report = stability["report"]
        assert "is_stable" in report

        # 3. 深部分析（倾倒轨迹）
        resp = client.post("/api/v1/chimney/deep", json=chimney_model)
        assert resp.status_code == 200
        deep = resp.json()
        assert "analysis" in deep or "success" in deep

    def test_xai_pipeline(self, client, sample_3story_frame):
        """XAI 分析完整流程"""
        model = sample_3story_frame.model_dump()

        resp = client.post("/api/v1/xai/explain", json={"model": model})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        report = data["report"]
        assert report["total_elements"] > 0
        assert "removable_elements" in report or "element_details" in report

    def test_visualization_pipeline(self, client, sample_3story_frame):
        """力场可视化完整流程"""
        model = sample_3story_frame.model_dump()

        from core.models import AnalysisResult, DemolitionAction
        analysis = AnalysisResult().model_dump()

        # 力场快照
        resp = client.post("/api/v1/visualization/force-field", json={
            "model": model,
            "analysis_result": analysis,
        })
        assert resp.status_code == 200
        ff = resp.json()
        assert ff["success"] is True
        assert "frame" in ff
        assert len(ff["frame"]["elements"]) > 0

        # 力场时间线
        actions = [
            DemolitionAction(step=1, target_element_ids=[1]).model_dump(),
            DemolitionAction(step=2, target_element_ids=[2]).model_dump(),
        ]
        resp = client.post("/api/v1/visualization/timeline", json={
            "model": model,
            "actions": actions,
        })
        assert resp.status_code == 200
        tl = resp.json()
        assert tl["success"] is True
        assert "timeline" in tl
        assert len(tl["timeline"]["frames"]) > 0

    def test_report_generation_pipeline(self, client, sample_3story_frame):
        """工程报告生成流程"""
        model = sample_3story_frame.model_dump()

        resp = client.get("/api/v1/analysis/report",
                          params={"model_id": model.get("model_id", "test")})
        assert resp.status_code == 200
        data = resp.json()
        assert "engines" in data or "analysis_modes" in data

    def test_rl_pipeline(self, client, sample_3story_frame):
        """RL 对比流程"""
        model = sample_3story_frame.model_dump()

        resp = client.post("/api/v1/rl/compare", json=model)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "rl_plan" in data
        assert "baseline_plan" in data
