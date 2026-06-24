from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas.agent import AgentTaskRequest, NodeFeedback
from app.services.mcp_gateway import MCPGateway, MCPGatewayResult
from app.services.orchestrator import AgentOrchestrator


def _settings(**overrides):
    values = {
        "mcp_enabled": False,
        "mcp_server_url": "",
        "mcp_tool_name": "",
        "mcp_auth_token": "",
        "mcp_timeout_seconds": 5,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeMCPClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests: list[dict] = []

    async def post(self, url: str, **kwargs) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return FakeResponse(self.payload)


class FakeGateway:
    async def enrich_request(
        self,
        request_text: str,
        context: dict[str, str],
    ) -> MCPGatewayResult:
        return MCPGatewayResult(
            context={"mcp_machine_status": "warning"},
            evidence=["[mcp:equipment.status] spindle vibration warning"],
            node_feedback=[
                NodeFeedback(
                    node_id="mcp-tool-call",
                    node_name="MCP Tool Call",
                    status="completed",
                    detail="MCP test tool completed.",
                )
            ],
        )


@pytest.mark.asyncio
async def test_mcp_gateway_disabled_is_noop() -> None:
    gateway = MCPGateway(settings=_settings(mcp_enabled=False))

    result = await gateway.enrich_request("check equipment", {})

    assert result.evidence == []
    assert result.context == {}
    assert result.node_feedback == []


@pytest.mark.asyncio
async def test_mcp_gateway_enabled_without_url_returns_skipped_node() -> None:
    gateway = MCPGateway(settings=_settings(mcp_enabled=True))

    result = await gateway.enrich_request("check equipment", {})

    assert result.evidence == []
    assert result.node_feedback[0].node_id == "mcp-connect"
    assert result.node_feedback[0].status == "skipped"


@pytest.mark.asyncio
async def test_mcp_gateway_calls_configured_tool_and_extracts_evidence() -> None:
    client = FakeMCPClient(
        {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "content": [
                    {"type": "text", "text": "machine EQ-1 vibration is high"}
                ],
                "structuredContent": {"risk_level": "high"},
            },
        }
    )
    gateway = MCPGateway(
        settings=_settings(
            mcp_enabled=True,
            mcp_server_url="http://mcp.local/rpc",
            mcp_tool_name="equipment.status",
        ),
        client=client,
    )

    result = await gateway.enrich_request("check equipment", {"line": "A"})

    assert result.evidence == [
        "[mcp:equipment.status] machine EQ-1 vibration is high"
    ]
    assert result.context["mcp_risk_level"] == "high"
    assert result.node_feedback[0].status == "completed"
    assert client.requests[0]["json"]["method"] == "tools/call"


@pytest.mark.asyncio
async def test_orchestrator_appends_mcp_feedback_without_breaking_agent_flow() -> None:
    orch = AgentOrchestrator(mcp_gateway=FakeGateway())
    request = AgentTaskRequest(
        request_text="设备振动异常需要预测性维护",
        require_llm=False,
    )

    response = await orch.execute(request, db=None)

    assert response.agent_name == "predictive_maintenance"
    assert "[mcp:equipment.status] spindle vibration warning" in response.evidence
    assert any(node.node_id == "mcp-tool-call" for node in response.node_feedback)
