"""V1.0 端到端回归测试

完整流程：自然语言输入 → 解析 → 序列生成 → 静力分析 → 拆除模拟 → 稳定性检查
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


class TestV1Pipeline:
    """V1.0 全流程回归测试"""

    def test_full_pipeline(self, client):
        """完整拆除决策流程"""
        # 1. 健康检查
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

        # 2. 自然语言解析
        from urllib.parse import quote
        text = "3层钢框架，Q355钢材，H400x200截面，跨度6米，层高3.6米"
        resp = client.post(f"/api/v1/model/parse?text={quote(text)}")
        assert resp.status_code == 200
        model_data = resp.json()
        assert model_data["success"] is True
        model = model_data["model"]

        # 3. 模型验证
        resp = client.post("/api/v1/model/validate", json=model)
        assert resp.status_code == 200

        # 4. 序列生成
        resp = client.post("/api/v1/plan/sequence", json=model)
        assert resp.status_code == 200
        plan_data = resp.json()
        assert plan_data["success"] is True
        plan = plan_data["plan"]
        assert len(plan["actions"]) > 0

        # 5. 静力分析
        resp = client.post("/api/v1/analysis/static", json=model)
        assert resp.status_code == 200
        analysis_data = resp.json()
        assert analysis_data["success"] is True
        analysis = analysis_data["analysis"]

        # 6. 稳定性检查
        resp = client.post("/api/v1/stability/check", json=model)
        assert resp.status_code == 200
        stability = resp.json()
        assert "is_stable" in stability

        # 7. 拆除模拟（第一步）
        first_action = plan["actions"][0]
        resp = client.post("/api/v1/analysis/dynamic", json={
            "model": model,
            "action": first_action,
        })
        assert resp.status_code == 200

        # 8. AI 智能体方案
        resp = client.post("/api/v1/agent/plan", json=model)
        assert resp.status_code == 200

    def test_pipeline_minimal_model(self, client, sample_1story_frame):
        """最小模型全流程"""
        model = sample_1story_frame.model_dump()

        steps = [
            ("POST", "/api/v1/model/validate", model),
            ("POST", "/api/v1/plan/sequence", model),
            ("POST", "/api/v1/analysis/static", model),
            ("POST", "/api/v1/stability/check", model),
        ]
        for method, url, body in steps:
            resp = client.post(url, json=body)
            assert resp.status_code == 200, f"{url} failed: {resp.status_code}"

    def test_pipeline_agent_validate(self, client, sample_3story_frame):
        """AI 方案验证流程"""
        model = sample_3story_frame.model_dump()

        # 生成方案
        resp = client.post("/api/v1/agent/plan", json=model)
        if resp.status_code == 200 and "plan" in resp.json():
            plan = resp.json()["plan"]
            # 验证方案
            resp2 = client.post("/api/v1/agent/validate", json={
                "model": model,
                "plan": plan,
            })
            assert resp2.status_code == 200
