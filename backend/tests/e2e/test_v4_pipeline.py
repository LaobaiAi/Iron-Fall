"""V4.0 端到端回归测试

结构解析 → 多智能体决策 → 辩论记录 → 方案融合 → 案例库检索 → 全系统集成
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


class TestV4Pipeline:
    """V4.0 多智能体与案例库全流程"""

    def test_multi_agent_full_pipeline(self, client, sample_3story_frame):
        """多智能体决策完整流程"""
        model = sample_3story_frame.model_dump()

        # 1. 多智能体决策
        resp = client.post("/api/v1/multi-agent/decide", json={"model": model})
        assert resp.status_code == 200
        decision_data = resp.json()
        assert decision_data["success"] is True
        decision = decision_data["decision"]

        # 验证 MultiAgentDecision 结构
        assert "decision_id" in decision
        assert "final_plan" in decision
        assert "agent_opinions" in decision
        assert "consensus_score" in decision

        # 共识度应在 [0, 1]
        cs = decision["consensus_score"]
        assert 0.0 <= cs <= 1.0

    def test_debate_pipeline(self, client, sample_3story_frame):
        """辩论记录流程"""
        model = sample_3story_frame.model_dump()

        resp = client.post("/api/v1/multi-agent/debate", json=model)
        assert resp.status_code == 200
        debate_data = resp.json()
        assert "divergent_points" in debate_data or "rounds" in debate_data

    def test_case_library_pipeline(self, client, sample_3story_frame):
        """案例库检索完整流程"""
        model = sample_3story_frame.model_dump()

        # 1. 案例库统计
        resp = client.get("/api/v1/cases/stats")
        assert resp.status_code == 200
        stats = resp.json()
        # API 可能返回 {"success": true, "stats": {...}} 或直接返回 stats
        actual_stats = stats.get("stats", stats)
        assert "total_cases" in actual_stats
        assert actual_stats["total_cases"] > 0

        # 2. 全部案例
        resp = client.get("/api/v1/cases")
        assert resp.status_code == 200
        cases = resp.json()
        assert len(cases["cases"]) > 0

        # 3. 案例详情
        first_case_id = cases["cases"][0]["case_id"]
        resp = client.get(f"/api/v1/cases/{first_case_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["case"]["case_id"] == first_case_id

        # 4. 基于模型检索案例
        resp = client.post("/api/v1/cases/search", json=model)
        assert resp.status_code == 200
        results = resp.json()
        assert "matches" in results or "results" in results

        # 5. 按标签检索
        tags_to_try = cases["cases"][0].get("tags", [])
        if tags_to_try:
            resp = client.get(f"/api/v1/cases/tag/{tags_to_try[0]}")
            assert resp.status_code == 200

    def test_integration_test(self, client, sample_3story_frame):
        """全系统集成测试端点"""
        model = sample_3story_frame.model_dump()

        resp = client.post("/api/v1/integration/test", json={"model": model})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "multi_agent" in data or "case_matches" in data or "scenario" in data

    def test_end_to_end_cross_version(self, client, sample_3story_frame):
        """跨版本 V1→V4 完整联调"""
        model = sample_3story_frame.model_dump()

        # V1: 序列生成
        seq = client.post("/api/v1/plan/sequence", json=model)
        assert seq.status_code == 200

        # V3: XAI 分析
        xai = client.post("/api/v1/xai/explain", json={"model": model})
        assert xai.status_code == 200

        # V4: 多智能体决策
        ma = client.post("/api/v1/multi-agent/decide", json={"model": model})
        assert ma.status_code == 200

        # V4: 案例库检索
        cases = client.post("/api/v1/cases/search", json=model)
        assert cases.status_code == 200
