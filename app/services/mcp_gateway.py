from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import get_settings
from app.schemas.agent import NodeFeedback


@dataclass(slots=True)
class MCPGatewayResult:
    context: dict[str, str] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    node_feedback: list[NodeFeedback] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _node(
    node_id: str,
    node_name: str,
    status: str,
    detail: str,
    started_at: datetime,
) -> NodeFeedback:
    return NodeFeedback(
        node_id=node_id,
        node_name=node_name,
        status=status,
        detail=detail,
        started_at=started_at,
        completed_at=_now(),
    )


class MCPGateway:
    """Optional MCP tool gateway.

    The gateway is deliberately fail-soft: a failed external tool call returns
    node feedback and never blocks the core agent orchestration path.
    """

    def __init__(self, settings: Any | None = None, client: Any | None = None) -> None:
        self.settings = settings if settings is not None else get_settings()
        self._client = client

    async def enrich_request(
        self,
        request_text: str,
        context: dict[str, str],
    ) -> MCPGatewayResult:
        if not getattr(self.settings, "mcp_enabled", False):
            return MCPGatewayResult()

        started_at = _now()
        server_url = str(getattr(self.settings, "mcp_server_url", "") or "").strip()
        if not server_url:
            return MCPGatewayResult(
                node_feedback=[
                    _node(
                        "mcp-connect",
                        "MCP Connect",
                        "skipped",
                        "MCP is enabled but MCP_SERVER_URL is empty.",
                        started_at,
                    )
                ]
            )

        tool_name = str(getattr(self.settings, "mcp_tool_name", "") or "").strip()
        try:
            if tool_name:
                return await self._call_tool(
                    server_url,
                    tool_name,
                    request_text,
                    context,
                    started_at,
                )
            return await self._list_tools(server_url, started_at)
        except httpx.TimeoutException:
            detail = "MCP request timed out."
        except httpx.HTTPError as exc:
            detail = f"MCP transport failed: {exc.__class__.__name__}."
        except Exception as exc:
            detail = f"MCP gateway failed: {exc.__class__.__name__}."

        return MCPGatewayResult(
            node_feedback=[
                _node("mcp-call", "MCP Tool Call", "failed", detail, started_at)
            ]
        )

    async def _list_tools(
        self,
        server_url: str,
        started_at: datetime,
    ) -> MCPGatewayResult:
        payload = {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": "tools/list",
            "params": {},
        }
        data = await self._post_json(server_url, payload)
        if error := data.get("error"):
            return MCPGatewayResult(
                node_feedback=[
                    _node(
                        "mcp-tool-discovery",
                        "MCP Tool Discovery",
                        "failed",
                        self._safe_error_detail(error),
                        started_at,
                    )
                ]
            )

        tool_names = self._extract_tool_names(data.get("result", {}))
        detail = (
            f"Discovered {len(tool_names)} MCP tools."
            if tool_names
            else "MCP server responded without tools."
        )
        evidence = [f"[mcp:tools] {', '.join(tool_names[:8])}"] if tool_names else []
        return MCPGatewayResult(
            evidence=evidence,
            node_feedback=[
                _node(
                    "mcp-tool-discovery",
                    "MCP Tool Discovery",
                    "completed",
                    detail,
                    started_at,
                )
            ],
        )

    async def _call_tool(
        self,
        server_url: str,
        tool_name: str,
        request_text: str,
        context: dict[str, str],
        started_at: datetime,
    ) -> MCPGatewayResult:
        payload = {
            "jsonrpc": "2.0",
            "id": uuid4().hex,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": {
                    "query": request_text,
                    "context": context,
                },
            },
        }
        data = await self._post_json(server_url, payload)
        if error := data.get("error"):
            return MCPGatewayResult(
                node_feedback=[
                    _node(
                        "mcp-tool-call",
                        "MCP Tool Call",
                        "failed",
                        self._safe_error_detail(error),
                        started_at,
                    )
                ]
            )

        evidence, tool_context = self._extract_tool_result(
            tool_name,
            data.get("result", {}),
        )
        return MCPGatewayResult(
            context=tool_context,
            evidence=evidence,
            node_feedback=[
                _node(
                    "mcp-tool-call",
                    "MCP Tool Call",
                    "completed",
                    f"MCP tool '{tool_name}' completed with {len(evidence)} evidence items.",
                    started_at,
                )
            ],
        )

    async def _post_json(
        self,
        server_url: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        token = str(getattr(self.settings, "mcp_auth_token", "") or "")
        if token:
            headers["Authorization"] = "Bearer " + token
        timeout = int(getattr(self.settings, "mcp_timeout_seconds", 5) or 5)

        if self._client is not None:
            response = await self._client.post(
                server_url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()

        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(server_url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _safe_error_detail(error: Any) -> str:
        if isinstance(error, dict):
            code = error.get("code", "unknown")
            message = str(error.get("message", "MCP error"))[:160]
            return f"MCP error {code}: {message}"
        return "MCP server returned an error."

    @staticmethod
    def _extract_tool_names(result: Any) -> list[str]:
        if not isinstance(result, dict):
            return []
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            return []
        names: list[str] = []
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                names.append(str(tool["name"]))
        return names

    @staticmethod
    def _extract_tool_result(
        tool_name: str,
        result: Any,
    ) -> tuple[list[str], dict[str, str]]:
        if not isinstance(result, dict):
            return ([f"[mcp:{tool_name}] tool call completed."], {})

        evidence: list[str] = []
        content = result.get("content", [])
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = str(item.get("text", "")).strip()
                    if text:
                        evidence.append(f"[mcp:{tool_name}] {text[:300]}")

        tool_context: dict[str, str] = {}
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            for key, value in structured.items():
                if isinstance(value, (str, int, float, bool)):
                    tool_context[f"mcp_{key}"] = str(value)[:500]
            if not evidence and structured:
                preview = json.dumps(structured, ensure_ascii=False)[:300]
                evidence.append(f"[mcp:{tool_name}] {preview}")

        if not evidence:
            evidence.append(
                f"[mcp:{tool_name}] tool call completed without text content."
            )
        return evidence, tool_context
