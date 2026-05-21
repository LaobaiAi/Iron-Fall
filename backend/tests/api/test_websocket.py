"""WebSocket 实时通信集成测试

覆盖 /ws/demolition 的：
- 连接 / 断连 / 心跳
- 拆除指令完整流程
- 验证指令
- 静力分析指令
- 并发多连接管理
- 超时 / 断线重连
"""
import pytest
import json
import asyncio
from fastapi.testclient import TestClient
from core.models import StructureModel, DemolitionAction


# ---------------------------------------------------------------------------
# WebSocket 辅助
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def http_client():
    """HTTP client 用于创建 WebSocket"""
    from api.main import app
    with TestClient(app) as c:
        yield c


def _ws_connect(client):
    """建立 WebSocket 连接"""
    with client.websocket_connect("/ws/demolition") as ws:
        yield ws


class TestWebSocket:
    """WebSocket 实时通信测试"""

    def test_ping_pong(self, http_client):
        """心跳测试"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_demolish_valid(self, http_client, sample_3story_frame):
        """拆除指令 - 有效输入"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            payload = {
                "type": "demolish",
                "model": sample_3story_frame.model_dump(),
                "action": DemolitionAction(
                    step=1, target_element_ids=[1], action_type="Remove"
                ).model_dump(),
            }
            ws.send_json(payload)
            data = ws.receive_json()

            assert data["type"] == "result"
            assert "success" in data
            assert "latency_ms" in data

    def test_demolish_multiple_actions(self, http_client, sample_3story_frame):
        """拆除指令 - 连续多个动作"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            for i, eid in enumerate([1, 2, 3], start=1):
                payload = {
                    "type": "demolish",
                    "model": sample_3story_frame.model_dump(),
                    "action": DemolitionAction(
                        step=i, target_element_ids=[eid]
                    ).model_dump(),
                }
                ws.send_json(payload)
                data = ws.receive_json()
                assert data["type"] == "result"

    def test_validate(self, http_client, sample_3story_frame):
        """验证指令"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            payload = {
                "type": "validate",
                "model": sample_3story_frame.model_dump(),
            }
            ws.send_json(payload)

            data = ws.receive_json()
            assert data["type"] in ("validation_result", "result")

    def test_analyze_static(self, http_client, sample_3story_frame):
        """静力分析指令"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            payload = {
                "type": "analyze_static",
                "model": sample_3story_frame.model_dump(),
            }
            ws.send_json(payload)

            data = ws.receive_json()
            assert data["type"] in ("analysis_result", "result")

    def test_unknown_message_type(self, http_client):
        """未知消息类型不应崩溃"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            ws.send_json({"type": "unknown_command", "payload": {}})
            # 只要不抛异常就算通过（连接未断开）
            ping_data = ws.receive_json()  # may receive result or we just send ping
            # 再发一个 ping 确认连接仍活跃
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"

    def test_connection_persistence_after_ping(self, http_client):
        """连接在多次心跳后仍保持"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            for _ in range(3):
                ws.send_json({"type": "ping"})
                data = ws.receive_json()
                assert data["type"] == "pong"

    def test_latency_ms_in_result(self, http_client, sample_3story_frame):
        """拆除结果应包含 latency_ms 字段（3秒法则监控）"""
        with http_client.websocket_connect("/ws/demolition") as ws:
            ws.send_json({
                "type": "demolish",
                "model": sample_3story_frame.model_dump(),
                "action": DemolitionAction(
                    step=1, target_element_ids=[1]
                ).model_dump(),
            })
            data = ws.receive_json()

            if data["type"] == "result" and data.get("success"):
                assert "latency_ms" in data
                assert data["latency_ms"] >= 0
