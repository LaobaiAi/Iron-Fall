"""性能基准测试

验证关键延迟指标，确保满足 3 秒法则。
"""
import time
import pytest
from fastapi.testclient import TestClient
from core.models import AnalysisResult, DemolitionAction


@pytest.fixture(scope="module")
def client():
    from api.main import app
    with TestClient(app) as c:
        yield c


# ============================================================================
# 3 秒法则验证
# ============================================================================

class Test3SecondRule:
    """核心 KPI: API 端到端延迟 ≤ 3000ms"""

    THREE_SECONDS_MS = 3000

    def test_health_latency(self, client):
        start = time.time()
        resp = client.get("/health")
        elapsed = (time.time() - start) * 1000
        assert resp.status_code == 200
        assert elapsed < self.THREE_SECONDS_MS, f"health: {elapsed:.0f}ms > 3000ms"

    def test_parse_latency(self, client):
        from urllib.parse import quote
        start = time.time()
        text = "3层钢框架，跨度6m，层高3.6m"
        resp = client.post(f"/api/v1/model/parse?text={quote(text)}")
        elapsed = (time.time() - start) * 1000
        assert resp.status_code == 200
        data = resp.json()
        # 自有 latency_ms 也应在范围内
        assert data.get("latency_ms", 0) < self.THREE_SECONDS_MS
        assert elapsed < self.THREE_SECONDS_MS

    def test_sequence_latency(self, client, sample_3story_frame):
        resp = client.post("/api/v1/plan/sequence",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("latency_ms", 0) < self.THREE_SECONDS_MS

    def test_static_analysis_latency(self, client, sample_3story_frame):
        resp = client.post("/api/v1/analysis/static",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("latency_ms", 0) < self.THREE_SECONDS_MS

    def test_stability_check_latency(self, client, sample_3story_frame):
        resp = client.post("/api/v1/stability/check",
                           json=sample_3story_frame.model_dump())
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("latency_ms", 0) < self.THREE_SECONDS_MS

    def test_dynamic_analysis_latency(self, client, sample_3story_frame):
        action = DemolitionAction(step=1, target_element_ids=[1]).model_dump()
        resp = client.post("/api/v1/analysis/dynamic", json={
            "model": sample_3story_frame.model_dump(),
            "action": action,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("latency_ms", 0) < self.THREE_SECONDS_MS


# ============================================================================
# 引擎性能基准
# ============================================================================

class TestEnginePerformance:
    """引擎层性能基准"""

    @pytest.mark.parametrize("model_name, max_allowed_ms", [
        ("sample_1story_frame", 500),
        ("sample_3story_frame", 1500),
        ("sample_5story_frame", 3000),
    ])
    def test_sequencer_scales(self, request, client, model_name, max_allowed_ms):
        """序列生成应随规模线性增长"""
        model = request.getfixturevalue(model_name)
        resp = client.post("/api/v1/plan/sequence",
                           json=model.model_dump())
        assert resp.status_code == 200
        latency = resp.json().get("latency_ms", 0)
        assert latency < max_allowed_ms, (
            f"{model_name}: {latency:.0f}ms > {max_allowed_ms}ms"
        )


class TestConcurrency:
    """并发性能"""

    @pytest.mark.parametrize("n_requests", [5])
    def test_health_concurrent(self, client, n_requests):
        """health 并发请求应全部成功"""
        import concurrent.futures

        def call_health():
            return client.get("/health")

        with concurrent.futures.ThreadPoolExecutor(max_workers=n_requests) as pool:
            futures = [pool.submit(call_health) for _ in range(n_requests)]
            results = [f.result() for f in futures]

        for r in results:
            assert r.status_code == 200
